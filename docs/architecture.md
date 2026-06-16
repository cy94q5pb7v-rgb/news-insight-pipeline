# Архитектура и поток данных

Документ описывает, как устроены два конвейера, какую роль играет каждый модуль и
как они связаны. Где механизм неочевиден — отмечено «по коду видно».

> Термины: *стадия* — отдельный шаг конвейера; *стаб (stub)* — заготовка
> кандидата (заголовок + URL + источник), ещё без текста и оценок;
> *кандидат (candidate)* — стаб после разрешения URL, скоринга и извлечения текста;
> *архив* — JSON-файл с накопленными новостями; *гипотеза/инсайт* — структурированное
> наблюдение, выведенное LLM-агентом из новостей и материалов.

---

## 1. Два конвейера, один источник истины — БД портала

Система состоит из двух частей, которые соединяются через БД и JSON-архивы:

1. **Новостной конвейер** (`pipeline/` + `core/`) — серия cron-скриптов, которые
   шаг за шагом превращают поисковые запросы в готовые новости с саммари и
   рейтингами, складывая их в архивы и в SQLite.
2. **Генерация инсайтов** (`insights/`) — веб-слой (FastAPI-роутеры) поверх
   очереди фоновых задач: берёт новости из архивов + материалы из БД и через
   LLM-агента производит гипотезы.

Связующее звено — **SQLite-база** (`schema/schema.sql`, доступ через
`core/kb_db.py`) и **JSON-архивы** (`travel_news_archive.json`,
`packages_news_archive.json`, доступ через `core/archives.py`).

---

## 2. Новостной конвейер: файлы по стадиям

Стадии пронумерованы как «R1 / R1.5 / R2» в комментариях кода (R1 = сбор и
первичная обработка, R1.5 = досуммаризация, R2 = дальнейшая обработка во
внешней системе, в репозиторий не входит).

| Файл | Роль | Вход | Выход |
|---|---|---|---|
| `r1_fetch_urls.py` | сбор стабов, фильтры, разрешение URL, trust_score, извлечение текста, классификация | поисковые запросы (зашиты в коде) | `r1_urls.json` (кандидаты) |
| `r1_prefetch.py` | добивает пустые `article_text` каскадом fetch | `r1_urls.json` | `r1_urls.json` (обновлённый) + кэш в `news_state.json` |
| `r1_classify.py` | детерминированный классификатор тем (helper для стадии 2) | title + text (argv) | строка case_type на stdout |
| `r1_summarize_finals.py` | суммаризация через LLM-агента, 100% покрытие summary | `r1_news.json` | `r1_news.json` (с `summary_ru`) |
| `r1_collect_prefetch.sh` | оркестрация: fetch + prefetch под flock | — | лог в `/tmp` |
| `r1_evening_check.py` | вечерний отчёт о работе конвейера | архивы + БД | Telegram-сообщение |
| `r1_news_watchdog.py` | алерт если новости не собрались/без саммари | `r1_news.json` | Telegram-алерт |

Важная деталь по коду: `r1_fetch_urls.py` пишет `r1_urls.json`, но **`r1_news.json`
производится стадией R1-LLM, которой в репозитории нет** (это LLM-агент, который
из кандидатов отбирает финальные items и проставляет `case_type`, `relevance_score`,
`relevance_reason`, `bank_applicability_reason`, `title_ru`). `r1_summarize_finals.py`
лишь добивает `summary_ru` для items в `r1_news.json`. То есть **рейтинги
релевантности присваиваются на стадии R1-LLM (вне репо), а `trust_score` — на
стадии сбора в `r1_fetch_urls.py`** детерминированно по домену.

---

## 3. core/ — переиспользуемые модули и их связи

```
config.py ──────────────┐ (пути, регулярки, пороги)
                         ├──► dedupe.py ──► archives.py
article_fetch.py         │                    │
   (каскад извлечения)   │                    ▼
                         │            travel/packages archives (JSON)
kb_db.py (SQLite) ◄──────┘                    │
   ├── kb_ingest.py (загрузка + enrichment)   │
   └── news_state.py (реакции/заметки/кэш)    │
llm_agent.py (парсинг ответа CLI-агента) ◄────┘ (используется enrichment + insights)
```

- **`config.py`** — единый источник путей и констант. `_TITLE_WORD_RE`,
  `_TITLE_STOP`, `NEAR_DUP_THRESHOLD` используются дедупом; `R1_NEWS_PATH`,
  `TRAVEL_ARCHIVE_PATH`, `PACKAGES_ARCHIVE_PATH` — архивами; `KB_DB_PATH` — БД.
  Замечание по коду: при импорте `config.py` создаёт файл `.jwt_secret`
  (`secrets.token_hex(32)`), если его нет — это побочный эффект импорта.

- **`dedupe.py`** — near-duplicate детект по заголовкам. Считает Jaccard-сходство
  множеств значимых слов (`_title_similarity`); если ≥ `NEAR_DUP_THRESHOLD` (0.7)
  в окне `NEAR_DUP_WINDOW_DAYS` (5 дней) — items схлопываются, дубликаты не
  выбрасываются, а прикрепляются в `dup_sources` (`_attach_dup`). Чистая логика
  без внешних зависимостей.

