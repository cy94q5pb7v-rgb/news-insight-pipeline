#!/usr/bin/env python3
"""Сквозное РАБОЧЕЕ демо новостного конвейера — офлайн-дружелюбное.

Запуск из корня репозитория:

    pip install -r requirements.txt
    python examples/run_pipeline.py

Что делает (с мягкой деградацией на каждом шаге):
    1. читает публичные RSS-фиды из examples/sample_feeds.txt (feedparser);
    2. классифицирует каждую новость   -> pipeline.r1_classify.classify();
    3. скорит доверие по домену         -> trust-таблица (core/archives.py);
    4. опц. тянет полный текст статьи    -> trafilatura, если установлен;
    5. схлопывает near-дубли            -> core.dedupe._prune_near_dups();
    6. суммаризация + рейтинг           -> llm.StubBackend (заглушка, без сети);
    7. пишет результат в SQLite (example_output.db) + печатает сводку.

Ни ключей, ни внешних сервисов не требуется. ИИ-шаг — детерминированная
заглушка (llm.StubBackend); как подключить реальную модель — см. llm.py.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

# ── sys.path: добавляем корень репо, чтобы работали пакетные импорты ──────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pipeline.r1_classify import classify           # noqa: E402
from core.dedupe import _prune_near_dups            # noqa: E402
from llm import StubBackend                         # noqa: E402

# Trust-таблица домен→скор. Берём из core/archives.py (там же логика суффикс-walk).
try:
    from core.archives import _TRUST_REGISTRY, _score_url
    _HAS_SCORE_URL = True
except Exception:                                    # pragma: no cover
    from core.archives import _TRUST_REGISTRY
    _HAS_SCORE_URL = False

FEEDS_FILE = os.path.join(_HERE, "sample_feeds.txt")
DB_PATH = os.path.join(_ROOT, "example_output.db")
HTTP_TIMEOUT = 20          # сек на загрузку одного фида
MAX_PER_FEED = 25          # сколько новостей брать максимум из одного фида


def _log(msg: str) -> None:
    print(msg, flush=True)


def _score_domain(url: str) -> tuple[float, str]:
    """(trust_score, matched_domain) для URL. Падать не имеет права."""
    if _HAS_SCORE_URL:
        try:
            return _score_url(url)
        except Exception:
            pass
    # Локальный фолбэк — простой суффикс-walk по _TRUST_REGISTRY.
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return 0.10, ""
    for prefix in ("www.", "m.", "amp.", "ru.", "en."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if host in _TRUST_REGISTRY:
        return _TRUST_REGISTRY[host], host
    parts = host.split(".")
    for i in range(1, len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in _TRUST_REGISTRY:
            return _TRUST_REGISTRY[suffix], suffix
    return 0.10, ""


def _read_feeds() -> list[str]:
    feeds: list[str] = []
    try:
        with open(FEEDS_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    feeds.append(line)
    except FileNotFoundError:
        _log(f"[warn] нет файла фидов {FEEDS_FILE}")
    return feeds


def _maybe_full_text(url: str, fallback: str) -> tuple[str, str]:
    """Пытаемся вытащить полный текст через trafilatura; иначе fallback (RSS summary)."""
    try:
        from core.article_fetch import _fetch_via_trafilatura
    except Exception:
        return fallback, "rss-summary"
    try:
        text, mode = _fetch_via_trafilatura(url)
        if text:
            return text, mode
    except Exception:
        pass
    return fallback, "rss-summary"


def collect_items() -> list[dict]:
    try:
        import feedparser
    except ImportError:
        _log("[fatal] не установлен feedparser. Выполни: pip install -r requirements.txt")
        sys.exit(1)

    feeds = _read_feeds()
    if not feeds:
        _log("[warn] список фидов пуст — нечего собирать")
        return []

    want_full = "trafilatura" in sys.modules or _trafilatura_available()
    items: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for feed_url in feeds:
        _log(f"[feed] {feed_url}")
        try:
            # feedparser сам грузит URL; ограничиваем сокет-таймаутом.
            import socket
            socket.setdefaulttimeout(HTTP_TIMEOUT)
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            _log(f"   [skip] ошибка загрузки: {type(e).__name__}: {e}")
            continue

        entries = getattr(parsed, "entries", []) or []
        if not entries:
            _log("   [skip] пустой фид / недоступен")
            continue

        host = (urlparse(feed_url).hostname or "").replace("www.", "")
        added = 0
        for e in entries[:MAX_PER_FEED]:
            title = (getattr(e, "title", "") or "").strip()
            link = (getattr(e, "link", "") or "").strip()
            summary = (getattr(e, "summary", "") or getattr(e, "description", "") or "").strip()
            # грубо чистим html-теги из summary
            summary = _strip_html(summary)
            if not title:
                continue

            topic = classify(title, summary)
            if topic == "NONE":
                continue

            trust, matched = _score_domain(link or feed_url)
            text = summary
            mode = "rss-summary"
            if want_full and link:
                text, mode = _maybe_full_text(link, summary)

            items.append({
                "title": title,
                "url": link,
                "source": matched or host,
                "summary_src": summary,
                "text": text,
                "fetch_mode": mode,
                "case_type": topic,
                "trust_score": trust,
                "trust_matched_domain": matched,
                "collected_at": now_iso,
            })
            added += 1
        _log(f"   [ok] взято подходящих: {added} (всего записей в фиде: {len(entries)})")

    return items


def _trafilatura_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("trafilatura") is not None
    except Exception:
        return False


def _strip_html(s: str) -> str:
    import re
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def summarize(items: list[dict]) -> None:
    backend = StubBackend()
    for it in items:
        res = backend.summarize_and_rate(it["title"], it.get("text") or "", it["case_type"])
        it["summary"] = res["summary"]
        it["rating"] = res["rating"]
        it["rationale"] = res["rationale"]


def write_db(items: list[dict]) -> int:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, url TEXT, source TEXT,
            case_type TEXT, trust_score REAL, trust_matched_domain TEXT,
            fetch_mode TEXT, summary TEXT, rating INTEGER, rationale TEXT,
            collected_at TEXT
        )
        """
    )
    rows = [
        (
            it["title"], it["url"], it["source"], it["case_type"],
            it["trust_score"], it["trust_matched_domain"], it["fetch_mode"],
            it.get("summary", ""), it.get("rating", 0), it.get("rationale", ""),
            it["collected_at"],
        )
        for it in items
    ]
    cur.executemany(
        "INSERT INTO news_items "
        "(title,url,source,case_type,trust_score,trust_matched_domain,"
        "fetch_mode,summary,rating,rationale,collected_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    con.close()
    return n


def print_summary(items: list[dict], collapsed: int, db_rows: int) -> None:
    print()
    print("=" * 64)
    print("  СВОДКА ПО ЗАПУСКУ КОНВЕЙЕРА (демо)")
    print("=" * 64)
    print(f"  Собрано релевантных новостей : {len(items)}")
    print(f"  Схлопнуто near-дублей        : {collapsed}")
    print(f"  Записано строк в SQLite      : {db_rows}  ({os.path.basename(DB_PATH)})")

    by_topic: dict[str, int] = {}
    for it in items:
        by_topic[it["case_type"]] = by_topic.get(it["case_type"], 0) + 1
    print("\n  По темам:")
    if by_topic:
        for topic, cnt in sorted(by_topic.items(), key=lambda x: -x[1]):
            print(f"    - {topic:<26} {cnt}")
    else:
        print("    (пусто)")

    print("\n  Топ-5 по доверию к источнику:")
    top = sorted(items, key=lambda x: (x["trust_score"], x.get("rating", 0)), reverse=True)[:5]
    if top:
        for it in top:
            t = it["title"][:58]
            print(f"    [{it['trust_score']:.2f}] r{it.get('rating', 0)} "
                  f"{it['source']:<18} {t}")
    else:
        print("    (пусто)")
    print("=" * 64)


def main() -> None:
    print("Демо новостного конвейера — офлайн, без ключей.\n")
    if _trafilatura_available():
        print("[info] trafilatura найдена — полный текст статей будет извлекаться.\n")
    else:
        print("[info] trafilatura не установлена — используем RSS-summary (это норма).\n")

    items = collect_items()
    if not items:
        print("\n[warn] не удалось собрать ни одной релевантной новости.")
        print("       Возможные причины: нет сети / фиды недоступны / нет совпадений по теме.")
        print("       Демо завершилось без ошибок, но БД будет пустой.")

    collapsed = _prune_near_dups(items, "title") if items else 0
    summarize(items)
    db_rows = write_db(items)
    print_summary(items, collapsed, db_rows)


if __name__ == "__main__":
    main()
