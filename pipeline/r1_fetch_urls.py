#!/usr/bin/env python3
"""R1 v2 — safe, fast, RU-travel-focused candidate collector.

Design constraints (learned from v1 failure):
  * NO Playwright / NO Chromium / NO `daily_trend_monitor_yandex` import.
    Previous version called `m.resolve_google_news_url()` and `m.fetch_article_text()`
    which both spawn full headless Chromium per call. With 6 parallel workers ×
    ~80 URLs that ate the whole VPS (load average 56).
  * Pure stdlib: urllib + xml.etree + concurrent.futures.
  * Concurrency: ThreadPoolExecutor(max_workers=3) — IO-bound HTTP only,
    no processes, no memory hogs. Total runtime target: < 60s for ~100 URLs.

Source coverage (RU travel-banking focus):
  * Google News RSS — ~35 запросов, тяжёлый акцент на RU банки/travel
  * Direct site: queries to bank domains (sber/vtb/tbank/alfa/raiffeisen/gazprom)
  * Direct RSS feeds от tier-1 publishers (Reuters/Skift/PhocusWire/RBC/Vedomosti/...)

Each candidate gets `trust_score` ∈ [0.10, 1.00]:
  1.00 — official bank press, regulator, tier-1 business press (Reuters/FT/RBC)
  0.85 — major news (RIA/TASS/Banki.ru/Skift/PhocusWire/TechCrunch)
  0.70 — RU travel-trade press (ratanews/atorus/tourdom/frequentflyers)
  0.50 — aggregators (Yahoo Finance), regional news
  0.30 — tech blogs, Medium, vc.ru
  0.15 — forums, social aggregators
  0.10 — unknown / no domain match
"""
import sys
import os
import json
import re
import time
import base64
import threading
import subprocess
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urljoin
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


# === Freshness filter (24h cutoff) ============================================
# Применяется к RSS-фидам (TIER1) и Google News (mode=collect, mode=google),
# где у каждого item есть pubDate. mode=scrape пропускает фильтр (на listing
# страницах нет date-метаданных). mode=yandex (SearXNG) — пропускает (time_range
# ломает Bing/Yandex и возвращает 0 results).
FRESHNESS_HOURS = 24


def _is_fresh(pub_str: str, max_hours: int = FRESHNESS_HOURS) -> bool:
    """Возвращает True если pubDate не старше max_hours.

    Если pubDate отсутствует или не парсится — возвращаем True (не отбрасываем,
    лучше пропустить лишнего чем потерять валидную свежую новость без даты).
    """
    if not pub_str:
        return True
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt is None:
            return True
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return age <= timedelta(hours=max_hours)
    except Exception:
        return True

# === Sequential Chromium guard ===
# ru-fetch может (на JS-challenge сайтах или с --browser) спавнить Playwright Chromium.
# Каждый Chromium ~250 МБ. Если 4 worker'а одновременно его поднимут — server collapse
# (мы это уже проходили). Семафор гарантирует 1 Chromium за раз. Curl-операции идут
# параллельно как обычно — лочим ТОЛЬКО browser-явные операции.
_BROWSER_LOCK = threading.Semaphore(1)
BROWSER_TIMEOUT = 50  # max wait for one Chromium-based call

# === URL resolution cache (24h TTL) ===
URL_CACHE_PATH = "/tmp/r1_url_cache.json"
URL_CACHE_TTL = 24 * 3600
_url_cache = None
_cache_lock = threading.Lock()


def _cache_load() -> dict:
    try:
        with open(URL_CACHE_PATH) as f:
            d = json.load(f)
        cutoff = time.time() - URL_CACHE_TTL
        return {k: v for k, v in d.items() if isinstance(v, dict) and v.get("ts", 0) > cutoff}
    except Exception:
        return {}


def _cache_save() -> None:
    global _url_cache
    if _url_cache is None:
        return
    try:
        with open(URL_CACHE_PATH, "w") as f:
            json.dump(_url_cache, f)
    except Exception:
        pass


def _cache_get(key: str):
    global _url_cache
    with _cache_lock:
        if _url_cache is None:
            _url_cache = _cache_load()
        e = _url_cache.get(key)
    if not e:
        return None
    return e.get("v")


def _cache_set(key: str, value) -> None:
    global _url_cache
    with _cache_lock:
        if _url_cache is None:
            _url_cache = _cache_load()
        _url_cache[key] = {"v": value, "ts": time.time()}

# RU-fetch binary path (same one compare-tool uses; has curl-fast → browser fallback)
RU_FETCH_BIN = "/opt/newsapp/bypass/bin/ru-fetch"

# Topic filter — отбрасываем offtopic уже на стадии стабов (до resolve+text fetch).
# Direct RSS Vedomosti/RBC/Kommersant/Forbes отдают много политики/войны/спорта —
# 60+ из 70 кандидатов были не про travel, агент их пропускал в финал. Этот filter
# отрезает их по title прежде, чем агенту вообще понадобится решать.
# Travel-strict 3-category filter:
#   Категории по запросу пользователя (как в case_type r1_news.json):
#     1. "Travel в банкинге"  → travel + banking
#     2. "AI travel"          → travel + AI
#     3. "AI travel в банкинге" → travel + banking + AI
#   ВСЕ требуют travel-сигнал. Без него — skip.

# Travel-сигналы (хотя бы один нужен).
# Большинство pattern'ов БЕЗ word-boundary — чтобы ловить "авиаперевозкам",
# "отельный", "Hotels", "аэропортов" (склонения и формы).
TRAVEL_RE = re.compile(
    # Generic travel
    r"travel\b|\btravel-|туризм|туристическ|турист\w*|"
    r"путешеств|поездк|поездок|поездку|"
    # Hotels
    r"отел[ьяиеёов]|\bhotel|hospitality|гостиниц|"
    # Aviation (RU partial — без \b чтобы ловить склонения)
    r"авиа(?:компани|перевоз|билет|услуг|пассаж|линий|сообщ|транспорт)?|"
    r"airline|airway|\bflight\b|flights\b|\bair\s+travel|"
    r"перелёт|перелет|\bрейс\w*|\bAir\b|"
    # Airports
    r"аэропорт|\bairport|airports|"
    # Travel agents / agencies
    r"турагент|tour\s*operator|туропер|trip\s*advisor|"
    # Booking / loyalty
    r"booking|бронир|reservation|"
    r"loyalty|\bmiles\b|\bмили\b|frequent\s*flyer|программ[ыа]\s+лояльност|"
    r"lounge|бизнес-зал|"
    r"\bкруиз|\bcruise|cruises|"
    # Visa / passport
    r"\bвизы?\b|\bвиз[уыо]\w*|\bvisa\b|passport|паспорт|"
    # Rail travel (passenger only, not cargo)
    r"\bРЖД\s+(?:пасса|туристическ)|пасса[жш]ирск[аяиое]\s+поезд|"
    # OTA / aggregators / industry players
    r"aviasales|kayak|expedia|airbnb|skift|onetwotrip|phocuswire|phocuswright|"
    r"booking\.com|tutu\.ru|ostrovok|trivago|hopper|navan|spotnana|amex\s*gbt|"
    r"Яндекс\s*Путешеств|СберТревел|Сбер\s*Travel|МТС\s*Тревел|"
    # Hotel chains
    r"marriott|hilton|hyatt|\bihg\b|accor|wyndham|ascott|choice\s*hotels|"
    r"radisson|fairmont|four\s*seasons|"
    # Airlines
    r"spirit\s*airlines|delta\s*air|united\s*airlines|american\s*airlines|"
    r"emirates|lufthansa|qatar\s*airways|ryanair|easyjet|virgin\s+(?:atlantic|voyages)|"
    r"аэрофлот|\bs7\b|россия\s*авиа|победа\s*авиа|уральские\s*авиа|"
    r"Azur\s+Air|red\s*wings|nordstar|smartavia|utair|nordwind|"
    # RU travel-trade
    r"ratanews|atorus|tourdom|frequentflyers|tour52|"
    r"\bАТОР\b|РСТ\b|Ростуризм|Минэкономразвития\s+туризм",
    re.I,
)

# Banking-сигналы (для категорий 1 и 3)
BANKING_RE = re.compile(
    r"\bбанк|\bbank\b|banking|fintech|финтех|"
    r"cashback|кэшбэк|кешбэк|"
    r"карт[аыеу]\b|\bcard\b|карточн|"
    r"премиальн|премиум|премьерск|prime|"
    r"подписк|"
    r"payment|плате[жщ]|оплат|"
    r"Сбер|Тинькофф|T-Bank|TBank|ВТБ\b|Альфа|Газпромбанк|Райффайзен|МТС[\s-]?Банк|"
    r"Visa\b|Mastercard|Amex|American\s*Express|"
    r"Revolut|N26|Monzo|Wise\b|Klarna|Stripe|PayPal|"
    r"СберПрайм|Яндекс\s*Плюс|МТС\s*Premium|T-PRO|Ozon\s*Premium",
    re.I,
)

# AI-сигналы (для категорий 2 и 3)
AI_RE = re.compile(
    r"\bAI\b|\bИИ\b|"
    r"chatgpt|\bGPT[-\s]?\d|gemini|copilot|claude\b|llama|mistral|"
    r"нейросет|искусственн.{0,10}интеллект|"
    r"machine\s*learning|deep\s*learning|"
    r"AI[-\s]?агент|AI[-\s]?ассистент|"
    r"ИИ[-\s]?агент|ИИ[-\s]?ассистент|"
    r"генеративн|generative|LLM\b",
    re.I,
)


def _is_travel_topic(title: str) -> bool:
    """Travel-relevance filter: requires at least one travel-related token.

    Достаточно одного TRAVEL_RE-слова в title. Pure travel news (Spirit Airlines
    closure, Emirates resumes flights) — пропускаются. Pure banking без travel
    (Sber profit, CBR rate, ВТБ stocks) — skip. Pure AI без travel (ChatGPT update)
    — skip. Sport / politics / art — skip (нет travel-keyword).

    Стадия 2 (агент) делает финальный отбор case_type:
      "Travel в банкинге" / "AI travel" / "AI travel в банкинге"
    и пропускает items, которые не вписываются ни в одну.
    """
    if not title:
        return False
    return bool(TRAVEL_RE.search(title))


# URL-shape blacklist — отрезает landing-страницы, продуктовые карточки, промо,
# login/about-страницы, social-media URLs. Yandex search возвращал такие как
# валидные результаты («sber.ru/.../travel/», «alfabank.ru/.../alfa-travel-premium/»),
# а агент потом не мог из них выжать новость и ставил placeholder "Travel-новость".
#
# Whitelist-paths (если URL содержит — пропускаем даже при матче blacklist):
#   /news/, /press/, /article/, /lenta/, /publications/, /20YY/MM/DD/
URL_NEWS_WHITELIST_RE = re.compile(
    r"/(news|press|press-release|press-relizy|article|articles|publication|"
    r"publications|story|stories|lenta|novosti|stati|materials|doc|"
    r"finances|finance|business|economics|tech|technology|markets)/|"
    r"/20\d{2}/\d{1,2}/|/\d{1,2}/\d{1,2}/20\d{2}/",
    re.I,
)

URL_BAD_HOST_RE = re.compile(
    r"^(login\.|m\.tiktok\.|"
    r"(www\.)?(tiktok|instagram|facebook|twitter|youtube|telegram)\.com$|"
    r"(www\.)?vk\.com$|(www\.)?youtu\.be$|(www\.)?ok\.ru$|(www\.)?dzen\.ru$|"
    # Telegram channel pages — t.me URLs не отдают article, только embed
    r"(www\.)?t\.me$|(www\.)?telegram\.me$|"
    # mail.ru company-page — company landing aggregator, не статьи
    # (news.mail.ru/company/aeroflot/ и т.п.)
    # Aggregator-домены, в которых только продуктовые карточки, не новости
    r"(www\.)?finuslugi\.ru$|(www\.)?sravni\.ru$)",
    re.I,
)

# Landing/product/promo path-tokens. Срабатывает только если whitelist не победил.
URL_BAD_PATH_RE = re.compile(
    r"/(cards?|credit-cards?|debit-cards?|loyalty|promo|landing|about|"
    r"contacts?|privacy|terms|cookie|sitemap|login|signup|register|"
    r"subscribe|tariffs?|rates?|catalog|categor|tag|page|"
    r"feedback|support|help|faq|career|jobs|press-kit|investor|legal|"
    r"prime|premier|prosto|gift|bonus|reviews?|otzyv)(/|$|\?|#)",
    re.I,
)

# Travel-product-page tokens (sber-travel, alfa-travel-premium, tinkoff-travel-premium).
# Префикс банка + опциональные суффиксы вроде "-premium", "-business".
URL_TRAVEL_PRODUCT_RE = re.compile(
    r"/(alfa[-_]?travel|sber[-_]?travel|sbertravel|tinkoff[-_]?travel|"
    r"t[-_]travel|t[-_]bank[-_]travel|raif[-_]?travel|"
    r"vtb[-_]?travel|premium[-_]?travel|travel[-_]?premium)"
    r"[a-z0-9_-]*(/|$|\?|#)",
    re.I,
)

# Top-level «landing» одним сегментом (sber.ru/travel/, sber.ru/everyday/).
URL_TOPLEVEL_LANDING_RE = re.compile(
    r"^/(travel|finance|finances|loans|credit|deposit|deposits|investments|"
    r"insurance|premium|business|corporate|retail|personal|everyday|"
    r"mobile|app|shop|store|pay|wallet|brokers?|markets?|education|"
    r"clients|partners)/?$|"
    # booking.com/index.ru.html, booking.com/index.html — root landing с локалью
    r"^/index\.[a-z]{2,5}\.html?$|^/index\.html?$|"
    # mail.ru/company/<brand>/ — aggregator company landing
    r"^/company/[\w-]+/?$",
    re.I,
)

