"""Insights routes: hypotheses page, data, regenerate, drawer — and the insights_regen handler."""
import json
import sqlite3
import subprocess
import uuid
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import orchestrator
from templates import INSIGHTS_HTML, FEEDBACK_WIDGET_HTML
from web_app import (
    _require_auth, _compat_status, _kb_conn, _kb_require_read, _kb_require_upload,
    _kb_can_upload, _kb_can_moderate, _load_travel_archive, _load_packages_archive,
    _extract_reply, OPENCLAW, AGENT_ID, LANG_RU_HINT,
    _title_similarity, _find_user,
)

router = APIRouter()


INSIGHTS_DOC_CHARS = 2400
INSIGHTS_MAX_DOCS = 60
INSIGHTS_MIN_CONF = 0.9
INSIGHT_CATEGORIES = ("ПУ/подписки", "Travel", "UX/UI")
CATEGORY_TO_SECTION = {"ПУ/подписки": "packages", "Travel": "travel", "UX/UI": "uxui"}
SECTION_TO_CATEGORY = {v: k for k, v in CATEGORY_TO_SECTION.items()}
INSIGHTS_PROMPT_MAX = 180_000
INSIGHT_NEW_WINDOW_HOURS = 72

# ── Insight Lifecycle ───────────────────────────────────────────────────────
LIFECYCLE_STATUSES = ("synthesized", "in_review", "validated", "adopted", "archived")
PROTECTED_STATUSES = ("in_review", "validated", "adopted")

# Whitelist of allowed transitions through UI. validated → in_review is intentionally
# absent (only admin SQL); synthesized → validated requires going through in_review.
ALLOWED_TRANSITIONS = {
    "synthesized": ("in_review", "archived"),
    "in_review":   ("validated", "archived", "synthesized"),
    "validated":   ("adopted", "archived"),
    "adopted":     ("archived",),
    "archived":    ("synthesized",),  # only with confirm:true
}

LIFECYCLE_DEDUP_THRESHOLD = 0.7  # Jaccard similarity for regen-protection


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_overdue(next_check_at: str | None) -> bool:
    if not next_check_at:
        return False
    return next_check_at[:10] <= _today_iso()


def _allowed_transitions(current: str) -> list[str]:
    return list(ALLOWED_TRANSITIONS.get(current or "synthesized", ()))


def _is_admin(username: str) -> bool:
    u = _find_user(username) or {}
    return bool(u.get("is_admin"))

