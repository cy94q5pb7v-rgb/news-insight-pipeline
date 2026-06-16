#!/usr/bin/env python3
"""r1_prefetch.py — populate article_text in /tmp/r1_urls.json.

Runs at 06:30 UTC, between Stage-1 modes (06:00-06:25) and Stage-2 LLM (06:40).
Uses trafilatura -> ru-fetch+browser -> bs4 cascade. Saves Stage-2 LLM from
having to call exec tools (it was lazy and skipped fetching, leaving 81%
items with empty article_text -> empty summary_ru).

Wall budget: 9 minutes. Per-item budget: ~12s curl + 75s browser fallback.
RAM budget: 1 sequential Chromium (~200 MB peak), no concurrency.
"""
import sys, os, json, time, subprocess

sys.path.insert(0, "/opt/newsapp/.openclaw/workspace/scripts")
import r1_fetch_urls as r1

URLS_PATH = "/opt/newsapp/.openclaw/workspace/ops/r1_urls.json"
MIN_TEXT_LEN = 200
MAX_FETCH = 200
WALL_BUDGET_S = 28 * 60
BROWSER_BUDGET_S = 75
RU_FETCH_BIN = "/opt/newsapp/bypass/bin/ru-fetch"




BLOCK_MARKERS = (
    # English Cloudflare/WAF markers
    "just a moment",
    "checking your browser",
    "security verification",
    "performing security",
    "attention required",
    "cloudflare ray id",
    "this website is using a security service",
    "enable javascript and cookies to continue",
    "ddos protection by cloudflare",
    # Russian translation of Cloudflare WAF
    "выполнение проверки безопасности",
    "этот веб-сайт использует сервис безопасности",
    "защиты от вредоносных ботов",
    "несовместимое расширение браузера",
    "проверяет, что вы не бот",
    "захоплено",  # ddos-guard
    "ддос-атак",
)


def _is_block_page(text: str) -> bool:
    """Detect WAF/Cloudflare block page in extracted text. Returns True if blocked."""
    if not text:
        return False
    snippet = text.lower()[:800]
    return any(m in snippet for m in BLOCK_MARKERS)


def fetch_one(url, title_hint="", trust_score=0.0):
    """Multi-tier fetch. Returns (text, mode_label)."""
    if not url:
        return ("", "no-url")
    # Tier 1: trafilatura.fetch_url (fast, direct)
    try:
        text = r1._fetch_via_trafilatura(url, max_chars=4000)
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return (text, "trafilatura")
    except Exception:
        pass
    # Tier 2: ru-fetch (auto-routes through xray for RU domains, with browser fallback)
    try:
        result = subprocess.run(
            ["timeout", str(BROWSER_BUDGET_S), RU_FETCH_BIN, url],
            capture_output=True, timeout=BROWSER_BUDGET_S + 5,
        )
        html = result.stdout.decode("utf-8", "replace")
        if html and len(html) >= 1000:
            # Try trafilatura.extract on the fetched HTML
            try:
                import trafilatura
                text = trafilatura.extract(
                    html, include_comments=False, include_tables=False,
                    no_fallback=False, with_metadata=False, favor_recall=True,
                ) or ""
                if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
                    return (text[:4000], "ru-fetch+trafilatura")
            except Exception:
                pass
            # Tier 2b: bs4 fallback on same HTML
            try:
                text = r1._strip_html(html, max_chars=4000)
                if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
                    return (text, "ru-fetch+bs4")
            except Exception:
                pass
    except subprocess.TimeoutExpired:
        # ru-fetch timeout — fallback to snippets
        pass
    except Exception:
        pass
    # Tier 4: snippets aggregator (DDG + Google News RSS) — БЕСПЛАТНО
    snippet_text = ""
    try:
        snippet_text, mode = _fetch_via_snippets(url, title_hint=title_hint)
        if snippet_text and len(snippet_text) >= MIN_TEXT_LEN:
            # Solid snippet result — use it unless trust is high enough to spend on Tavily
            if len(snippet_text) >= 800 or (trust_score or 0) < 0.5:
                return (snippet_text, mode)
            # else: high-trust + thin-ish snippets → escalate to Tavily
    except Exception:
        pass

    # Tier 5: Tavily Extract — ПЛАТНО (1-2 credits/call), only for high-trust items
    try:
        text, mode = _fetch_via_tavily(url, trust_score=(trust_score or 0))
        if text and len(text) >= MIN_TEXT_LEN:
            return (text, mode)
    except Exception:
        pass

    # If snippets had something but skipped Tavily — use it
    if snippet_text and len(snippet_text) >= MIN_TEXT_LEN:
        return (snippet_text, "snippets")

    return ("", "thin")


