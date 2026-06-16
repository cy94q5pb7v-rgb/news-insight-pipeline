"""Travel + packages news archives — load & accumulate."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from core.config import (
    R1_NEWS_PATH, TRAVEL_ARCHIVE_PATH,
    DIGEST_RUN_PATH, PACKAGES_ARCHIVE_PATH,
    PACKAGES_BACKFILL_DAYS, _DIGEST_ITEM_RE,
)
from core.dedupe import _prune_near_dups, _find_near_dup_title, _parse_iso, _attach_dup


# ── Trust registry (mirror of r1_fetch_urls.py TRUST_REGISTRY) ───────────────
# Лёгкая копия для on-the-fly scoring в endpoint'ах /travel|packages|kb/news,
# чтобы UI показывал badge даже для items, записанных до того как accumulator
# научился копировать trust_score.
_TRUST_REGISTRY: dict[str, float] = {
    # 1.00 — tier-1 business press + regulators + official corporate
    "reuters.com": 1.00, "ft.com": 1.00, "wsj.com": 1.00, "bloomberg.com": 1.00,
    "economist.com": 1.00, "forbes.com": 1.00, "hbr.org": 1.00, "fortune.com": 1.00,
    "marketwatch.com": 1.00,
    "rbc.ru": 1.00, "vedomosti.ru": 1.00, "kommersant.ru": 1.00, "forbes.ru": 1.00,
    "cbr.ru": 1.00, "minfin.gov.ru": 1.00, "moex.com": 1.00,
    "sber.ru": 1.00, "sberbank.ru": 1.00, "sberbank.com": 1.00,
    "vtb.ru": 1.00, "vtb.com": 1.00,
    "tbank.ru": 1.00, "t-bank.ru": 1.00, "tinkoff.ru": 1.00,
    "alfabank.ru": 1.00, "alfa-bank.ru": 1.00,
    "raiffeisen.ru": 1.00, "raiffeisen-bank.ru": 1.00,
    "gazprombank.ru": 1.00, "gpbru.com": 1.00,
    "otkritie.com": 1.00, "rosbank.ru": 1.00, "psbank.ru": 1.00,
    "sovcombank.ru": 1.00, "mtsbank.ru": 1.00, "otpbank.ru": 1.00,
    "tochka.com": 1.00, "akbars.ru": 1.00, "uralsib.ru": 1.00,
    "booking.com": 1.00, "expedia.com": 1.00, "airbnb.com": 1.00,
    "marriott.com": 1.00, "hilton.com": 1.00, "hyatt.com": 1.00, "ihg.com": 1.00,
    "delta.com": 1.00, "united.com": 1.00, "aa.com": 1.00, "emirates.com": 1.00,
    "visa.com": 1.00, "mastercard.com": 1.00, "americanexpress.com": 1.00,
    "stripe.com": 1.00, "paypal.com": 1.00, "klarna.com": 1.00,
    "revolut.com": 1.00, "n26.com": 1.00, "monzo.com": 1.00, "wise.com": 1.00,
    # 0.85 — major news + travel-trade tier-1
    "bbc.com": 0.85, "bbc.co.uk": 0.85, "nytimes.com": 0.85, "cnn.com": 0.85,
    "theguardian.com": 0.85, "washingtonpost.com": 0.85, "axios.com": 0.85,
    "ap.org": 0.85, "apnews.com": 0.85, "cnbc.com": 0.85,
    "businessinsider.com": 0.85, "qz.com": 0.85,
    "ria.ru": 0.85, "interfax.ru": 0.85, "tass.ru": 0.85, "tass.com": 0.85,
    "lenta.ru": 0.85, "iz.ru": 0.85, "izvestia.ru": 0.85,
    "frankrg.com": 0.85, "banki.ru": 0.85, "sravni.ru": 0.85,
    "finam.ru": 0.85, "investing.com": 0.85,
    "techcrunch.com": 0.85, "theverge.com": 0.85, "wired.com": 0.85,
    "arstechnica.com": 0.85, "engadget.com": 0.85, "venturebeat.com": 0.85,
    "skift.com": 0.85, "phocuswire.com": 0.85, "phocuswright.com": 0.85,
    "travelweekly.com": 0.85, "businesstravelnews.com": 0.85,
    "finextra.com": 0.85, "pymnts.com": 0.85, "americanbanker.com": 0.85,
    "thebanker.com": 0.85, "fintechmagazine.com": 0.85, "thefintechtimes.com": 0.85,
    # 0.70 — RU travel-trade + regional business
    "ratanews.ru": 0.70, "atorus.ru": 0.70, "tourdom.ru": 0.70,
    "tour52.ru": 0.70, "frequentflyers.ru": 0.70,
    "gazeta.ru": 0.70, "mk.ru": 0.70, "rg.ru": 0.70,
    "fontanka.ru": 0.70, "spbvedomosti.ru": 0.70,
    "j.tinkoff.ru": 0.70, "journal.tinkoff.ru": 0.70,
    "secretmag.ru": 0.70,
    "fastcompany.com": 0.70, "inc.com": 0.70,
    # 0.50 — aggregators / regional
    "yahoo.com": 0.50, "finance.yahoo.com": 0.50, "au.finance.yahoo.com": 0.50,
    "msn.com": 0.50, "news.yahoo.com": 0.50,
    # 0.30 — UGC-heavy platforms
    "medium.com": 0.30, "dev.to": 0.30, "substack.com": 0.30,
    "linkedin.com": 0.30, "vc.ru": 0.30, "habr.com": 0.30,
    # 0.15 — UGC forums
    "reddit.com": 0.15, "ycombinator.com": 0.15, "news.ycombinator.com": 0.15,
    "tripadvisor.com": 0.15, "tripadvisor.ru": 0.15,
    "t.me": 0.40,  # Telegram aggregator — официальные банковские каналы могут быть выше, но средне

    # ─ trust additions 2026-05-06: foreign travel-trade + AI-travel publishers
    "travelandtourworld.com": 0.85,
    "breakingtravelnews.com": 0.85,
    "businesstraveller.com": 0.85,
    "travelweekly.com.au": 0.85,
    "afp.com": 0.85,
    "hoteltechnologynews.com": 0.70,
    "hotel-online.com": 0.70,
    "businesstravelexecutive.com": 0.70,
    "futuretravelexperience.com": 0.70,
    "thecompanydime.com": 0.70,
    "tearsheet.co": 0.70,
    "ttnworldwide.com": 0.70,
    "traveldailymedia.com": 0.70,
    "traveldailynews.com": 0.70,
    "hotelnewsresource.com": 0.70,
    "airportxnews.com": 0.50,
    "travelhost.com": 0.50,
    "travelwires.com": 0.50,
    "meetings-conventions-asia.com": 0.50,
    "tipranks.com": 0.50,
    "stocktitan.net": 0.50,
    "proactiveinvestors.com": 0.50,
    "devdiscourse.com": 0.50,
    "thetravel.com": 0.50,
    "manilatimes.net": 0.50,
    "visahq.com": 0.50,
    "digitaltoday.co.kr": 0.50,
    "citybiz.co": 0.50,
    "aol.com": 0.50,
    "straitstimes.com": 0.70,
    "channelnewsasia.com": 0.85,
}


def _score_url(url: str) -> tuple[float, str]:
    """Compute (trust_score, matched_domain) for an URL via _TRUST_REGISTRY.

    Suffix walk: a.b.c → b.c → c. Returns (0.10, "") if nothing matches.
    """
    if not url:
        return 0.10, ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return 0.10, ""
    for prefix in ("www.", "m.", "mobile.", "amp.", "ru.", "en."):
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


def _ensure_trust(it: dict) -> dict:
    """Backfill trust_score + trust_matched_domain on archive item if missing."""
    if it.get("trust_score") is None:
        score, matched = _score_url(it.get("url", ""))
        it["trust_score"] = score
        it["trust_matched_domain"] = matched
    elif "trust_matched_domain" not in it:
        it["trust_matched_domain"] = ""
    return it


# ── Travel archive ────────────────────────────────────────────────────────────

def _load_travel_archive() -> dict:
    if TRAVEL_ARCHIVE_PATH.exists():
        try:
            return json.loads(TRAVEL_ARCHIVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": [], "updated_at": ""}


def _accumulate_travel_archive() -> dict:
    archive = _load_travel_archive()
    items = archive.get("items") or []
    archive["items"] = items
    pruned = _prune_near_dups(items, "title_ru")
    if not R1_NEWS_PATH.exists():
        if pruned:
            archive["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                TRAVEL_ARCHIVE_PATH.write_text(
                    json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        return archive
    try:
        latest = json.loads(R1_NEWS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return archive
    seen_hash = {it.get("article_hash") for it in items if it.get("article_hash")}
    # Index for in-place field-merge (relevance, trust_origin, is_event_news появляются
    # ретроспективно в Stage-2 v5+; existing archive entries добавлены до этого).
    by_hash = {it.get("article_hash"): it for it in items if it.get("article_hash")}
    UPDATABLE_FIELDS = ("summary_ru", "relevance_score", "relevance_reason", "trust_origin", "is_event_news", "bank_applicability", "bank_applicability_reason")
    refreshed = 0
    for it in latest.get("items") or []:
        h = (it or {}).get("article_hash")
        if h and h in by_hash:
            arch_it = by_hash[h]
            local_changed = False
            for f in UPDATABLE_FIELDS:
                cur, new = arch_it.get(f), it.get(f)
                if (cur is None or cur == "") and new is not None and new != "":
                    arch_it[f] = new
                    local_changed = True
            if local_changed:
                refreshed += 1
    # \u0421\u043c\u044b\u0441\u043b\u043e\u0432\u0430\u044f \u0433\u0440\u0443\u043f\u043f\u0438\u0440\u043e\u0432\u043a\u0430 \u0434\u0443\u0431\u043b\u0435\u0439 \u0438\u0437 stage-2 (story_group); fallback \u043d\u0430 \u043b\u0435\u043a\u0441\u0438\u043a\u0443, \u0435\u0441\u043b\u0438 \u043f\u043e\u043b\u044f \u043d\u0435\u0442
    _raw = latest.get("items") or []
    _groups: dict = {}
    _incoming: list = []
    for _it in _raw:
        _sg = (_it or {}).get("story_group")
        if _sg is None:
            _incoming.append(_it)
        else:
            _groups.setdefault(_sg, []).append(_it)
    for _sg, _gi in _groups.items():
        if len(_gi) == 1:
            _incoming.append(_gi[0])
        else:
            _gi.sort(key=lambda x: -((x.get("trust_score") or 0)))
            _primary = _gi[0]
            for _other in _gi[1:]:
                _attach_dup(_primary, _other, "title_ru")
            _incoming.append(_primary)
    added = 0
    for it in _incoming:
        h = (it or {}).get("article_hash")
        url = (it or {}).get("url") or ""
        title = (it or {}).get("title_ru") or ""
        if not h or h in seen_hash or not url or not title:
            if h and h in by_hash and it.get("dup_sources"):
                _dst = by_hash[h]
                _ds = _dst.setdefault("dup_sources", [])
                _seen = {d.get("url") for d in _ds}
                _seen.add(_dst.get("url"))
                for _d in it.get("dup_sources") or []:
                    if _d.get("url") and _d["url"] not in _seen:
                        _ds.append(_d)
                        _seen.add(_d["url"])
            continue
        collected = it.get("collected_at") or latest.get("created_at") or ""
        _dup_main = _find_near_dup_title(title, _parse_iso(collected), items, "title_ru")
        if _dup_main is not None:
            _attach_dup(_dup_main, it, "title_ru")
            continue
        items.append({
            "article_hash": h,
            "title_ru": title,
            "summary_ru": (it.get("summary_ru") or "").strip(),
            "url": url,
            "source": it.get("source") or "",
            "case_type": it.get("case_type") or "",
            "trust_score": it.get("trust_score"),
            "trust_matched_domain": it.get("trust_matched_domain") or "",
            "trust_origin": it.get("trust_origin") or "",
            "is_event_news": it.get("is_event_news"),
            "relevance_score": it.get("relevance_score"),
            "relevance_reason": (it.get("relevance_reason") or "").strip(),
            "collected_at": collected,
        })
        seen_hash.add(h)
        added += 1
    if added or pruned or refreshed:
        archive["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            TRAVEL_ARCHIVE_PATH.write_text(
                json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
    return archive


# ── Packages (Telegram banking digest) archive ──────────────────────────────

def _load_packages_archive() -> dict:
    if PACKAGES_ARCHIVE_PATH.exists():
        try:
            return json.loads(PACKAGES_ARCHIVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": [], "updated_at": "", "last_run_ts": 0}


def _parse_digest_summary(text: str) -> list[dict]:
    items = []
    for m in _DIGEST_ITEM_RE.finditer(text or ""):
        title = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip().rstrip(".,;:")
        posted = (m.group(3) or "").strip().rstrip(".,;:")
        if not title or not url.startswith("http"):
            continue
        items.append({"title": title, "url": url, "posted_at": posted})
    return items


def _iter_digest_runs():
    """Yield (run_ms, items) for every jsonl entry whose summary contains news lines."""
    if not DIGEST_RUN_PATH.exists():
        return
    try:
        with DIGEST_RUN_PATH.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                summary = d.get("summary") or ""
                if not summary or "📰" not in summary:
                    continue
                items = _parse_digest_summary(summary)
                if not items:
                    continue
                run_ms = int(d.get("runAtMs") or d.get("ts") or 0)
                yield run_ms, items
    except Exception:
        return


def _source_from_url(url: str) -> str:
    try:
        tail = url.split("t.me/", 1)[1]
        name = tail.split("/", 1)[0]
        return "@" + name if name else "t.me"
    except Exception:
        return "t.me"


def _accumulate_packages_archive() -> dict:
    archive = _load_packages_archive()
    items = archive.get("items") or []
    archive["items"] = items
    pruned = _prune_near_dups(items, "title")
    seen_exact = {
        (it.get("url") or "", it.get("title") or "")
        for it in items
        if it.get("url") and it.get("title")
    }
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=PACKAGES_BACKFILL_DAYS)).timestamp() * 1000)
    max_run_ms = int(archive.get("last_run_ts") or 0)
    added = 0
    for run_ms, run_items in _iter_digest_runs():
        if run_ms < cutoff_ms:
            continue
        run_iso = (
            datetime.fromtimestamp(run_ms / 1000, tz=timezone.utc).isoformat()
            if run_ms else datetime.now(timezone.utc).isoformat()
        )
        run_dt = _parse_iso(run_iso)
        for it in run_items:
            url = it.get("url") or ""
            title = it.get("title") or ""
            if not url or not title:
                continue
            if (url, title) in seen_exact:
                continue
            if _find_near_dup_title(title, run_dt, items, "title") is not None:
                continue
            h = hashlib.sha256((url + "\n" + title).encode("utf-8")).hexdigest()[:16]
            items.append({
                "article_hash": h,
                "title": title,
                "url": url,
                "source": _source_from_url(url),
                "posted_at": it.get("posted_at") or "",
                "collected_at": run_iso,
            })
            seen_exact.add((url, title))
            added += 1
        if run_ms > max_run_ms:
            max_run_ms = run_ms
    archive["last_run_ts"] = max_run_ms
    if added or pruned:
        archive["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            PACKAGES_ARCHIVE_PATH.write_text(
                json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
    return archive