- **`archives.py`** — загрузка и накопление архивов travel и packages. Держит
  **зеркало trust-реестра** (`_TRUST_REGISTRY`) для on-the-fly скоринга в
  endpoint'ах. `_accumulate_travel_archive` мёржит новые items из `r1_news.json`,
  ретроспективно дополняет поля (`UPDATABLE_FIELDS`), группирует по `story_group`,
  прогоняет дедуп. packages-архив строится из Telegram-дайджеста (jsonl-логи).

- **`article_fetch.py`** — универсальный извлекатель текста. Каскад:
  trafilatura → ru-fetch(+trafilatura) → snippets(DDG+GN RSS) → Tavily(платно).
  Каждый tier проверяет `_is_block_page` (Cloudflare/WAF). Это «чистая» версия
  того же каскада, что встроен в `r1_prefetch.py::fetch_one`.

- **`kb_db.py`** — соединение SQLite (WAL-режим), идемпотентная инициализация
  схемы + миграции (`_kb_init`), проверки прав (`_kb_can_read/upload/moderate`),
  сериализация строки в dict. Виртуальная таблица `kb_fts` (FTS5) для поиска.

- **`kb_ingest.py`** — извлечение текста из файлов (PDF/DOCX/TXT/MD) и URL,
  вставка в `kb_docs`, фоновый enrichment через LLM-агента (TLDR + summary +
  авто-теги). Перед enrichment подтягивает inline-URL из текста
  (`_resolve_inline_urls`), чтобы дать модели контекст без браузер-инструмента.

- **`news_state.py`** — состояние новостей в едином JSON-файле с in-process
  блокировкой: реакции (лайк/дизлайк), заметки, закладки, чат по статье, кэш
  полного текста статьи и кэш саммари.

- **`llm_agent.py`** — **ключевая точка интеграции с LLM**. Содержит парсеры
  вывода `openclaw agent --json` (`_extract_reply` достаёт текст ответа,
  `_parse_first_json_object` находит сбалансированный JSON в выводе),
  языковую подсказку `LANG_RU_HINT` и server-side очистку «утечек» внутренних
  правил из ответа (`_scrub_agent_reply`).

---

## 4. insights/ — слой генерации инсайтов

```
orchestrator.py  (очередь задач: SQLite jobs/job_events, приоритеты, ретраи)
      ▲ register_kind("insights_regen", _run_insights_job, serial=True)
      │
routes_insights.py
   ├── _collect_new_docs_for_insights()  ← новости из archives + материалы из kb_docs
   ├── _build_insights_prompt()          ← большой промпт «продуктовый аналитик»
   ├── subprocess(openclaw agent)        ← LLM-агент → JSON-гипотезы
   ├── _validate_and_store()             ← валидация, dedup-защита, запись в kb_hypotheses
   └── lifecycle endpoints               ← жизненный цикл гипотез (synthesized→…→archived)

routes_kb.py     (API базы знаний: upload/text/url/list/search/approve/delete)
template_insights.py  (HTML-страница инсайтов — UI, отдаётся как строка)
```

- **`orchestrator.py`** — асинхронная очередь фоновых задач на SQLite. Приоритет
  по тарифу пользователя (admin > premium > basic), FIFO внутри тарифа; глобальный,
  per-user и per-kind лимиты конкуренции (семафоры); ретраи с экспоненциальной
  задержкой (`TransientError`); восстановление прерванных задач после рестарта
  (`_recover_interrupted`). Подробно — в `docs/insights.md`.

- **`routes_insights.py`** — собирает источники, строит промпт, вызывает агента,
  валидирует и сохраняет гипотезы, реализует жизненный цикл и API для UI.

- **`routes_kb.py`** — CRUD базы знаний (материалов): загрузка файла/текста/URL,
  список с модерацией, полнотекстовый поиск (FTS5), approve/delete.

- **`template_insights.py`** — единственная UI-часть в репозитории: одна большая
  строка-константа `INSIGHTS_HTML` (~1.9k строк HTML/CSS/JS, светлая/тёмная тема,
  фильтры, drawer, граф связей между гипотезами). Логики нет — только разметка,
  плейсхолдеры (`__USER__`, `__CANUPLOAD__` …) подставляются в роутере.

---

## 5. Где проходят границы (швы для адаптации)

- **LLM**: `subprocess([OPENCLAW, "agent", ...])` — в `r1_summarize_finals.py`,
  `kb_ingest.py`, `routes_insights.py`. Парсинг — `core/llm_agent.py`.
- **Anti-bot fetch**: бинарь `ru-fetch` (`RU_FETCH_BIN`) — в `r1_fetch_urls.py`,
  `r1_prefetch.py`, `article_fetch.py`. Не входит в репозиторий.
- **Внешний веб-слой**: `from web_app import ...` в роутерах — это импорты из
  основного приложения, которого тут нет.
- **Пути/файлы**: абсолютные пути `/opt/newsapp/...` — захардкожены, вынести в конфиг.
