#!/usr/bin/env python3
"""r1_summarize_finals.py — R1.5 step.

Runs after R1 (06:40 UTC), before R2 (07:00 UTC). Ensures every final item
in r1_news.json has a proper variant-A summary_ru.

Algorithm:
1. Read /opt/newsapp/.openclaw/workspace/ops/r1_news.json
2. Find items where summary_ru is empty AND trust_score >= 0.3
3. For each: call Tavily Extract (advanced depth) to fetch article_text
4. If text >= 300 chars: collect into batch
5. Spawn ONE openclaw agent run that summarizes the batch into variant-A summaries
6. Merge summaries back into r1_news.json
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import hashlib
from pathlib import Path

NEWS_PATH = "/opt/newsapp/.openclaw/workspace/ops/r1_news.json"
INPUT_BATCH = "/tmp/r1_summarize_input.json"
OUTPUT_BATCH = "/tmp/r1_summarize_output.json"
LOG_PATH = "/tmp/r1_summarize_finals.log"

OPENCLAW = "openclaw"
AGENT_ID = "trendwatch"

MIN_TRUST = 0.0            # cover EVERY news item; user requirement = 100% summary coverage
MIN_TEXT_LEN = 300         # below this, can't write a good summary
MAX_TAVILY_CALLS = 35      # was 20 — raised 2026-05-29 (free tier still 67/day total)
TAVILY_TIMEOUT = 30
TAVILY_KEYS_FILE = "/opt/newsapp/web/.tavily_keys"
TRENDWATCH_ENV = "/opt/newsapp/.openclaw/workspace/scripts/trendwatch_env.sh"

# Webwright 5th tier — last-resort browser agent rescue when the regular
# cascade returned nothing or under MIN_TEXT_LEN. Hard cap to protect
# token budget if many URLs fail the same morning.
MAX_WEBWRIGHT_CALLS = 0  # disabled after wiki timeout test 2026-05-27; flip to 5+ when prompt is tuned
WEBWRIGHT_TIMEOUT_S = 300
WEBWRIGHT_WORKSPACE_ROOT = "/tmp/webwright_rescue"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_tavily_keys():
    """Multi-source loader (same priority as r1_prefetch.py):
    1) /opt/newsapp/web/.tavily_keys (one key per line)
    2) env TAVILY_API_KEY / TAVILY_API_KEY_2..5
    3) parse from trendwatch_env.sh
    """
    import re
    keys = []
    seen = set()

    def _add(k):
        k = (k or "").strip().strip('"').strip("'")
        if k.startswith("tvly-") and k not in seen:
            seen.add(k)
            keys.append(k)

    if Path(TAVILY_KEYS_FILE).exists():
        for line in Path(TAVILY_KEYS_FILE).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                _add(line)
    for i in range(1, 6):
        suffix = "" if i == 1 else f"_{i}"
        _add(os.environ.get(f"TAVILY_API_KEY{suffix}", ""))
    if Path(TRENDWATCH_ENV).exists():
        content = Path(TRENDWATCH_ENV).read_text()
        for m in re.finditer(r'TAVILY_API_KEY(?:_\d+)?[=\s]+["\']?(tvly-[A-Za-z0-9_-]+)', content):
            _add(m.group(1))
    return keys


def tavily_extract(url, api_key):
    """One Tavily Extract API call. Returns text or None."""
    try:
        req = urllib.request.Request(
            "https://api.tavily.com/extract",
            data=json.dumps({
                "urls": [url],
                "api_key": api_key,
                "extract_depth": "advanced",
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=TAVILY_TIMEOUT).read())
        results = resp.get("results", [])
        if not results:
            return None
        text = (results[0].get("raw_content") or "").strip()
        return text if len(text) >= MIN_TEXT_LEN else None
    except urllib.error.HTTPError as e:
        log(f"  tavily HTTPError {e.code} for {url[:60]}")
        return None
    except Exception as e:
        log(f"  tavily err {type(e).__name__}: {str(e)[:80]} for {url[:60]}")
        return None


def webwright_rescue(url: str, item_id: str) -> tuple[str, str]:
    """Last-resort fetcher: invoke openclaw agent with the webwright skill.

    Returns (text, mode_label) where text is the extracted article body and
    mode_label is for stats. Empty text + mode like 'webwright-<reason>'
    means failure — caller treats it as "no text".

    Hard requirements (all enforced via try/except):
      - never raise, even on subprocess crash / timeout / missing files
      - never spend more than WEBWRIGHT_TIMEOUT_S seconds on a single URL
      - never overwrite the caller's session — use a unique --session-id
      - write/read text via a per-call file so stdout chatter doesn't pollute it
    """
    try:
        ts = int(time.time())
        workspace = f"{WEBWRIGHT_WORKSPACE_ROOT}/{item_id}_{ts}"
        output_file = f"{workspace}/text.txt"
        os.makedirs(workspace, exist_ok=True)

        prompt = (
            "Используй навык webwright, чтобы извлечь основной текст статьи.\n\n"
            f"URL: {url}\n"
            f"Рабочая папка: {workspace}\n"
            f"Файл результата: {output_file}\n\n"
            "ВАЖНО — упрощённый режим:\n"
            "- НЕ создавай plan.md, НЕ создавай final_runs/, НЕ делай скриншоты.\n"
            "- Запусти один Playwright-скрипт (через webwright-run final_script.py — это обязательная обёртка для изоляции памяти на этом VPS).\n"
            "- Скрипт открывает страницу в headless Firefox, ждёт networkidle, извлекает основной текст статьи (через article-тег / основной контентный контейнер, без меню/футера/cookie-banner).\n"
            "- Записывает извлечённый plain text в файл результата.\n"
            "- Если страница заблокирована (paywall / captcha / 403) или текста меньше 300 символов — запиши в файл одно слово BLOCKED и выйди.\n"
            "- НЕ комментируй процесс в чате — нужен только файл-результат.\n"
        )

        session_id = f"webwright-rescue-{item_id}-{ts}"
        cmd = [
            OPENCLAW, "agent",
            "--agent", AGENT_ID,
            "--session-id", session_id,
            "--message", prompt,
            "--json",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=WEBWRIGHT_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            log(f"  webwright timeout ({WEBWRIGHT_TIMEOUT_S}s) for {url[:60]}")
            return "", "webwright-timeout"
        except Exception as e:
            log(f"  webwright subprocess err {type(e).__name__}: {str(e)[:80]}")
            return "", "webwright-spawn-err"

        if proc.returncode != 0:
            log(f"  webwright rc={proc.returncode} stderr={proc.stderr[:160]}")
            # don't return yet — agent may have written the file before exiting

        if not Path(output_file).exists():
            log(f"  webwright: no output file produced")
            return "", "webwright-no-output"

        try:
            text = Path(output_file).read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            log(f"  webwright: cannot read output: {type(e).__name__}")
            return "", "webwright-read-err"

        if text.upper() == "BLOCKED":
            log(f"  webwright reported BLOCKED for {url[:60]}")
            return "", "webwright-blocked"
        if len(text) < MIN_TEXT_LEN:
            log(f"  webwright thin ({len(text)}c) for {url[:60]}")
            return "", f"webwright-thin-{len(text)}"

        log(f"  webwright OK {len(text)}c for {url[:60]}")
        return text[:8000], "webwright"
    except Exception as e:
        # Bulletproof catch-all: webwright_rescue must NEVER raise into caller.
        log(f"  webwright UNHANDLED {type(e).__name__}: {str(e)[:120]}")
        return "", "webwright-crash"


def fetch_for_empty(items):
    """For each empty-summary item: multi-tier fetch cascade via r1_prefetch.fetch_one.

    Cascade order (built into r1_prefetch.fetch_one):
      Tier 1: trafilatura — fast direct fetch
      Tier 2: ru-fetch + trafilatura/bs4 — via xray VLESS proxy (RU IP)
      Tier 4: snippets (DDG + Google News RSS) — free aggregator
      Tier 5: Tavily Extract — paid, last resort
    """
    # Import here so module compiles even if r1_prefetch deps aren't installed at import time
    sys.path.insert(0, "/opt/newsapp/.openclaw/workspace/scripts")
    try:
        import r1_prefetch
    except Exception as e:
        log(f"ERROR: cannot import r1_prefetch: {e}")
        return {}

    # Items needing rescue: empty summary AND trust >= MIN_TRUST
    targets = [
        it for it in items
        if not (it.get("summary_ru") or "").strip()
        and (it.get("trust_score") or 0) >= MIN_TRUST
    ]
    # Sort by trust desc — high-trust items get fetched first (cascade is slow per-item)
    targets.sort(key=lambda x: -(x.get("trust_score") or 0))
    log(f"Empty items needing rescue (trust >= {MIN_TRUST}): {len(targets)}")

    fetched = {}
    mode_stats = {}
    webwright_used = 0
    for n, it in enumerate(targets[:MAX_TAVILY_CALLS], 1):
        url = (it.get("url") or "").strip()
        if not url:
            continue
        item_id = it.get("id") or it.get("article_hash") or hashlib.sha256(url.encode()).hexdigest()[:16]
        title_hint = (it.get("title_ru") or it.get("title_en") or "")[:80]
        try:
            text, mode = r1_prefetch.fetch_one(url, title_hint=title_hint, trust_score=it.get("trust_score") or 0)
        except Exception as e:
            log(f"  [{n}] fetch_one err {type(e).__name__}: {str(e)[:80]}")
            text, mode = "", "error"

        # 5th tier: Webwright (browser agent via openclaw + skill) as last resort
        # when the regular cascade produced empty or thin text. Hard-capped via
        # MAX_WEBWRIGHT_CALLS to protect the gpt-5.5 token budget.
        cascade_thin = (not text) or len(text) < MIN_TEXT_LEN
        if cascade_thin and webwright_used < MAX_WEBWRIGHT_CALLS:
            log(f"  [{n}/{MAX_TAVILY_CALLS}] cascade thin via={mode}, escalating to webwright ({webwright_used + 1}/{MAX_WEBWRIGHT_CALLS})")
            try:
                ww_text, ww_mode = webwright_rescue(url, str(item_id))
            except Exception as e:
                # webwright_rescue itself catches everything, but belt + suspenders
                log(f"  [{n}] webwright_rescue raised (should not happen): {type(e).__name__}: {str(e)[:80]}")
                ww_text, ww_mode = "", "webwright-outer-crash"
            webwright_used += 1
            if ww_text and len(ww_text) >= MIN_TEXT_LEN:
                text, mode = ww_text, ww_mode  # promote to successful
            else:
                # keep original mode so stats reflect what actually failed first;
                # but tag failure mode for visibility
                mode = f"{mode}->{ww_mode}"

        mode_stats[mode] = mode_stats.get(mode, 0) + 1
        if text and len(text) >= MIN_TEXT_LEN:
            fetched[item_id] = text[:8000]
            log(f"  [{n}/{MAX_TAVILY_CALLS}] OK {len(text)}c via={mode} trust={it.get('trust_score')} | {title_hint[:50]}")
        else:
            log(f"  [{n}/{MAX_TAVILY_CALLS}] NO TEXT via={mode} trust={it.get('trust_score')} | {title_hint[:50]}")
    log(f"Fetch totals: {len(fetched)}/{len(targets[:MAX_TAVILY_CALLS])} items via cascade; modes={mode_stats} (webwright used: {webwright_used}/{MAX_WEBWRIGHT_CALLS})")
    return fetched


def summarize_batch(items, fetched_texts):
    """Spawn openclaw agent with batch summarize task. Returns dict {id: summary_ru}.

    Includes ALL empty-summary items (trust >= MIN_TRUST), regardless of whether
    Tavily was able to fetch article_text. Items without text get a fallback
    summary built from R1-populated fields (title + relevance_reason +
    bank_applicability_reason) — ensures 100% coverage of /news section.
    """
    batch = []
    id_to_item = {}
    with_text = 0
    without_text = 0
    for it in items:
        if (it.get("summary_ru") or "").strip():
            continue
        if (it.get("trust_score") or 0) < MIN_TRUST:
            continue
        item_id = it.get("id") or it.get("article_hash") or hashlib.sha256((it.get("url") or "").encode()).hexdigest()[:16]
        text = fetched_texts.get(item_id, "") or ""
        # Cap to 2500 chars (was 5000) to avoid context overflow on shared sessions
        batch.append({
            "id": item_id,
            "title_ru": it.get("title_ru") or "",
            "title_en": it.get("title_en") or "",
            "url": it.get("url") or "",
            "trust": it.get("trust_score") or 0,
            "case_type": it.get("case_type") or "",
            "relevance_reason": it.get("relevance_reason") or "",
            "bank_applicability_reason": it.get("bank_applicability_reason") or "",
            "article_text": text[:2500],
        })
        id_to_item[item_id] = it
        if text:
            with_text += 1
        else:
            without_text += 1
    log(f"Batch composition: with_text={with_text}, without_text(fallback)={without_text}")

    if not batch:
        log("No batch to summarize")
        return {}

    with open(INPUT_BATCH, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    log(f"Batch written: {len(batch)} items → {INPUT_BATCH}")

    # Remove old output
    Path(OUTPUT_BATCH).unlink(missing_ok=True)

    prompt = f"""ЗАДАЧА: написать summary_ru для {len(batch)} items из {INPUT_BATCH}.

