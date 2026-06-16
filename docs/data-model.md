# Модель данных

Хранилище — **SQLite**. Схема в `schema/schema.sql` (извлечённая, без данных).
Боевая схема создаётся идемпотентно функцией `_kb_init` в `core/kb_db.py` с
in-place миграциями — поэтому в реальной БД присутствуют ещё несколько таблиц
(`kb_fts`, `kb_feedback`, `kb_feedback_comments`) и индексов, которых нет в
`schema.sql`. Ниже разобраны таблицы из `schema.sql` плюс отмечены те, что
добавляются миграцией.

> Соглашения: первичные ключи — TEXT (`uuid4().hex[:16]` или хэши). Даты — TEXT в
> ISO-8601 (UTC). Булевы — INTEGER 0/1. Связь гипотез с источниками — M:N через
> таблицу-связку.

---

## kb_news_items — снимок новостей-источников

Снимок новостей, на которые могут ссылаться гипотезы (пишется при генерации
инсайтов через `_upsert_news_snapshot`, `INSERT OR REPLACE`).

| Поле | Назначение |
|---|---|
| `id` (PK) | id вида `news:<hash16>` (хэш URL) |
| `title` | заголовок (русский, `title_ru` из архива) |
| `summary` | саммари (`summary_ru`) |
| `url` | ссылка на статью |
| `source` | источник (домен или имя издателя) |
| `origin` | `travel` или `packages` — из какого архива |
| `case_type` | тип кейса («AI travel в банкинге» и т.п.) |
| `collected_at` | когда собрана |

Связи: на `kb_news_items.id` ссылается `kb_hypothesis_sources.doc_id` (когда
источник — новость).

---

## news_summaries — журнал суммаризаций

(В `schema.sql` присутствует; в коде репозитория напрямую не используется —
по-видимому, обслуживается стадией/эндпоинтом вне этого среза. Структура —
журнал асинхронных задач суммаризации.)

| Поле | Назначение |
|---|---|
| `article_id` (PK) | id статьи |
| `kind` | тип суммаризации |
| `title`, `url`, `source` | метаданные статьи |
| `status` | статус задачи |
| `summary` | результат |
| `error` | текст ошибки |
| `created_by`, `cancelled_by` | кто создал/отменил |
| `created_at`, `updated_at` | временные метки |

---

## kb_hypotheses — гипотезы/инсайты (центральная таблица)

| Поле | Назначение |
|---|---|
| `id` (PK) | `uuid4().hex[:16]` |
| `statement` | наблюдение + интерпретация (что произошло и что это значит) |
| `rationale` | импликация + обоснование (что делать и почему) |
| `category` | строго одна из: `ПУ/подписки`, `Travel`, `UX/UI` |
| `confidence` | REAL [0..1] — уверенность модели |
| `validated` | 1, если `confidence > 0.9` |
| `evidence_count` | число источников-подтверждений |
| `created_at` | дата создания |
| `run_id` | id прогона, который её произвёл (→ `kb_insight_runs.id`) |
| `source_kind` | `material` / `news` / `mixed` (по типу источников) |
| `lifecycle_status` | стадия: synthesized/in_review/validated/adopted/archived |
| `owner_username` | владелец (для in_review→validated→adopted) |
| `next_check_at` | дата следующей проверки (для «просроченных») |
| `lifecycle_updated_at` | когда менялся жизненный цикл |

Поля после `run_id` (от `source_kind`) добавлены миграцией — в `schema.sql` видны
в `ALTER`-подобной форме на одной строке.

Связи: 1 гипотеза → много строк в `kb_hypothesis_sources`. `run_id` →
`kb_insight_runs`.

---

## kb_hypothesis_sources — связка гипотеза↔источник (M:N)

| Поле | Назначение |
|---|---|
| `hypothesis_id` | → `kb_hypotheses.id` |
| `doc_id` | → `kb_docs.id` (материал) **или** `kb_news_items.id` (новость, префикс `news:`) |
| `excerpt` | дословная цитата ≤220–400 символов, подтверждающая наблюдение |
| `is_origin` | 1, если это первичный источник инсайта |
| PK | `(hypothesis_id, doc_id)` |

Это «доказательная база» гипотезы. По общим `doc_id` строится граф связей между
гипотезами (общий источник = ребро).

---

## kb_insight_runs — журнал прогонов генерации

| Поле | Назначение |
|---|---|
| `id` (PK) | id прогона (`uuid4().hex[:12]`) |
| `started_at`, `finished_at` | начало/конец |
| `status` | `running` / `done` / `error` / `ok` |
| `author` | кто запустил |
| `docs_total` | сколько документов проанализировано |
| `hypotheses_total` | сколько гипотез предложено |
| `validated_total` | сколько прошло порог валидации |
| `error` | текст ошибки |

Используется для определения «новизны» гипотез (`_latest_run_started_at`) и для
отображения статуса последнего прогона в UI.

---

## kb_insight_docs — реестр обработанных документов

| Поле | Назначение |
|---|---|
| `doc_id` (PK) | id материала или новости |
| `first_run_id` | прогон, который впервые его обработал |
| `processed_at` | когда |

Обеспечивает **инкрементальность**: при повторной генерации анализируются только
документы, которых здесь ещё нет. При миграции бэкфилится из существующих
источников гипотез (`legacy-backfill`).

---

## kb_docs — материалы базы знаний

Загруженные пользователями документы (PDF/DOCX/TXT/MD/URL/текст), из которых
(вместе с новостями) генерируются инсайты.

| Поле | Назначение |
|---|---|
| `id` (PK) | `uuid4().hex[:16]` |
| `title` | заголовок |
| `source_type` | `file` / `text` / `url` / `news` |
| `source_ref` | имя файла или URL |
| `file_ext`, `mime`, `size` | метаданные файла |
| `content` | извлечённый текст (обязательное) |
| `tags` | пользовательские теги (CSV) |
| `author` | загрузивший |
| `created_at`, `updated_at` | временные метки |
| `summary` | LLM-саммари (enrichment) |
| `auto_tags` | авто-теги от LLM (CSV) |
| `tldr` | одно предложение-суть |
| `enrichment_status` | `pending` / `done` / `error` / `cancelled` |
| `enrichment_error` | текст ошибки enrichment |
| `moderation_status` | `pending` / `approved` |
| `approved_by`, `approved_at` | кто/когда одобрил |

Поля от `summary` и далее — добавлены миграцией. Связи: `kb_docs.id` ↔
`kb_hypothesis_sources.doc_id`; параллельно ведётся FTS-индекс `kb_fts`.

---

## Таблицы, добавляемые миграцией (нет в schema.sql)

Создаются в `core/kb_db.py::_kb_init`:

- **`kb_fts`** — виртуальная таблица FTS5 (`unicode61 remove_diacritics`) для
  полнотекстового поиска по материалам (`id, title, content, tags`).
- **`kb_feedback`** — обратная связь пользователей (текст, статус, AI-оценка
  приоритета через агента).
- **`kb_feedback_comments`** — комментарии к обратной связи.
- Очередь оркестратора (**`jobs`**, **`job_events`**) создаётся отдельно в
  `insights/orchestrator.py::ensure_schema` — она про фоновые задачи, не про
  контент.

---

## Карта связей (упрощённо)

```
kb_insight_runs ──run_id──┐
                          ▼
kb_docs ──────doc_id────► kb_hypothesis_sources ──hypothesis_id──► kb_hypotheses
kb_news_items ─doc_id────►        (M:N)                                  │
   ▲                                                                     │
   └──(снимок при генерации)                          kb_insight_docs ◄──┘ (что обработано)
```
