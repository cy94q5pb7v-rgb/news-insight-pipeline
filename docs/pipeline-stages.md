# Этапы новостного конвейера — подробно

Это сердцевина системы. Ниже — каждый этап и подэтап: что делает, вход/выход,
какой файл и функция отвечает. Особое внимание — скорингу доверия (`trust_score`),
релевантности, классификации тем, дедупу и присвоению рейтингов.

---

## Этап 1. Сбор стабов (candidate stubs)

**Файл:** `pipeline/r1_fetch_urls.py` · функция `collect_stubs(mode)`
**Вход:** поисковые запросы, зашитые в коде (`QUERIES`, `GOOGLE_FRESH_QUERIES`,
`YANDEX_QUERIES`, `TIER1_FEEDS`, `RU_SCRAPE_PAGES`).
**Выход:** список стабов `{title, url, source, query, pub}`.

Источники собираются раздельными «режимами» (`mode`), чтобы разнести нагрузку по
разным cron-job'ам (на VPS с 1.9 ГБ RAM долгий скрипт ронял gateway):

| mode | Источник | Время | Примечание |
|---|---|---|---|
| `collect` | Google News RSS (узкие RU-запросы) + Direct RSS tier-1 | ~15с | без браузера |
| `google` | Google News «свежие темы» (when:3d, EN+RU) | ~80с | авто-локаль по кириллице |
| `yandex` | SearXNG (мета-поиск, ~160 запросов) | ~5 мин | health-check + circuit breaker |
| `scrape` | Прямой HTML-scrape RU travel-сайтов | ~25с | per-domain CSS-селекторы |
| `all` | всё сразу (legacy) | ~150с | не для прода |

**Подэтапы внутри сбора:**

- **Google News** (`_gn_url`): определяет язык запроса по кириллице → выбирает
  локаль `hl=ru&gl=RU` или `hl=en-US&gl=US` (иначе RU-локаль возвращает ~0
  результатов на EN-запросы). Парсит RSS через `xml.etree`. Берёт топ
  `GOOGLE_NEWS_TOP_N` (25) items на запрос.
- **Direct RSS** (`TIER1_FEEDS`): ~60 проверенных фидов (Reuters/Skift/RBC/
  Vedomosti/Habr/banki.ru/…). Поддерживает и RSS, и Atom. Лимит
  `TIER1_FEED_LIMIT` (15) на фид.
- **SearXNG** (`searxng_search`): JSON-API self-hosted мета-поисковика. Выбор
  подмножества движков по языку запроса (`_detect_query_lang_and_kind`): RU →
  yandex+ddg+bing, EN → ddg+bing+brave, `site:`-запросы — по TLD домена. Cap 2
  результата на хост, чтобы один источник не залил выдачу. Защита VPS:
  health-check перед фазой, бюджет времени 360с, circuit breaker (25 подряд
  пустых результатов = движки троттлят, стоп), задержка между запросами.
- **HTML-scrape** (`scrape_news_page`): urllib → при неудаче ru-fetch (RU-IP
  через xray, для geo-blocked сайтов). Парсинг — BS4 с per-domain CSS-хинтами
  (`DOMAIN_LINK_SELECTORS`), fallback на regex. SPA-хосты сразу идут через
  ru-fetch `--browser`.

**Свежесть** (`_is_fresh`, `FRESHNESS_HOURS=24`): для RSS/Google News
отбрасываются items старше 24ч по `pubDate`. Если даты нет — оставляем (лучше
лишнее, чем потерять валидное).

---

## Этап 2. Фильтр по форме URL и по теме

Применяется внутри `push()` (замыкание в `collect_stubs`) к каждому стабу до
дедупа.

### 2a. Фильтр формы URL — `_is_bad_url_shape(url)`

Отрезает landing/product/promo/login-страницы, которые поисковики возвращают как
«новости» (`sber.ru/travel/`, `alfabank.ru/.../alfa-travel-premium/`). Логика по
коду:

1. **Hard-block** соцсетей/login по хосту (`URL_BAD_HOST_RE`: tiktok, instagram,
   vk, t.me, dzen и пр.).
2. **Корневая страница** без пути — drop.
3. **Per-domain правило** для RU travel-trade сайтов (`NEWS_PATH_REQUIRED_HOSTS`):
   считается статьёй только URL с `/news/`, `/press/`, `/article/` и т.п.
   (`NEWS_PATH_RE`). Иначе — секция-навигация, drop.