ИСТОЧНИК: {INPUT_BATCH} — JSON-массив items с полями:
  id, title_ru, title_en, url, trust, case_type,
  relevance_reason (короткий тег + краткая суть от R1),
  bank_applicability_reason (зачем это банковскому travel-блоку),
  article_text (тело статьи; может быть пустое или содержать мусор/баннеры).

═══════════════════════════════════════════════════════════════════
ЯЗЫК — ПРИОРИТЕТ №1: ЧИСТЫЙ ЕСТЕСТВЕННЫЙ РУССКИЙ
═══════════════════════════════════════════════════════════════════

Аудитория — русскоязычные банковские специалисты, читают саммари для
оперативных решений. Текст должен звучать как от русскоязычного отраслевого
аналитика, а не как машинный перевод.

Правило: если для англоязычного термина есть нормальный русский аналог —
ИСПОЛЬЗУЙ ЕГО. Англицизм допустим ТОЛЬКО когда русский аналог отсутствует
или сильно искажает смысл.

ОБЯЗАТЕЛЬНЫЕ ПЕРЕВОДЫ (НЕ оставляй в латинице):
  AI → ИИ
  AI-powered / AI-first → на базе ИИ / с ИИ в основе
  AI-агент, AI-ассистент, AI-консьерж → ИИ-агент, ИИ-ассистент, ИИ-консьерж
  AI-платформа → платформа на базе ИИ
  travel → путешествия / поездки (тревел — только в составных типа «тревел-рынок»)
  travel-fintech, travel-tech → финтех для путешествий, технологии для путешествий
  travel-блок Сбера → подразделение путешествий Сбера
  airline experience → клиентский опыт авиапассажира / сервис авиакомпании
  airline operations / flight operations → операционные процессы авиакомпании / управление полётами
  customer service / customer support → клиентская поддержка / клиентский сервис
  customer experience (CX) → клиентский опыт
  customer journey → клиентский путь
  in-feed planning → планирование внутри ленты
  voice-native, voice queries → голосовое управление, голосовые запросы
  natural-language queries → запросы на естественном языке
  seamless connectivity → бесшовное подключение (только если важна суть «без переключений»)
  airport rides → трансфер из аэропорта
  baggage / luggage handling → хранение и обработка багажа
  inbound tourism → въездной туризм
  business leisure / bleisure → деловой туризм с элементами отдыха
  corporate travel → корпоративные поездки
  MICE → деловой туризм (мероприятия, инсентив, конференции, выставки)
  premium card → премиальная карта
  loyalty program / loyalty card → программа лояльности / бонусная карта
  co-branded card → совместная карта (с партнёром)
  frequent flyer → программа постоянного пассажира
  lounge access → доступ в зал ожидания (lounge)
  boutique hotels → бутик-отели
  hotel back office → внутренние процессы отеля
  metasearch → метапоиск
  OTA (Online Travel Agency) → онлайн-турагентство
  destination offers → предложения по направлениям
  itinerary → маршрут поездки
  funding / round → раунд финансирования
  design partner → партнёр по разработке
  go-to-market → выход на рынок
  product launch → запуск продукта
  revenue management → управление доходностью
  cabin crew / pilots → бортпроводники / пилоты
  M&A → сделки слияния и поглощения