INSIGHTS_PROMPT = """\
Ты — продуктовый аналитик для команды премиального розничного блока банка Сбер (СберПервый, премиум-карты, travel-привилегии для премиального клиента). На входе — подборка материалов: стратегические отчёты Сбера, исследования рынка (Frank RG и т.п.), новостные заметки о банках и travel-сервисах в мире. На выходе — инсайты, которые продуктовая команда сразу может использовать в дискавери, бенчмарках и формулировании гипотез для тестирования.

═══════════════════════════════════════════════════════════════════
ИССЛЕДОВАТЕЛЬСКАЯ РАМКА — держи её в голове при чтении
═══════════════════════════════════════════════════════════════════

Главный вопрос:
«Какие сдвиги на мировом и российском рынке премиум-банкинга, travel-привилегий и AI-сервисов в финансах команда премиум-блока Сбера может переносить, тестировать или учитывать в своём роадмапе?»

Подвопросы, которые формируют рамку извлечения инсайтов:
- Что меняется в составе премиум-пакета (привилегии, цены, пороги входа)?
- Какие travel-механики банков работают и почему (lounge, страхование, concierge, AI-помощники)?
- Какие новые product-форматы появляются (split payments, co-branded карты, multi-currency, AI-консьерж в приложении)?
- Какие сдвиги в поведении affluent-клиентов фиксируются (digital habits, ожидания от премиум)?
- Какие риски и ограничения для премиум-сегмента видны (compliance, geo-блокировки, ужесточение правил)?

Любой инсайт должен отвечать на одну из этих рамок — иначе это просто факт без бизнес-значимости.

═══════════════════════════════════════════════════════════════════
ФАКТ ≠ ИНСАЙТ
═══════════════════════════════════════════════════════════════════

ФАКТ: «Mastercard открыла Taste by Priceless lounges в Hong Kong и São Paulo» — это пересказ.

ИНСАЙТ: «Mastercard сдвигает lounge-привилегию от количественной метрики (сколько проходов) к качественной (бренд + еда + впечатление) — это означает, что в premium-сегменте конкуренция перемещается на качество в самой привилегии. Для премиум-блока Сбера, где сильная база ON·PASS / Mir Pass (900+ залов), это сигнал к тестированию брендированных pop-up зон в ключевых аэропортах вместо расширения количества проходов.»

Разница: инсайт = факт + что это значит для рынка + что с этим делать команде.

═══════════════════════════════════════════════════════════════════
МЫШЛЕНИЕ В 3 РОЛЯХ — Reader → Synthesizer → Critic
═══════════════════════════════════════════════════════════════════

Перед тем как написать каждый инсайт, мысленно пройди 3 этапа:

ЭТАП 1 (Reader) — извлеки атомарные факты
Пройди по материалам. Для каждой темы выпиши: что конкретно сказано (с цитатой). Не интерпретируй пока, только evidence.

ЭТАП 2 (Synthesizer) — найди неочевидное
Сгруппируй похожие факты из разных источников. Ищи:
- ПРОТИВОРЕЧИЯ: данные расходятся с расхожим мнением или между источниками
- ПАТТЕРНЫ: несколько игроков делают одно и то же — это уже сдвиг рынка
- НЕВЫСКАЗАННОЕ: что логически следует из суммы фактов, но прямо не сказано
- СДВИГ ДИНАМИКИ: не «сколько», а «почему изменилось» и «к чему ведёт»

ЭТАП 3 (Critic) — задай вопрос «и что с того?»
Для каждого кандидата спроси: что команде премиум-блока Сбера ДЕЛАТЬ с этим инсайтом? Если ответ — «никак, это просто факт» — выбрасывай. Импликация должна быть конкретной (поставить эксперимент / изучить кейс / сравнить с нашим продуктом / включить в roadmap-обсуждение).

═══════════════════════════════════════════════════════════════════
СТРУКТУРА КАЖДОГО ИНСАЙТА — 5 обязательных полей
═══════════════════════════════════════════════════════════════════

`observation` (1-2 предложения):
  Конкретный факт из источника с именами/числами/датами/географиями. Это то, что Reader извлёк.
  ✓ «Outpayce (подразделение Amadeus) и Hands In в 2026 запускают split payments несколькими картами в travel-чекауты, начиная с крупной ближневосточной авиакомпании»
  ✗ «Появляются новые платёжные механики» (без имён и чисел)

`interpretation` (1-3 предложения):
  Что этот факт означает для рынка/тренда. Это то, что Synthesizer вывел — связь с другими фактами, паттерн, неочевидное.
  ✓ «Industry players впервые на уровне инфраструктуры решают payment-friction в дорогих групповых travel-покупках, признавая что отказы по платежам отнимают до 40% таких сделок. Это паттерн «банк ≠ только эмитент карты, банк = инфраструктура travel-checkout»
  ✗ «Это важно для индустрии» (банальность)

`implication` (1-3 предложения):
  Что команде премиум-блока Сбера делать с этим. КОНКРЕТНО:
  - изучить кейс / поговорить с конкурентом / сделать deep-dive
  - сравнить с нашим текущим продуктом — где разрыв
  - поставить hypothesis-testing эксперимент (БЕЗ выдуманных сегментов и сроков)
  - включить в roadmap-обсуждение какой темы
  - сигнал к мониторингу (если ещё рано действовать)
  ✓ «Стоит изучить, как Outpayce и Hands In структурируют split-payments для travel-чекаута — это потенциальный белый ход для premium travel-агрегатора Сбера, где клиенты с дорогими групповыми поездками наверняка сталкиваются с теми же 40% отказов»
  ✗ «Это можно использовать» (нет конкретики)
  ✗ «Стоит провести A/B-тест на 5% клиентов СберПервого за 60 дней» (выдуманные сегменты и сроки)

`evidence_cite` — дословная цитата ≤220 символов из источника, поддерживающая observation. Не перефразируй — копируй как есть.

`confidence` (0.3-0.95) — реальная уверенность в инсайте:
- 0.8-0.95: несколько источников с прямыми данными ИЛИ один источник с экспериментальными результатами
- 0.6-0.8: материал + новости подкрепляют, без жёстких данных
- 0.4-0.6: одиночный сигнал, паттерн не доказан
- 0.3-0.4: слабый сигнал, нужна валидация

═══════════════════════════════════════════════════════════════════
СВЯЗЬ С СУЩЕСТВУЮЩИМИ ПОЛЯМИ JSON
═══════════════════════════════════════════════════════════════════

Поле `statement` = observation + interpretation, склеенные в один связный текст.
Поле `rationale` = implication + кратко на чём основана интерпретация (вместе 2-4 предложения).

То есть финальный JSON — стандартный (как раньше), но содержание каждого поля чётко структурировано.

═══════════════════════════════════════════════════════════════════
ЯЗЫК — ЕСТЕСТВЕННЫЙ РУССКИЙ, БЕЗ АНГЛИЦИЗМОВ ГДЕ ЕСТЬ РУССКИЙ АНАЛОГ
═══════════════════════════════════════════════════════════════════

Аудитория — русскоязычные банковские специалисты, читают для оперативных решений. Текст должен звучать как от русскоязычного отраслевого аналитика, а не машинный перевод.

ОБЯЗАТЕЛЬНЫЕ ЗАМЕНЫ (не оставляй в латинице):
  AI / AI-агент / AI-консьерж → ИИ / ИИ-агент / ИИ-консьерж
  AI-powered / AI-first → на базе ИИ / с ИИ в основе
  voice-first / voice-native → голосовое управление / голосовой интерфейс
  voice queries → голосовые запросы
  cashless transport/payment → безналичный транспортный/платёжный (продукт)
  payment-friction / pain point → трение в платежах / болевая точка
  everyday payments → повседневные платежи
  premium-карта / premium-сегмент / premium-пакет → премиальная карта / премиум-сегмент / премиум-пакет (через кириллицу!)
  premium banking → премиальный банкинг
  airline experience → клиентский опыт авиапассажира
  customer experience (CX) → клиентский опыт
  customer journey → клиентский путь
  customer support → клиентская поддержка
  spend-gates → пороги по тратам
  travel-агрегатор / travel-партнёр / travel-чекаут → агрегатор путешествий / тревел-партнёр / оформление туристического заказа
  travel-карта / travel-страхование → карта для путешествий / страхование путешествий
  travel-MCC → travel-категории трат (MCC)
  loyalty-программа / loyalty-механика → программа лояльности / механика лояльности
  co-branded card → совместная карта
  multi-currency → мультивалютная
  frequent flyer → программа постоянного пассажира
  lounge-доступ → доступ в зал ожидания (lounge)
  hybrid touchpoints → гибридные точки контакта
  deep-dive → глубокое изучение / разбор
  inbound / outbound tourism → въездной / выездной туризм
  unit economics → юнит-экономика
  frontend / backend → витрина / внутренние процессы
  roadmap → дорожная карта (или роадмап в командном контексте)
  compliance → соответствие требованиям / комплаенс
  hospitality → гостеприимство / гостиничный сегмент
  affluent → состоятельный сегмент (или affluent — только в специальном контексте Frank RG)

МОЖНО ОСТАВЛЯТЬ ЛАТИНИЦЕЙ:
  Бренды: Visa, Mastercard, AmEx, Hilton, Booking.com, Expedia, Trip.com,
    Airbnb, Delta, United, Virgin Atlantic, OpenAI, ChatGPT, Anthropic, Claude,
    Google, Apple, Capital One, Chase, JPMorgan, Revolut, Wise, Klarna, Uber,
    Pegasus, Skift, Frank RG, Outpayce, Hands In, Amadeus, CarTrawler, FirstBank,
    Banca Intesa, Air Serbia, Ixigo, Tara, PASMO, Mir Pass, ON·PASS, NSPK,
    GigaChat-Travel и т.п.
  Технические аббревиатуры: API, ML, NLP, B2B, B2C, SaaS, MoU, LOI, MCC, eSIM, NPS, BNPL
  Русские бренды на русском: Сбер, СберПервый, СберПрайм, ВТБ, Альфа Премиум,
    Альфа Only, Газпром Бонус Премиум, ПСБ Orange Premium Club, Юнибанк, FrankRG.

ЗАПРЕЩЕНО:
- Смешивать кириллицу и латиницу в одном слове («AI-консьерж» — НЕТ, «ИИ-консьерж»;
  «travel-сегмент» — НЕТ, «сегмент путешествий»)
- Использовать слова без перевода если есть аналог в списке выше

САМОПРОВЕРКА перед отправкой каждого инсайта:
- Прошёл ли по списку обязательных замен? Нет ли смеси кириллицы и латиницы в одном слове?

═══════════════════════════════════════════════════════════════════
ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА (без них инсайт отсевают)
═══════════════════════════════════════════════════════════════════

КАЖДЫЙ инсайт должен:
- Содержать ≥2 элементов конкретики в observation: имя бренда / цифра / дата / география / конкретная механика (split payments, lounge, co-branded, multi-currency, MoU, MCC...)
- Иметь непустую implication длиной ≥60 символов, с указанием что КОНКРЕТНО делать
- Опираться на ≥1 реальный doc_id из подборки с дословной цитатой
- НЕ содержать выдуманных сегментов («с активами 3-10 млн ₽», «2+ поездки в год»), если их нет в источнике
- НЕ содержать выдуманных сроков («за 60 дней», «через 90 дней», «в течение квартала»), если их нет в источнике
- НЕ начинаться с «Сообщается», «По заголовку», «В материале»
- НЕ использовать штампы: уникальный, инновационный, революционный, передовой, синергия, бесшовный

ИМПЛИКАЦИЯ запрещена в формате:
✗ «Стоит изучить» (что именно?)
✗ «Можно использовать» (как и где?)
✗ «Это важно для команды» (нет действия)
✗ «Нужно мониторить» (что именно мониторить?)
✗ «Provider A/B-теста на 5% клиентов за N дней» (выдуманные параметры)

ИМПЛИКАЦИЯ должна:
✓ Назвать конкретное действие («изучить механику Х», «сравнить с нашим продуктом Y», «провести deep-dive с командой Z», «вынести на ближайший roadmap-комитет», «найти аналог в РФ»)
✓ Объяснить почему именно это действие следует из инсайта

═══════════════════════════════════════════════════════════════════
КОЛИЧЕСТВО
═══════════════════════════════════════════════════════════════════

Целевое: 18-25 инсайтов. Лучше 15 сильных, чем 25 с натяжкой.

Группируй близкие наблюдения в один инсайт. Если из 3 новостей виден один и тот же паттерн — один инсайт со ссылками на все 3 источника, не три отдельных.

═══════════════════════════════════════════════════════════════════
ПРИМЕРЫ ✅ ХОРОШИХ инсайтов
═══════════════════════════════════════════════════════════════════

ПРИМЕР 1:
{
  "statement": "Outpayce (подразделение Amadeus) и Hands In в 2026 запускают split payments несколькими картами в travel-чекауты авиакомпаний и туркомпаний, начиная с крупной ближневосточной авиакомпании. Industry впервые на уровне инфраструктуры решает payment-friction в дорогих групповых travel-покупках — признание, что отказы по платежам отнимают до 40% таких сделок.",
  "rationale": "Команде премиум-блока Сбера стоит изучить, как Outpayce и Hands In структурируют split-payments для travel-чекаута — это потенциальный белый ход для premium travel-агрегатора, где клиенты с дорогими групповыми поездками наверняка сталкиваются с теми же 40% отказов. Паттерн виден ещё у Expedia × Klarna и Booking × Affirm: travel становится отдельным payment-vertical, не обычным retail.",
  "category": "Travel",
  "confidence": 0.82
}

ПРИМЕР 2:
{
  "statement": "ПСБ с 01.06.2026 ужесточает Orange Premium Club: порог бесплатного обслуживания в Москве и МО растёт с 2 до 3 млн ₽, плата — с 3 500 до 3 990 ₽; в Private Banking с 01.05.2026 из программы лояльности убраны MCC туроператоров и медицины. Это контр-тренд: пока большинство банков расширяет travel-привилегии, ПСБ их сокращает в Private Banking и поднимает входной барьер в премиум.",
  "rationale": "Команде стоит вынести на ближайшее обсуждение продуктового комитета: рынок входа в премиум подтягивается вверх (3 млн ₽ как новая нижняя граница affluent у крупного игрока), и параллельно отдельные банки начинают резать категории travel в loyalty — нужно понять, видим ли мы у себя похожие сигналы в churn или active-base. Mastercard и FirstBank, наоборот, расширяют travel-привилегии — рынок раскалывается на два движения.",
  "category": "ПУ/подписки",
  "confidence": 0.85
}

ПРИМЕР 3:
{
  "statement": "Visa и Trip.com Group подписали MoU, где Trip.com становится global Anchor Partner программы Visa Destinations с интеграцией Visa Infinite в 200+ странах и фокусом на mainland China × APAC. Платёжная сеть оформляется как trusted-канал travel-discovery через CRM партнёра — модель «банк = полка curated премиальных впечатлений».",
  "rationale": "Стоит изучить структуру партнёрства Visa Destinations и понять, где Сбер мог бы быть либо anchor-партнёром через GigaChat-Travel, либо использовать аналогичную модель с travel-агрегатором на дружественных юрисдикциях. У FirstBank × Visa и Air Serbia × Banca Intesa виден тот же паттерн «банк + travel-партнёр = совместный лояльный продукт», но Visa Destinations — самый масштабный пример.",
  "category": "Travel",
  "confidence": 0.80
}

═══════════════════════════════════════════════════════════════════
ПРИМЕРЫ ❌ ПЛОХИХ инсайтов (так не пиши)
═══════════════════════════════════════════════════════════════════

❌ ПЕРЕСКАЗ без интерпретации и импликации:
"Mastercard открыла Taste by Priceless lounges в Hong Kong и São Paulo." — голый факт, нет «что с того».

❌ БАНАЛЬНОСТЬ без конкретики и без действия:
"Если приложение расширяется к сервисам всей поездки, то удерживает клиента." — общее место. Нет имён, цифр. Нет действия.

❌ ВЫДУМКА сегментов и сроков:
"У клиентов СберПервого с активами 3-10 млн ₽, 2+ зарубежными поездками в год запуск GigaChat-Travel увеличит активацию 3+ привилегий за первые 60 дней." — выдуманные критерии и сроки. Не от источника.

❌ ИМПЛИКАЦИЯ без конкретики:
"Стоит изучить этот тренд." (что именно? как? с кем?)

═══════════════════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА — строго один JSON-объект, без Markdown
═══════════════════════════════════════════════════════════════════

{
  "hypotheses": [
    {
      "statement": "[observation + interpretation, склеенные в 2-4 предложения]",
      "rationale": "[implication + что её поддерживает, 2-4 предложения]",
      "category": "ПУ/подписки",
      "confidence": 0.0,
      "sources": [
        {"doc_id": "abc123", "excerpt": "дословная цитата ≤220 символов", "is_origin": true},
        {"doc_id": "def456", "excerpt": "...", "is_origin": false}
      ]
    }
  ]
}

КАТЕГОРИЯ — строго одна из: ПУ/подписки, Travel, UX/UI.

МАТЕРИАЛЫ:
"""


