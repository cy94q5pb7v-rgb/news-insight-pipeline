"""Универсальный модуль для извлечения текста статей с anti-bot bypass.

Используется:
  - r1_prefetch.py (cron prefetch)
  - routes/news_page.py /api/news/{hash}/generate-summary
  - routes/news_page.py /api/news/{hash}/article
  - core/kb_ingest.py (URL upload в Insight Hub)
  - любой другой код webapp'а где нужен текст статьи

API:
  fetch_article_text(url, title_hint="", trust_score=0.5, allow_tavily=True) -> (text, mode_label)

Cascade:
  Tier 1: trafilatura.fetch_url + extract              (free)
  Tier 2: ru-fetch + trafilatura.extract               (free, RU-proxy)
  Tier 4: snippets aggregator (DDG + Google News RSS)  (free, ~2KB multi-source)
  Tier 5: Tavily Extract                                (paid, basic→advanced, ≥0.5 trust gate)

  Между Tier 4 и 5: если snippets вернул ≥800 chars — НЕ эскалируем на Tavily.

Каждый tier проверяет _is_block_page() — Cloudflare/WAF strings не утекают в text.
"""
import json, os, re, subprocess, time, urllib.request, urllib.error, urllib.parse
import pathlib
from typing import Tuple

# ─── Tunables ─────────────────────────────────────────────────────────
MIN_TEXT_LEN = 200
TAVILY_PER_RUN_CAP = 50
TAVILY_QUOTA_THRESHOLD = 950  # mark key exhausted at this usage
TAVILY_CACHE_TTL = 60.0  # quota probe cache (sec)
BROWSER_BUDGET_S = 25
RU_FETCH_BIN = "/opt/newsapp/.openclaw/workspace/scripts/ru-fetch"

# ─── Block page detection ────────────────────────────────────────────
BLOCK_MARKERS = (
    "just a moment", "checking your browser", "security verification",
    "performing security", "attention required", "cloudflare ray id",
    "this website is using a security service",
    "enable javascript and cookies to continue",
    "ddos protection by cloudflare",
    "выполнение проверки безопасности",
    "этот веб-сайт использует сервис безопасности",
    "защиты от вредоносных ботов",
    "несовместимое расширение браузера",
    "проверяет, что вы не бот",
    "захоплено", "ддос-атак",
)


def _is_block_page(text: str) -> bool:
    if not text:
        return False
    snippet = text.lower()[:800]
    return any(m in snippet for m in BLOCK_MARKERS)


# ─── Tavily key management ──────────────────────────────────────────
_TAVILY_KEYS_CACHE = None
_TAVILY_EXHAUSTED = set()
_TAVILY_QUOTA_OK = None
_TAVILY_QUOTA_LAST_CHECK = 0.0
_TAVILY_CALLS = 0


def _tavily_api_keys():
    global _TAVILY_KEYS_CACHE
    if _TAVILY_KEYS_CACHE is not None:
        return _TAVILY_KEYS_CACHE
    out, seen = [], set()

    def _add(label, key):
        key = (key or "").strip().strip('"').strip("'")
        if key.startswith("tvly-") and key not in seen:
            seen.add(key)
            out.append((label, key))

    # 1) .tavily_keys file (multi-line)
    try:
        with open("/opt/newsapp/web/.tavily_keys", "r", encoding="utf-8") as f:
            key_idx = 0
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                key_idx += 1
                _add(f"file:keys#{key_idx}", line)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  tavily keys file read err: {e}")

    # 2) Env vars
    for i in range(1, 6):
        suffix = "" if i == 1 else f"_{i}"
        _add(f"env:KEY{suffix or '_1'}", os.environ.get(f"TAVILY_API_KEY{suffix}", ""))

    # 3) Legacy single file
    try:
        with open("/opt/newsapp/web/.tavily_key", "r", encoding="utf-8") as f:
            _add("file:tavily_key", f.read().strip())
    except FileNotFoundError:
        pass

    # 4) trendwatch_env.sh
    try:
        with open("/opt/newsapp/.openclaw/workspace/scripts/trendwatch_env.sh") as f:
            content = f.read()
        for m in re.finditer(r'TAVILY_API_KEY(?:_\d+)?[=\s]+["\']?(tvly-[A-Za-z0-9_-]+)', content):
            _add("env.sh", m.group(1))
    except Exception:
        pass

    _TAVILY_KEYS_CACHE = out
    return out


