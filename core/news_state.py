"""Server-persisted news state: reactions, notes, bookmarks.

Storage: single JSON file (ops/news_state.json) с in-process locking.
File-format:
{
  "reactions": {
    "<article_hash>": {
      "likes": 3, "dislikes": 1,
      "by_user": {"user@x": "like", "y@z": "dislike"}
    }
  },
  "notes": {
    "<article_hash>": {
      "by_user": {
        "user@x": {"text": "...", "updated_at": "ISO"}
      }
    }
  },
  "bookmarks": {
    "<article_hash>": {
      "by_user": ["user@x", "y@z"]
    }
  }
}
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

NEWS_STATE_PATH = Path("/opt/newsapp/.openclaw/workspace/ops/news_state.json")
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    if NEWS_STATE_PATH.exists():
        try:
            return json.loads(NEWS_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"reactions": {}, "notes": {}, "bookmarks": {}}


def _save(state: dict) -> None:
    NEWS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = NEWS_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(NEWS_STATE_PATH)


def react(article_hash: str, user: str, action: str) -> dict:
    """action: 'like' | 'dislike' | 'clear'. Возвращает новое состояние item."""
    if action not in ("like", "dislike", "clear"):
        raise ValueError(f"invalid action: {action}")
    with _LOCK:
        state = _load()
        reactions = state.setdefault("reactions", {})
        item = reactions.setdefault(article_hash, {"likes": 0, "dislikes": 0, "by_user": {}})
        prev = item["by_user"].get(user)
        # Снимаем предыдущую реакцию
        if prev == "like":
            item["likes"] = max(0, item["likes"] - 1)
        elif prev == "dislike":
            item["dislikes"] = max(0, item["dislikes"] - 1)
        # Применяем новую
        if action == "like":
            item["by_user"][user] = "like"
            item["likes"] += 1
        elif action == "dislike":
            item["by_user"][user] = "dislike"
            item["dislikes"] += 1
        else:  # clear
            item["by_user"].pop(user, None)
        _save(state)
        return {
            "likes": item["likes"],
            "dislikes": item["dislikes"],
            "my": item["by_user"].get(user),
        }


def set_note(article_hash: str, user: str, text: str) -> dict:
    with _LOCK:
        state = _load()
        notes = state.setdefault("notes", {})
        item = notes.setdefault(article_hash, {"by_user": {}})
        text = (text or "").strip()
        if text:
            item["by_user"][user] = {"text": text, "updated_at": _now_iso()}
        else:
            item["by_user"].pop(user, None)
        _save(state)
        return item["by_user"].get(user) or {"text": "", "updated_at": ""}


def toggle_bookmark(article_hash: str, user: str) -> dict:
    with _LOCK:
        state = _load()
        bm = state.setdefault("bookmarks", {})
        item = bm.setdefault(article_hash, {"by_user": []})
        users = item.setdefault("by_user", [])
        if user in users:
            users.remove(user)
            mine = False
        else:
            users.append(user)
            mine = True
        _save(state)
        return {"by_me": mine, "total": len(users)}


def state_for_feed(user: str) -> dict:
    """Возвращает компактный snapshot — что показать на feed уровне.

    Структура: {hash: {likes, dislikes, my, bookmarked, has_note}}
    """
    state = _load()
    reactions = state.get("reactions", {}) or {}
    notes = state.get("notes", {}) or {}
    bm = state.get("bookmarks", {}) or {}
    out: dict = {}
    keys = set(reactions.keys()) | set(notes.keys()) | set(bm.keys())
    for h in keys:
        r = reactions.get(h, {}) or {}
        n = notes.get(h, {}) or {}
        b = bm.get(h, {}) or {}
        users = b.get("by_user", []) or []
        my_note = (n.get("by_user", {}) or {}).get(user, {}).get("text", "")
        by_user = r.get("by_user", {}) or {}
        likers_other = sorted([u for u, v in by_user.items() if v == "like" and u != user])
        out[h] = {
            "likes": r.get("likes", 0),
            "dislikes": r.get("dislikes", 0),
            "my": by_user.get(user),
            "bookmarked": user in users,
            "bookmark_total": len(users),
            "has_note": bool(my_note),
            "top_reactors": likers_other[:3],
        }
    return out


def append_chat(article_hash: str, user: str, role: str, text: str) -> list:
    """role: 'user' | 'agent'. Возвращает обновлённую историю (последние 30 сообщений)."""
    if role not in ("user", "agent"):
        raise ValueError(f"bad role: {role}")
    text = (text or "").strip()
    if not text:
        return []
    with _LOCK:
        state = _load()
        chats = state.setdefault("chats", {})
        item = chats.setdefault(article_hash, {"by_user": {}})
        users = item.setdefault("by_user", {})
        history = users.setdefault(user, [])
        history.append({"role": role, "text": text[:6000], "ts": _now_iso()})
        users[user] = history[-30:]  # cap last 30 messages
        _save(state)
        return list(users[user])


def get_chat(article_hash: str, user: str) -> list:
    state = _load()
    chats = state.get("chats", {}) or {}
    item = chats.get(article_hash, {}) or {}
    return list((item.get("by_user", {}) or {}).get(user, []) or [])


def clear_chat(article_hash: str, user: str) -> None:
    with _LOCK:
        state = _load()
        chats = state.get("chats", {}) or {}
        item = chats.get(article_hash)
        if not item:
            return
        users = item.get("by_user", {}) or {}
        users.pop(user, None)
        if not users:
            chats.pop(article_hash, None)
        _save(state)


def cache_article(article_hash: str, text: str) -> None:
    """Cache full article text для drill-in. TTL контролируется снаружи через get_article_cached."""
    if not text:
        return
    with _LOCK:
        state = _load()
        cache = state.setdefault("articles", {})
        cache[article_hash] = {"text": text[:12000], "ts": _now_iso()}
        _save(state)


def get_article_cached(article_hash: str, max_age_h: int = 168) -> str:
    state = _load()
    cache = (state.get("articles") or {}).get(article_hash, {}) or {}
    text = cache.get("text") or ""
    ts = cache.get("ts") or ""
    if not text or not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - dt).total_seconds() > max_age_h * 3600:
            return ""
    except Exception:
        return ""
    return text


def detail_for_user(article_hash: str, user: str) -> dict:
    """Полный detail: реакции (агрегированные) + моя реакция + моя заметка + chat-кол-во."""
    state = _load()
    r = (state.get("reactions") or {}).get(article_hash, {}) or {}
    n = (state.get("notes") or {}).get(article_hash, {}) or {}
    b = (state.get("bookmarks") or {}).get(article_hash, {}) or {}
    chats = (state.get("chats") or {}).get(article_hash, {}).get("by_user", {}) or {}
    my_note_obj = (n.get("by_user", {}) or {}).get(user, {}) or {}
    by_user = r.get("by_user", {}) or {}
    # Team reactions: кто из коллег как отреагировал (без моего email)
    likers = sorted([u for u, v in by_user.items() if v == "like" and u != user])
    dislikers = sorted([u for u, v in by_user.items() if v == "dislike" and u != user])
    return {
        "likes": r.get("likes", 0),
        "dislikes": r.get("dislikes", 0),
        "my_reaction": by_user.get(user),
        "bookmarked": user in (b.get("by_user", []) or []),
        "bookmark_total": len(b.get("by_user", []) or []),
        "my_note": my_note_obj.get("text", ""),
        "my_note_updated_at": my_note_obj.get("updated_at", ""),
        "likers_other": likers[:10],
        "dislikers_other": dislikers[:10],
        "my_chat_msgs": len(chats.get(user, []) or []),
        "team_chat_active": len([u for u in chats if (chats.get(u) or [])]),
    }


def cache_summary(article_hash: str, text: str) -> None:
    """Cache LLM-generated 2-sentence summary for a news item (global, not per-user)."""
    if not text:
        return
    with _LOCK:
        state = _load()
        cache = state.setdefault("summaries", {})
        cache[article_hash] = {"text": text[:1200], "ts": _now_iso()}
        _save(state)


def get_summary_cached(article_hash: str) -> str:
    state = _load()
    return ((state.get("summaries") or {}).get(article_hash, {}) or {}).get("text", "") or ""


def all_cached_summaries() -> dict:
    """Return {hash: text} for every cached summary. Used to merge into feed."""
    state = _load()
    summaries = state.get("summaries") or {}
    return {h: (v or {}).get("text", "") for h, v in summaries.items() if (v or {}).get("text")}


def get_user_prefs(user: str) -> dict:
    """Return persisted UI prefs for user (filters + sort)."""
    state = _load()
    return (state.get("user_prefs") or {}).get(user, {}) or {}


def set_user_prefs(user: str, prefs: dict) -> dict:
    """Merge whitelisted prefs into stored state. Returns updated dict."""
    if not isinstance(prefs, dict):
        prefs = {}
    ALLOWED = {"case", "date", "trust", "personal", "hide_read", "sort"}
    with _LOCK:
        state = _load()
        all_prefs = state.setdefault("user_prefs", {})
        existing = all_prefs.get(user) or {}
        for k, v in prefs.items():
            if k in ALLOWED:
                existing[k] = v
        all_prefs[user] = existing
        _save(state)
        return existing