@router.get("/kb/insights", response_class=HTMLResponse)
async def kb_insights_page(user: str = Depends(_require_auth)):
    _kb_require_read(user)
    can_upload = "true" if _kb_can_upload(user) else "false"
    can_mod = "true" if _kb_can_moderate(user) else "false"
    is_admin = _is_admin(user)
    init = (user[:1] or "·").upper()
    admin_item = ('<a class="ocu-item" href="/admin"><svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z\"/><path d=\"M9 12l2 2 4-4\"/></svg>Админка</a>') if is_admin else ""
    return HTMLResponse(
        INSIGHTS_HTML.replace("__USER__", user).replace("__CANUPLOAD__", can_upload)
                     .replace("__CANMOD__", can_mod).replace("__INIT__", init).replace("__ADMIN_ITEM__", admin_item)
                     .replace("__FEEDBACK_WIDGET__", FEEDBACK_WIDGET_HTML),
        headers={"Cache-Control": "no-store"},
    )


def _parse_iso(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _latest_run_started_at(c) -> str:
    """Started_at of the most recent FINISHED regeneration run; '' if none."""
    row = c.execute(
        "SELECT started_at FROM kb_insight_runs "
        "WHERE finished_at IS NOT NULL AND status='ok' "
        "ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return (row["started_at"] if row else "") or ""


def _is_new_for_run(created_at: str, latest_started_at: str) -> bool:
    """A hypothesis is 'new' iff it was created today (UTC) AND was produced by
    the most recent completed regeneration. The next successful regen drops the
    'new' flag from prior hypotheses automatically (they fail the started_at check)."""
    dt = _parse_iso(created_at)
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    if dt.date() != now.date():
        return False
    ref = _parse_iso(latest_started_at)
    if ref is not None and dt < ref:
        return False
    return True


# Back-compat shim — older callsites that haven't been refactored.
def _is_new_iso(created_at: str) -> bool:
    with _kb_conn() as c:
        ref = _latest_run_started_at(c)
    return _is_new_for_run(created_at, ref)


def _score_doc_quality(row) -> tuple[str, list[str]]:
    """Return (level, reasons). level in {'green','yellow','red'}."""
    reasons = []
    content = row["content"] or ""
    L = len(content)
    src = row["source_type"]
    if L < 200:
        reasons.append("короткий текст")
    if L < 60:
        return "red", reasons
    if src == "url" and not (row["source_ref"] or "").startswith(("http://", "https://")):
        reasons.append("ссылка не http")
    if src == "url" and L < 400:
        reasons.append("страница почти без контента")
    if reasons:
        return "yellow", reasons
    return "green", []


def _build_insights_prompt(docs: list[dict]) -> str:
    parts = [INSIGHTS_PROMPT]
    for d in docs:
        kind = d.get("kind") or "material"
        header = f"\n--- DOC id={d['id']} | kind={kind} | title={d['title']}"
        if d["source_ref"]:
            header += f" | source={d['source_ref'][:80]}"
        if d["tags"]:
            header += f" | tags={d['tags']}"
        header += " ---\n"
        parts.append(header)
        parts.append(d["content"])
    result = "".join(parts)
    if len(result) > INSIGHTS_PROMPT_MAX:
        result = result[:INSIGHTS_PROMPT_MAX] + "\n… [обрезано по лимиту]"
    return result


def _parse_insights_json(raw: str) -> dict | None:
    start = raw.find("{")
    while start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except json.JSONDecodeError:
                        break
        start = raw.find("{", start + 1)
    return None


def _normalize_category(raw: str) -> str:
    if not raw:
        return ""
    r = raw.strip().lower().replace("-", "/").replace(" / ", "/")
    if r in {"ui", "ux", "ux/ui", "ui/ux", "юзабилити", "интерфейс", "онбординг"}:
        return "UX/UI"
    if r in {"travel", "тревел", "путешествия", "путешествие"}:
        return "Travel"
    if r in {"пу/подписки", "пу", "подписки", "тарифы", "пакеты", "пакеты услуг", "премиум", "комиссии"}:
        return "ПУ/подписки"
    for cat in INSIGHT_CATEGORIES:
        if cat.lower() in r:
            return cat
    return ""


def _validate_and_store(run_id: str, parsed: dict, valid_doc_ids: set[str], *, append: bool) -> tuple[int, int]:
    hyps = parsed.get("hypotheses") or []
    proposed = 0
    validated = 0
    merged = 0  # Lifecycle-dedup merges (existing protected hyp got new sources)
    now = datetime.now(timezone.utc).isoformat()
    with _kb_conn() as c:
        # Protect hypotheses with active lifecycle from being clobbered by regen.
        # We read them BEFORE deletion so dedup can match against them.
        protected_rows = c.execute(
            "SELECT id, statement, category FROM kb_hypotheses "
            "WHERE lifecycle_status IN ('in_review','validated','adopted')"
        ).fetchall()
        protected_by_cat: dict[str, list] = {}
        for p in protected_rows:
            protected_by_cat.setdefault(p["category"] or "", []).append(p)
        protected_ids = [p["id"] for p in protected_rows]
        if not append:
            if protected_ids:
                qs = ",".join("?" * len(protected_ids))
                c.execute(
                    f"DELETE FROM kb_hypothesis_sources WHERE hypothesis_id NOT IN ({qs})",
                    protected_ids,
                )
                c.execute(
                    f"DELETE FROM kb_hypotheses WHERE id NOT IN ({qs})", protected_ids
                )
            else:
                c.execute("DELETE FROM kb_hypothesis_sources")
                c.execute("DELETE FROM kb_hypotheses")
        for h in hyps:
            stmt = (h.get("statement") or "").strip()
            rat  = (h.get("rationale") or "").strip()
            cat  = _normalize_category(h.get("category") or "")
            if not cat:
                continue
            try:
                conf = float(h.get("confidence") or 0)
            except Exception:
                conf = 0
            conf = max(0.0, min(1.0, conf))
            srcs = h.get("sources") or []
            seen = set()
            good_srcs = []
            for s in srcs:
                did = (s or {}).get("doc_id")
                if not did or did not in valid_doc_ids or did in seen:
                    continue
                seen.add(did)
                good_srcs.append({
                    "doc_id": did,
                    "excerpt": ((s.get("excerpt") or "")[:400]).strip(),
                    "is_origin": 1 if s.get("is_origin") else 0,
                })
            if not stmt or not good_srcs:
                continue
            proposed += 1
            is_valid = 1 if conf > INSIGHTS_MIN_CONF else 0
            if is_valid:
                validated += 1
            news_count = sum(1 for s in good_srcs if s["doc_id"].startswith("news:"))
            if news_count == len(good_srcs):
                source_kind = "news"
            elif news_count == 0:
                source_kind = "material"
            else:
                source_kind = "mixed"
            # Lifecycle dedup: if a protected hypothesis in the same category is
            # ≥0.7 Jaccard-similar by statement, merge new sources into it
            # instead of creating a duplicate. This preserves owner / status.
            match = None
            best_sim = 0.0
            for p in protected_by_cat.get(cat, []):
                sim = _title_similarity(stmt, p["statement"] or "")
                if sim > best_sim:
                    best_sim = sim
                    match = p
            if match and best_sim >= LIFECYCLE_DEDUP_THRESHOLD:
                for s in good_srcs:
                    c.execute(
                        "INSERT OR IGNORE INTO kb_hypothesis_sources "
                        "(hypothesis_id, doc_id, excerpt, is_origin) VALUES (?,?,?,?)",
                        (match["id"], s["doc_id"], s["excerpt"], s["is_origin"]),
                    )
                # Recount actual sources (OR IGNORE may have skipped duplicates).
                c.execute(
                    "UPDATE kb_hypotheses SET evidence_count = "
                    "(SELECT COUNT(*) FROM kb_hypothesis_sources WHERE hypothesis_id=?) "
                    "WHERE id=?",
                    (match["id"], match["id"]),
                )
                merged += 1
                continue  # don't insert a duplicate
            hid = uuid.uuid4().hex[:16]
            c.execute(
                "INSERT INTO kb_hypotheses (id, statement, rationale, category, confidence, "
                "validated, evidence_count, created_at, run_id, source_kind, lifecycle_status, "
                "lifecycle_updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (hid, stmt, rat, cat, conf, is_valid, len(good_srcs), now, run_id,
                 source_kind, "synthesized", now),
            )
            for s in good_srcs:
                c.execute(
                    "INSERT OR IGNORE INTO kb_hypothesis_sources "
                    "(hypothesis_id, doc_id, excerpt, is_origin) VALUES (?,?,?,?)",
                    (hid, s["doc_id"], s["excerpt"], s["is_origin"]),
                )
    print(f"[insights_regen] dedup: matched={merged} new={proposed - merged} protected={len(protected_ids)}")
    return proposed, validated


def _collect_news_for_insights() -> list[dict]:
    items: list[dict] = []
    try:
        tarch = _load_travel_archive()
    except Exception:
        tarch = {"items": []}
    for it in (tarch.get("items") or []):
        url = (it or {}).get("url") or ""
        title = (it or {}).get("title_ru") or ""
        if not url or not title:
            continue
        h = (it.get("article_hash") or "").strip()
        nid = "news:" + (h[:16] if h else hashlib.sha256(url.encode()).hexdigest()[:16])
        items.append({
            "id": nid, "title": title,
            "summary": (it.get("summary_ru") or "").strip(),
            "url": url, "source": it.get("source") or "",
            "origin": "travel", "case_type": it.get("case_type") or "",
            "collected_at": it.get("collected_at") or "",
        })
    try:
        parch = _load_packages_archive()
    except Exception:
        parch = {"items": []}
    for it in (parch.get("items") or []):
        url = (it or {}).get("url") or ""
        title = (it or {}).get("title") or ""
        if not url or not title:
            continue
        nid = "news:" + hashlib.sha256(url.encode()).hexdigest()[:16]
        items.append({
            "id": nid, "title": title, "summary": "",
            "url": url, "source": it.get("source") or "",
            "origin": "packages", "case_type": "",
            "collected_at": it.get("collected_at") or it.get("posted_at") or "",
        })
    seen = set()
    deduped = []
    for n in items:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        deduped.append(n)
    return deduped


def _upsert_news_snapshot(items: list[dict]) -> None:
    if not items:
        return
    with _kb_conn() as c:
        for n in items:
            c.execute(
                "INSERT OR REPLACE INTO kb_news_items "
                "(id, title, summary, url, source, origin, case_type, collected_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (n["id"], n["title"], n["summary"], n["url"], n["source"],
                 n["origin"], n["case_type"], n["collected_at"]),
            )