# Domains where ТОЛЬКО /news/ URLs считаются статьями. Скрейп листингов на этих
# сайтах вытягивает и section-навигацию (atorus.ru/business-i-analitika/...,
# atorus.ru/transport/...) — это не статьи, а категории. Whitelist по path
# слишком слаб, потому что у этих сайтов article URLs не содержат YYYY/MM/DD.
NEWS_PATH_REQUIRED_HOSTS = {
    # RU travel-trade
    "atorus.ru", "www.atorus.ru",
    "ratanews.ru", "www.ratanews.ru",
    "tourdom.ru", "www.tourdom.ru",
    "frequentflyers.ru", "www.frequentflyers.ru",
    "tour52.ru", "www.tour52.ru",
    "trn-news.ru", "www.trn-news.ru",
    "tourister.ru", "www.tourister.ru",
    "aviasales.ru", "www.aviasales.ru",
    # RU bank domains — Yandex search всё время тащит их product/landing pages
    # (sber.ru/travel/, vtb.ru/privilegia/..., gazprombank.ru/premium/travel/).
    # Реальные банковские новости публикуются ТОЛЬКО в /press/, /news/, /press-centre/.
    "sber.ru", "www.sber.ru", "sberbank.ru", "www.sberbank.ru",
    "sberbank.com", "www.sberbank.com", "press.sberbank.ru",
    "tbank.ru", "www.tbank.ru", "t-bank.ru", "www.t-bank.ru",
    "tinkoff.ru", "www.tinkoff.ru",
    "vtb.ru", "www.vtb.ru", "vtb.com", "www.vtb.com",
    "alfabank.ru", "www.alfabank.ru", "alfa-bank.ru", "www.alfa-bank.ru",
    "gazprombank.ru", "www.gazprombank.ru", "gpbru.com", "www.gpbru.com",
    "raiffeisen.ru", "www.raiffeisen.ru", "raif.ru", "www.raif.ru",
    "raiffeisen-bank.ru", "www.raiffeisen-bank.ru",
    "mtsbank.ru", "www.mtsbank.ru",
    "otkritie.com", "www.otkritie.com", "open.ru", "www.open.ru",
    "psbank.ru", "www.psbank.ru",
    "rosbank.ru", "www.rosbank.ru",
    "sovcombank.ru", "www.sovcombank.ru",
    "otpbank.ru", "www.otpbank.ru",
    "tochka.com", "www.tochka.com",
    "akbars.ru", "www.akbars.ru",
    "uralsib.ru", "www.uralsib.ru",
}
# Whitelisted news paths (для travel-trade сайтов: news, press, blog, story etc).
NEWS_PATH_RE = re.compile(r"/(news|press|press[-_]?relizy|press[-_]?releases?|"
                          r"press[-_]?center|press[-_]?centre|press[-_]?room|"
                          r"article|articles|blog|story|stories|"
                          r"materials|publications|stati|novosti|insights|"
                          r"analytics)/", re.I)
# Bank domains — ужесточённый список. /blog/, /story/, /article/ НЕ принимаются
# потому что банки используют их под маркетинговые / продуктовые страницы
# (tbank.ru/finance/blog/premium-for-travel/ — это блог-обзор продукта, не новость).
BANK_NEWS_PATH_RE = re.compile(r"/(news|press|press[-_]?relizy|"
                               r"press[-_]?releases?|press[-_]?center|"
                               r"press[-_]?centre|press[-_]?room|"
                               r"novosti|pressroom|"
                               r"sustainability[-_]?report|annual[-_]?report)"
                               r"(?:[/?]|$)", re.I)
BANK_HOSTS_FOR_STRICT = {
    "sber.ru", "www.sber.ru", "sberbank.ru", "www.sberbank.ru",
    "sberbank.com", "www.sberbank.com",
    "tbank.ru", "www.tbank.ru", "t-bank.ru", "www.t-bank.ru",
    "tinkoff.ru", "www.tinkoff.ru",
    "vtb.ru", "www.vtb.ru", "vtb.com", "www.vtb.com",
    "alfabank.ru", "www.alfabank.ru", "alfa-bank.ru", "www.alfa-bank.ru",
    "gazprombank.ru", "www.gazprombank.ru", "gpbru.com", "www.gpbru.com",
    "raiffeisen.ru", "www.raiffeisen.ru", "raif.ru", "www.raif.ru",
    "raiffeisen-bank.ru", "www.raiffeisen-bank.ru",
    "mtsbank.ru", "www.mtsbank.ru",
    "otkritie.com", "www.otkritie.com", "open.ru", "www.open.ru",
    "psbank.ru", "www.psbank.ru",
    "rosbank.ru", "www.rosbank.ru",
    "sovcombank.ru", "www.sovcombank.ru",
    "otpbank.ru", "www.otpbank.ru",
    "tochka.com", "www.tochka.com",
    "akbars.ru", "www.akbars.ru",
    "uralsib.ru", "www.uralsib.ru",
}


def _is_bad_url_shape(url: str) -> bool:
    """True если URL похож на landing/product/promo/login, а не на статью.

    Правило: blacklist срабатывает ТОЛЬКО если в URL нет news-whitelist маркера.
    Это страхует от ложного дропа статей вида /news/2025/cards-update/ —
    /cards/ есть в path, но /news/ его перебивает.
    """
    if not url:
        return True
    p = urlparse(url)
    host = (p.hostname or "").lower()
    path = p.path or "/"
    # Hard-block social/login hosts полностью
    if URL_BAD_HOST_RE.search(host):
        return True
    # Корневая страница без path («https://sber.ru/» или просто «https://sber.ru»)
    if path in ("", "/"):
        return True
    # Per-domain rule: на RU travel-trade сайтах только /news/ etc. = статья.
    # Section-навигация (atorus.ru/business-i-analitika/...) тут просачивалась.
    if host in NEWS_PATH_REQUIRED_HOSTS and not NEWS_PATH_RE.search(path):
        return True
    # Stricter rule for bank domains: только /press/ или /news/ + ничего ещё.
    # Это убивает tbank.ru/finance/blog/premium-for-travel/ (блог-обзор продукта),
    # vtb.ru/privilegia/premialnye-servisy/ (продуктовая страница страховки),
    # gazprombank.ru/premium/travel/ (лендинг).
    if host in BANK_HOSTS_FOR_STRICT and not BANK_NEWS_PATH_RE.search(path):
        return True
    # Whitelist override
    if URL_NEWS_WHITELIST_RE.search(path):
        return False
    # Top-level landing keyword («/travel/», «/everyday/»)
    if URL_TOPLEVEL_LANDING_RE.match(path):
        return True
    # Path-based blacklist
    if URL_BAD_PATH_RE.search(path):
        return True
    # Travel-product-page (sber-travel, alfa-travel-premium, etc.)
    if URL_TRAVEL_PRODUCT_RE.search(path):
        return True
    return False


# Domain regex for "ru-fetch territory" — banks, RU news, RU regulators.
# Matches the same pattern that ru-fetch uses internally for SOCKS5 routing.
RU_DOMAIN_RE = re.compile(
    r"(^|\.)(sber|sberbank|vtb|tinkoff|t-bank|tbank|alfabank|alfa-bank|raiffeisen|"
    r"raiffeisen-bank|gazprombank|gpbru|otkritie|psbank|rosbank|sovcombank|mtsbank|"
    r"otpbank|home-credit|banki|sravni|frankrg|forbes|rbc|vedomosti|kommersant|"
    r"tochka|cbr|ratanews|atorus|tourdom|frequentflyers|tour52|"
    r"ria|interfax|tass|lenta|iz|izvestia|gazeta|mk|rg|"
    r"j\.tinkoff|journal\.tinkoff|secretmag|vc|fontanka|themoscowtimes)\.(ru|com)$",
    re.I,
)

# Tunables
GOOGLE_NEWS_TOP_N = 25  # was 7 — raised 2026-05-29 for better recall
RESOLVE_WORKERS = 4
CANDIDATE_BUDGET = 320  # was 220 — raised 2026-05-29 for better recall
HTTP_TIMEOUT = 6  # tight — bad feeds should fail fast (was 10)
ARTICLE_MAX_CHARS = 2500
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",  # avoid gzip — keeps stdlib decoding simple
}