def _check_one_tavily_key(key):
    try:
        req = urllib.request.Request(
            "https://api.tavily.com/usage",
            headers={"Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        account = d.get("account") or {}
        used = account.get("plan_usage", 0) or 0
        limit = account.get("plan_limit", 1000) or 1000
        return used, limit, used < TAVILY_QUOTA_THRESHOLD
    except Exception:
        return -1, -1, False


def _check_tavily_quota(verbose=False, force=False):
    global _TAVILY_QUOTA_OK, _TAVILY_QUOTA_LAST_CHECK
    now = time.time()
    if not force and _TAVILY_QUOTA_OK is not None and (now - _TAVILY_QUOTA_LAST_CHECK) < TAVILY_CACHE_TTL:
        return _TAVILY_QUOTA_OK
    keys = _tavily_api_keys()
    if not keys:
        if verbose:
            print("  tavily: no API keys")
        _TAVILY_QUOTA_OK = False
        _TAVILY_QUOTA_LAST_CHECK = now
        return False
    if verbose:
        print(f"  tavily: {len(keys)} key(s) configured (probe TTL {int(TAVILY_CACHE_TTL)}s)")
    any_ok = False
    for label, k in keys:
        if label in _TAVILY_EXHAUSTED:
            continue
        used, limit, ok = _check_one_tavily_key(k)
        if used < 0:
            if verbose:
                print(f"  tavily [{label}]: probe failed (network/rate-limit/invalid)")
            continue
        if verbose:
            mark = "✓" if ok else "✗ (exhausted)"
            print(f"  tavily [{label}]: {used}/{limit} used, {limit-used} remaining {mark}")
        if ok:
            any_ok = True
        else:
            _TAVILY_EXHAUSTED.add(label)
    _TAVILY_QUOTA_OK = any_ok
    _TAVILY_QUOTA_LAST_CHECK = now
    return any_ok


def _pick_active_tavily_key():
    for label, k in _tavily_api_keys():
        if label not in _TAVILY_EXHAUSTED:
            return label, k
    return None, None


# ─── Snippet aggregator (Tier 4) ─────────────────────────────────────
def _fetch_via_snippets(url, title_hint=""):
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    if title_hint and len(title_hint) > 12:
        q = title_hint
    else:
        try:
            p = urllib.parse.urlparse(url)
            slug = p.path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            q = f"{slug} site:{p.netloc}"
        except Exception:
            q = url

    snippets = []
    seen = set()
    import html as _html

    def _add(src_label, text):
        text = (text or "").strip()
        if len(text) < 30:
            return
        key = text[:60].lower()
        if key in seen:
            return
        seen.add(key)
        snippets.append((src_label, text[:600]))

    try:
        ddg_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
        req = urllib.request.Request(ddg_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            h = r.read().decode("utf-8", errors="replace")
        for m in re.finditer(r'<a[^>]*class="result__snippet[^"]*"[^>]*>(.*?)</a>', h, flags=re.DOTALL):
            txt = re.sub(r"<[^>]+>", " ", m.group(1))
            txt = re.sub(r"\s+", " ", txt).strip()
            txt = _html.unescape(txt)
            _add("DDG", txt)
    except Exception:
        pass

    if len(snippets) < 4:
        try:
            gn_url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=en-US&gl=US"
            req = urllib.request.Request(gn_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                rss = r.read().decode("utf-8", errors="replace")
            for item in re.findall(r"<item>(.*?)</item>", rss, flags=re.DOTALL)[:4]:
                d_m = re.search(r"<description>(.*?)</description>", item, flags=re.DOTALL)
                if not d_m:
                    continue
                d_text = re.sub(r"<[^>]+>", " ", d_m.group(1))
                d_text = re.sub(r"\s+", " ", d_text).strip()
                d_text = _html.unescape(d_text)
                if title_hint and d_text[:80].lower() == title_hint[:80].lower():
                    continue
                _add("GN", d_text)
        except Exception:
            pass

    if not snippets:
        return "", "snippets-empty"
    snippets.sort(key=lambda s: -len(s[1]))
    composite = "\n\n".join(f"[{src}] {txt}" for src, txt in snippets[:8])
    if len(composite) < 400:
        return composite, "snippets-thin"
    return composite[:4000], "snippets"


# ─── Tavily extract (Tier 5) ────────────────────────────────────────
def _fetch_via_tavily(url, trust_score=0.5):
    global _TAVILY_CALLS
    if _TAVILY_CALLS >= TAVILY_PER_RUN_CAP:
        return "", "tavily-cap"
    if not _check_tavily_quota():
        return "", "tavily-quota"
    if trust_score < 0.5:
        return "", "tavily-skip-lowtrust"

    def _call(key, depth):
        body = json.dumps({"urls": [url], "extract_depth": depth, "include_images": False}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/extract",
            data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read())
            results = d.get("results") or []
            if results and results[0].get("raw_content"):
                return results[0]["raw_content"], ""
            return "", ""
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                err_body = ""
            body_lower = err_body.lower()
            rate_keywords = ("excessive requests", "too many requests", "rate limit", "please reduce")
            quota_keywords = ("insufficient credit", "insufficient_credit", "quota exceeded", "plan limit", "usage limit", "out of credit")
            if any(w in body_lower for w in rate_keywords):
                kind = "rate-limit"
            elif e.code == 402 or any(w in body_lower for w in quota_keywords):
                kind = "quota"
            elif e.code == 429:
                kind = "rate-limit"
            else:
                kind = "http"
            return "", kind
        except Exception:
            return "", "net"

    rate_retries = 0
    MAX_RATE_RETRIES = 3
    RATE_BACKOFF = (2.0, 5.0, 10.0)
    while True:
        label, key = _pick_active_tavily_key()
        if not key:
            return "", "tavily-all-exhausted"
        _TAVILY_CALLS += 1
        text, err = _call(key, "basic")
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return text[:8000], f"tavily-basic[{label}]"
        if err == "rate-limit":
            if rate_retries < MAX_RATE_RETRIES:
                time.sleep(RATE_BACKOFF[rate_retries])
                rate_retries += 1
                continue
            return "", "tavily-rate-limit-max"
        if err == "quota":
            _TAVILY_EXHAUSTED.add(label)
            rate_retries = 0
            continue
        _TAVILY_CALLS += 1
        text, err = _call(key, "advanced")
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return text[:8000], f"tavily-advanced[{label}]"
        if err == "rate-limit":
            if rate_retries < MAX_RATE_RETRIES:
                time.sleep(RATE_BACKOFF[rate_retries])
                rate_retries += 1
                continue
            return "", "tavily-rate-limit-max"
        if err == "quota":
            _TAVILY_EXHAUSTED.add(label)
            rate_retries = 0
            continue
        return "", "tavily-fail"


# ─── Tier 1: direct trafilatura ─────────────────────────────────────
def _fetch_via_trafilatura(url):
    try:
        import trafilatura
        html = trafilatura.fetch_url(url, no_ssl=False)
        if not html:
            return "", "trafilatura-empty"
        text = trafilatura.extract(
            html, include_comments=False, include_tables=False,
            no_fallback=False, with_metadata=False, favor_recall=True,
        ) or ""
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return text[:8000], "trafilatura"
        return "", "trafilatura-thin"
    except Exception as e:
        return "", f"trafilatura-err:{type(e).__name__}"


# ─── Tier 2: ru-fetch (xray + browser) ──────────────────────────────
def _fetch_via_ru_fetch(url):
    if not os.path.exists(RU_FETCH_BIN):
        return "", "ru-fetch-missing"
    try:
        r = subprocess.run(
            ["timeout", str(BROWSER_BUDGET_S), RU_FETCH_BIN, url],
            capture_output=True, timeout=BROWSER_BUDGET_S + 5,
        )
        html = (r.stdout or b"").decode("utf-8", "replace")
        if not html or len(html) < 1000:
            return "", "ru-fetch-thin"
        try:
            import trafilatura
            text = trafilatura.extract(
                html, include_comments=False, include_tables=False,
                no_fallback=False, with_metadata=False, favor_recall=True,
            ) or ""
            if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
                return text[:8000], "ru-fetch+trafilatura"
        except Exception:
            pass
        return "", "ru-fetch-no-text"
    except subprocess.TimeoutExpired:
        return "", "ru-fetch-timeout"
    except Exception:
        return "", "ru-fetch-err"


# ─── MAIN ENTRY ─────────────────────────────────────────────────────
def fetch_article_text(url: str, title_hint: str = "", trust_score: float = 0.5,
                       allow_tavily: bool = True) -> Tuple[str, str]:
    """Universal cascade. Returns (text, mode_label).

    allow_tavily=False — skip Tier 5 (например для KB upload где платный credit избыточен).
    trust_score < 0.5 — Tavily skip даже если allow_tavily=True.
    """
    if not url:
        return "", "no-url"

    # Tier 1
    text, mode = _fetch_via_trafilatura(url)
    if text:
        return text, mode

    # Tier 2
    text, mode = _fetch_via_ru_fetch(url)
    if text:
        return text, mode

    # Tier 4
    snippet_text, snippet_mode = _fetch_via_snippets(url, title_hint=title_hint)

    # Если snippets дали ≥800 chars — используем (не платим за Tavily)
    if snippet_text and len(snippet_text) >= 800:
        return snippet_text, snippet_mode

    # Tier 5
    if allow_tavily:
        tavily_text, tavily_mode = _fetch_via_tavily(url, trust_score=trust_score)
        if tavily_text and len(tavily_text) >= MIN_TEXT_LEN:
            return tavily_text, tavily_mode

    # Fall back к snippets даже коротким (>= MIN_TEXT_LEN)
    if snippet_text and len(snippet_text) >= MIN_TEXT_LEN:
        return snippet_text, snippet_mode

    return "", "thin"