def _collect_new_docs_for_insights() -> tuple[list[dict], bool]:
    with _kb_conn() as c:
        processed = {r[0] for r in c.execute("SELECT doc_id FROM kb_insight_docs")}
        rows = c.execute(
            "SELECT id, title, source_type, source_ref, tags, content, created_at "
            "FROM kb_docs WHERE moderation_status='approved' "
            "ORDER BY created_at DESC LIMIT ?",
            (INSIGHTS_MAX_DOCS,),
        ).fetchall()
    is_first = not processed
    docs: list[dict] = []
    for r in rows:
        if not is_first and r["id"] in processed:
            continue
        content = (r["content"] or "").strip()
        if len(content) > INSIGHTS_DOC_CHARS:
            content = content[:INSIGHTS_DOC_CHARS].rstrip() + "…"
        docs.append({
            "id": r["id"], "title": r["title"],
            "source_type": r["source_type"], "source_ref": r["source_ref"] or "",
            "tags": r["tags"] or "", "content": content, "kind": "material",
        })
    news = _collect_news_for_insights()
    _upsert_news_snapshot(news)
    news.sort(key=lambda x: x.get("collected_at") or "", reverse=True)
    for n in news[:INSIGHTS_MAX_DOCS]:
        if not is_first and n["id"] in processed:
            continue
        body_parts = []
        if n.get("summary"):
            body_parts.append(n["summary"])
        if n.get("case_type"):
            body_parts.append("Тип: " + n["case_type"])
        body = "\n".join(body_parts).strip() or n["title"]
        if len(body) > INSIGHTS_DOC_CHARS:
            body = body[:INSIGHTS_DOC_CHARS].rstrip() + "…"
        docs.append({
            "id": n["id"], "title": n["title"],
            "source_type": "news", "source_ref": n["source"] or n["url"],
            "tags": ("news," + (n.get("origin") or "")).strip(","),
            "content": body, "kind": "news",
        })
    return docs, is_first