МОЖНО ОСТАВЛЯТЬ ЛАТИНИЦЕЙ (узнаваемые глобальные бренды без русского аналога):
  Бренды: Visa, Mastercard, American Express (AmEx), Hilton, Marriott, Hyatt,
    Booking.com, Expedia, Trip.com, Airbnb, Delta, United, Lufthansa, Emirates,
    Virgin Atlantic, OpenAI, ChatGPT, Anthropic, Claude, Google, Apple,
    Capital One, Chase Sapphire, JPMorgan, Revolut, Wise, Klarna, Uber,
    Pegasus, Workday, Skift и прочие глобальные названия как есть.
  Технические аббревиатуры: API, ML, NLP, B2B, B2C, SaaS, SMS, PDF, URL
  Русские бренды — на русском: Сбер, СберПервый, ВТБ, Альфа-банк, Райффайзен,
    Газпромбанк, Юнибанк, FrankRG

ЗАПРЕЩЕНО:
  • смешивать кириллицу и латиницу в одном слове («AI-консьерж» — НЕТ,
    «ИИ-консьерж»; «travel-сегмент» — НЕТ, «сегмент путешествий»)
  • неестественные кальки: «опыт авиакомпании», «решение позволяет получать
    данные» — переписывай: «сервис авиакомпании», «инструмент даёт доступ к данным»
  • штампы: «уникальный», «инновационный», «революционный», «передовой»,
    «комплексное решение», «синергия»
  • начало с «По заголовку», «Сообщается», «Стало известно», «В материале»
  • повтор заголовка

