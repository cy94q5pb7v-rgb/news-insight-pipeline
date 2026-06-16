"""Near-duplicate title detection + ISO date parsing helpers.

Used by news archive accumulators to collapse the same story reported by
different channels / with slight rewording.
"""
from datetime import datetime, timedelta

from core.config import (
    _TITLE_WORD_RE, _TITLE_STOP,
    NEAR_DUP_THRESHOLD, NEAR_DUP_WINDOW_DAYS,
)


def _title_tokens(t: str) -> set:
    return {
        w.lower()
        for w in _TITLE_WORD_RE.findall(t or "")
        if len(w) > 1 and w.lower() not in _TITLE_STOP
    }


def _parse_iso(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _title_similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _find_near_dup_title(
    new_title: str, new_dt, existing_items: list, title_key: str
) -> dict | None:
    if not new_title:
        return None
    nt = _title_tokens(new_title)
    if not nt:
        return None
    cutoff = None
    if new_dt is not None:
        cutoff = new_dt - timedelta(days=NEAR_DUP_WINDOW_DAYS)
    for it in existing_items:
        ex_title = it.get(title_key) or ""
        if not ex_title:
            continue
        if cutoff is not None:
            ex_dt = _parse_iso(it.get("collected_at") or "")
            if ex_dt is not None and ex_dt < cutoff:
                continue
        et = _title_tokens(ex_title)
        if not et:
            continue
        union = nt | et
        if union and len(nt & et) / len(union) >= NEAR_DUP_THRESHOLD:
            return it
    return None


def _dup_ref(it: dict, title_key: str) -> dict:
    return {
        "source": it.get("source") or "",
        "url": it.get("url") or "",
        "trust_score": it.get("trust_score"),
        "collected_at": it.get("collected_at") or "",
        "title": it.get(title_key) or "",
    }


def _attach_dup(main: dict, dropped: dict, title_key: str) -> None:
    """\u041f\u0440\u0438\u043a\u0440\u0435\u043f\u0438\u0442\u044c \u0434\u0443\u0431\u043b\u044c \u043a \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043d\u043e\u0432\u043e\u0441\u0442\u0438 (dedup \u043f\u043e url)."""
    bucket = main.setdefault("dup_sources", [])
    seen = {d.get("url") for d in bucket}
    seen.add(main.get("url"))
    for ref in [_dup_ref(dropped, title_key)] + list(dropped.get("dup_sources") or []):
        u = ref.get("url")
        if u and u not in seen:
            bucket.append(ref)
            seen.add(u)


def _prune_near_dups(items: list, title_key: str) -> int:
    """Collapse near-duplicate items in-place, keeping the earliest by collected_at.
    \u0414\u0443\u0431\u043b\u0438 \u041d\u0415 \u0432\u044b\u0431\u0440\u0430\u0441\u044b\u0432\u0430\u044e\u0442\u0441\u044f, \u0430 \u043f\u0440\u0438\u043a\u0440\u0435\u043f\u043b\u044f\u044e\u0442\u0441\u044f \u0432 dup_sources.
    Returns number of items collapsed."""
    items.sort(key=lambda x: x.get("collected_at") or "")
    kept: list = []
    removed = 0
    for it in items:
        dup = _find_near_dup_title(
            it.get(title_key) or "", _parse_iso(it.get("collected_at") or ""), kept, title_key
        )
        if dup is None:
            kept.append(it)
        else:
            _attach_dup(dup, it, title_key)
            removed += 1
    if removed:
        items[:] = kept
    return removed