4. **Жёсткое правило для банков** (`BANK_HOSTS_FOR_STRICT`): принимается только
   `/press/` или `/news/` (`BANK_NEWS_PATH_RE`) — `/blog/`, `/story/` у банков
   это маркетинг/продукт, drop.
5. **Whitelist-override** (`URL_NEWS_WHITELIST_RE`): если в пути есть
   `/news/`, `/press/`, `/20YY/MM/DD/` и т.п. — пропускаем, даже если ниже что-то
   совпало бы с blacklist.
6. **Top-level landing** (`/travel/`, `/everyday/`), **path-blacklist**
   (`/cards/`, `/promo/`, `/login/`…), **travel-product-page**
   (`sber-travel`, `alfa-travel-premium`) — drop.

### 2b. Тематический фильтр — `_is_travel_topic(title)`

Требует **хотя бы один travel-сигнал** в заголовке (`TRAVEL_RE` — огромная
регулярка: туризм/отели/авиа/аэропорты/booking/loyalty/визы/OTA/бренды
авиакомпаний и отелей). Без travel-сигнала — drop. Это отсекает «чистый банкинг»
(прибыль Сбера), «чистый AI» (релиз GPT-5), спорт/политику.

Финальное решение по категории (travel + banking и/или AI) принимается позже —
на стадии классификации (этап 6).

---

## Этап 3. Разрешение редиректов

**Функция:** `resolve_redirect(url, allow_browser)` (+ `_decode_gnews_url`,
`resolve_via_browser`).

Google News прячет URL издателя в base64 внутри пути `/rss/articles/<...>`.
Стратегия (от дешёвого к дорогому):

1. **Локальный base64-декод** (`_decode_gnews_url`) — старый формат GN-URL, без
   сети.
2. **`googlenewsdecoder`** (batchexecute API) — новый HMAC-формат, без браузера
   (критично для VPS). Кэш 24ч.
3. **HTTP-redirect follow** через urllib.
4. **Браузер** (`resolve_via_browser` через `ru-fetch --browser --head`) —
   только если `allow_browser=True` (по умолчанию выключено в prod-режимах,
   чтобы не плодить Chromium). Защищён семафором `_BROWSER_LOCK` (1 Chromium за
   раз). Результаты кэшируются на 24ч (`/tmp/r1_url_cache.json`).

Если GN-URL так и не разрешился — стаб отбрасывается.

---

## Этап 4. Скоринг доверия источника — `trust_score`

**Функция:** `_trust_score(url)` поверх словаря `TRUST_REGISTRY`.

`trust_score ∈ [0.10 … 1.00]` присваивается **по домену** разрешённого URL:

| Балл | Категория источника |
|---|---|
| 1.00 | регулятор + tier-1 деловая пресса (Reuters/FT/RBC/Vedomosti), официальные пресс-релизы банков, корпоративные сайты авиа/отелей/платёжных сетей |
| 0.85 | крупные новости (RIA/TASS/BBC/CNBC), tier-1 travel-trade (Skift/PhocusWire), финтех-trade (Finextra/PYMNTS), официальные каналы авиакомпаний |
| 0.70 | RU travel-trade (ratanews/atorus/tourdom/frequentflyers), регион. бизнес-пресса |
| 0.50 | агрегаторы (Yahoo Finance), региональные новости |
| 0.30 | тех-блоги, Medium, vc.ru, habr (UGC, но модерируемый) |
| 0.15 | форумы, UGC (reddit, hacker news, tripadvisor) |
| 0.10 | неизвестный домен / нет совпадения |

Механика поиска: нормализация хоста (`_domain` снимает `www.`, `m.`, `amp.`,
`ru.`, `en.`), точное совпадение в реестре, затем «прогулка по суффиксу»
(`a.b.com` → `b.com` → `com`). Зеркало реестра живёт в `core/archives.py`
(`_TRUST_REGISTRY` + `_score_url`) для on-the-fly скоринга на стороне веб-слоя и
ретроспективного бэкфилла (`_ensure_trust`).

`trust_score` дальше управляет поведением: текст извлекается только при `score ≥
0.30`; Tavily (платный tier) вызывается только при `trust ≥ 0.50`; финальная
сортировка кандидатов — по `(trust_score, длина текста)` убыванием, cap 200.

---

## Этап 5. Извлечение текста статьи

**Функция:** `fetch_text(url)` (в `r1_fetch_urls.py`) и более полный каскад
`fetch_article_text` (в `core/article_fetch.py`) / `fetch_one`
(в `r1_prefetch.py`).

Каскад (от бесплатного к платному, каждый tier проверяет `_is_block_page` —
строки Cloudflare/WAF не должны утечь в текст):

