# Практический гид по переиспользованию

Код извлечён из большей системы. Этот гид показывает, какие файлы брать под
конкретную задачу и что в них заменить. Все пути — от корня репозитория.

> Общие швы для замены (встречаются почти везде):
> 1. **CLI LLM-обёртка** — `subprocess([OPENCLAW, "agent", ...])` → свой вызов модели.
> 2. **БД-пути** — `core/config.py` (`KB_DB_PATH`, `*_ARCHIVE_PATH`, `R1_NEWS_PATH`).
> 3. **Конфиг** — trust-реестр, регулярки тем, поисковые запросы.
> 4. **Бинарь `ru-fetch`** (`RU_FETCH_BIN`) и абсолютные пути `/opt/newsapp/...`.

> **Готовый ИИ-шов + рабочий пример.** Чтобы не разбираться в CLI-обёртке с нуля,
> в корне есть `llm.py` — чистый шов: протокол `LLMBackend` (метод
> `summarize_and_rate(title, text, topic) -> {"summary", "rating", "rationale"}`)
> и офлайн-заглушка `StubBackend` без сети и ключей. Подключение реальной модели —
> заменить один метод (скелет `MyLLMBackend` лежит в комментарии того же файла).
> Сквозной запускаемый пример, который связывает классификацию, скоринг доверия,
> дедуп и этот ИИ-шов в одну цепочку и пишет SQLite, — `examples/run_pipeline.py`
> (см. «Быстрый старт» в README). Это самый быстрый способ увидеть ядро в работе.

---

## Сценарий A. «Хочу только сбор ссылок + скоринг доверия»

**Бери:**
- `pipeline/r1_fetch_urls.py` — основной файл.
- `core/dedupe.py` — если нужен near-dup (опционально).

**Что используешь напрямую:**
- `collect_stubs(mode)` — сбор стабов из Google News / RSS / SearXNG / scrape.
- `_trust_score(url)` + словарь `TRUST_REGISTRY` — скоринг доверия по домену.
- `_is_bad_url_shape(url)`, `_is_travel_topic(title)` — фильтры формы и темы.
- `resolve_redirect(url)` — разрешение Google News / редиректов.

**Что заменить/настроить:**
- `TRUST_REGISTRY` — подставь свои доверенные домены и баллы (или оставь как
  пример структуры).
- `QUERIES`, `GOOGLE_FRESH_QUERIES`, `YANDEX_QUERIES`, `TIER1_FEEDS`,
  `RU_SCRAPE_PAGES` — свои запросы/фиды/сайты под свой домен.
- `TRAVEL_RE`/`BANKING_RE`/`AI_RE` — свои регулярки тем (если фильтр темы нужен).
- `SEARXNG_URL` — адрес своего SearXNG (или выкини yandex-режим, оставь
  `mode=collect` без него).
- `RU_FETCH_BIN` — если нет своего anti-bot прокси, убери ru-fetch-ветки (останется
  чистый urllib; geo-blocked/SPA-сайты просто не спарсятся).
- `OUTPUT_PATH` (`/tmp/r1_urls.json`) — куда писать кандидатов.

**LLM не нужен** — этот срез полностью детерминированный.

---

## Сценарий B. «Хочу только извлечение текста статей»

**Бери:** `core/article_fetch.py` (самодостаточный, ~один импорт-шов).

**Точка входа:** `fetch_article_text(url, title_hint, trust_score, allow_tavily)`
→ `(text, mode_label)`. Каскад trafilatura → ru-fetch → snippets(DDG+GN) → Tavily.

**Что заменить/настроить:**
- `RU_FETCH_BIN` — путь к своему прокси-fetcher'у, либо убрать Tier 2.
- Ключи Tavily — `_tavily_api_keys()` читает из файла `.tavily_keys`,
  env-переменных `TAVILY_API_KEY[_N]` и `trendwatch_env.sh`. Оставь один источник,
  или передавай `allow_tavily=False` чтобы вообще не использовать платный tier.
- Пути к файлам ключей (`/opt/newsapp/web/.tavily_keys` и т.п.) — под свою среду.

Альтернатива: тот же каскад встроен в `pipeline/r1_prefetch.py::fetch_one` (с
concurrency-обвязкой и кэшем) — бери его, если нужна пакетная предзагрузка.

---

## Сценарий C. «Хочу только суммаризацию / вызов LLM»

**Бери:**
- `core/llm_agent.py` — парсеры вывода LLM-агента (**это и есть точка LLM**).
- `pipeline/r1_summarize_finals.py` — как образец промпта и batch-логики.

**Точка LLM:** во всех местах модель вызывается так:

```python
proc = subprocess.run(
    [OPENCLAW, "agent", "--agent", AGENT_ID, "--session-id", sid,
     "--message", prompt, "--json"],
    capture_output=True, text=True, timeout=...,
)
reply, err = _extract_reply(proc.stdout)          # из core/llm_agent.py
parsed = _parse_first_json_object(reply)          # если ждём JSON
```