def main():
    if not os.path.exists(URLS_PATH):
        print("r1_prefetch: no /tmp/r1_urls.json (Stage-1 did not run?)")
        return
    with open(URLS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        items, wrapper, list_mode = data, {"items": data}, True
    else:
        # Stage-1 (r1_fetch_urls.py) writes 'candidates' key; legacy 'items' fallback.
        items = data.get("candidates") or data.get("items") or []
        wrapper, list_mode = data, False
    print(f"r1_prefetch: loaded {len(items)} items")

    # Initial verbose probe of Tavily quotas (also primes _TAVILY_EXHAUSTED)
    try:
        _check_tavily_quota(verbose=True)
    except Exception as e:
        print(f"  tavily initial probe err: {e}")

    # Sort by trust DESC, prefetch top-N
    indexed = sorted(
        enumerate(items),
        key=lambda ix: -(ix[1].get("trust_score") or 0.1),
    )

    started = time.time()
    stats = {}
    processed = 0
    stats_lock = threading.Lock()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process_one(orig_idx, it):
        """Run cascade for one item. Returns (orig_idx, mode, text)."""
        existing = (it.get("article_text") or "").strip()
        if len(existing) >= MIN_TEXT_LEN:
            return (orig_idx, "skipped-existing", "")
        url = it.get("url") or ""
        title_hint = (it.get("title_en") or it.get("title") or it.get("title_ru") or "").strip()
        trust = it.get("trust_score") or 0.0
        text, mode = fetch_one(url, title_hint=title_hint, trust_score=trust)
        return (orig_idx, mode, text)

    # Submit items in chunks; cancel pending if wall-budget exceeded
    CONCURRENCY = 2
    CHUNK_SIZE = CONCURRENCY * 4  # submit batches of 8, drain, repeat
    chunks = [indexed[i:i+CHUNK_SIZE] for i in range(0, len(indexed), CHUNK_SIZE)]

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for chunk in chunks:
            if time.time() - started > WALL_BUDGET_S:
                print(f"r1_prefetch: wall-budget reached at chunk submission, stop at processed={processed}")
                break
            if processed >= MAX_FETCH:
                print(f"r1_prefetch: MAX_FETCH={MAX_FETCH} cap reached")
                break

            futures = {}
            for orig_idx, it in chunk:
                if processed + len(futures) >= MAX_FETCH:
                    break
                fut = executor.submit(_process_one, orig_idx, it)
                futures[fut] = (orig_idx, it)

            # Drain futures with timeout
            remaining_budget = WALL_BUDGET_S - (time.time() - started)
            try:
                for fut in as_completed(futures, timeout=max(60, remaining_budget)):
                    orig_idx, _ = futures[fut]
                    try:
                        idx_back, mode, text = fut.result(timeout=5)
                    except Exception as e:
                        with stats_lock:
                            stats["task-err"] = stats.get("task-err", 0) + 1
                        continue
                    with stats_lock:
                        stats[mode] = stats.get(mode, 0) + 1
                        processed += 1
                    if text:
                        items[orig_idx]["article_text"] = text
                    if processed % 10 == 0:
                        elapsed = time.time() - started
                        print(f"  {processed} processed, {elapsed:.0f}s elapsed, stats={stats}")
            except Exception as e:
                # Likely timeout on as_completed — chunk took too long
                print(f"  chunk drain timeout/err: {type(e).__name__}: {str(e)[:80]}")
                # Cancel pending in this chunk
                for fut in futures:
                    if not fut.done():
                        fut.cancel()
                if time.time() - started > WALL_BUDGET_S:
                    print(f"r1_prefetch: wall-budget reached during drain, stop at processed={processed}")
                    break

    # Save back atomically
    if list_mode:
        out = items
    else:
        out = wrapper
        # Write back to same key we read from
        if "candidates" in wrapper:
            out["candidates"] = items
        else:
            out["items"] = items
    with open(URLS_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(URLS_PATH + ".tmp", URLS_PATH)

    # P1 #11: persist article_text into webapp news_state.json articles cache.
    # Drawer-open будет мгновенным вместо 3-8s trafilatura-fetch.
    _persist_articles_to_news_state(items)

    elapsed = time.time() - started
    print(f"r1_prefetch DONE in {elapsed:.0f}s")
    for k, v in sorted(stats.items()):
        if v:
            print(f"  {k}: {v}")
    if _TAVILY_CALLS_THIS_RUN:
        print(f"  tavily total api-calls this run: {_TAVILY_CALLS_THIS_RUN} (cap {TAVILY_PER_RUN_CAP})")





def _fetch_via_snippets(url: str, title_hint: str = "", min_chars: int = 400):
    """Tier 4: aggregate search engine snippets when direct fetch fails.
    Возвращает (composite_text, mode_label). mode='snippets' если набралось >=min_chars.

    Использует:
      - DuckDuckGo HTML (основной — стабильно отдаёт ~5-10 snippets)
      - Google News RSS description (вторичный — короче, но добавляет ракурс)

    Не пытается пробить Cloudflare; вместо этого собирает то, что
    search engines уже проиндексировали (у них есть clearance к публичной части)."""
    import urllib.request as _u, urllib.parse as _p, re as _re
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # Build query: title-hint preferred (cleanest signal); fallback — domain + URL slug
    if title_hint and len(title_hint) > 12:
        q = title_hint
    else:
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            slug = p.path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            q = f"{slug} site:{p.netloc}"
        except Exception:
            q = url

    snippets = []
    seen = set()

    def _add(src_label, text):
        text = (text or "").strip()
        if len(text) < 30:
            return
        key = text[:60].lower()
        if key in seen:
            return
        seen.add(key)
        snippets.append((src_label, text[:600]))

    # 1) DuckDuckGo HTML
    try:
        ddg_url = "https://html.duckduckgo.com/html/?q=" + _p.quote(q)
        req = _u.Request(ddg_url, headers={"User-Agent": UA})
        with _u.urlopen(req, timeout=12) as r:
            h = r.read().decode("utf-8", errors="replace")
        for m in _re.finditer(r'<a[^>]*class="result__snippet[^"]*"[^>]*>(.*?)</a>', h, flags=_re.DOTALL):
            txt = _re.sub(r"<[^>]+>", " ", m.group(1))
            txt = _re.sub(r"\s+", " ", txt).strip()
            import html as _html; txt = _html.unescape(txt); txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                       .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
            _add("DDG", txt)
    except Exception:
        pass

    # 2) Google News RSS — description content cleaned of HTML
    if len(snippets) < 4:
        try:
            gn_url = "https://news.google.com/rss/search?q=" + _p.quote(q) + "&hl=en-US&gl=US"
            req = _u.Request(gn_url, headers={"User-Agent": UA})
            with _u.urlopen(req, timeout=12) as r:
                rss = r.read().decode("utf-8", errors="replace")
            for item in _re.findall(r"<item>(.*?)</item>", rss, flags=_re.DOTALL)[:4]:
                d_m = _re.search(r"<description>(.*?)</description>", item, flags=_re.DOTALL)
                if not d_m:
                    continue
                d_raw = d_m.group(1)
                # GN descriptions wrap link+title in HTML; skip pure-link-only ones
                d_text = _re.sub(r"<[^>]+>", " ", d_raw)
                d_text = _re.sub(r"\s+", " ", d_text).strip()
                d_text = (d_text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                            .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
                # GN often has just title repeated — filter out
                if title_hint and d_text[:80].lower() == title_hint[:80].lower():
                    continue
                _add("GN", d_text)
        except Exception:
            pass

    if not snippets:
        return ("", "snippets-empty")

    # Compose: lead with longest snippet, then add unique perspectives
    snippets.sort(key=lambda s: -len(s[1]))
    composite = "\n\n".join(f"[{src}] {txt}" for src, txt in snippets[:8])
    if len(composite) < min_chars:
        return (composite, "snippets-thin")
    return (composite[:4000], "snippets")





# ─── Tavily Extract (Tier 5) — paid fallback through residential IPs ──
TAVILY_PER_RUN_CAP = 50
TAVILY_QUOTA_THRESHOLD = 950  # if monthly usage >= this, skip Tier 5
_TAVILY_CALLS_THIS_RUN = 0
_TAVILY_QUOTA_OK = None  # None=unknown, True=ok, False=exhausted


import threading
_TAVILY_LOCK = threading.Lock()
_TAVILY_KEYS_CACHE = None
_TAVILY_EXHAUSTED = set()  # keys (labels) that failed in this run


def _tavily_api_keys():
    """Return ORDERED list of (label, key) tuples. Priority: file → env → legacy → env.sh."""
    global _TAVILY_KEYS_CACHE
    if _TAVILY_KEYS_CACHE is not None:
        return _TAVILY_KEYS_CACHE
    import os, re
    out = []
    seen = set()

    def _add(label, key):
        key = (key or "").strip().strip('"').strip("'")
        if key.startswith("tvly-") and key not in seen:
            seen.add(key)
            out.append((label, key))

    # 1) Multi-line file (preferred for multi-key setup)
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

    # 2) Env vars: TAVILY_API_KEY, TAVILY_API_KEY_2, ..., TAVILY_API_KEY_5
    for i in range(1, 6):
        suffix = "" if i == 1 else f"_{i}"
        _add(f"env:KEY{suffix or '_1'}", os.environ.get(f"TAVILY_API_KEY{suffix}", ""))

    # 3) Legacy single-key file
    try:
        with open("/opt/newsapp/web/.tavily_key", "r", encoding="utf-8") as f:
            _add("file:tavily_key", f.read().strip())
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # 4) Parse from trendwatch_env.sh (one or many)
    try:
        with open("/opt/newsapp/.openclaw/workspace/scripts/trendwatch_env.sh") as f:
            content = f.read()
        for m in re.finditer(r'TAVILY_API_KEY(?:_\d+)?[=\s]+["\\\']?(tvly-[A-Za-z0-9_-]+)', content):
            _add("env.sh", m.group(1))
    except Exception:
        pass

    _TAVILY_KEYS_CACHE = out
    return out


def _check_one_tavily_key(key):
    """Probe /usage for a specific key. Returns (used, limit, ok)."""
    try:
        import urllib.request, json as _j
        req = urllib.request.Request(
            "https://api.tavily.com/usage",
            headers={"Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = _j.loads(r.read())
        account = d.get("account") or {}
        used = account.get("plan_usage", 0) or 0
        limit = account.get("plan_limit", 1000) or 1000
        return used, limit, used < TAVILY_QUOTA_THRESHOLD
    except Exception as e:
        return -1, -1, False


_TAVILY_QUOTA_CACHE_TTL = 60.0  # seconds; balance freshness vs rate-limit
_TAVILY_QUOTA_LAST_CHECK = 0.0  # timestamp


def _check_tavily_quota(verbose=False, force=False):
    """Probe Tavily quotas с кешем TTL=60s.
    'каждый раз' интерпретируется как 'не реже раза в минуту' — иначе Tavily rate-limit'ит.
    In-flight 429 detection в _fetch_via_tavily обеспечивает живую реакцию между probe'ами.
    force=True игнорирует кеш."""
    global _TAVILY_QUOTA_OK, _TAVILY_QUOTA_LAST_CHECK
    import time as _time
    now = _time.time()
    if not force and _TAVILY_QUOTA_OK is not None and (now - _TAVILY_QUOTA_LAST_CHECK) < _TAVILY_QUOTA_CACHE_TTL:
        return _TAVILY_QUOTA_OK

    keys = _tavily_api_keys()
    if not keys:
        if verbose:
            print("  tavily: no API keys configured")
        _TAVILY_QUOTA_OK = False
        _TAVILY_QUOTA_LAST_CHECK = now
        return False
    if verbose:
        print(f"  tavily: {len(keys)} key(s) configured (probe TTL {int(_TAVILY_QUOTA_CACHE_TTL)}s)")
    any_ok = False
    for label, k in keys:
        if label in _TAVILY_EXHAUSTED:
            continue
        used, limit, ok = _check_one_tavily_key(k)
        if used < 0:
            if verbose:
                print(f"  tavily [{label}]: quota probe failed (network/rate-limit/invalid key)")
            continue
        remaining = limit - used
        marker = "✓" if ok else "✗ (exhausted)"
        if verbose:
            print(f"  tavily [{label}]: {used}/{limit} used, {remaining} remaining {marker}")
        if ok:
            any_ok = True
        else:
            _TAVILY_EXHAUSTED.add(label)
    _TAVILY_QUOTA_OK = any_ok
    _TAVILY_QUOTA_LAST_CHECK = now
    return any_ok


def _pick_active_tavily_key():
    """Return (label, key) of first non-exhausted key, or (None, None)."""
    for label, k in _tavily_api_keys():
        if label not in _TAVILY_EXHAUSTED:
            return label, k
    return None, None


def _fetch_via_tavily(url, trust_score=0.0):
    """Tier 5: Tavily Extract с multi-key failover.
    Tries basic (1 credit) → advanced (2 credits) на активном ключе.
    При 429/quota-error меняет ключ и повторяет.
    Returns (text, mode_label)."""
    global _TAVILY_CALLS_THIS_RUN
    with _TAVILY_LOCK:
        if _TAVILY_CALLS_THIS_RUN >= TAVILY_PER_RUN_CAP:
            return ("", "tavily-cap")
    if not _check_tavily_quota():
        return ("", "tavily-quota")
    if trust_score < 0.5:
        return ("", "tavily-skip-lowtrust")

    import urllib.request, urllib.error, json as _j

    def _call(key, depth):
        """Returns (text, error_kind). error_kind ∈ {'', 'quota', 'http', 'net'}."""
        body = _j.dumps({"urls": [url], "extract_depth": depth, "include_images": False}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/extract",
            data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                d = _j.loads(r.read())
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
            # Differentiate rate-limit (transient) from quota-exhausted (terminal for key)
            rate_keywords = ("excessive requests", "too many requests", "rate limit", "please reduce")
            quota_keywords = ("insufficient credit", "insufficient_credit", "quota exceeded", "plan limit", "usage limit", "out of credit")
            if any(w in body_lower for w in rate_keywords):
                kind = "rate-limit"
            elif e.code == 402 or any(w in body_lower for w in quota_keywords):
                kind = "quota"
            elif e.code == 429:
                kind = "rate-limit"  # default 429 → rate-limit (most common)
            else:
                kind = "http"
            print(f"    tavily HTTP {e.code} ({kind}): {err_body[:180]}")
            return "", kind
        except Exception as e:
            print(f"    tavily net err: {e}")
            return "", "net"

    # Try each key in order until one works or all exhausted.
    # rate-limit → sleep+retry up to 3 times; quota → failover key.
    import time as _time
    rate_retries = 0
    MAX_RATE_RETRIES = 3
    RATE_BACKOFF = (2.0, 5.0, 10.0)
    while True:
        label, key = _pick_active_tavily_key()
        if not key:
            return ("", "tavily-all-exhausted")

        # 1) Basic on this key (1 credit)
        with _TAVILY_LOCK:
            _TAVILY_CALLS_THIS_RUN += 1
        text, err = _call(key, "basic")
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return (text[:8000], f"tavily-basic[{label}]")
        if err == "rate-limit":
            if rate_retries < MAX_RATE_RETRIES:
                wait = RATE_BACKOFF[rate_retries]
                print(f"    tavily [{label}] rate-limited, sleep {wait}s and retry (attempt {rate_retries+1}/{MAX_RATE_RETRIES})")
                _time.sleep(wait)
                rate_retries += 1
                continue
            else:
                print(f"    tavily [{label}] rate-limit retries exhausted; failing this URL")
                return ("", "tavily-rate-limit-max")
        if err == "quota":
            print(f"    tavily [{label}] exhausted (quota), failover to next key")
            _TAVILY_EXHAUSTED.add(label)
            rate_retries = 0
            continue

        # 2) Advanced on same key (2 credits)
        with _TAVILY_LOCK:
            _TAVILY_CALLS_THIS_RUN += 1
        text, err = _call(key, "advanced")
        if text and len(text) >= MIN_TEXT_LEN and not _is_block_page(text):
            return (text[:8000], f"tavily-advanced[{label}]")
        if err == "rate-limit":
            if rate_retries < MAX_RATE_RETRIES:
                wait = RATE_BACKOFF[rate_retries]
                print(f"    tavily [{label}] rate-limited on advanced, sleep {wait}s")
                _time.sleep(wait)
                rate_retries += 1
                continue
            else:
                return ("", "tavily-rate-limit-max")
        if err == "quota":
            print(f"    tavily [{label}] exhausted on advanced, failover to next key")
            _TAVILY_EXHAUSTED.add(label)
            rate_retries = 0
            continue

        # Non-quota, non-rate-limit failure (real http error / not found / etc.)
        return ("", "tavily-fail")



def _persist_articles_to_news_state(items):
    """Batch-write all fetched article_text to news_state.json articles cache.
    Uses canonical hash from core/archives.py: sha256(url + '\n' + title)[:16].
    Atomic via temp+rename. Single read-modify-write at end to minimize race
    with webapp (which runs in another process)."""
    import hashlib
    from datetime import datetime, timezone

    NEWS_STATE_PATH = "/opt/newsapp/.openclaw/workspace/ops/news_state.json"
    MIN_PERSIST = 200  # don't cache stubs <200 chars

    new_articles = {}
    for it in items:
        text = (it.get("article_text") or "").strip()
        if len(text) < MIN_PERSIST:
            continue
        url = (it.get("url") or "").strip()
        title = (it.get("title") or it.get("title_ru") or it.get("title_en") or "").strip()
        if not url:
            continue
        # article_hash = sha256(url)[:16] — canonical from r1_fetch_urls.py / archive
        h = it.get("article_hash") or hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        new_articles[h] = {
            "text": text[:12000],
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    if not new_articles:
        print("r1_prefetch persist: nothing to persist (no items >= 200 chars)")
        return

    # Atomic read-modify-write
    try:
        with open(NEWS_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}
    except Exception as e:
        print(f"r1_prefetch persist: news_state read failed: {e}")
        return

    cache = state.setdefault("articles", {})
    before = len(cache)
    cache.update(new_articles)
    after = len(cache)

    tmp = NEWS_STATE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NEWS_STATE_PATH)
        print(f"r1_prefetch persist: cache {before} -> {after} (+{len(new_articles)} articles)")
    except Exception as e:
        print(f"r1_prefetch persist: write failed: {e}")


if __name__ == "__main__":
    main()