ЦИФРЫ И ВРЕМЯ:
  $6.3B → 6,3 млрд $
  Q4 2026 → IV квартал 2026
  даты: 21 мая 2026 (не «May 21, 2026»)

═══════════════════════════════════════════════════════════════════
СТРУКТУРА summary_ru (для КАЖДОГО item) — ТОЛЬКО САММАРИ СТАТЬИ
═══════════════════════════════════════════════════════════════════

Это саммари новостной статьи в журналистском стиле — БЕЗ рекомендаций,
без оценок «что нам с этого», без выводов «для бизнеса». Только факты
из статьи.

- 3-5 предложений, 400-700 символов на русском
- 2 смысловых блока в одном связном тексте:
  1. ЧТО ПРОИЗОШЛО: кто, что сделал/запустил/купил/объявил, когда, где
  2. ДЕТАЛИ: цифры (суммы, проценты), технологии, партнёры, география,
     механика для пользователя, контекст рынка — всё, что есть в статье

ЗАПРЕЩЕНО:
- Блоки типа «для СберПервого / для премиального травел-блока / нам важно».
- Рекомендации «можно скопировать», «стоит внедрить», «полезно перенести».
- Оценочные выводы «это сигнал тренда», «это шаг в сторону Х» — если этого
  нет в самой статье. Если автор статьи делает такой вывод — можно процитировать.