def _mark_docs_processed(run_id: str, doc_ids: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _kb_conn() as c:
        for did in doc_ids:
            c.execute(
                "INSERT OR IGNORE INTO kb_insight_docs (doc_id, first_run_id, processed_at) VALUES (?,?,?)",
                (did, run_id, now),
            )


def _run_insights_job(user: str, payload: dict, job_id: str) -> dict:
    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat()
    with _kb_conn() as c:
        c.execute(
            "INSERT INTO kb_insight_runs (id, started_at, status, author, docs_total) "
            "VALUES (?,?,?,?,?)",
            (run_id, started, "running", user, 0),
        )
    try:
        docs, is_first = _collect_new_docs_for_insights()
        if not docs:
            raise RuntimeError("Нет новых источников для анализа — все материалы и новости уже разобраны. Добавьте новые материалы или дождитесь свежих новостей и попробуйте снова.")
        valid_ids = {d["id"] for d in docs}
        new_materials = sum(1 for d in docs if d.get("kind") != "news")
        new_news = sum(1 for d in docs if d.get("kind") == "news")
        prompt = _build_insights_prompt(docs) + LANG_RU_HINT
        orchestrator.set_phase(job_id, "agent")
        session_id = f"insights-{run_id}"
        proc = subprocess.Popen(
            [OPENCLAW, "agent", "--agent", AGENT_ID, "--session-id", session_id, "--message", prompt, "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        orchestrator.track_process(job_id, proc)
        try:
            stdout, stderr = proc.communicate(timeout=900)
        except subprocess.TimeoutExpired:
            try: proc.kill()
            except Exception: pass
            raise RuntimeError("Агент не ответил за 15 минут")
        if proc.returncode != 0:
            raise RuntimeError(f"agent exit {proc.returncode}: {(stderr or '')[:400]}")
        reply, parse_err = _extract_reply(stdout)
        if parse_err and not reply:
            raise RuntimeError(parse_err)
        parsed = _parse_insights_json(reply)
        if not parsed or "hypotheses" not in parsed:
            raise RuntimeError("Агент не вернул валидный JSON с hypotheses")
        orchestrator.set_phase(job_id, "storing")
        proposed, validated = _validate_and_store(run_id, parsed, valid_ids, append=not is_first)
        _mark_docs_processed(run_id, list(valid_ids))
        finished = datetime.now(timezone.utc).isoformat()
        with _kb_conn() as c:
            c.execute(
                "UPDATE kb_insight_runs SET finished_at=?, status=?, docs_total=?, "
                "hypotheses_total=?, validated_total=? WHERE id=?",
                (finished, "done", len(docs), proposed, validated, run_id),
            )
        return {
            "run_id": run_id, "docs": len(docs),
            "new_materials": new_materials, "new_news": new_news,
            "proposed": proposed, "validated": validated,
            "incremental": not is_first,
        }
    except Exception as e:
        finished = datetime.now(timezone.utc).isoformat()
        try:
            with _kb_conn() as c:
                c.execute(
                    "UPDATE kb_insight_runs SET finished_at=?, status=?, error=? WHERE id=?",
                    (finished, "error", str(e)[:500], run_id),
                )
        except Exception:
            pass
        raise


orchestrator.register_kind(
    "insights_regen", _run_insights_job, timeout_s=960, serial=True, recover=False
)


@router.post("/kb/insights/regenerate")
async def kb_insights_regenerate(user: str = Depends(_require_auth)):
    _kb_require_upload(user)
    existing = await orchestrator.find_active(user, "insights_regen")
    if existing:
        return {"job_id": existing, "already_running": True}
    res = await orchestrator.submit(user, "insights_regen", {})
    return {"job_id": res["job_id"], "queue_pos": res.get("queue_pos")}


@router.get("/kb/insights/regenerate/status/{job_id}")
async def kb_insights_status(job_id: str, user: str = Depends(_require_auth)):
    return _compat_status(await orchestrator.get_status(job_id, user), expect_kind="insights_regen")


@router.get("/kb/insights/data", response_class=JSONResponse)
async def kb_insights_list(user: str = Depends(_require_auth), category: str = "", source: str = ""):
    wanted: str = ""
    if category:
        wanted = SECTION_TO_CATEGORY.get(category.strip().lower(), category.strip())
        if wanted not in INSIGHT_CATEGORIES:
            wanted = ""
    src_f = (source or "").strip().lower()
    if src_f not in {"material", "news", "mixed"}:
        src_f = ""
    with _kb_conn() as c:
        h_rows = c.execute(
            "SELECT * FROM kb_hypotheses ORDER BY validated DESC, evidence_count DESC, confidence DESC"
        ).fetchall()
        s_rows = c.execute("SELECT * FROM kb_hypothesis_sources").fetchall()
        run = c.execute(
            "SELECT * FROM kb_insight_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        latest_ok_started = _latest_run_started_at(c)
    hyp_sources: dict[str, set[str]] = {}
    for s in s_rows:
        hyp_sources.setdefault(s["hypothesis_id"], set()).add(s["doc_id"])

    def _derive_kind(hid: str, stored: str) -> str:
        if stored in {"material", "news", "mixed"}:
            return stored
        sids = hyp_sources.get(hid, set())
        if not sids:
            return "material"
        news_n = sum(1 for x in sids if (x or "").startswith("news:"))
        if news_n == 0:
            return "material"
        if news_n == len(sids):
            return "news"
        return "mixed"

    hypotheses = []
    source_counts = {"material": 0, "news": 0, "mixed": 0}
    for r in h_rows:
        cat = r["category"] or ""
        sk = _derive_kind(r["id"], (r["source_kind"] if "source_kind" in r.keys() else "") or "")
        source_counts[sk] = source_counts.get(sk, 0) + 1
        if wanted and cat != wanted:
            continue
        if src_f and sk != src_f:
            continue
        ec = len(hyp_sources.get(r["id"], set())) or int(r["evidence_count"] or 0)
        keys = r.keys()
        nca = (r["next_check_at"] if "next_check_at" in keys else "") or ""
        ls = (r["lifecycle_status"] if "lifecycle_status" in keys else "") or "synthesized"
        hypotheses.append({
            "id": r["id"], "statement": r["statement"], "rationale": r["rationale"],
            "category": cat, "section": CATEGORY_TO_SECTION.get(cat, ""),
            "confidence": float(r["confidence"] or 0), "validated": bool(r["validated"]),
            "evidence_count": ec, "created_at": r["created_at"] or "",
            "is_new": _is_new_for_run(r["created_at"] or "", latest_ok_started),
            "source_kind": sk,
            "lifecycle_status": ls,
            "owner_username": (r["owner_username"] if "owner_username" in keys else "") or "",
            "next_check_at": nca,
            "is_overdue": _is_overdue(nca),
        })
    edges = []
    ids = [h["id"] for h in hypotheses]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            shared = hyp_sources.get(ids[i], set()) & hyp_sources.get(ids[j], set())
            if shared:
                edges.append({"a": ids[i], "b": ids[j], "w": len(shared)})
    last_run = None
    if run:
        last_run = {
            "id": run["id"], "started_at": run["started_at"],
            "finished_at": run["finished_at"], "status": run["status"],
            "author": run["author"],
            "docs_total": int(run["docs_total"] or 0),
            "hypotheses_total": int(run["hypotheses_total"] or 0),
            "validated_total": int(run["validated_total"] or 0),
            "error": run["error"] or "",
        }
    cat_counts = {c: 0 for c in INSIGHT_CATEGORIES}
    for r in h_rows:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    return JSONResponse({
        "hypotheses": hypotheses, "edges": edges, "last_run": last_run,
        "can_regenerate": _kb_can_upload(user), "category": wanted,
        "category_counts": cat_counts, "categories": list(INSIGHT_CATEGORIES),
        "category_to_section": CATEGORY_TO_SECTION,
        "source_filter": src_f, "source_counts": source_counts,
    }, headers={"Cache-Control": "no-store"})


@router.get("/kb/insights/section/{section_id}", response_class=JSONResponse)
async def kb_insights_section(section_id: str, user: str = Depends(_require_auth), limit: int = 5):
    section_id = (section_id or "").strip().lower()
    cat = SECTION_TO_CATEGORY.get(section_id)
    if not cat:
        raise HTTPException(404, "unknown section")
    limit = max(1, min(20, int(limit or 5)))
    with _kb_conn() as c:
        rows = c.execute(
            "SELECT h.id, h.statement, h.confidence, h.validated, h.evidence_count, h.created_at, "
            "h.source_kind, h.lifecycle_status, h.owner_username, h.next_check_at, "
            "(SELECT COUNT(*) FROM kb_hypothesis_sources s WHERE s.hypothesis_id=h.id) AS ec2 "
            "FROM kb_hypotheses h WHERE h.category = ? "
            "ORDER BY h.validated DESC, h.confidence DESC, h.created_at DESC LIMIT ?",
            (cat, limit),
        ).fetchall()
        src_map: dict[str, set[str]] = {}
        if rows:
            ids = [r["id"] for r in rows]
            qs = ",".join("?" * len(ids))
            for s in c.execute(
                f"SELECT hypothesis_id, doc_id FROM kb_hypothesis_sources WHERE hypothesis_id IN ({qs})",
                ids,
            ).fetchall():
                src_map.setdefault(s["hypothesis_id"], set()).add(s["doc_id"])
        latest_ok_started = _latest_run_started_at(c)

    def _kind_for(rid: str, stored: str) -> str:
        if stored in {"material", "news", "mixed"}:
            return stored
        sids = src_map.get(rid, set())
        if not sids:
            return "material"
        news_n = sum(1 for x in sids if (x or "").startswith("news:"))
        if news_n == 0:
            return "material"
        if news_n == len(sids):
            return "news"
        return "mixed"

    items = [{
        "id": r["id"], "statement": r["statement"],
        "confidence": float(r["confidence"] or 0), "validated": bool(r["validated"]),
        "evidence_count": int(r["ec2"] or r["evidence_count"] or 0),
        "is_new": _is_new_for_run(r["created_at"] or "", latest_ok_started),
        "created_at": r["created_at"] or "",
        "lifecycle_status": (r["lifecycle_status"] if "lifecycle_status" in r.keys() else "") or "synthesized",
        "owner_username": (r["owner_username"] if "owner_username" in r.keys() else "") or "",
        "next_check_at": (r["next_check_at"] if "next_check_at" in r.keys() else "") or "",
        "is_overdue": _is_overdue((r["next_check_at"] if "next_check_at" in r.keys() else "") or ""),
        "source_kind": _kind_for(r["id"], (r["source_kind"] or "") if "source_kind" in r.keys() else ""),
    } for r in rows]
    return JSONResponse({"section": section_id, "category": cat, "items": items},
                        headers={"Cache-Control": "no-store"})


# ── Lifecycle GETs registered BEFORE /{hyp_id} so /mine and /badge don't get
# captured by the parametric route (FastAPI resolves in declaration order).
@router.get("/kb/insights/mine", response_class=JSONResponse)
async def kb_insights_mine(user: str = Depends(_require_auth),
                            status: str = "", overdue: str = ""):
    me = (user or "").lower()
    today = _today_iso()
    wanted_statuses = [s.strip() for s in (status or "").split(",") if s.strip()]
    only_overdue = (overdue or "").lower() in ("1", "true", "yes")
    with _kb_conn() as c:
        h_rows = c.execute(
            "SELECT * FROM kb_hypotheses "
            "WHERE LOWER(COALESCE(owner_username,'')) = ? "
            "   OR (created_at IS NOT NULL AND substr(created_at,1,10) = ?) "
            "ORDER BY validated DESC, evidence_count DESC, created_at DESC",
            (me, today),
        ).fetchall()
        s_rows = c.execute("SELECT hypothesis_id, doc_id FROM kb_hypothesis_sources").fetchall()
        latest_ok_started = _latest_run_started_at(c)
    src_map: dict[str, set[str]] = {}
    for s in s_rows:
        src_map.setdefault(s["hypothesis_id"], set()).add(s["doc_id"])
    items = []
    counts = {"in_review": 0, "overdue": 0, "new": 0}
    for r in h_rows:
        ls = r["lifecycle_status"] or "synthesized"
        owner = (r["owner_username"] or "").lower()
        nca = r["next_check_at"] or ""
        is_overdue = _is_overdue(nca)
        is_new = _is_new_for_run(r["created_at"] or "", latest_ok_started)
        ec = len(src_map.get(r["id"], set())) or int(r["evidence_count"] or 0)
        if owner == me:
            if ls == "in_review":
                counts["in_review"] += 1
            if is_overdue:
                counts["overdue"] += 1
        if is_new:
            counts["new"] += 1
        if wanted_statuses and ls not in wanted_statuses:
            continue
        if only_overdue and not is_overdue:
            continue
        items.append({
            "id": r["id"], "statement": r["statement"], "rationale": r["rationale"] or "",
            "category": r["category"] or "",
            "section": CATEGORY_TO_SECTION.get(r["category"] or "", ""),
            "confidence": float(r["confidence"] or 0),
            "validated": bool(r["validated"]),
            "evidence_count": ec, "source_kind": r["source_kind"] or "material",
            "lifecycle_status": ls, "owner_username": r["owner_username"] or "",
            "next_check_at": nca, "is_overdue": is_overdue, "is_new": is_new,
            "created_at": r["created_at"] or "",
            "allowed_transitions": _allowed_transitions(ls),
        })
    items.sort(key=lambda x: (
        not x["is_overdue"],
        x["next_check_at"] or "9999-99-99",
        -1 * (1 if x["is_new"] else 0),
        x["created_at"] or "",
    ))
    return JSONResponse({"me": user, "counts": counts, "hypotheses": items},
                         headers={"Cache-Control": "no-store"})


@router.get("/kb/insights/badge", response_class=JSONResponse)
async def kb_insights_badge(user: str = Depends(_require_auth)):
    me = (user or "").lower()
    today = _today_iso()
    with _kb_conn() as c:
        in_review = c.execute(
            "SELECT COUNT(*) AS n FROM kb_hypotheses "
            "WHERE LOWER(COALESCE(owner_username,'')) = ? AND lifecycle_status='in_review'",
            (me,),
        ).fetchone()["n"]
        overdue = c.execute(
            "SELECT COUNT(*) AS n FROM kb_hypotheses "
            "WHERE LOWER(COALESCE(owner_username,'')) = ? "
            "  AND next_check_at IS NOT NULL AND next_check_at <> '' "
            "  AND substr(next_check_at,1,10) <= ?",
            (me, today),
        ).fetchone()["n"]
        both = c.execute(
            "SELECT COUNT(*) AS n FROM kb_hypotheses "
            "WHERE LOWER(COALESCE(owner_username,'')) = ? AND lifecycle_status='in_review' "
            "  AND next_check_at IS NOT NULL AND next_check_at <> '' "
            "  AND substr(next_check_at,1,10) <= ?",
            (me, today),
        ).fetchone()["n"]
    count = int(in_review) + int(overdue) - int(both)
    return JSONResponse(
        {"count": count, "in_review": int(in_review), "overdue": int(overdue)},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/kb/insights/{hyp_id}")
async def kb_insights_get(hyp_id: str, user: str = Depends(_require_auth)):
    with _kb_conn() as c:
        h = c.execute("SELECT * FROM kb_hypotheses WHERE id=?", (hyp_id,)).fetchone()
        if not h:
            raise HTTPException(404, "not found")
        s_rows = c.execute(
            "SELECT s.*, d.title, d.source_type, d.source_ref, d.file_ext "
            "FROM kb_hypothesis_sources s "
            "LEFT JOIN kb_docs d ON d.id = s.doc_id "
            "WHERE s.hypothesis_id=? ORDER BY s.is_origin DESC",
            (hyp_id,),
        ).fetchall()
        news_ids = [s["doc_id"] for s in s_rows if (s["doc_id"] or "").startswith("news:")]
        news_map: dict[str, dict] = {}
        if news_ids:
            qs = ",".join("?" * len(news_ids))
            for nr in c.execute(
                f"SELECT id, title, summary, url, source, origin FROM kb_news_items WHERE id IN ({qs})",
                news_ids,
            ).fetchall():
                news_map[nr["id"]] = {
                    "title": nr["title"] or "", "summary": nr["summary"] or "",
                    "url": nr["url"] or "", "source": nr["source"] or "",
                    "origin": nr["origin"] or "",
                }
        quality_map = {}
        for s in s_rows:
            did = s["doc_id"] or ""
            if did and not did.startswith("news:"):
                drow = c.execute(
                    "SELECT content, source_type, source_ref FROM kb_docs WHERE id=?",
                    (did,),
                ).fetchone()
                if drow:
                    lvl, reasons = _score_doc_quality(drow)
                    quality_map[did] = {"level": lvl, "reasons": reasons}
    sources = []
    src_ids: set[str] = set()
    for s in s_rows:
        did = s["doc_id"] or ""
        if not did:
            continue
        src_ids.add(did)
        if did.startswith("news:"):
            n = news_map.get(did) or {}
            sources.append({
                "doc_id": did, "kind": "news",
                "title": n.get("title") or "(новость удалена)",
                "source_type": "news", "source_ref": n.get("url") or "",
                "file_ext": "", "excerpt": s["excerpt"] or n.get("summary") or "",
                "is_origin": bool(s["is_origin"]),
                "origin": n.get("origin") or "",
                "news_source": n.get("source") or "",
                "quality": {"level": "amber", "reasons": ["новость"]},
            })
        else:
            sources.append({
                "doc_id": did, "kind": "material",
                "title": s["title"] or "(удалён)",
                "source_type": s["source_type"] or "",
                "source_ref": s["source_ref"] or "",
                "file_ext": s["file_ext"] or "",
                "excerpt": s["excerpt"] or "",
                "is_origin": bool(s["is_origin"]),
                "quality": quality_map.get(did, {"level": "red", "reasons": ["удалён"]}),
            })
    stored_kind = ""
    try:
        stored_kind = (h["source_kind"] or "") if "source_kind" in h.keys() else ""
    except Exception:
        stored_kind = ""
    if stored_kind in {"material", "news", "mixed"}:
        source_kind = stored_kind
    else:
        news_n = sum(1 for x in src_ids if x.startswith("news:"))
        if not src_ids or news_n == 0:
            source_kind = "material"
        elif news_n == len(src_ids):
            source_kind = "news"
        else:
            source_kind = "mixed"
    return {
        "id": h["id"], "statement": h["statement"], "rationale": h["rationale"],
        "category": h["category"] or "",
        "section": CATEGORY_TO_SECTION.get(h["category"] or "", ""),
        "confidence": float(h["confidence"] or 0),
        "validated": bool(h["validated"]),
        "evidence_count": len(sources) or int(h["evidence_count"] or 0),
        "created_at": h["created_at"] or "",
        "is_new": _is_new_iso(h["created_at"] or ""),
        "source_kind": source_kind, "sources": sources,
        "lifecycle_status": (h["lifecycle_status"] if "lifecycle_status" in h.keys() else "") or "synthesized",
        "owner_username": (h["owner_username"] if "owner_username" in h.keys() else "") or "",
        "next_check_at": (h["next_check_at"] if "next_check_at" in h.keys() else "") or "",
        "lifecycle_updated_at": (h["lifecycle_updated_at"] if "lifecycle_updated_at" in h.keys() else "") or "",
        "is_overdue": _is_overdue((h["next_check_at"] if "next_check_at" in h.keys() else "") or ""),
        "allowed_transitions": _allowed_transitions((h["lifecycle_status"] if "lifecycle_status" in h.keys() else "") or "synthesized"),
    }


# ── Insight Lifecycle endpoints ──────────────────────────────────────────────
@router.post("/kb/insights/{hyp_id}/lifecycle")
async def kb_insights_lifecycle(hyp_id: str, request: Request,
                                  user: str = Depends(_require_auth)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_status = (body.get("status") or "").strip()
    confirm = bool(body.get("confirm"))
    if new_status not in LIFECYCLE_STATUSES:
        raise HTTPException(400, "bad status")
    with _kb_conn() as c:
        row = c.execute(
            "SELECT lifecycle_status, owner_username FROM kb_hypotheses WHERE id=?",
            (hyp_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        cur = row["lifecycle_status"] or "synthesized"
        owner = row["owner_username"] or ""
        if new_status == cur:
            return JSONResponse({"ok": True, "hyp_id": hyp_id, "status": cur,
                                  "lifecycle_updated_at": "", "owner_username": owner})
        if new_status not in ALLOWED_TRANSITIONS.get(cur, ()):
            return JSONResponse(
                {"detail": "transition_not_allowed", "from": cur, "to": new_status},
                status_code=409,
            )
        if new_status == "archived" and not confirm:
            return JSONResponse({"detail": "confirm_required"}, status_code=409)
        # Promotion to validated/adopted requires an owner.
        next_owner = owner
        if new_status == "in_review" and not owner:
            next_owner = user  # auto-claim on first transition
        if new_status in ("validated", "adopted") and not next_owner:
            return JSONResponse({"detail": "assign_owner_first"}, status_code=409)
        now = _utcnow_iso()
        c.execute(
            "UPDATE kb_hypotheses SET lifecycle_status=?, owner_username=?, "
            "lifecycle_updated_at=? WHERE id=?",
            (new_status, next_owner or None, now, hyp_id),
        )
    return {"ok": True, "hyp_id": hyp_id, "status": new_status,
             "lifecycle_updated_at": now, "owner_username": next_owner}


@router.post("/kb/insights/{hyp_id}/owner")
async def kb_insights_owner(hyp_id: str, request: Request,
                              user: str = Depends(_require_auth)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("username", "")
    target = None if raw is None else (raw or "").strip().lower() or None
    is_admin = _is_admin(user)
    with _kb_conn() as c:
        row = c.execute(
            "SELECT owner_username FROM kb_hypotheses WHERE id=?", (hyp_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        cur_owner = (row["owner_username"] or "").strip().lower()
        # Enforce: only admin can assign anyone; non-admin can only claim self
        # (when ownerless) or release self.
        if not is_admin:
            if target and target != user.lower():
                raise HTTPException(403, "cannot assign others")
            if cur_owner and cur_owner != user.lower():
                raise HTTPException(403, "another owner")
        # Atomic claim when transitioning ownerless → owned by `target`.
        if target and not cur_owner:
            r = c.execute(
                "UPDATE kb_hypotheses SET owner_username=?, lifecycle_updated_at=? "
                "WHERE id=? AND (owner_username IS NULL OR owner_username='')",
                (target, _utcnow_iso(), hyp_id),
            )
            if r.rowcount == 0:
                fresh = c.execute(
                    "SELECT owner_username FROM kb_hypotheses WHERE id=?", (hyp_id,)
                ).fetchone()
                return JSONResponse(
                    {"detail": "owner_taken",
                     "owner_username": (fresh["owner_username"] or "") if fresh else ""},
                    status_code=409,
                )
        else:
            c.execute(
                "UPDATE kb_hypotheses SET owner_username=?, lifecycle_updated_at=? "
                "WHERE id=?",
                (target, _utcnow_iso(), hyp_id),
            )
    return {"ok": True, "hyp_id": hyp_id, "owner_username": target or ""}


@router.post("/kb/insights/{hyp_id}/next_check")
async def kb_insights_next_check(hyp_id: str, request: Request,
                                   user: str = Depends(_require_auth)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("date", None)
    if raw not in (None, ""):
        s = str(raw).strip()
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            raise HTTPException(400, "bad date")
        new_date = s
    else:
        new_date = None
    is_admin = _is_admin(user)
    with _kb_conn() as c:
        row = c.execute(
            "SELECT owner_username FROM kb_hypotheses WHERE id=?", (hyp_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        owner = (row["owner_username"] or "").strip().lower()
        if not is_admin and owner and owner != user.lower():
            raise HTTPException(403, "not owner")
        if not is_admin and not owner:
            raise HTTPException(403, "no owner — claim first")
        c.execute(
            "UPDATE kb_hypotheses SET next_check_at=?, lifecycle_updated_at=? WHERE id=?",
            (new_date, _utcnow_iso(), hyp_id),
        )
    return {"ok": True, "hyp_id": hyp_id, "next_check_at": new_date or ""}