1. **Tier 1 — trafilatura** (`_fetch_via_trafilatura`): чистый Python, хорош на
   JS-heavy современных новостных сайтах.
2. **Tier 2 — ru-fetch** (`_fetch_via_bypass` / `_fetch_via_ru_fetch`): через
   SOCKS5/xray-прокси с RU-IP (для geo-blocked RU-доменов и SPA с
   browser-fallback), затем trafilatura/BS4 на полученном HTML.
3. **Tier 4 — snippets** (`_fetch_via_snippets`): агрегатор сниппетов из
   DuckDuckGo HTML + Google News RSS description. Бесплатный «дешёвый текст»,
   когда прямой fetch не пробился. Если набралось ≥800 символов — не эскалируем
   на платный Tavily.
4. **Tier 5 — Tavily Extract** (`_fetch_via_tavily`): платный API. basic
   (1 credit) → advanced (2 credits). Multi-key failover, обработка rate-limit
   (бэкофф) vs quota-exhausted (смена ключа), per-run cap, проверка квоты с
   TTL-кэшем. Только для `trust ≥ 0.50`.

Ключи Tavily загружаются из нескольких источников по приоритету: файл
`.tavily_keys` → env-переменные `TAVILY_API_KEY[_N]` → legacy-файл → парсинг
`trendwatch_env.sh` (`_tavily_api_keys`).

Очистка HTML (`_strip_html`): BS4 берёт только семантический контент
(`h1-h4, p, li, blockquote`), удаляя `script/style/nav/header/footer/aside` и
блоки с классами `menu/nav/sidebar/cookie`. Анти-бот детект на чистом тексте
(`ANTIBOT_MARKERS_RE`) — заблокированные страницы возвращают пустую строку.

**`r1_prefetch.py`** запускается отдельным cron-шагом между сбором и
суммаризацией: добивает items с пустым `article_text` тем же каскадом (2 worker'а,
wall-budget ~28 мин, sequential Chromium ~200 МБ). Результат кэшируется в
`news_state.json` (`_persist_articles_to_news_state`), чтобы drawer на портале
открывался мгновенно.

---

## Этап 6. Классификация темы — детерминированно, без LLM

**Файлы:** `pipeline/r1_classify.py` (отдельный CLI-helper) и
`r1_fetch_urls.py::_classify_case_type` (та же логика inline).

Зачем без LLM: на стадии 2 LLM-агент «галлюцинировал AI-сигнал», чтобы засунуть
item в нужную категорию. Регулярки дают жёсткий контроль — `case_type` ставится
только при явном keyword-сигнале.

Логика (поиск в `title` + первых 1500 символах `article_text`):

```
has_travel  = TRAVEL_RE  совпала?
has_banking = BANKING_RE совпала?
has_ai      = AI_RE      совпала?

if not has_travel:                  → NONE   (drop — не наш кейс)
if has_ai and has_banking:          → "AI travel в банкинге"
elif has_ai:                        → "AI travel"
elif has_banking:                   → "Travel в банкинге"
else:                               → NONE   (чистый travel — отбрасываем)
```

Три целевые категории совпадают с тремя запросами пользователя:
1. «Travel в банкинге» (travel + banking),
2. «AI travel» (travel + AI),
3. «AI travel в банкинге» (travel + banking + AI).

В `resolve_one` есть тонкость: если текст ≥300 символов и классификатор ничего не
нашёл — item дропается; если текст короткий/пустой (fetch не удался) — item
оставляется с `case_type=None`, чтобы стадия 2 догрузила свежий текст и
переклассифицировала через `r1_classify.py`.

---

## Этап 6.5. Запись и слияние кандидатов

**Функция:** `resolve_one` (worker) → `merge_into_file` → `r1_urls.json`.

`resolve_one` для каждого стаба: разрешает URL → считает trust → извлекает текст
(если trust ≥ 0.30) → классифицирует case_type. Запускается пулом из
`RESOLVE_WORKERS` (4) потоков. `cap_by_diversity` ограничивает поток от одного
источника (round-robin по `source`, бюджет `CANDIDATE_BUDGET=320`).

`merge_into_file`: атомарный мёрж (запись во временный файл + rename), дедуп по
нормализованному URL (`_norm_url` снимает фрагмент и utm_*), сортировка по
`(trust_score, длина текста)`, cap 200, обрезка `article_text` до 800 символов в
финальном файле (чтобы не раздувать heap gateway при чтении).

---

## Этап 7. Суммаризация и присвоение рейтингов (LLM)