- Прямое обращение к читателю «вам стоит обратить внимание».
- ⛔ МЕТА-КОММЕНТАРИИ о доступности данных: НЕ пиши «Полного текста статьи
  нет», «Детали ограничены», «В доступном фрагменте», «Из доступного текста»,
  «Подробности не раскрыты», «Дополнительные партнёры в доступном тексте не
  подтверждены», «Надёжных данных не нашлось» и любые подобные оправдания.
  Это техническая информация, которая не должна попадать в саммари. Просто
  пиши то, что знаешь, в утвердительной форме. Если данных мало — саммари
  будет короче (300-500 символов), но БЕЗ объяснений почему.

Поле bank_applicability_reason в input — это служебная метка для маршрутизации,
НЕ используй её как материал для саммари. То же про case_type — только метка.

ВЫБОР ИСТОЧНИКА ДАННЫХ (важно):
- ЕСЛИ article_text непустое и содержит осмысленный текст статьи (есть цифры,
  имена, факты) — опирайся ПРЕЖДЕ ВСЕГО на article_text.
- ЕСЛИ article_text пустое ИЛИ это мусор (cookie banner, captcha, paywall,
  навигация, "404 not found", куски HTML) — строй summary из title_ru/title_en
  + relevance_reason + bank_applicability_reason + case_type. В этом режиме
  summary будет без новых цифр сверх тех, что уже есть в title/relevance_reason,
  но всё равно должен дать 3 блока: ЧТО (из title), ДЕТАЛИ (из relevance_reason
  + case_type), ПОЧЕМУ ВАЖНО (из bank_applicability_reason). Длина 400+ символов
  всё равно обязательна — раскрой контекст из имеющихся полей.
- НИКОГДА не выдумывай цифры, имена, даты, которых нет ни в article_text, ни в
  полях R1. Лучше написать обобщённо («раунд финансирования», «партнёрство с
  банком»), чем выдумать конкретику.