**Чтобы подключить свою модель**, замени `subprocess`-вызов на вызов своего SDK
(OpenAI/Anthropic/локальная модель) и верни тот же контракт:
- для суммаризации — текст ответа (или JSON `{id: summary}`, который агент пишет в
  `OUTPUT_BATCH`-файл);
- `_extract_reply` ожидает структуру `{"result": {"payloads": [{"text": ...}]}}` —
  если зовёшь свой SDK, просто верни `reply` напрямую, минуя этот парсер.

`_parse_first_json_object` / `_parse_insights_json` (балансировка скобок) полезны
сами по себе — достать JSON из «болтливого» ответа модели.

**Промпт-инжиниринг как образец:** большой промпт суммаризации (правила перевода
англицизмов на русский, структура summary, запрет выдумывать цифры) — в
`r1_summarize_finals.py`. Бери как шаблон для домена «новостной аналитик».

---

## Сценарий D. «Хочу только генерацию инсайтов»

**Бери:**
- `insights/orchestrator.py` — очередь фоновых задач (почти самодостаточна).
- `insights/routes_insights.py` — логика генерации и промпт.
- `core/kb_db.py` + `schema/schema.sql` — хранилище гипотез.
- `core/llm_agent.py` — парсинг ответа.

**Что заменить/настроить:**
- Импорты-швы в `routes_insights.py`: `from web_app import (...)`,
  `import orchestrator`, `from templates import ...`. Замени на свои реализации
  (`_kb_conn`, `_require_auth`, `_find_user`, загрузчики архивов и т.д.).
- `INSIGHTS_PROMPT` — свой системный промпт под свой домен (текущий заточен под
  «продуктового аналитика премиального банка»).
- `INSIGHT_CATEGORIES` / `_normalize_category` — свои категории.
- Вызов агента (`subprocess.Popen([OPENCLAW, ...])`) → свой вызов модели.
- Источники: `_collect_news_for_insights` тянет из travel/packages-архивов —
  подставь свои источники документов.

`orchestrator.py` можно взять **отдельно** как универсальную очередь задач на
SQLite (приоритеты по тарифу, ретраи, восстановление, метрики) — он зависит
только от стандартной библиотеки. Зарегистрируй свои `register_kind(...)` и вызови
`startup(user_tier_lookup, db_path)`.

---

## Сценарий E. «Хочу только базу знаний с FTS-поиском»

**Бери:** `core/kb_db.py` + `core/kb_ingest.py` + `insights/routes_kb.py` +
`schema/schema.sql`.

- `kb_db.py` — соединение, схема, миграции, права, FTS5.
- `kb_ingest.py` — извлечение текста из PDF/DOCX/TXT/MD/URL + вставка + enrichment.
- `routes_kb.py` — готовые FastAPI-эндпоинты upload/text/url/list/search/approve/delete.

**Заменить:** импорты-швы (`from web_app import ...`, `from templates import ...`),
LLM-вызов в enrichment (`_kb_enrich_sync`), пути (`KB_DIR`, `KB_DB_PATH`).
Enrichment можно вовсе отключить (не вызывать `_kb_enrich_bg`) — поиск и хранение
работают и без LLM.

---

## Сценарий F. «Хочу только дедуп новостей по заголовкам»

**Бери:** `core/dedupe.py` (+ нужные константы из `core/config.py`:
`_TITLE_WORD_RE`, `_TITLE_STOP`, `NEAR_DUP_THRESHOLD`, `NEAR_DUP_WINDOW_DAYS`).

Самодостаточно. Ключевые функции: `_title_similarity(a, b)` (Jaccard по
значимым словам), `_find_near_dup_title(...)`, `_prune_near_dups(items, key)`
(схлопывает дубликаты in-place, прикрепляя их в `dup_sources`). Порог и окно —
настраиваемые. `_TITLE_STOP` — список русских+английских стоп-слов, при желании
расширь под свой язык.

---

## Чек-лист адаптации (общий)

1. Создать `.env` из `.env.example`, заполнить (Tavily, SearXNG, LLM-агент, пути).
2. Заменить абсолютные пути `/opt/newsapp/...` на свои (или вынести в config).
3. Заменить CLI LLM-обёртку (`subprocess(openclaw)`) на свой вызов модели.
4. Реализовать/заглушить импорты-швы (`web_app`, `templates`, `core.users`,
   `core.auth`, `orchestrator` там, где он импортируется снаружи).
5. Подставить свой бинарь fetch (`ru-fetch`) или убрать его ветки.
6. Настроить trust-реестр, регулярки тем, поисковые запросы под свой домен.
7. Инициализировать SQLite (`_kb_init` / `ensure_schema`) — схема создастся сама.