**Файл:** `pipeline/r1_summarize_finals.py`. **Вход:** `r1_news.json`.

> Важно по коду: `r1_news.json` (финальные отобранные items с `relevance_score`,
> `relevance_reason`, `bank_applicability_reason`, `title_ru`, `case_type`)
> производится **стадией R1-LLM, которой нет в этом репозитории**. То есть
> «рейтинги релевантности» (relevance/applicability) присваивает та стадия;
> `r1_summarize_finals.py` отвечает только за `summary_ru`.

Алгоритм:

1. Найти items с пустым `summary_ru` и `trust_score ≥ MIN_TRUST` (=0.0 — покрытие
   100%).
2. Для каждого — догрузить `article_text` каскадом `r1_prefetch.fetch_one`
   (опционально 5-й tier «webwright» — браузер-агент, по умолчанию выключен:
   `MAX_WEBWRIGHT_CALLS=0`).
3. Собрать batch (даже items без текста — у них fallback-summary строится из
   `title` + `relevance_reason` + `bank_applicability_reason`).
4. Один прогон LLM-агента (`openclaw agent`, изолированная сессия) с большим
   промптом: правила перевода англицизмов на русский, структура summary (3-5
   предложений, 400-700 символов, без рекомендаций/мета-комментариев), запрет
   выдумывать цифры. Агент пишет результат в `r1_summarize_output.json`.
5. Слить summary обратно в `r1_news.json` (атомарно, только summary ≥200 символов).

«Присвоение рейтингов» в терминах пользователя складывается из двух источников:
- **`trust_score`** — детерминированно на этапе 4 (по домену);
- **`relevance_score` / `bank_applicability`** — на стадии R1-LLM (вне репо),
  переносятся в архив через `UPDATABLE_FIELDS` в `core/archives.py`.

---

## Этап 8. Дедупликация и накопление в архив

**Файлы:** `core/dedupe.py` + `core/archives.py`.

`_accumulate_travel_archive` (`archives.py`):

1. Загрузить архив, прогнать near-dup прунинг существующих items
   (`_prune_near_dups` по `title_ru`).
2. Ретроспективно дополнить поля у уже существующих items из свежего
   `r1_news.json` (`UPDATABLE_FIELDS`: summary_ru, relevance_score,
   relevance_reason, trust_origin, is_event_news, bank_applicability…).
3. Сгруппировать входящие по `story_group` (смысловая группировка из стадии 2);
   в группе оставить primary с макс. trust, остальные прикрепить как `dup_sources`.
4. Для каждого нового item: проверить exact-дубль по хэшу и near-dup по заголовку
   (`_find_near_dup_title` в окне 5 дней), иначе добавить с полным набором полей.

**Дедуп-механика** (`dedupe.py`): `_title_tokens` строит множество значимых слов
(без стоп-слов и однобуквенных), `_title_similarity` — Jaccard (пересечение /
объединение). Порог 0.7. Дубликаты **не теряются** — копятся в `dup_sources`
(источник, URL, trust, дата).

packages-архив (`_accumulate_packages_archive`) строится отдельно — из
Telegram-дайджеста (jsonl-логи прогонов), парсит строки новостей регуляркой
`_DIGEST_ITEM_RE`, бэкфилл за `PACKAGES_BACKFILL_DAYS` (7) дней.

---

## Этап 9. Загрузка в БД портала

**Файлы:** `core/kb_db.py` (схема/доступ) + `insights/routes_insights.py`
(`_upsert_news_snapshot` пишет новости в `kb_news_items`).

Новости из архивов попадают в таблицу `kb_news_items` снимком при генерации
инсайтов (чтобы гипотезы могли ссылаться на конкретные новости как на источники).
Материалы (PDF/DOCX/URL) грузятся через `core/kb_ingest.py` в `kb_docs` +
FTS-индекс `kb_fts`. Полная модель данных — в `docs/data-model.md`.

---

## Служебные скрипты (вне основного пути)

- **`r1_news_watchdog.py`** — read-only сторож. Раз в день проверяет свежесть
  `r1_news.json`: если пусто или старше `STALE_HOURS` (20) — Telegram-алерт; если
  ≥50% items без `summary_ru` — отдельный алерт (prefetch не отработал).
- **`r1_evening_check.py`** — вечерний отчёт: триггерит накопление через запрос к
  работающему веб-приложению, считает прирост за вечер, шлёт сводку в Telegram.
- **`r1_collect_prefetch.sh`** — bash-обёртка под `flock` (защита от параллельного
  запуска): `r1_fetch_urls.py --mode=collect && r1_prefetch.py`.