# ── Trust registry ──────────────────────────────────────────────────────
TRUST_REGISTRY: dict[str, float] = {
    # ─ 1.00 · regulator + tier-1 business press
    "reuters.com": 1.00, "ft.com": 1.00, "wsj.com": 1.00, "bloomberg.com": 1.00,
    "economist.com": 1.00, "forbes.com": 1.00, "hbr.org": 1.00, "fortune.com": 1.00,
    "marketwatch.com": 1.00,
    # RU regulator + tier-1
    "rbc.ru": 1.00, "vedomosti.ru": 1.00, "kommersant.ru": 1.00, "forbes.ru": 1.00,
    "cbr.ru": 1.00, "minfin.gov.ru": 1.00, "moex.com": 1.00,
    # Official bank press releases (RU)
    "sber.ru": 1.00, "sberbank.ru": 1.00, "sberbank.com": 1.00,
    "vtb.ru": 1.00, "vtb.com": 1.00,
    "tbank.ru": 1.00, "t-bank.ru": 1.00, "tinkoff.ru": 1.00,
    "alfabank.ru": 1.00, "alfa-bank.ru": 1.00,
    "raiffeisen.ru": 1.00, "raiffeisen-bank.ru": 1.00,
    "gazprombank.ru": 1.00, "gpbru.com": 1.00,
    "otkritie.com": 1.00, "rosbank.ru": 1.00, "psbank.ru": 1.00,
    "sovcombank.ru": 1.00, "mtsbank.ru": 1.00, "otpbank.ru": 1.00,
    "tochka.com": 1.00, "akbars.ru": 1.00, "uralsib.ru": 1.00,
    # Travel + airline + hotel corporate (international tier-1)
    "booking.com": 1.00, "expedia.com": 1.00, "airbnb.com": 1.00,
    "marriott.com": 1.00, "hilton.com": 1.00, "hyatt.com": 1.00, "ihg.com": 1.00,
    "delta.com": 1.00, "united.com": 1.00, "aa.com": 1.00, "emirates.com": 1.00,
    # Card networks + fintech corporate
    "visa.com": 1.00, "mastercard.com": 1.00, "americanexpress.com": 1.00,
    "stripe.com": 1.00, "paypal.com": 1.00, "klarna.com": 1.00,
    "revolut.com": 1.00, "n26.com": 1.00, "monzo.com": 1.00, "wise.com": 1.00,

    # ─ 0.85 · major news
    "bbc.com": 0.85, "bbc.co.uk": 0.85, "nytimes.com": 0.85, "cnn.com": 0.85,
    "theguardian.com": 0.85, "washingtonpost.com": 0.85, "axios.com": 0.85,
    "ap.org": 0.85, "apnews.com": 0.85, "cnbc.com": 0.85,
    "businessinsider.com": 0.85, "qz.com": 0.85,
    # RU major
    "ria.ru": 0.85, "interfax.ru": 0.85, "tass.ru": 0.85, "tass.com": 0.85,
    "lenta.ru": 0.85, "iz.ru": 0.85, "izvestia.ru": 0.85,
    # RU industry analytics
    "frankrg.com": 0.85, "banki.ru": 0.85, "sravni.ru": 0.85,
    "finam.ru": 0.85, "investing.com": 0.85,
    # Tech press
    "techcrunch.com": 0.85, "theverge.com": 0.85, "wired.com": 0.85,
    "arstechnica.com": 0.85, "engadget.com": 0.85, "venturebeat.com": 0.85,
    # Travel-trade tier-1 (international)
    "skift.com": 0.85, "phocuswire.com": 0.85, "phocuswright.com": 0.85,
    "travelweekly.com": 0.85, "businesstravelnews.com": 0.85,
    "buyingbusinesstravel.com": 0.85,
    # Fintech-trade
    "finextra.com": 0.85, "pymnts.com": 0.85, "americanbanker.com": 0.85,
    "thebanker.com": 0.85, "fintechmagazine.com": 0.85, "thefintechtimes.com": 0.85,

    # ─ 0.70 · trade press / RU travel media
    "travelpulse.com": 0.70, "travelandleisure.com": 0.70,
    "hotelnewsnow.com": 0.70, "hotelmanagement.net": 0.70, "hospitalitynet.org": 0.70,
    "eyefortravel.com": 0.70, "tnooz.com": 0.70,
    "fastcompany.com": 0.70, "inc.com": 0.70, "crainsnewyork.com": 0.70,
    "themoscowtimes.com": 0.70, "moscowtimes.com": 0.70,
    # RU travel-trade specifically
    "ratanews.ru": 0.70, "atorus.ru": 0.70, "tourdom.ru": 0.70,
    "tour52.ru": 0.70, "frequentflyers.ru": 0.70,
    "buyingbusinesstravel.ru": 0.70, "trn-news.ru": 0.70, "tourister.ru": 0.70,
    # RU mid-tier news
    "gazeta.ru": 0.70, "mk.ru": 0.70, "rg.ru": 0.70,
    "fontanka.ru": 0.70, "spbvedomosti.ru": 0.70,
    "j.tinkoff.ru": 0.70, "journal.tinkoff.ru": 0.70,
    "secretmag.ru": 0.70,

    # ─ 0.85 · airlines (official corporate channels)
    "aeroflot.ru": 0.85, "aeroflot.com": 0.85,
    "s7.ru": 0.85, "flys7.com": 0.85,
    "pobeda.aero": 0.85, "flypobeda.com": 0.85,
    "utair.ru": 0.85, "rossiya-airlines.com": 0.85,
    "smartavia.com": 0.85, "nordwindairlines.ru": 0.85,
    "azur-air.com": 0.85, "redwings.aero": 0.85,
    # ─ 0.85 · RU fintech analytics
    "thebell.io": 0.85, "frankrg.com": 0.85,

    # ─ 0.50 · aggregators / regional press
    "yahoo.com": 0.50, "finance.yahoo.com": 0.50, "au.finance.yahoo.com": 0.50,
    "msn.com": 0.50, "news.yahoo.com": 0.50,
    "businesstoday.in": 0.50, "livemint.com": 0.50, "moneycontrol.com": 0.50,
    "asia.nikkei.com": 0.50, "nikkei.com": 0.50, "scmp.com": 0.50,
    # RU finance / banking analytics
    "finversia.ru": 0.50, "fomag.ru": 0.50,

    # ─ 0.30 · tech blogs / Medium / vc.ru (UGC-heavy platforms)
    "medium.com": 0.30, "dev.to": 0.30, "substack.com": 0.30,
    "linkedin.com": 0.30, "vc.ru": 0.30, "habr.com": 0.30,
    # RU curated banking aggregators (UGC, но проверены редакцией)
    "vbr.ru": 0.30, "klerk.ru": 0.30,
    "premiumbanking.info": 0.30,

    # ─ 0.15 · UGC forums
    "reddit.com": 0.15, "ycombinator.com": 0.15, "news.ycombinator.com": 0.15,
    "tripadvisor.com": 0.15, "tripadvisor.ru": 0.15,
}


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    for prefix in ("www.", "m.", "mobile.", "amp.", "ru.", "en."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def _trust_score(url: str) -> tuple[float, str]:
    host = _domain(url)
    if not host:
        return 0.10, ""
    if host in TRUST_REGISTRY:
        return TRUST_REGISTRY[host], host
    parts = host.split(".")
    for i in range(1, len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in TRUST_REGISTRY:
            return TRUST_REGISTRY[suffix], suffix
    return 0.10, ""


def _norm_url(url: str) -> str:
    """Strip fragment + utm_*; keep scheme/host/path/clean-qs."""
    try:
        p = urlparse(url)
        clean_qs = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_")]
        return f"{p.scheme}://{p.hostname or ''}{p.path}" + (
            ("?" + urlencode(clean_qs)) if clean_qs else ""
        )
    except Exception:
        return url


# ── URL resolver — pure stdlib, NO browser ─────────────────────────────
def _decode_gnews_url(gn_url: str) -> str:
    """Extract publisher URL from Google News /rss/articles/<base64> path.

    Google News encodes the original publisher URL in the base64-encoded path.
    Decoding it locally avoids needing JS execution (Playwright). Pattern:
      news.google.com/rss/articles/CBMi<base64-payload>?<query>
    The decoded payload is a protobuf-ish binary that contains the URL as
    plain UTF-8 text — we extract via regex.
    """
    m = re.search(r"/articles/([A-Za-z0-9_-]+)", gn_url)
    if not m:
        return ""
    encoded = m.group(1)
    # Try multiple padding variants (urlsafe vs std b64)
    for pad in ("", "=", "==", "==="):
        try:
            decoded = base64.urlsafe_b64decode(encoded + pad)
        except Exception:
            continue
        try:
            text = decoded.decode("utf-8", "ignore")
        except Exception:
            continue
        # Find http(s) URL in decoded bytes — pick first non-google one of reasonable length
        for u in re.findall(r'https?://[^\s\x00-\x1f"\'<>]+', text):
            if "news.google.com" in u or "google.com/rss" in u:
                continue
            if len(u) < 16:
                continue
            # Strip trailing junk that often appears after URL in protobuf framing
            u = re.sub(r"[\x80-\xff].*$", "", u)
            return u
        break
    return ""


def resolve_via_browser(url: str) -> str:
    """Use ru-fetch --browser --head to resolve URL after JS redirects.

    Sequential (через _BROWSER_LOCK) — 1 Chromium за раз. Cached на 24ч.
    Используется для Google News URL'ов нового формата (HMAC-token), которые
    base64-decoder не может вытащить.
    """
    if not url:
        return ""
    cached = _cache_get("resolve:" + url)
    if cached is not None:
        return cached
    final = ""
    with _BROWSER_LOCK:
        try:
            r = subprocess.run(
                [RU_FETCH_BIN, url, "--browser", "--head"],
                capture_output=True, timeout=BROWSER_TIMEOUT,
            )
            stdout = r.stdout.decode("utf-8", "replace")
            # ru-fetch-browser --head printed: HTTP {status} title="..." url={final} proxy=...
            m = re.search(r"\burl=(\S+)", stdout)
            if m:
                final = m.group(1).strip()
                if final == url or "news.google" in final:
                    final = ""
        except Exception:
            pass
    _cache_set("resolve:" + url, final)
    return final


def resolve_redirect(url: str, allow_browser: bool = True) -> str:
    """Resolve URL to its final publisher form.

    allow_browser=False: для mode=collect/google — БЕЗ Chromium-spawn'ов.
    Holds collect-mode fast and light (target <60с).

    Strategy для GN URLs:
      1. base64-decode локально (старый формат GN URL).
      2. Если не получилось — urllib HTTP redirect follow (новый HMAC-формат
         GN URL, ~95% случаев). Без браузера, быстро.
      3. Если allow_browser=True — Chromium fallback (slow, ~250 МБ peak).
    """
    if not url:
        return ""
    if "news.google.com/rss/articles/" in url:
        decoded = _decode_gnews_url(url)
        if decoded:
            return decoded
        # Python-only HMAC GN URL decoder через googlenewsdecoder (batchexecute).
        # Не запускает Chromium — критично для VPS с 1.9 ГБ RAM без swap.
        # Кеш 24ч через _cache_set, чтобы не дёргать Google повторно.
        cached = _cache_get("gnewsdec:" + url)
        if cached is not None:
            if cached:
                return cached
        else:
            try:
                from googlenewsdecoder import gnewsdecoder
                res = gnewsdecoder(url, interval=0)
                if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
                    final = (res["decoded_url"] or "").strip()
                    if final and "news.google" not in final:
                        _cache_set("gnewsdec:" + url, final)
                        return final
                _cache_set("gnewsdec:" + url, "")
            except Exception:
                _cache_set("gnewsdec:" + url, "")
        if allow_browser:
            via_browser = resolve_via_browser(url)
            if via_browser:
                return via_browser
        return ""  # GN-URL без resolve — пропускаем
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return r.url or url
    except urllib.error.HTTPError as e:
        return getattr(e, "url", "") or ""
    except Exception:
        return ""


# === Yandex search via ru-fetch+browser ===
# SearXNG: self-hosted мета-поисковик на 127.0.0.1:8888.
# Стоит на этом же VPS в Docker-контейнере r1-searxng. Internal-only (не выходит наружу).
# Преимущества vs Yandex-search-через-browser:
#   • JSON ответ (не парсим HTML)
#   • Нет _BROWSER_LOCK / Chromium → быстрее, меньше RAM
#   • Multi-engine: Yandex + DuckDuckGo + Bing + Brave параллельно — резильентность
#     если один engine троттлит/captcha-блокирует.
SEARXNG_URL = "http://127.0.0.1:8888/search"
SEARXNG_HEALTH_URL = "http://127.0.0.1:8888/"
SEARXNG_TIMEOUT = 12
# Engine subsets выбираются ПО ЯЗЫКУ запроса.
#   RU (Cyrillic) → Yandex + DuckDuckGo (Yandex лучший для RU, DDG как backup)
#   EN (Latin)    → DuckDuckGo + Bing + Brave (Yandex плох для EN)
#   site:queries  → DuckDuckGo + Bing (site: оператор лучше работает у них)
# Это снижает суммарное количество outbound calls с 90×5=450 до 90×2.5≈225,
# а главное — не нагружает Bing/Brave запросами на которых они троттлят (RU).
SEARXNG_ENGINES_RU = "yandex,duckduckgo,bing"
SEARXNG_ENGINES_EN = "duckduckgo,bing,brave"
# site: queries — нужны 3 engines потому что один из них может не индексировать
# конкретный домен (например, Bing плох с гос-банковскими сайтами, Yandex
# хорош с RU-доменами но не с phocuswire.com).
SEARXNG_ENGINES_SITE_RU = "yandex,bing,duckduckgo"
SEARXNG_ENGINES_SITE_EN = "bing,duckduckgo,brave"
SEARXNG_ENGINES_ALL = "yandex,duckduckgo,bing,brave"


def _detect_query_lang_and_kind(query: str) -> tuple[str, str]:
    """Возвращает (engines, lang) для запроса.

    Routing logic:
      site:RU-домен → yandex+bing+ddg (Yandex мастер по RU-доменам)
      site:EN-домен → bing+ddg+brave (Bing мастер по EN-доменам)
      RU-концепт → yandex+ddg+bing
      EN-концепт → ddg+bing+brave
    """
    has_cyrillic = any('Ѐ' <= c <= 'ӿ' for c in query)
    is_site_query = "site:" in query.lower()
    # Для site: query определяем язык домена, а не запроса
    if is_site_query:
        # Извлекаем "site:domain.tld" токен
        ql = query.lower()
        # Russian TLD .ru / .by / .kz → RU routing
        is_site_ru = (".ru" in ql.split("site:", 1)[1][:30]
                      or ".by" in ql.split("site:", 1)[1][:30])
        if is_site_ru:
            return SEARXNG_ENGINES_SITE_RU, "ru"
        return SEARXNG_ENGINES_SITE_EN, "en"
    if has_cyrillic:
        return SEARXNG_ENGINES_RU, "ru"
    return SEARXNG_ENGINES_EN, "en"


def searxng_health_check() -> bool:
    """Quick check: SearXNG-контейнер живой и отвечает."""
    try:
        req = urllib.request.Request(SEARXNG_HEALTH_URL,
                                     headers={"User-Agent": "r1-health/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def searxng_search(query: str, max_results: int = 10,
                   time_range: str = "") -> list[str]:
    """Search через self-hosted SearXNG (lang-aware engine subset).

    time_range: "" / "day" / "week" / "month" / "year".
    ВАЖНО: time_range НЕ работает с Bing/Yandex (engines возвращают 0 results
    при time_range=month). Поэтому default = "" (без фильтра по времени).
    Свежесть контролируем через "2026" в самих queries и через дедуп с архивом.
    Возвращает list of publisher URL'ов. Кешируется 24ч под "yx:" префиксом.
    """
    if not query:
        return []
    cached = _cache_get("yx:" + query)
    if cached is not None:
        return cached
    engines, lang = _detect_query_lang_and_kind(query)
    params = {
        "q": query,
        "format": "json",
        "engines": engines,
        "language": lang,
    }
    if time_range:
        params["time_range"] = time_range
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    url = f"{SEARXNG_URL}?{qs}"
    raw = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "r1-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=SEARXNG_TIMEOUT) as r:
            raw = r.read(500_000).decode("utf-8", "replace")
    except Exception:
        _cache_set("yx:" + query, [])
        return []
    if not raw:
        _cache_set("yx:" + query, [])
        return []
    try:
        data = json.loads(raw)
    except Exception:
        _cache_set("yx:" + query, [])
        return []
    results: list[str] = []
    seen_hosts: dict[str, int] = {}
    for hit in data.get("results", []):
        u = hit.get("url", "")
        if not u or not u.startswith(("http://", "https://")):
            continue
        host = (urlparse(u).hostname or "").lower()
        # Skip search-internal links, social etc — те что наш URL_BAD_HOST_RE дропнет
        if "yandex." in host or "google." in host or "/clck/" in u:
            continue
        # Cap 2 per host чтобы один источник не залил SERP
        if seen_hosts.get(host, 0) >= 2:
            continue
        seen_hosts[host] = seen_hosts.get(host, 0) + 1
        results.append(u)
        if len(results) >= max_results:
            break
    _cache_set("yx:" + query, results)
    return results


# Backward-compat alias — старые вызовы yandex_search() автоматически
# используют SearXNG. Можно удалить когда убедимся что всё работает.
yandex_search = searxng_search


# === Direct scrape RU travel sites ===
# Per-domain CSS hints — для топ RU news/press страниц с известной структурой.
# Каждый паттерн ищет ссылки на article-страницы в HTML списка новостей.
# При отсутствии хоста в этом словаре — fallback на generic <a> + URL-фильтр.
DOMAIN_LINK_SELECTORS: dict[str, str] = {
    # RU travel-trade (server-rendered HTML)
    "atorus.ru":          "a[href*='/news/']",
    "ratanews.ru":        "a[href*='/news/']",
    "tourdom.ru":         "a[href*='/news/']",
    # RU bank/business analytics
    "gazprombank.ru":     "a[href*='/press/']",
    "raiffeisen.ru":      "a[href*='/about/press/']",
    "finversia.ru":       "a[href*='/news/']",
    "kommersant.ru":      "a[href*='/doc/']",
    # Aeroflot (через ru-fetch + xray RU IP)
    "aeroflot.ru":        "a[href*='/news/']",
    # ── New (2026-05-07): re-enabled with browser-fallback ru-fetch ──
    "frankrg.com":        "a.news-card",
    "banki.ru":           "a[href*='/news/'][href*='/lenta/'], a[href*='/news/daytheme/'], a[href*='/news/?'][class*='news']",
    "tbank.ru":           "a[href*='/about/news/'], a[href*='/blog/tag/news/']",
    "tinkoff.ru":         "a[href*='/about/news/'], a[href*='/blog/tag/news/']",
    "vtb.ru":             "a[href*='/about/press/'], a[href*='/personal/investicii/press/']",
}


def _scrape_fetch_html(label: str, page_url: str) -> str:
    """Fetch listing HTML.

    Pipeline:
      1. urllib (быстро, без proxy)
      2. Если urllib дал <500 байт ИЛИ упал — fallback на ru-fetch --curl-only
         (идёт через xray SOCKS5 = RU IP, помогает на geo-blocked сайтах вроде
         Aeroflot. Без Chromium → RAM-безопасно).
    """
    # SPA-only hosts: skip urllib (returns shell only), go straight to ru-fetch+browser.
    SPA_HOSTS = ("tbank.ru", "tinkoff.ru", "aeroflot.ru", "alfabank.ru", "sber.ru",
                 "sberbank.ru", "press.sberbank.ru", "mts.ru", "mtsbank.ru")
    base_host = (urlparse(page_url).hostname or "").lower().replace("www.", "")
    is_spa = any(h in base_host for h in SPA_HOSTS)

    first_err = ""
    if not is_spa:
        # Step 1: plain urllib
        try:
            req = urllib.request.Request(page_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                html = r.read().decode("utf-8", errors="replace")
            if html and len(html) >= 500:
                return html
        except Exception as e:
            first_err = str(e)[:80]
        else:
            first_err = "urllib returned too small"
    else:
        first_err = "SPA host - skip urllib"

    # Step 2: ru-fetch fallback (RU IP via xray + browser fallback for SPA)
    # Для SPA-hosts (tbank/aeroflot/sber/alfa) форсируем --browser, потому что
    # curl возвращает несколько-сот-KB shell-HTML, который проходит size-check
    # но не содержит реальных news-карточек (рендерятся JS).
    cmd = [RU_FETCH_BIN, page_url]
    if is_spa:
        cmd.append("--browser")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, timeout=90,
        )
        html = result.stdout.decode("utf-8", "replace")
        if html and len(html) >= 500:
            print(f"SC [{label}] urllib fail ({first_err}); ru-fetch OK ({len(html)} bytes)",
                  file=sys.stderr)
            return html
        print(f"SC ERR [{label}] urllib fail ({first_err}); ru-fetch also small ({len(html)} bytes)",
              file=sys.stderr)
        return ""
    except Exception as e:
        print(f"SC ERR [{label}] urllib fail ({first_err}); ru-fetch fail ({str(e)[:60]})",
              file=sys.stderr)
        return ""


def scrape_news_page(label: str, page_url: str, max_links: int = 15) -> list[dict]:
    """urllib + BS4 + per-domain CSS hints. Без Chromium, без _BROWSER_LOCK.
    Fallback на ru-fetch (xray RU IP) если urllib не сработал.
    """
    cached = _cache_get("scrape:" + page_url)
    if cached is not None:
        return cached

    html = _scrape_fetch_html(label, page_url)
    if not html:
        _cache_set("scrape:" + page_url, [])
        return []

    base_host = (urlparse(page_url).hostname or "").lower().replace("www.", "")
    out: list[dict] = []
    seen: set[str] = set()

    if _has_bs4():
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # Find per-domain selector
        selector = None
        for hint_host, css in DOMAIN_LINK_SELECTORS.items():
            if hint_host in base_host:
                selector = css
                break

        anchors = soup.select(selector) if selector else soup.find_all("a")
        for a in anchors:
            href = (a.get("href") or "").strip()
            title = " ".join(a.get_text(" ", strip=True).split())
            if not href or len(title) < 15:
                continue
            if href.startswith("/"):
                href = urljoin(page_url, href)
            elif not href.startswith("http"):
                continue
            host = (urlparse(href).hostname or "").lower().replace("www.", "")
            if base_host not in host:
                continue
            if href in seen:
                continue
            if re.search(r"/(category|tag|page|search|login|about|contact|privacy|terms|sitemap|rss|feed)/?$",
                         href, re.I):
                continue
            seen.add(href)
            out.append({"title": title, "url": href})
            if len(out) >= max_links:
                break
    else:
        # Fallback: original regex (без BS4)
        for m in re.finditer(r'<a[^>]+href="(https?://[^"\s]+)"[^>]*>([^<]{15,200})</a>', html):
            u, title = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            host = (urlparse(u).hostname or "").lower().replace("www.", "")
            if base_host not in host:
                continue
            if u in seen:
                continue
            seen.add(u)
            if re.search(r"/(category|tag|page|search|login|about|contact|privacy|terms)/?", u, re.I):
                continue
            out.append({"title": title, "url": u})
            if len(out) >= max_links:
                break

    _cache_set("scrape:" + page_url, out)
    return out


_BS4_AVAILABLE: bool | None = None


def _has_bs4() -> bool:
    global _BS4_AVAILABLE
    if _BS4_AVAILABLE is None:
        try:
            import bs4  # noqa: F401
            _BS4_AVAILABLE = True
        except ImportError:
            _BS4_AVAILABLE = False
    return _BS4_AVAILABLE


# Маркеры anti-bot/captcha — детектируем до классификации, чтобы агент Stage-2
# не пытался переводить «JavaScript is disabled» как заголовок статьи.
ANTIBOT_MARKERS_RE = re.compile(
    r"just\s*a\s*moment|cloudflare|attention\s*required|"
    r"javascript\s*is\s*disabled|включите\s*javascript|"
    r"captcha|are\s*you\s*human|please\s*verify|"
    r"window\.__PRELOADED_|window\.NUXT_DATA|"
    r"страница\s*не\s*найдена|access\s*denied|доступ\s*ограничен",
    re.I,
)


def _strip_html(raw: str, max_chars: int) -> str:
    """BS4-based article extraction — берёт ТОЛЬКО семантический контент.

    Подход взят из crawl4ai/frontier-intelligence:
      1. Парсим HTML через lxml.
      2. Удаляем noise: <script>, <style>, <nav>, <header>, <footer>, <aside>,
         <form>, <iframe>, <noscript>, и блоки с класс/id-маркерами навигации.
      3. Извлекаем ТОЛЬКО h1-h4, p, li, blockquote — это всегда article body.
      4. Конкатенируем с разделителем, обрезаем до max_chars.

    Что это решает (вс прошлый regex-strip):
      • RBC/Vedomosti sidebar — раньше тащил «Финансы / Карты / Вклады», что
        путало агента Stage-2 в classify (видел banking-keywords из навигации).
      • Rambler/HowTrip — раньше тащил window.__PRELOADED_ JS-инлайны.
      • ATOR/RATA category pages — раньше тащил «Перейти к основному
        содержанию ... Главное меню ...» как «текст статьи».

    Антибот-детект: если в очищенном тексте ANTIBOT_MARKERS_RE — возвращаем
    пустую строку (Stage-2 такие items дропает).

    Fallback: если BS4 недоступен (на не-server машинах в тестах) — старый
    regex-стрип без noise-фильтрации.
    """
    if not raw:
        return ""
    if _has_bs4():
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw, "lxml")
            # Cloudflare check на title — анти-бот стабы у них в <title>
            t_el = soup.find("title")
            if t_el:
                tt = (t_el.get_text(" ", strip=True) or "").lower()
                if "just a moment" in tt or "attention required" in tt:
                    return ""
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "form", "iframe", "noscript", "svg",
                             "button", "select"]):
                tag.decompose()
            for sel in ("[class*='menu']", "[class*='nav']",
                        "[class*='footer']", "[class*='header']",
                        "[class*='sidebar']", "[class*='breadcrumb']",
                        "[class*='cookie']", "[id*='nav']", "[id*='menu']"):
                for el in soup.select(sel):
                    el.decompose()
            chunks: list[str] = []
            for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li",
                                     "blockquote"]):
                t = el.get_text(" ", strip=True)
                if t and len(t) >= 8:
                    chunks.append(t)
            text = " ".join(chunks)
            text = " ".join(text.split())
            # Anti-bot detect ПОСЛЕ extract — на чистом тексте
            if ANTIBOT_MARKERS_RE.search(text[:2000]):
                return ""
            return text[:max_chars]
        except Exception:
            pass
    # Fallback: regex strip
    raw2 = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw2 = re.sub(r"<style[^>]*>.*?</style>", " ", raw2, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", raw2)
    text = " ".join(text.split())
    if ANTIBOT_MARKERS_RE.search(text[:2000]):
        return ""
    return text[:max_chars]


def _fetch_via_urllib(url: str, max_chars: int) -> str:
    """Direct urllib fetch. Fast, no-proxy. For non-RU domains."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read(200_000).decode("utf-8", "replace")
    except Exception:
        return ""
    return _strip_html(raw, max_chars)


def _fetch_via_bypass(url: str, max_chars: int) -> str:
    """Call ~/bypass/bin/ru-fetch --curl-only через subprocess.

    --curl-only ВАЖНО: блокирует browser fallback. Иначе Phase 2 (3 parallel workers)
    могла бы спавнить 3 Chromium'а одновременно при ServicePipe-сайтах, что грозит OOM
    (3 × 250 МБ Chromium на VPS с 1.9 GB).

    Tradeoff: ServicePipe-protected сайты (alfabank, иногда другие) вернут пустой текст
    — но title и URL у нас есть, агент стадии 2 справится.

    Browser-fallback всё ещё доступен для Phase 1 операций (Yandex/scrape/GN-resolve)
    через _BROWSER_LOCK semaphore — 1 Chromium за раз.
    """
    try:
        result = subprocess.run(
            [RU_FETCH_BIN, url, "--curl-only"],
            capture_output=True, timeout=20,
        )
        raw = result.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""
    if not raw:
        return ""
    return _strip_html(raw, max_chars)


def _fetch_via_trafilatura(url: str, max_chars: int) -> str:
    """Pure-Python article extractor — лучше BS4 на JS-heavy сайтах
    (Skift, PhocusWire, devdiscourse и пр.), без Chromium.

    Использует trafilatura.fetch_url + extract. Если pkg не доступен или
    extract вернул < 200 символов — возвращает "".
    """
    try:
        import trafilatura
    except Exception:
        return ""
    try:
        html = trafilatura.fetch_url(url, no_ssl=False)
        if not html:
            return ""
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            with_metadata=False,
        )
        if not text or len(text) < 200:
            return ""
        # Anti-bot detect
        if ANTIBOT_MARKERS_RE.search(text[:2000]):
            return ""
        return text[:max_chars]
    except Exception:
        return ""


def fetch_text(url: str, max_chars: int = ARTICLE_MAX_CHARS) -> str:
    """Domain-routed text fetch:
      - Try trafilatura first (Pure Python, handles JS-heavy sites well)
      - RU bank/news/travel domains → ru-fetch (SOCKS5 + browser fallback)
      - All other domains → direct urllib
    """
    if not url:
        return ""
    # 1. Try trafilatura first — best on JS-heavy modern news sites
    txt = _fetch_via_trafilatura(url, max_chars)
    if txt:
        return txt
    # 2. Domain-routed fallback
    host = _domain(url)
    if host and RU_DOMAIN_RE.search(host):
        return _fetch_via_bypass(url, max_chars)
    return _fetch_via_urllib(url, max_chars)


# ── Search queries (Google News RSS) ───────────────────────────────────
# RU travel-banking heavy: банки → premium-карты → travel-фичи.
QUERIES = [
    # ─── RU: банки × travel (премиум-карты, кэшбэк, lounge) ────────────
    "Сбер travel премиум when:3d",
    "СберПрайм travel when:3d",
    "СберПрайм путешествия when:3d",
    "СберТревел when:3d",
    "Тинькофф Premium travel when:3d",
    "Тинькофф premium карта travel when:3d",
    "T-Bank премиум travel when:3d",
    "ВТБ Прайм travel when:3d",
    "ВТБ Привилегия travel when:3d",
    "Альфа-Премиум travel when:3d",
    "Альфа-Банк премиум карта when:3d",
    "Газпромбанк премиум travel when:3d",
    "Райффайзен Premium Direct when:3d",
    "Райффайзен премиум travel when:3d",
    "МТС Банк premium travel when:3d",
    "Яндекс Плюс travel when:3d",
    "Яндекс Плюс путешествия when:3d",
    # Travel-банковские продукты общие
    "банк travel кэшбэк карта when:3d",
    "банк лаунж аэропорт карта when:3d",
    "премиальная карта банк Россия when:3d",
    "банковская карта путешествия when:3d",
    "консьерж сервис банк премиум when:3d",
    "банк подписка travel when:3d",
    "travel-страхование банк when:3d",
    "мили программа лояльности банк when:3d",
    "DragonPass MirPass банк when:3d",
    "PriorityPass банковская карта when:3d",
    # site: queries для прямого поиска по доменам банков
    "site:tinkoff.ru travel when:3d",
    "site:tbank.ru travel when:3d",
    "site:tbank.ru премиум when:3d",
    "site:sber.ru travel when:3d",
    "site:sberbank.ru премьер when:3d",
    "site:vtb.ru travel when:3d",
    "site:alfabank.ru travel when:3d",
    "site:gazprombank.ru премиум when:3d",
    "site:raiffeisen.ru premium when:3d",
    "site:tinkoff.ru lounge when:3d",
    "site:sber.ru подписка when:3d",
    # ─── RU: travel-индустрия общая ──────────────────────────────────
    "туризм Россия новости when:3d",
    "путешествия Россия 2026 when:3d",
    "Аэрофлот новости when:3d",
    "S7 Airlines новости when:3d",
    "Победа авиа when:3d",
    "Россия авиалинии when:3d",
    "Aviasales новости when:3d",
    "OneTwoTrip when:3d",
    "Tutu.ru новости when:3d",
    "Ostrovok новости when:3d",
    "Яндекс Путешествия when:3d",
    "Booking бронирование Россия when:3d",
    "отели открытие Россия when:3d",
    "Ростуризм Russia tourism when:3d",
    "АТОР туристические when:3d",
    "international flights Russia 2026 when:3d",
    "виза туризм Россия 2026 when:3d",
    # ─── RU: AI × travel ──────────────────────────────────────────────
    "ИИ турагент when:3d",
    "ИИ планирование путешествий when:3d",
    "AI travel Россия when:3d",
    "ИИ travel банк when:3d",
    "нейросеть travel путешествия when:3d",
    "генеративный AI travel when:3d",
    "GPT путешествия when:3d",
    "ChatGPT путешествия when:3d",
    "AI бронирование отелей Россия when:3d",
    # ─── EN: AI × travel ─────────────────────────────────────────────
    "AI travel when:3d",
    "AI hotel booking when:3d",
    "AI flight booking when:3d",
    "AI itinerary planner when:3d",
    "AI travel agent launch when:3d",
    "AI travel concierge when:3d",
    "ChatGPT travel when:3d",
    "Gemini travel when:3d",
    "AI hospitality when:3d",
    "AI customer service hotel when:3d",
    # ─── broader AI × travel (added 2026-06-08, balance) ─────────────
    "agentic AI travel booking when:3d",
    "AI trip planning startup when:3d",
    "AI travel app launch when:3d",
    "AI travel assistant when:3d",
    "AI travel personalization when:3d",
    "AI турпланировщик when:3d",
    "нейросеть для путешествий when:3d",
    "ИИ ассистент путешествия when:3d",
    # ─── EN: travel-banking ──────────────────────────────────────────
    "credit card travel rewards launch when:3d",
    "premium card launch travel when:3d",
    "co-branded travel card when:3d",
    "lounge access bank card when:3d",
    "travel insurance bank card when:3d",
    "FX card multi-currency when:3d",
    "neobank travel when:3d",
    "private banking travel when:3d",
    "travel cashback card when:3d",
    "airline credit card launch when:3d",
    # ─── EN: travel-industry ─────────────────────────────────────────
    "Booking.com when:3d",
    "Expedia news when:3d",
    "Airbnb news when:3d",
    "Marriott news when:3d",
    "Hilton news when:3d",
    "Hyatt news when:3d",
    "Spirit Airlines when:3d",
    "Delta Airlines news when:3d",
    "United Airlines news when:3d",
    "Emirates news when:3d",
    "Lufthansa news when:3d",
    "Skift news when:3d",
    "PhocusWire when:3d",
    "travel industry news 2026 when:3d",
    "hotel industry layoffs when:3d",
    "OTA news when:3d",
    # ─── EN: payment networks × travel ───────────────────────────────
    "Visa travel when:3d",
    "Mastercard travel when:3d",
    "American Express travel when:3d",
    "Revolut travel when:3d",
    "Wise travel when:3d",
    "Chase Sapphire when:3d",
    "Capital One travel when:3d",
    # ─── EN: Phase A — конференции / индустрия / M&A / regulation ─────
    "Phocuswright Conference when:3d",
    "Skift Forum when:3d",
    "ITB Berlin 2026 when:3d",
    "WTM London when:3d",
    "Money2020 travel when:3d",
    "travel M&A 2026 when:3d",
    "travel fintech funding when:3d",
    "corporate travel platform when:3d",
    "Navan launch when:3d",
    "Spotnana when:3d",
    "Egencia Amex GBT when:3d",
    "DOT airline rule 2026 when:3d",
    "EU travel regulation 2026 when:3d",
    "hospitality tech 2026 when:3d",
    "Mews Cloudbeds when:3d",
    "travel layoffs 2026 when:3d",
    "OTA earnings 2026 when:3d",
    "travel startup acquisition when:3d",
    "Sabre Amadeus Travelport when:3d",
    # ─── RU: Phase A — site: на банковские press / RU аналитику ───────
    "site:pressa.sber.ru travel when:3d",
    "site:pressa.sber.ru премиум when:3d",
    "site:journal.tinkoff.ru travel when:3d",
    "site:frankrg.com банк travel when:3d",
    "site:vtb.ru travel премиум when:3d",
    "site:tbank.ru lounge when:3d",
    # ─── RU: Phase B — конкретные launch/event сценарии (концентрат) ──
    "Тинькофф путешествия запуск when:3d",
    "Тинькофф premium запуск travel when:3d",
    "T-Bank премиум travel запуск when:3d",
    "T-Bank путешествия запуск when:3d",
    "Сбер премьер travel запуск when:3d",
    "Сбер премьер travel сервис when:3d",
    "СберПрайм travel новый when:3d",
    "СберТревел запуск when:3d",
    "Альфа premium travel запуск when:3d",
    "Альфа-Банк premium travel when:3d",
    "ВТБ Привилегия travel запуск when:3d",
    "ВТБ Прайм travel запуск when:3d",
    "Газпромбанк премиум travel запуск when:3d",
    "Райффайзен премиум travel запуск when:3d",
    "МТС Travel запуск when:3d",
    "МТС Premium travel when:3d",
    "Яндекс Плюс travel запуск when:3d",
    "Озон Банк travel when:3d",
    "Wildberries Банк travel when:3d",
    "Совкомбанк Халва travel when:3d",
    "Почта Банк travel премиум when:3d",
    "ПСБ travel премиум when:3d",
    "Открытие банк travel when:3d",
    "Росбанк travel премиум when:3d",
    "Уралсиб travel премиум when:3d",
    # ─── RU: AI × travel × банк — концентрат ───────────────────────────
    "ИИ консьерж банк премиум when:3d",
    "AI планировщик путешествий банк when:3d",
    "AI ассистент travel банк Россия when:3d",
    "нейросеть travel банк запуск when:3d",
    "GenAI travel Россия банк when:3d",
    "AI бронирование банк premium Россия when:3d",
]


# ── Direct RSS feeds from tier-1 publishers (NOT via Google News) ──────
# Каждый URL проверен — feeds.reuters.com мёртв (DNS fail), убран.
# RATA/Tourdom 404 на их публичных путях — убраны.
# PhocusWire/Travel Weekly/PYMNTS отдают 403 на curl-style requests — убраны
# (их новости всё равно попадают через Google News).
TIER1_FEEDS = [
    # ─── International business / tech press ───────────────────────────
    ("Bloomberg Tech",        "https://feeds.bloomberg.com/technology/news.rss"),
    ("TechCrunch",            "https://techcrunch.com/feed/"),
    ("TechCrunch Transport",  "https://techcrunch.com/category/transportation/feed/"),
    ("WIRED Business",        "https://www.wired.com/feed/category/business/latest/rss"),
    ("Ars Technica AI",       "https://arstechnica.com/ai/feed/"),
    ("VentureBeat AI",        "https://venturebeat.com/category/ai/feed/"),
    # ─── RU general financial (фильтр оставит travel) ──────────────────
    ("Kommersant Финансы",    "https://www.kommersant.ru/RSS/section-finance.xml"),
    ("RBC Финансы",           "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("RBC Технологии",        "https://rssexport.rbc.ru/rbcnews/news/27/full.rss"),
    ("Vedomosti Бизнес",      "https://www.vedomosti.ru/rss/rubric/business"),
    ("Vedomosti Финансы",     "https://www.vedomosti.ru/rss/rubric/finance"),
    ("Vedomosti Технологии",  "https://www.vedomosti.ru/rss/rubric/technology"),
    ("Vedomosti Транспорт",   "https://www.vedomosti.ru/rss/rubric/business/transport"),
    ("Forbes RU",             "https://www.forbes.ru/newrss.xml"),
    ("The Bell",              "https://thebell.io/rss"),
    # ─── RU Habr (модерируемый, financial / banking / AI hubs) ─────────
    ("Habr Финансы",          "https://habr.com/ru/rss/hubs/finance/all/"),
    ("Habr ИИ",               "https://habr.com/ru/rss/hubs/artificial_intelligence/all/"),
    ("Habr Финтех",           "https://habr.com/ru/rss/hubs/fintech/all/"),
    # ─── International travel-trade tier-1 ─────────────────────────────
    ("Skift",                 "https://skift.com/feed/"),
    ("PhocusWire",            "https://www.phocuswire.com/RSS"),
    ("Travel Weekly",         "https://www.travelweekly.com/RSS"),
    # ─── International fintech-trade tier-1 ────────────────────────────
    ("Finextra",              "https://www.finextra.com/rss/headlines.aspx"),
    ("PYMNTS",                "https://www.pymnts.com/feed/"),
    ("FintechMagazine",       "https://fintechmagazine.com/rss/feed.xml"),
    # ─── RU banki.ru — официальная лента ───────────────────────────────
    ("Banki.ru новости",      "https://www.banki.ru/xml/news.rss"),
    ("Banki.ru daytheme",     "https://www.banki.ru/xml/daytheme.rss"),
    # ─── RU travel-trade RSS (вместо HTML scrape — SPA-сайты не парсятся) ──
    ("TASS общая",            "https://tass.ru/rss/v2.xml"),
    ("FrequentFlyers RSS",    "https://www.frequentflyers.ru/feed/"),
    # ─── EXPANDED 2026-05-08: travel-trade verticals ─────────────────
    ("Skift Hospitality",     "https://skift.com/category/hospitality/feed/"),
    ("Skift Tech",            "https://skift.com/category/business-of-loyalty/feed/"),
    ("Skift Travel Tech",     "https://skift.com/category/travel-tech/feed/"),
    ("Hospitality Net",       "https://www.hospitalitynet.org/news/list.rss"),
    ("Hotel News Resource",   "https://www.hotelnewsresource.com/rss/news.xml"),
    ("Hotel Management",      "https://www.hotelmanagement.net/rss.xml"),
    ("Travel Daily News",     "https://www.traveldailynews.com/feed/"),
    ("Travel Daily Asia",     "https://www.traveldailymedia.com/feed/"),
    ("Tnooz",                 "https://www.tnooz.com/feed/"),
    ("HotelierAcademy",       "https://hotelieracademy.com/feed/"),
    # ─── International fintech-trade ─────────────────────────────────
    ("The Banker",            "https://www.thebanker.com/Feed"),
    ("Banking Technology",    "https://www.bankingtech.com/feed/"),
    ("Fintech Futures",       "https://www.fintechfutures.com/feed/"),
    ("The Paypers",           "https://thepaypers.com/index.cfm?xml/news.xml"),
    ("AltFi",                 "https://www.altfi.com/feed/news"),
    # ─── Aviation industry ───────────────────────────────────────────
    ("Aviation Week",         "https://aviationweek.com/rss.xml"),
    ("Routes Online",         "https://www.routesonline.com/rss/news/"),
    ("AeroTime News",         "https://www.aerotime.aero/rss.xml"),
    ("ATW Online",            "https://atwonline.com/feed"),
    # ─── RU дополнительные ──────────────────────────────────────────
    ("RBC Деньги",            "https://rssexport.rbc.ru/rbcnews/news/4/full.rss"),
    ("RBC Бизнес",            "https://rssexport.rbc.ru/rbcnews/news/29/full.rss"),
    ("Aviasales Блог",        "https://www.aviasales.ru/blog/feed/"),
    ("Tutu RSS",              "https://www.tutu.ru/rss/news.xml"),
    # ─── Tech / AI broad ────────────────────────────────────────────
    ("MIT Tech Review AI",    "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("The Verge AI",          "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("ZDNet AI",              "https://www.zdnet.com/topic/artificial-intelligence/rss.xml"),
]
TIER1_FEED_LIMIT = 15  # больше items — keyword-filter их пробежит и оставит только travel


# === Google News fresh themes (mode=google) ===
# Свежие тематические запросы (when:3d) для расширенного покрытия зарубежных
# кейсов AI-в-travel и travel-в-банкинге. Параллельно с QUERIES (которые узко
# заточены под RU банки) — этот список тематически-широкий, EN-heavy, и работает
# в режиме "что нового за последние 24ч". Логика заимствована из проверенной
# TrendWatch (trendwatch_collect.py::EXTRA_QUERIES + дополнения).
#
# Auto-locale: кириллица в query → hl=ru&gl=RU, иначе → hl=en-US&gl=US.
# Все queries проходят те же фильтры что и QUERIES (URL_BAD_HOST_RE,
# _is_travel_topic, _trust_score, _classify_case_type).
GOOGLE_FRESH_QUERIES = [
    # ─── EN: broad themes (свежие зарубежные кейсы) ─────────────────────
    "travel payment solution launch when:3d",
    "hospitality technology AI when:3d",
    "airline fintech partnership when:3d",
    "hotel booking AI platform when:3d",
    "corporate travel management AI when:3d",
    "travel loyalty program launch when:3d",
    "travel insurance fintech when:3d",
    "digital wallet travel feature when:3d",
    "open banking travel when:3d",
    "travel tech startup funding when:3d",
    "OTA artificial intelligence feature when:3d",
    "metasearch AI travel when:3d",
    "revenue management AI hotel when:3d",
    "chatbot travel booking launch when:3d",
    "travel app AI feature when:3d",
    "embedded finance travel when:3d",
    "travel fintech acquisition when:3d",
    "contactless payment hotel when:3d",
    "virtual card travel launch when:3d",
    "travel rewards AI when:3d",
    "AI travel agent startup when:3d",
    "neobank travel feature when:3d",
    "airline AI assistant launch when:3d",
    "hotel AI personalization when:3d",
    "co-branded travel credit card when:3d",
    "bank travel partnership announce when:3d",
    "travel concierge AI launch when:3d",
    # ─── EN: company-specific (зарубежные крупные игроки) ────────────────
    "Lufthansa digital innovation when:3d",
    "Emirates AI travel when:3d",
    "Marriott technology launch when:3d",
    "Hilton AI feature when:3d",
    "Airbnb AI feature when:3d",
    "Grab travel fintech when:3d",
    "Paytm travel when:3d",
    "Agoda AI when:3d",
    "Capital One travel feature when:3d",
    "Revolut Stays when:3d",
    "Wise travel when:3d",
    "Klarna travel when:3d",
    "Visa travel announce when:3d",
    "Mastercard travel feature when:3d",
    "Amex travel launch when:3d",
    "Chase Sapphire travel when:3d",
    "Booking.com AI launch when:3d",
    "Expedia AI feature when:3d",
    "MakeMyTrip launch when:3d",
    "Trip.com AI when:3d",
    # ─── RU: дополнительные свежие темы ──────────────────────────────────
    "цифровой банк путешествия запуск when:3d",
    "кешбэк путешествия банк when:3d",
    "оплата отель финтех when:3d",
    "туризм искусственный интеллект запуск when:3d",
    "travel карта банк when:3d",
    "ИИ ассистент путешествия when:3d",
    "банк лаунж аэропорт новости when:3d",
]


# === Yandex search queries (RU travel-banking фокус) ===
# Каждый запрос идёт через yandex.ru/search → ru-fetch+browser → парс HTML.
# Sequential через _BROWSER_LOCK, кешируется на 24ч. Лимит 12 чтобы runtime
# оставался разумным (~60-90 секунд на этот phase).
YANDEX_QUERIES = [
    # ======================================================================
    # ЧАСТЬ 1: TARGETED — site: на top-источники.
    # Эти запросы идут ПЕРВЫМИ — даже если поток обрежется time-budget'ом,
    # топ-источники гарантированно опрошены.
    # ======================================================================

    # ── RU bank press releases (8) ──
    "site:press.sberbank.ru travel",
    "site:tbank.ru/about/news travel",
    "site:vtb.ru/about/press-relizy travel",
    "site:alfabank.ru/about/press travel",
    "site:gazprombank.ru/press-center travel",
    "site:raiffeisen.ru/about/press travel",
    "site:mtsbank.ru/about/press travel",
    "site:sovcombank.ru/news travel",

    # ── RU tier-1 business press (8) ──
    "site:rbc.ru AI travel",
    "site:rbc.ru travel банк",
    "site:vedomosti.ru travel банк",
    "site:vedomosti.ru AI travel",
    "site:kommersant.ru travel банк",
    "site:forbes.ru AI travel",
    "site:thebell.io travel",
    "site:banki.ru/news travel премиум",

    # ── RU travel-trade (4) ──
    "site:atorus.ru/news travel",
    "site:ratanews.ru travel банк",
    "site:tourdom.ru AI travel",
    "site:frequentflyers.ru карта",

    # ── EN tier-1 travel-trade (5) ──
    "site:skift.com AI travel",
    "site:skift.com co-brand",
    "site:phocuswire.com AI",
    "site:phocuswire.com banking",
    "site:travelweekly.com AI",

    # ── EN tier-1 fintech / business (5) ──
    "site:bloomberg.com travel AI",
    "site:techcrunch.com travel AI",
    "site:reuters.com travel banking",
    "site:finextra.com travel",
    "site:pymnts.com travel",

    # ======================================================================
    # ЧАСТЬ 2: КОНЦЕПТ-ЗАПРОСЫ (без брендов — для discovery новых источников)
    # ======================================================================

    # ── 1A. Travel в банкинге — концепции RU (15) ──
    "кэшбэк за путешествия карта банк",
    "travel-карта премиум банк запуск",
    "мили за билеты программа лояльности",
    "co-brand карта банк авиалиния",
    "премиум карта lounge консьерж",
    "DragonPass PriorityPass карта",
    "travel-страхование банковская карта",
    "мультивалютная карта путешествия",
    "карта frequent flyer Россия",
    "банковская премиальная программа",
    "miles программа банк Россия",
    "кешбэк отели бронирование банк",
    "карта премьер travel-привилегии",
    "консьерж-сервис премиум банк",
    "private banking путешествия Россия",

    # ── 1B. Travel в банкинге — концепции EN (15) ──
    "premium credit card travel benefits 2026",
    "co-brand airline credit card launch",
    "lounge access card 2026",
    "neobank travel features 2026",
    "travel fintech funding 2026",
    "premium card concierge travel",
    "miles rewards program update 2026",
    "multi-currency card travel 2026",
    "corporate travel payment card",
    "BNPL travel booking 2026",
    "frequent flyer program update 2026",
    "private banking travel concierge",
    "credit card travel insurance 2026",
    "premium banking travel partnership",
    "airline cobrand card 2026",

    # ── 2A. AI travel — концепции RU (15) ──
    "AI ассистент бронирование отелей",
    "нейросеть планирование путешествий",
    "ChatGPT туризм 2026",
    "генеративный ИИ туризм",
    "AI-сервис подбора отелей запуск",
    "AI-консьерж путешествия 2026",
    "GPT-чат-бот авиабилеты",
    "LLM туризм запуск",
    "нейросеть аэропорт пассажиры",
    "ИИ агент бронирование",
    "AI динамическое ценообразование отели",
    "автоматизация туризма AI",
    "AI-помощник путешественника",
    "нейросеть гостиничный бизнес",
    "AI рекомендация отелей бронирование",

    # ── 2B. AI travel — концепции EN (15) ──
    "AI travel agent launch 2026",
    "AI hotel booking startup 2026",
    "ChatGPT travel integration 2026",
    "generative AI hospitality 2026",
    "AI itinerary planner 2026",
    "AI travel concierge launch",
    "Gemini travel app",
    "Copilot travel booking",
    "LLM travel personalization",
    "AI hotel pricing dynamic",
    "AI airport passenger experience 2026",
    "AI airline customer service launch",
    "voice assistant travel booking",
    "AI travel SaaS funding 2026",
    "AI revenue management hospitality",

    # ── 3. AI+Banking+Travel — концепции (5 RU + 5 EN) ──
    "AI-ассистент банк путешествия",
    "нейросеть travel-кэшбэк банк",
    "AI программа лояльности banking travel",
    "AI-чат-бот премиум карта путешествия",
    "ИИ travel-сервис банк",
    "AI travel banking integration 2026",
    "fintech AI travel launch 2026",
    "AI loyalty program travel banking",
    "ChatGPT bank travel concierge",
    "AI co-brand travel card 2026",

    # ── 4. Entity tracking — конкретные бренды (RU + EN) (25) ──
    "Marriott Bonvoy AI launch",
    "Booking GenAI rollout",
    "Expedia ChatGPT integration",
    "Airbnb AI search launch",
    "Hilton Honors AI",
    "Hyatt loyalty AI",
    "Trip.com AI assistant",
    "Hopper AI launch 2026",
    "Kayak Gemini AI",
    "TripAdvisor AI features",
    "Аэрофлот Бонус карта 2026",
    "S7 Airlines Premium Visa",
    "Pobeda Airlines программа",
    "СберТревел запустил",
    "Тинькофф Travel премиум",
    "Альфа-Тревел запуск",
    "Яндекс Путешествия премиум",
    "Visa airline partnership 2026",
    "Mastercard travel rewards 2026",
    "American Express Platinum 2026",
    "Chase Sapphire Reserve update 2026",
    "Capital One Venture X 2026",
    "Revolut Stays expansion",
    "Wise multi-currency travel",
    "Klarna travel partner",

    # ── 5. Events / regulation / M&A — индустрия (15) ──
    "Money2020 travel fintech 2026",
    "Phocuswright Conference 2026",
    "Skift Forum 2026 keynote",
    "ITB Berlin 2026 keynote",
    "WTM London 2026",
    "DOT airline rule 2026",
    "EU travel regulation 2026",
    "Russia tourism regulation 2026",
    "travel M&A 2026",
    "Navan launch 2026",
    "Spotnana announcement",
    "Egencia Amex GBT 2026",
    "Sabre Amadeus Travelport 2026",
    "travel layoffs 2026",
    "OTA earnings 2026",
]
# Total: 30 site: + 90 concept + 25 entity + 15 events = 160 queries.
# (Чуть больше 150 — оставлено как breathing room для будущих добавлений
# отраслевых сюжетов; circuit breaker сам обрежет если engines начнут троттлить.)
#
# V8 OOM физически невозможен после миграции Stage-1 в system crontab —
# script-процесс независим от gateway heap.


# === Direct scrape pages (HTML-listing) ===
# Проверены 2026-05-06. SPA-сайты (Tinkoff/Alfa/MTS/FrankRG/Aviasales) убраны —
# они отдают 1-2 КБ без JS, CSS-парсинг бесполезен. TASS и FrequentFlyers
# перенесены в TIER1_FEEDS как RSS (надёжнее).
RU_SCRAPE_PAGES = [
    # ── Travel-trade (server-rendered HTML, working) ──
    ("Tourdom news",        "https://www.tourdom.ru/news/"),
    ("ATOR press",          "https://www.atorus.ru/news/press-centre"),
    ("RATA news",           "https://ratanews.ru/news/"),

    # ── Bank/business analytics (working with urllib) ──
    ("Gazprombank",         "https://www.gazprombank.ru/press/"),
    ("Raiffeisen",          "https://www.raiffeisen.ru/about/press/"),
    ("Finversia",           "https://www.finversia.ru/news"),
    ("Kommersant Бизнес",   "https://www.kommersant.ru/rubric/4"),

    # ── Sites accessible via xray (RU IP) — _scrape_via_bypass fallback ──
    ("Aeroflot news",       "https://www.aeroflot.ru/ru-ru/about/news_events/news"),

    # ── Re-enabled 2026-05-07 with browser-fallback ru-fetch ─────────
    ("FrankRG news",        "https://frankrg.com/news/"),
    ("Banki.ru news",       "https://www.banki.ru/news/"),
    ("VTB press",           "https://www.vtb.ru/about/press/"),
    # T-Bank / Aeroflot: SPA с XHR-news-list — даже browser-mode не пробивает.
    # Защемлено через прямой Google site:tbank.ru / site:tinkoff.ru в QUERIES.

    # ── DISABLED: SPA без JS-render (отдают 1-2 КБ или плохо парсятся) ──
    # ("Aviasales blog",      "https://www.aviasales.ru/blog/"),
    # ("Alfa press",          "https://alfabank.ru/about/press-center/"),
    # ("MTS Bank press",      "https://www.mtsbank.ru/about/press-center/"),
    # ("FrankRG news",        "https://frankrg.com/news/"),
    # ("Travel.ru news",      "https://travel.ru/news/"),  # SSL cert fail
    # ("TASS Туризм",         "https://tass.ru/turizm"),    # → перенесено в TIER1_FEEDS как RSS
    # ("FrequentFlyers",      "https://www.frequentflyers.ru/"),  # → TIER1_FEEDS RSS
    # ── DISABLED: full geo-block / anti-bot даже через xray ──
    # ("Sberbank press",      "https://press.sberbank.ru/news"),
    # ("VTB press",           "https://www.vtb.ru/about/press/"),
    # ("Sovcombank",          "https://sovcombank.ru/news"),
    # ("Open press",          "https://www.otkritie.com/press/news/"),
    # ("Banki.ru lenta",      "https://www.banki.ru/news/lenta/"),  # сильный anti-bot
    # ("S7 news",             "https://www.s7.ru/ru/about/news/"),  # url мёртв
]


# ── Pipeline ────────────────────────────────────────────────────────────
def collect_stubs(mode: str = "all") -> tuple[list[dict], list[dict], dict]:
    """Phase 1: collect raw {title,url,source,query,pub} stubs.

    mode:
      "collect" — только Google News + Direct RSS (~15с, 0 Chromium).
      "yandex"  — только Yandex search через ru-fetch+browser (~75с, 1 Chromium peak).
      "scrape"  — только direct scrape RU travel sites (~25с, 1 Chromium peak).
      "all"     — все 4 (legacy, ~150с, не для prod-cron).

    Каждый mode независим и не пересекается по нагрузке — это позволяет разнести
    их по разным cron-job'ам с интервалом 10 мин, чтобы gateway не тонул в
    долгом скрипте.
    """
    stubs: list[dict] = []
    seen: set[str] = set()
    errors: list[dict] = []
    stats = {"mode": mode,
             "google_news_queries": 0, "google_news_items": 0,
             "tier1_feeds": 0, "tier1_items": 0,
             "deduped": 0, "stubbed": 0}

    def push(title: str, url: str, source: str, query: str, pub: str) -> bool:
        if not url:
            return False
        # URL-shape blacklist: drops landing/product/login pages регардless of source.
        # Особенно полезно для Yandex search, который раньше тащил
        # sber.ru/travel/, alfabank.ru/.../alfa-travel-premium/ как «новости».
        if _is_bad_url_shape(url):
            stats["bad_url_shape_dropped"] = stats.get("bad_url_shape_dropped", 0) + 1
            return False
        # Strict topic filter: travel + (banking OR AI). Without travel-сигнала — skip.
        # См. _is_travel_topic — отбрасываем «Spirit Airlines» (pure travel),
        # «Сбер прибыль» (pure banking), «GPT-5 release» (pure AI).
        if title and not _is_travel_topic(title):
            stats["offtopic_dropped"] = stats.get("offtopic_dropped", 0) + 1
            return False
        n = _norm_url(url)
        if not n or n in seen:
            stats["deduped"] += 1
            return False
        seen.add(n)
        stubs.append({"title": title, "url": url, "source": source,
                      "query": query, "pub": pub})
        stats["stubbed"] += 1
        return True

    # Google News — detect language: Cyrillic → RU locale, else EN locale.
    # Google News in RU-locale returns ~0 results for EN queries; mixing locales
    # gives proper coverage on both sides.
    def _gn_url(q: str) -> str:
        is_ru = bool(re.search(r"[а-яА-ЯёЁ]", q))
        if is_ru:
            return f"https://news.google.com/rss/search?q={quote(q)}&hl=ru&gl=RU&ceid=RU:ru"
        return f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"

    do_collect = mode in ("all", "collect")
    do_yandex = mode in ("all", "yandex")
    do_scrape = mode in ("all", "scrape")
    do_google = (mode == "google")

    if not do_collect:
        QUERIES_iter = []
        TIER1_iter = []
    else:
        QUERIES_iter = QUERIES
        TIER1_iter = TIER1_FEEDS

    for q in QUERIES_iter:
        stats["google_news_queries"] += 1
        feed_url = _gn_url(q)
        try:
            req = urllib.request.Request(feed_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                root = ET.fromstring(r.read())
            items = root.findall("./channel/item")
            kept = 0
            stale = 0
            for it in items[:GOOGLE_NEWS_TOP_N]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                src_node = it.find("source")
                src = (src_node.text or "").strip() if src_node is not None else ""
                stats["google_news_items"] += 1
                if not _is_fresh(pub):
                    stale += 1
                    stats["stale_dropped"] = stats.get("stale_dropped", 0) + 1
                    continue
                if push(title, link, src, q, pub):
                    kept += 1
            print(f"GN [{q[:50]}]: total={len(items)} kept={kept} stale={stale}", file=sys.stderr)
        except Exception as e:
            errors.append({"query": q, "error": str(e)[:200]})
            print(f"GN ERR [{q[:30]}]: {e}", file=sys.stderr)

    # Direct tier-1 feeds
    for label, url in TIER1_iter:
        stats["tier1_feeds"] += 1
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                data = r.read()
            try:
                root = ET.fromstring(data)
            except ET.ParseError as e:
                print(f"T1 PARSE [{label}]: {e}", file=sys.stderr)
                continue
            items = root.findall("./channel/item")
            is_atom = False
            if not items:
                ns = "{http://www.w3.org/2005/Atom}"
                items = root.findall(f".//{ns}entry")
                is_atom = True
            kept = 0
            for it in items[:TIER1_FEED_LIMIT]:
                if is_atom:
                    ns = "{http://www.w3.org/2005/Atom}"
                    title = (it.findtext(f"{ns}title") or "").strip()
                    link_el = it.find(f"{ns}link")
                    link = link_el.get("href", "").strip() if link_el is not None else ""
                    pub = (it.findtext(f"{ns}updated") or "").strip()
                else:
                    title = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    pub = (it.findtext("pubDate") or "").strip()
                stats["tier1_items"] += 1
                if not _is_fresh(pub):
                    stats["stale_dropped"] = stats.get("stale_dropped", 0) + 1
                    continue
                if push(title, link, label, f"feed:{label}", pub):
                    kept += 1
            print(f"T1 [{label}]: total={len(items)} kept={kept}", file=sys.stderr)
        except Exception as e:
            errors.append({"feed": label, "error": str(e)[:200]})
            print(f"T1 ERR [{label}]: {e}", file=sys.stderr)

    # === Phase 1c: SearXNG search (multi-engine via self-hosted instance) ===
    # Safety guards для защиты VPS:
    #   1. Health-check перед началом — если контейнер мёртв, скипаем фазу
    #   2. Time budget 240 сек — обрезаем если cron-timeout приближается
    #   3. Circuit breaker — 10 подряд пустых результатов = engines троттлят, стоп
    #   4. Inter-query delay 250 ms — не bursting external engines
    #   5. site:queries в YANDEX_QUERIES идут ПЕРВЫМИ (приоритет высокого trust)
    if do_yandex:
        if not searxng_health_check():
            print("⚠ SearXNG health-check FAILED, skipping yandex-phase",
                  file=sys.stderr)
            stats["searxng_unhealthy"] = True
        else:
            # Apply --max-queries override (для ручного тестирования)
            queries_to_run = YANDEX_QUERIES
            if _MAX_QUERIES_OVERRIDE > 0:
                queries_to_run = YANDEX_QUERIES[:_MAX_QUERIES_OVERRIDE]
                print(f"⚠ --max-queries override: используем первые "
                      f"{len(queries_to_run)} из {len(YANDEX_QUERIES)} queries",
                      file=sys.stderr)
            print(f"\nSearXNG search ({len(queries_to_run)} queries, JSON API, "
                  f"delay={_QUERY_DELAY_OVERRIDE}s)…", file=sys.stderr)
            phase_start = time.time()
            # При 160 queries × ~1.5s avg + 0.2s delay = ~4.5 min.
            # Бюджет 6 мин — даёт headroom если engines подзависают, но без
            # риска cron-overlap (следующий cron только через 24 часа).
            phase_budget_sec = 360
            consecutive_empty = 0
            # 0-results — нормальная ситуация для site: query на тематический
            # домен (если за 3 дня нет travel-публикаций). Только 25 подряд =
            # красный флаг (engines троттлят).
            consecutive_empty_limit = 25
            for idx, q in enumerate(queries_to_run, 1):
                # Time budget check
                elapsed = time.time() - phase_start
                if elapsed > phase_budget_sec:
                    print(f"⚠ Time budget exceeded ({elapsed:.0f}s > {phase_budget_sec}s) "
                          f"at query {idx}/{len(queries_to_run)} — stopping early",
                          file=sys.stderr)
                    stats["yandex_truncated_at"] = idx
                    break
                # Circuit breaker — все engines забанили нас
                if consecutive_empty >= consecutive_empty_limit:
                    print(f"⚠ Circuit breaker: {consecutive_empty} consecutive "
                          f"empty results — engines throttling, stopping at query "
                          f"{idx}/{len(queries_to_run)}", file=sys.stderr)
                    stats["yandex_circuit_break_at"] = idx
                    break
                stats["yandex_queries"] = stats.get("yandex_queries", 0) + 1
                # site:queries — narrow scope, max 5 results достаточно
                # concept queries — wider, до 10
                max_n = 5 if "site:" in q.lower() else 10
                urls = searxng_search(q, max_results=max_n)
                if not urls:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0
                kept = 0
                for u in urls:
                    if push("", u, "SearXNG", f"sx:{q}", ""):
                        kept += 1
                stats["yandex_kept"] = stats.get("yandex_kept", 0) + kept
                # Чтобы не раздувать V8 heap у gateway — печатаем
                # каждый 5-й query, плюс final summary.
                if idx % 5 == 0 or idx == len(queries_to_run):
                    print(f"SX [{idx:>3}/{len(queries_to_run)}] {q[:35]:<35}: "
                          f"ret={len(urls):>2} kept={kept} (cum_kept={stats['yandex_kept']})",
                          file=sys.stderr)
                # Inter-query delay (override-able через --query-delay).
                # Default 0.2s, для щадящих тестов лучше 1.0+.
                time.sleep(_QUERY_DELAY_OVERRIDE)
            stats["yandex_phase_seconds"] = round(time.time() - phase_start, 1)
            print(f"SX phase done: {stats['yandex_queries']} queries, "
                  f"{stats['yandex_kept']} kept in {stats['yandex_phase_seconds']}s",
                  file=sys.stderr)

    # === Phase 1d: Direct scrape RU travel sites ===
    if do_scrape:
        print(f"\nScrape RU travel pages ({len(RU_SCRAPE_PAGES)} sites)…", file=sys.stderr)
        for label, page_url in RU_SCRAPE_PAGES:
            stats["scrape_pages"] = stats.get("scrape_pages", 0) + 1
            items = scrape_news_page(label, page_url)
            kept = 0
            for it in items:
                if push(it.get("title", ""), it.get("url", ""), label, f"scrape:{label}", ""):
                    kept += 1
            stats["scrape_kept"] = stats.get("scrape_kept", 0) + kept
            print(f"SC [{label}]: returned={len(items)} kept={kept}", file=sys.stderr)

    # === Phase 1e: Google News fresh themes (mode=google) ===
    # Свежие темы (when:3d) — отдельная опция от mode=collect, заточена под
    # зарубежные кейсы AI-в-travel и travel-в-банкинге. EN+RU auto-locale.
    if do_google:
        queries_to_run = GOOGLE_FRESH_QUERIES
        if _MAX_QUERIES_OVERRIDE > 0:
            queries_to_run = GOOGLE_FRESH_QUERIES[:_MAX_QUERIES_OVERRIDE]
            print(f"⚠ --max-queries override: {len(queries_to_run)}/"
                  f"{len(GOOGLE_FRESH_QUERIES)} queries", file=sys.stderr)
        print(f"\nGoogle News fresh themes "
              f"({len(queries_to_run)} queries, when:3d)…", file=sys.stderr)
        for q in queries_to_run:
            stats["google_news_queries"] += 1
            feed_url = _gn_url(q)
            try:
                req = urllib.request.Request(feed_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                    root = ET.fromstring(r.read())
                items = root.findall("./channel/item")
                kept = 0
                stale = 0
                for it in items[:GOOGLE_NEWS_TOP_N]:
                    title = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    pub = (it.findtext("pubDate") or "").strip()
                    src_node = it.find("source")
                    src = (src_node.text or "").strip() if src_node is not None else ""
                    stats["google_news_items"] += 1
                    if not _is_fresh(pub):
                        stale += 1
                        stats["stale_dropped"] = stats.get("stale_dropped", 0) + 1
                        continue
                    if push(title, link, src, q, pub):
                        kept += 1
                print(f"GF [{q[:50]}]: total={len(items)} kept={kept} stale={stale}",
                      file=sys.stderr)
            except Exception as e:
                errors.append({"query": q, "error": str(e)[:200]})
                print(f"GF ERR [{q[:30]}]: {e}", file=sys.stderr)

    return stubs, errors, stats


def cap_by_diversity(stubs: list[dict], budget: int) -> list[dict]:
    """Round-robin pick by source: prevent flood from one outlet."""
    by_src: dict[str, list[dict]] = {}
    for s in stubs:
        by_src.setdefault(s.get("source") or "_", []).append(s)
    out: list[dict] = []
    while len(out) < budget and any(by_src.values()):
        for src in list(by_src.keys()):
            if not by_src[src]:
                continue
            out.append(by_src[src].pop(0))
            if len(out) >= budget:
                break
    return out


# === Deterministic case_type classifier ===
# LLM на стадии 2 галлюцинирует "AI signal" чтобы засунуть item в категорию,
# даже когда AI там нет. Эта детерминированная regex-классификация на стадии 1
# даёт жёсткий контроль: case_type ставится ТОЛЬКО при явном keyword-сигнале
# в title или первых 1500 символах article_text.

_AI_KEYWORDS_RE = re.compile(
    r"\b(AI|ИИ|GPT[-\s]?\d*|ChatGPT|Gemini|Copilot|Claude|LLM|"
    r"AI[-\s]?агент|AI[-\s]?ассистент|AI[-\s]?помощник|AI[-\s]?чат[-\s]?бот|"
    r"ИИ[-\s]?агент|ИИ[-\s]?ассистент|ИИ[-\s]?помощник|"
    r"GenAI|Gen[\-\s]?AI|generative\s+AI|искусственн\w+\s+интеллект)\b|"
    r"\bнейросет\w*|нейронн\w+\s+сет|"
    r"machine\s+learning|deep\s+learning|"
    r"генеративн\w*\s+(?:AI|ИИ|модел|интеллект)",
    re.I,
)
_BANKING_KEYWORDS_RE = re.compile(
    # Bank brand names (RU + EN) — самый сильный сигнал
    r"\b(Сбер|Сбербанк|СберПрайм|СберТревел|Сбер\s*Travel|"
    r"Тинькофф|T[-\s]?Bank|TBank|T-?PRO|"
    r"ВТБ\b|ВТБ[-\s]?Прайм|ВТБ[-\s]?Привилегия|"
    r"Альфа[-\s]?Банк|Альфа[-\s]?Премиум|Альфа[-\s]?Тревел|Альфа[-\s]?Travel|"
    r"Газпромбанк|Газпром[-\s]?банк|"
    r"Райффайзен|Райфф?айзен[-\s]?банк|"
    r"МТС[-\s]?Банк|МТС[-\s]?Travel|МТС[-\s]?Тревел|"
    r"Открытие[-\s]?банк|Совкомбанк|Промсвязьбанк|Россельхозбанк|"
    r"Тинькофф[-\s]?Travel|Тинькофф[-\s]?Тревел|"
    r"Visa|Mastercard|Amex|American\s+Express|"
    r"Revolut|Klarna|N26|Monzo|Wise|Stripe|PayPal|"
    r"Яндекс[-\s]?Плюс|"
    r"СберПремьер|Сбер[-\s]?Премьер|"
    r"Альфа[-\s]?Премиум[-\s]?Direct)\b|"
    # Banking concepts (multi-word, чтобы не путать с обычными словами)
    r"\bкэшбэк\b|\bкешбэк\b|\bcashback\b|"
    r"программ[ыа]\s+лояльност|loyalty\s+program|frequent\s+flyer\s+program|"
    r"премиальн\w*\s+карт|premium\s+card|premier\s+card|"
    r"co[-\s]?brand\w*\s+(?:карт|card)|карт[аы]\s+(?:с\s+)?мил|"
    r"банков\w*\s+(?:карт|продукт|сервис|услуг|приложен)|"
    r"\bcredit\s+card\b|\bdebit\s+card\b|"
    r"\bmiles?\b|\bмили\b|reward\s+points|"
    r"DragonPass|PriorityPass|MirPass|MaxAirport|"
    r"\bлаундж\b|lounge\s+access|"
    r"travel[-\s]?страхов\w+|travel\s+insurance|"
    r"travel[-\s]?(?:карт|card)|travel[-\s]?cashback|travel[-\s]?кэшбэк|"
    # Bank in явном банковском контексте (не банкротство/банкомат/банкет)
    r"\bбанк(?:ов\w*|у|а|и|е|ом|ах)?\s+(?:объяв|запус|анонс|представ|"
    r"добав|интегр|подпис|сообщ|расши|предлаг|"
    r"совмест|partnership|сотруднич)|"
    r"банков\s+(?:России|РФ)|"
    r"\bbank\s+(?:launch|introduce|announce|unveil|partner|integrat)|"
    r"\bbanking\b|fintech|финтех|"
    r"\bnobank|neobank|необанк",
    re.I,
)
_TRAVEL_KEYWORDS_RE = re.compile(
    r"\bтуризм\w*|\bтурист\w*|\bтуроперат\w*|"
    r"путешеств\w*|поездк\w*|"
    r"отел[ьяиеёов]|\bhotel\w*|hospitality|гостиниц\w*|"
    r"авиа\w*|\bairline\w*|airway|\bflight\b|flights\b|перелёт\w*|перелет\w*|"
    r"\brail\b|\bтрэвел\w*|\btravel\b|\btravel-",
    re.I,
)


def _classify_case_type(title: str, article_text: str) -> str | None:
    """Детерминированная классификация: case_type на основе keyword-regex.

    Логика:
      • AI keyword + travel keyword + banking keyword → "AI travel в банкинге"
      • AI keyword + travel keyword (no banking) → "AI travel"
      • Banking keyword + travel keyword (no AI) → "Travel в банкинге"
      • Иначе → None (item должен быть отброшен)

    Поиск только в title и первых 1500 символах article_text — это статья,
    не страница целиком. Если sidebar/nav уже почищены через BS4, то article_text
    содержит только article body.
    """
    if not title and not article_text:
        return None
    blob = (title or "") + " " + (article_text or "")[:1500]
    has_ai = bool(_AI_KEYWORDS_RE.search(blob))
    has_banking = bool(_BANKING_KEYWORDS_RE.search(blob))
    has_travel = bool(_TRAVEL_KEYWORDS_RE.search(blob))
    if not has_travel:
        return None  # без travel вообще не наш кейс
    if has_ai and has_banking:
        return "AI travel в банкинге"
    if has_ai:
        return "AI travel"
    if has_banking:
        return "Travel в банкинге"
    return None  # есть только travel — это "Other", который мы отбрасываем


def resolve_one(stub: dict, allow_browser_resolve: bool = True) -> dict | None:
    """Worker: resolve URL → score trust → fetch text → classify case_type.

    allow_browser_resolve=False: для collect-mode. Тогда failing GN URLs
    отбрасываются вместо browser-fallback. Держит collect быстрым (~30-60с).

    case_type классифицируется детерминированно (без LLM) — items без явного
    AI/banking + travel сигнала отбрасываются прямо здесь, не попадают в
    /tmp/r1_urls.json. Это убивает галлюцинации LLM на стадии 2.
    """
    url = stub["url"]
    if not url:
        return None
    final_url = resolve_redirect(url, allow_browser=allow_browser_resolve) or url
    if "news.google." in final_url:
        return None  # не удалось resolve GN URL
    score, matched = _trust_score(final_url)
    text = fetch_text(final_url) if score >= 0.30 else ""
    case_type = _classify_case_type(stub.get("title", ""), text)
    # Если text >= 300 символов И classifier ничего не нашёл — это явно
    # не AI/banking + travel, просто travel или мусор. Drop.
    # Если text короткий/пустой (fetch провалился), KEEP с case_type=None —
    # Stage-2 сделает догрузку и реклассификацию через r1_classify.py helper.
    if case_type is None and len(text) >= 300:
        return None
    return {
        "title_en": stub["title"],
        "url": final_url,
        "source": stub["source"] or _domain(final_url),
        "query": stub["query"],
        "pub": stub["pub"],
        "article_text": text,
        "trust_score": score,
        "trust_matched_domain": matched,
        "case_type": case_type,  # либо detrministically классифицирован, либо None
    }


OUTPUT_PATH = "/opt/newsapp/.openclaw/workspace/ops/r1_urls.json"


def merge_into_file(new_candidates: list[dict], errors: list[dict], stats: dict) -> int:
    """Atomic merge: load existing /tmp/r1_urls.json → dedup by URL → append → write.

    Возвращает: число действительно ДОБАВЛЕННЫХ кандидатов (не уже существующих).
    Атомарность через write-to-temp + rename.
    """
    import os
    # Load existing (or empty)
    existing = {"candidates": [], "errors": [], "stats": {}}
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
            if not isinstance(existing, dict):
                existing = {"candidates": [], "errors": [], "stats": {}}
    except Exception:
        pass

    existing_urls = {_norm_url(c.get("url", "")) for c in existing.get("candidates", [])}
    added = 0
    for c in new_candidates:
        nu = _norm_url(c.get("url", ""))
        if not nu or nu in existing_urls:
            continue
        existing_urls.add(nu)
        existing["candidates"].append(c)
        added += 1

    existing["errors"] = (existing.get("errors", []) or []) + (errors or [])
    # Stats: merge per-mode keyed by mode label
    mode_label = stats.get("mode", "unknown")
    existing.setdefault("stats", {})
    if not isinstance(existing["stats"], dict):
        existing["stats"] = {}
    existing["stats"][f"mode_{mode_label}"] = stats
    existing["stats"]["last_mode"] = mode_label
    existing["stats"]["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Sort by trust + content length, cap to 200
    existing["candidates"].sort(
        key=lambda c: (c.get("trust_score", 0.10), len(c.get("article_text") or "")),
        reverse=True,
    )
    existing["candidates"] = existing["candidates"][:200]
    # ВАЖНО: trim article_text до 800 символов в финальном файле.
    # Это снижает /tmp/r1_urls.json с ~1 MB до ~200 KB и предотвращает
    # V8 heap OOM в gateway когда он читает файл для передачи в Stage-2.
    # Stage-2 всё равно догружает свежий контент через ru-fetch для null-classified.
    for c in existing["candidates"]:
        txt = c.get("article_text") or ""
        if len(txt) > 800:
            c["article_text"] = txt[:800]

    # Atomic rename
    tmp_path = OUTPUT_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    os.rename(tmp_path, OUTPUT_PATH)
    return added


def reset_state() -> None:
    """Wipe /tmp/r1_urls.json and url cache. Run at start of day."""
    import os
    for p in (OUTPUT_PATH, URL_CACHE_PATH):
        try:
            os.unlink(p)
            print(f"removed {p}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"warn: could not remove {p}: {e}")


def run_mode(mode: str) -> None:
    """Run a single phase: collect | yandex | scrape. Then merge into /tmp/r1_urls.json."""
    t0 = time.time()
    stubs, errors, stats = collect_stubs(mode=mode)
    stubs = cap_by_diversity(stubs, CANDIDATE_BUDGET)
    print(f"\n[mode={mode}] Phase 1 done in {time.time()-t0:.1f}s — {len(stubs)} stubs",
          file=sys.stderr)

    if not stubs:
        added = merge_into_file([], errors, stats)
        print(f"[mode={mode}, {time.time()-t0:.1f}s] no stubs collected; merged 0")
        return

    # Browser-resolve fallback for failing GN URLs — ТОЛЬКО для mode=all (legacy).
    # collect / google режимы используют Python-only декодер
    # (googlenewsdecoder через batchexecute API) — без Chromium = безопасно
    # для VPS (1.9 ГБ RAM, нет swap). См. resolve_redirect.
    # yandex/scrape — у них URLs не Google News.
    allow_browser = (mode == "all")

    candidates: list[dict] = []
    post_seen: set[str] = set()
    n_resolve_fail = 0
    n_dedup_post = 0
    with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS) as ex:
        futures = {ex.submit(resolve_one, s, allow_browser): s for s in stubs}
        for fut in as_completed(futures):
            try:
                cand = fut.result(timeout=30)
            except Exception as e:
                errors.append({"resolve_err": str(e)[:200]})
                n_resolve_fail += 1
                continue
            if not cand:
                n_resolve_fail += 1
                continue
            n = _norm_url(cand["url"])
            if n in post_seen:
                n_dedup_post += 1
                stats["deduped"] += 1
                continue
            post_seen.add(n)
            candidates.append(cand)
    stats["resolve_failed"] = n_resolve_fail
    stats["post_dedup"] = n_dedup_post

    added = merge_into_file(candidates, errors, stats)
    _cache_save()

    with_text = sum(1 for c in candidates if len(c.get("article_text", "")) >= 80)
    tier_dist: dict[float, int] = {}
    for c in candidates:
        t = round(c.get("trust_score", 0.1), 2)
        tier_dist[t] = tier_dist.get(t, 0) + 1
    print(f"\n[mode={mode}, {time.time()-t0:.1f}s] resolved {len(candidates)} "
          f"({with_text} with text), added {added} new to {OUTPUT_PATH}")
    print(f"Stats: {json.dumps(stats, ensure_ascii=False)}")
    print(f"Trust: {json.dumps({str(k): v for k, v in sorted(tier_dist.items(), reverse=True)})}")


HEALTH_PATH = "/tmp/r1_cron_health.json"

# Глобальные override-флаги для CLI-аргументов (--max-queries / --query-delay).
# Устанавливаются в main() из argparse, читаются в run_mode/yandex-phase.
# 0 = используй default (все queries / 0.2 сек).
_MAX_QUERIES_OVERRIDE = 0
_QUERY_DELAY_OVERRIDE = 0.20


def _write_health(mode: str, status: str, started_ts: float,
                  candidates: int = 0, error: str = "") -> None:
    """Атомарная запись /tmp/r1_cron_health.json с текущим состоянием прогона.

    Используется как замена gateway runs/<jobid>.jsonl после миграции в
    system crontab — даёт быстрый snapshot состояния pipeline.
    """
    try:
        # Read existing snapshot (per-mode)
        try:
            with open(HEALTH_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing.setdefault("modes", {})
        existing["modes"][mode] = {
            "status": status,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_ts)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_sec": round(time.time() - started_ts, 1),
            "candidates": candidates,
            "error": error[:300] if error else "",
        }
        existing["last_mode"] = mode
        existing["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = HEALTH_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        os.replace(tmp, HEALTH_PATH)
    except Exception:
        pass  # health-логирование никогда не должно крашить основной поток


def main():
    import argparse
    p = argparse.ArgumentParser(prog="r1_fetch_urls",
                                description="R1 news collector — split into modes for cron staggering")
    p.add_argument("--mode", choices=["all", "collect", "yandex", "scrape", "google", "reset"],
                   default="all",
                   help=("collect=Google News+RSS RU-focused (15s, no browser); "
                         "yandex=SearXNG (140 queries, ~5 min); "
                         "scrape=RU travel sites (25s, 1 Chromium peak); "
                         "google=Google News fresh themes EN/RU (when:3d, ~80s, no browser); "
                         "reset=wipe /tmp/r1_urls.json+cache; "
                         "all=legacy combined run"))
    p.add_argument("--max-queries", type=int, default=0,
                   help=("Лимит числа queries для yandex-mode. По умолчанию 0 = все. "
                         "Используй небольшое значение (5-10) при ручном тестировании "
                         "чтобы не перегружать search engines."))
    p.add_argument("--query-delay", type=float, default=0.20,
                   help=("Задержка между queries в SearXNG (сек). По умолчанию 0.2."
                         " Можно поставить 1.0+ для самого щадящего режима."))
    args = p.parse_args()
    # Передаём в run_mode через module globals (простой способ без рефакторинга API)
    global _MAX_QUERIES_OVERRIDE, _QUERY_DELAY_OVERRIDE
    _MAX_QUERIES_OVERRIDE = args.max_queries
    _QUERY_DELAY_OVERRIDE = args.query_delay

    started = time.time()
    try:
        if args.mode == "reset":
            reset_state()
            _write_health("reset", "ok", started)
            return
        run_mode(args.mode)
        # Подсчёт candidates после run_mode (опционально)
        cands = 0
        try:
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                cands = len(json.load(f).get("candidates", []))
        except Exception:
            pass
        _write_health(args.mode, "ok", started, candidates=cands)
    except SystemExit:
        raise
    except Exception as e:
        _write_health(args.mode, "error", started, error=str(e))
        raise


if __name__ == "__main__":
    main()