АЛГОРИТМ:
1. Прочитай {INPUT_BATCH} (JSON-массив).
2. Для КАЖДОГО item — напиши summary_ru по формату и языковым правилам выше.
3. САМО-ПРОВЕРКА перед записью: пройдись по каждому summary и убедись, что
   в нём нет англицизмов из «обязательных переводов» в латинице. Если есть —
   замени на русский аналог. Это критично — текст пойдёт русскоязычному
   пользователю.
4. Собери результат как JSON: {{"id1": "summary1", "id2": "summary2", ...}}
5. ЗАПИШИ через Write tool в {OUTPUT_BATCH}.
6. В финале выведи: "BATCH_DONE: N summaries written"

КАТЕГОРИЧЕСКИ ВАЖНО:
- НЕ менять r1_news.json напрямую. Только записать output в {OUTPUT_BATCH}.
- НЕ пропускать items: для каждого должен быть ключ в output с непустым summary
  длиной >=300 символов. Если совсем нет данных (и article_text, и R1-поля
  пустые) — пиши summary из 2-3 предложений на основе url+source как минимум.
- НЕ создавать helper-скриптов — всё через inline python3 -c если нужно.
"""

    # Isolated session per run — main session accumulates messages over time
    # and overflows context for big batches (observed: 176 msgs → context overflow).
    session_id = f"r15-{int(time.time())}"
    log(f"Spawning openclaw agent (batch of {len(batch)} items, session-id={session_id})…")
    try:
        # No timeout cap — agent runs as long as needed (gateway has own cap)
        proc = subprocess.run(
            [OPENCLAW, "agent", "--agent", AGENT_ID, "--session-id", session_id, "--message", prompt, "--json"],
            capture_output=True, text=True, timeout=1800,  # 30 min hard timeout
        )
        log(f"Agent rc={proc.returncode}, stdout {len(proc.stdout)} chars, stderr {len(proc.stderr)} chars")
        if proc.returncode != 0:
            log(f"Agent stderr: {proc.stderr[:500]}")
    except subprocess.TimeoutExpired:
        log("Agent timeout (30min cap)")
        return {}
    except Exception as e:
        log(f"Agent spawn error: {e}")
        return {}

    # Read output
    if not Path(OUTPUT_BATCH).exists():
        log(f"Agent didn't write {OUTPUT_BATCH}!")
        return {}
    try:
        with open(OUTPUT_BATCH, "r", encoding="utf-8") as f:
            result = json.load(f)
        if not isinstance(result, dict):
            log(f"Unexpected output type: {type(result).__name__}")
            return {}
        log(f"Got {len(result)} summaries from agent")
        return result
    except Exception as e:
        log(f"Output parse error: {e}")
        return {}


def main():
    # Open fresh log
    Path(LOG_PATH).unlink(missing_ok=True)
    log("=== r1_summarize_finals.py START ===")

    if not Path(NEWS_PATH).exists():
        log(f"ERROR: {NEWS_PATH} missing")
        sys.exit(1)

    with open(NEWS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])
    log(f"Loaded {len(items)} items from r1_news.json")

    empty_before = sum(1 for it in items if not (it.get("summary_ru") or "").strip())
    log(f"Items with empty summary_ru: {empty_before}")

    if empty_before == 0:
        log("Nothing to do, exiting")
        return

    # Step 1: Tavily Extract for empty items (best-effort — fallback handles misses)
    fetched = fetch_for_empty(items)
    # Don't early-return on empty fetched: items still go to batch with fallback
    # built from R1 fields (title + relevance_reason + bank_applicability_reason).

    # Step 2: Batch summarize via openclaw agent
    summaries = summarize_batch(items, fetched)
    if not summaries:
        log("No summaries produced, nothing to merge")
        return

    # Step 3: Merge back
    merged = 0
    for it in items:
        item_id = it.get("id") or it.get("article_hash") or hashlib.sha256((it.get("url") or "").encode()).hexdigest()[:16]
        new_sum = (summaries.get(str(item_id)) or summaries.get(item_id) or "").strip()
        if new_sum and len(new_sum) >= 200:
            it["summary_ru"] = new_sum
            merged += 1

    # Atomic write
    tmp = NEWS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NEWS_PATH)
    log(f"Merged {merged} new summaries into r1_news.json")

    empty_after = sum(1 for it in items if not (it.get("summary_ru") or "").strip())
    log(f"Items still empty: {empty_after} (was {empty_before})")
    log("=== DONE ===")


if __name__ == "__main__":
    main()
