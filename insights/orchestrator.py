"""Job orchestrator for Insight Hub web_app.

Sits between FastAPI endpoints and openclaw subprocess calls.
- SQLite-backed persistent queue (tables: jobs, job_events)
- Priority by tier (admin > premium > basic), FIFO within tier
- Global + per-user + per-kind concurrency limits
- Kind handlers registered by web_app before startup()
- Handlers run in asyncio.to_thread with their own timeout inside

Public API:
    register_kind(name, handler, *, timeout_s, serial=False, recover=True)
    ensure_schema(db_path)          # called inside _kb_init
    await startup(user_tier_lookup, db_path)
    await shutdown()
    await submit(user, kind, payload) -> {job_id, queue_pos}
    await get_status(job_id, user=None) -> dict | None
    await cancel(job_id, user=None) -> bool
    await list_for_admin(limit=100) -> dict
    set_phase(job_id, phase)        # handler helper for fine-grained status
    track_process(job_id, proc)     # handler helper for cancel support
"""

from __future__ import annotations

import asyncio
import heapq
import json
import logging
import os
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

log = logging.getLogger("orchestrator")

# ── Configuration ──────────────────────────────────────────────────────────
GLOBAL_MAX = int(os.getenv("ORCH_GLOBAL_MAX", "3"))
TIER_SLOTS = {"admin": 8, "premium": 3, "basic": 1}
TIER_PRIO = {"admin": 0, "premium": 1, "basic": 2}

_KINDS: dict[str, dict] = {}


class TransientError(RuntimeError):
    """Raise from a handler to signal that the error is retryable
    (network blip, agent timeout, transient openclaw failure).

    Orchestrator honours `max_retries` on the kind — re-queues with
    exponential backoff (30s, 90s, 270s...) up to that count."""


def register_kind(
    name: str,
    handler: Callable,
    *,
    timeout_s: int = 600,
    serial: bool = False,
    recover: bool = True,
    max_retries: int = 0,
) -> None:
    """Register a kind handler. Must be called BEFORE startup().

    handler(user: str, payload: dict, job_id: str) -> dict | None
    Returns the result dict on success, or raises on failure.
    Raise TransientError for retryable failures (honoured up to max_retries).
    Can be sync (run in thread) or async.
    """
    _KINDS[name] = dict(
        handler=handler, timeout_s=timeout_s, serial=serial, recover=recover,
        max_retries=max_retries,
    )


def _retry_delay_s(attempt: int) -> int:
    """Exponential backoff: 30, 90, 270, 810 seconds (base 30, factor 3)."""
    return 30 * (3 ** attempt)


# ── Internal state ─────────────────────────────────────────────────────────
_db_path: Path | None = None
_heap: list[tuple[int, str]] = []
_heap_set: set[str] = set()
_heap_lock: asyncio.Lock | None = None
_wake: asyncio.Event | None = None
_global_sem: asyncio.Semaphore | None = None
_user_sems: dict[str, asyncio.Semaphore] = {}
_user_tier: Callable[[str], str] | None = None
_kind_locks: dict[str, asyncio.Lock] = {}
_running_procs: dict[str, subprocess.Popen] = {}
_dispatcher_task: asyncio.Task | None = None
_cleanup_task: asyncio.Task | None = None


# ── DB helpers ─────────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path), timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=8000")
    return c


def ensure_schema(db_path) -> None:
    """Create jobs/job_events tables if missing. Idempotent."""
    global _db_path
    _db_path = Path(db_path)
    with _conn() as c:
        c.executescript(
            """
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          user TEXT NOT NULL,
          tier TEXT NOT NULL DEFAULT 'basic',
          kind TEXT NOT NULL,
          priority INTEGER NOT NULL,
          status TEXT NOT NULL,
          phase TEXT,
          payload_json TEXT NOT NULL,
          result_json TEXT,
          error TEXT,
          attempts INTEGER DEFAULT 0,
          submitted_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          worker_id TEXT,
          cancel_req INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority);
        CREATE INDEX IF NOT EXISTS idx_jobs_user_finished ON jobs(user, finished_at);
        CREATE TABLE IF NOT EXISTS job_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          ts TEXT NOT NULL,
          event TEXT NOT NULL,
          detail TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_jobe_job ON job_events(job_id);
        """
        )
        # ensure phase column on upgrade from pre-phase schema
        cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
        if "phase" not in cols:
            c.execute("ALTER TABLE jobs ADD COLUMN phase TEXT")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(c, job_id: str, event: str, detail: str | None = None) -> None:
    c.execute(
        "INSERT INTO job_events (job_id, ts, event, detail) VALUES (?,?,?,?)",
        (job_id, _now_iso(), event, detail),
    )


def _priority_score(tier: str, ts_ms: int) -> int:
    return TIER_PRIO.get(tier, 2) * 10**13 + ts_ms


# ── Handler helpers (called from inside a registered handler) ──────────────
def set_phase(job_id: str, phase: str) -> None:
    """Update fine-grained phase visible to /status polling (e.g. 'agent', 'storing')."""
    try:
        with _conn() as c:
            c.execute("UPDATE jobs SET phase=? WHERE id=?", (phase, job_id))
            _log_event(c, job_id, "phase", phase)
            c.commit()
    except Exception as e:
        log.warning("set_phase(%s, %s) failed: %s", job_id, phase, e)


def track_process(job_id: str, proc: subprocess.Popen) -> None:
    """Register a subprocess so cancel() can signal it."""
    _running_procs[job_id] = proc


def is_cancelled(job_id: str) -> bool:
    try:
        with _conn() as c:
            row = c.execute("SELECT cancel_req FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["cancel_req"])
    except Exception:
        return False


# ── Public API ─────────────────────────────────────────────────────────────
async def submit(user: str, kind: str, payload: dict) -> dict:
    if kind not in _KINDS:
        raise ValueError(f"unknown kind: {kind}")
    tier = _user_tier(user) if _user_tier else "basic"
    job_id = uuid.uuid4().hex
    submitted_ms = int(time.time() * 1000)
    priority = _priority_score(tier, submitted_ms)
    with _conn() as c:
        c.execute(
            "INSERT INTO jobs (id, user, tier, kind, priority, status, payload_json, submitted_at) "
            "VALUES (?,?,?,?,?, 'queued', ?, ?)",
            (
                job_id,
                user,
                tier,
                kind,
                priority,
                json.dumps(payload, ensure_ascii=False),
                _now_iso(),
            ),
        )
        _log_event(c, job_id, "submitted", f"tier={tier} kind={kind}")
        c.commit()
    assert _heap_lock is not None and _wake is not None
    async with _heap_lock:
        heapq.heappush(_heap, (priority, job_id))
        _heap_set.add(job_id)
    _wake.set()
    return {"job_id": job_id, "queue_pos": _queue_position(priority)}


def _queue_position(priority: int) -> int:
    with _conn() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='queued' AND priority <= ?",
            (priority,),
        ).fetchone()[0]
    return int(n)


async def get_status(job_id: str, user: str | None = None) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    if user and row["user"] != user:
        return None
    out = {
        "job_id": job_id,
        "kind": row["kind"],
        "status": row["status"],
        "phase": row["phase"],
        "tier": row["tier"],
        "attempts": row["attempts"],
        "submitted_at": row["submitted_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }
    try:
        start = row["started_at"] or row["submitted_at"]
        start_dt = datetime.fromisoformat(start) if start else None
        end_dt = (
            datetime.fromisoformat(row["finished_at"])
            if row["finished_at"]
            else datetime.now(timezone.utc)
        )
        out["elapsed_s"] = max(0, int((end_dt - start_dt).total_seconds())) if start_dt else 0
    except Exception:
        out["elapsed_s"] = 0
    if row["status"] == "queued":
        out["queue_pos"] = _queue_position(row["priority"])
    if row["status"] == "done" and row["result_json"]:
        try:
            out["result"] = json.loads(row["result_json"])
        except Exception:
            out["result"] = None
    if row["status"] in ("error", "interrupted", "cancelled") and row["error"]:
        out["error"] = row["error"]
    return out


async def cancel(job_id: str, user: str | None = None) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT user, status FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row:
            return False
        if user and row["user"] != user:
            return False
        if row["status"] in ("done", "error", "cancelled", "interrupted"):
            return True
        c.execute("UPDATE jobs SET cancel_req=1 WHERE id=?", (job_id,))
        _log_event(c, job_id, "cancel_requested")
        c.commit()
    if row["status"] == "queued":
        async with _heap_lock:  # type: ignore[arg-type]
            _heap_set.discard(job_id)
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='cancelled', finished_at=?, error='cancelled before start' WHERE id=?",
                (_now_iso(), job_id),
            )
            _log_event(c, job_id, "cancelled", "before_start")
            c.commit()
    else:
        proc = _running_procs.get(job_id)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    return True


async def find_active(user: str, kind: str) -> str | None:
    """Return job_id of user's active (queued/running) job of given kind, if any."""
    with _conn() as c:
        row = c.execute(
            "SELECT id FROM jobs WHERE user=? AND kind=? AND status IN ('queued','running') "
            "ORDER BY submitted_at DESC LIMIT 1",
            (user, kind),
        ).fetchone()
    return row["id"] if row else None


async def metrics(window_hours: int = 24) -> dict:
    """Aggregated stats over the last window_hours: counts, p50/p95 durations, error rate."""
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    out: dict = {"window_hours": window_hours, "by_kind": {}, "by_tier": {}, "totals": {}}
    with _conn() as c:
        rows = c.execute(
            "SELECT kind, tier, status, started_at, finished_at, submitted_at "
            "FROM jobs WHERE submitted_at >= ?",
            (since,),
        ).fetchall()
    buckets_kind: dict[str, list] = {}
    buckets_tier: dict[str, list] = {}
    tot = {"total": 0, "done": 0, "error": 0, "cancelled": 0, "interrupted": 0, "running": 0, "queued": 0}
    for r in rows:
        tot["total"] += 1
        tot[r["status"]] = tot.get(r["status"], 0) + 1
        buckets_kind.setdefault(r["kind"], []).append(dict(r))
        buckets_tier.setdefault(r["tier"], []).append(dict(r))

    def _stats(rs: list[dict]) -> dict:
        done = [x for x in rs if x["status"] == "done" and x["started_at"] and x["finished_at"]]
        fails = [x for x in rs if x["status"] in ("error", "interrupted")]
        durs = []
        for x in done:
            try:
                s = datetime.fromisoformat(x["started_at"])
                f = datetime.fromisoformat(x["finished_at"])
                durs.append((f - s).total_seconds())
            except Exception:
                pass
        waits = []
        for x in rs:
            if not x.get("started_at") or not x.get("submitted_at"):
                continue
            try:
                sub = datetime.fromisoformat(x["submitted_at"])
                st = datetime.fromisoformat(x["started_at"])
                waits.append(max(0.0, (st - sub).total_seconds()))
            except Exception:
                pass
        durs.sort(); waits.sort()
        def _pct(arr, p):
            if not arr: return 0
            k = max(0, min(len(arr) - 1, int(round((len(arr) - 1) * p))))
            return int(arr[k])
        return {
            "count": len(rs),
            "done": len(done),
            "errors": len(fails),
            "error_rate": round(len(fails) / max(1, len(rs)), 3),
            "p50_duration_s": _pct(durs, 0.50),
            "p95_duration_s": _pct(durs, 0.95),
            "avg_duration_s": int(sum(durs) / len(durs)) if durs else 0,
            "p50_wait_s": _pct(waits, 0.50),
            "p95_wait_s": _pct(waits, 0.95),
        }

    out["totals"] = tot
    out["by_kind"] = {k: _stats(v) for k, v in buckets_kind.items()}
    out["by_tier"] = {k: _stats(v) for k, v in buckets_tier.items()}
    return out


async def list_for_admin(limit: int = 100) -> dict:
    with _conn() as c:
        running = c.execute(
            "SELECT id, user, tier, kind, status, phase, started_at, attempts "
            "FROM jobs WHERE status='running' ORDER BY started_at"
        ).fetchall()
        queued = c.execute(
            "SELECT id, user, tier, kind, status, submitted_at, priority "
            "FROM jobs WHERE status='queued' ORDER BY priority LIMIT 200"
        ).fetchall()
        recent = c.execute(
            "SELECT id, user, tier, kind, status, phase, submitted_at, started_at, "
            "finished_at, error, attempts "
            "FROM jobs WHERE status IN ('done','error','cancelled','interrupted') "
            "ORDER BY COALESCE(finished_at, submitted_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    active = GLOBAL_MAX - (_global_sem._value if _global_sem else GLOBAL_MAX)
    return {
        "global_max": GLOBAL_MAX,
        "active_slots": max(0, active),
        "queue_depth": len(queued),
        "tiers": TIER_SLOTS,
        "kinds": {k: {"serial": v["serial"], "timeout_s": v["timeout_s"]} for k, v in _KINDS.items()},
        "running": [dict(r) for r in running],
        "queued": [dict(r) for r in queued],
        "recent": [dict(r) for r in recent],
    }


# ── Startup / shutdown ─────────────────────────────────────────────────────
async def startup(user_tier_lookup: Callable[[str], str], db_path) -> None:
    global _global_sem, _heap_lock, _wake, _user_tier, _dispatcher_task, _cleanup_task
    if _db_path is None:
        ensure_schema(db_path)
    _user_tier = user_tier_lookup
    _global_sem = asyncio.Semaphore(GLOBAL_MAX)
    _heap_lock = asyncio.Lock()
    _wake = asyncio.Event()
    for kind, meta in _KINDS.items():
        if meta.get("serial"):
            _kind_locks[kind] = asyncio.Lock()
    await _recover_interrupted()
    await _load_queue_from_db()
    _dispatcher_task = asyncio.create_task(_dispatcher_loop())
    _cleanup_task = asyncio.create_task(_daily_cleanup_loop())
    log.info(
        "orchestrator up: GLOBAL_MAX=%d kinds=%s tiers=%s",
        GLOBAL_MAX,
        list(_KINDS),
        TIER_SLOTS,
    )


async def shutdown() -> None:
    for t in (_dispatcher_task, _cleanup_task):
        if t and not t.done():
            t.cancel()
    try:
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='interrupted', error='server shutdown', finished_at=? "
                "WHERE status='running'",
                (_now_iso(),),
            )
            c.commit()
    except Exception:
        pass


async def _recover_interrupted() -> None:
    with _conn() as c:
        running = c.execute(
            "SELECT id, kind, attempts FROM jobs WHERE status='running'"
        ).fetchall()
        for r in running:
            kind = r["kind"]
            meta = _KINDS.get(kind, {})
            recoverable = meta.get("recover", True) and not meta.get("serial", False)
            if recoverable and r["attempts"] < 2:
                c.execute(
                    "UPDATE jobs SET status='queued', attempts=attempts+1, started_at=NULL, "
                    "worker_id=NULL, phase=NULL WHERE id=?",
                    (r["id"],),
                )
                _log_event(c, r["id"], "requeued", "after_restart")
            else:
                c.execute(
                    "UPDATE jobs SET status='interrupted', error='server restart interrupted job', "
                    "finished_at=? WHERE id=?",
                    (_now_iso(), r["id"]),
                )
                _log_event(c, r["id"], "interrupted", "after_restart")
        c.commit()


async def _load_queue_from_db() -> None:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, priority FROM jobs WHERE status='queued' ORDER BY priority"
        ).fetchall()
    assert _heap_lock is not None
    async with _heap_lock:
        _heap.clear()
        _heap_set.clear()
        for r in rows:
            heapq.heappush(_heap, (r["priority"], r["id"]))
            _heap_set.add(r["id"])
    if rows and _wake:
        _wake.set()


# ── Dispatcher / workers ───────────────────────────────────────────────────
def _get_user_sem(user: str, tier: str) -> asyncio.Semaphore:
    sem = _user_sems.get(user)
    if sem is None:
        slots = TIER_SLOTS.get(tier, 1)
        sem = asyncio.Semaphore(slots)
        _user_sems[user] = sem
    return sem


async def _dispatcher_loop() -> None:
    assert _wake is not None and _heap_lock is not None and _global_sem is not None
    while True:
        try:
            await _wake.wait()
            while True:
                async with _heap_lock:
                    job_id: str | None = None
                    while _heap:
                        prio, jid = heapq.heappop(_heap)
                        if jid in _heap_set:
                            _heap_set.discard(jid)
                            job_id = jid
                            break
                    if job_id is None:
                        _wake.clear()
                        break
                await _global_sem.acquire()
                with _conn() as c:
                    row = c.execute(
                        "SELECT * FROM jobs WHERE id=? AND status='queued'",
                        (job_id,),
                    ).fetchone()
                if not row:
                    _global_sem.release()
                    continue
                asyncio.create_task(_run_job(dict(row)))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("dispatcher error: %s", e)
            await asyncio.sleep(1)


async def _run_job(row: dict) -> None:
    assert _global_sem is not None
    job_id = row["id"]
    user = row["user"]
    tier = row["tier"]
    kind = row["kind"]
    meta = _KINDS.get(kind)
    if not meta:
        _mark_error(job_id, f"unknown kind: {kind}")
        _global_sem.release()
        return
    # cancel before start?
    if row.get("cancel_req"):
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='cancelled', finished_at=?, error='cancelled before start' WHERE id=?",
                (_now_iso(), job_id),
            )
            _log_event(c, job_id, "cancelled", "pre_start")
            c.commit()
        _global_sem.release()
        return
    user_sem = _get_user_sem(user, tier)
    kind_lock = _kind_locks.get(kind)
    user_acquired = False
    kind_acquired = False
    try:
        await user_sem.acquire()
        user_acquired = True
        if kind_lock:
            await kind_lock.acquire()
            kind_acquired = True
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (_now_iso(), job_id),
            )
            _log_event(c, job_id, "started")
            c.commit()
        payload = json.loads(row["payload_json"] or "{}")
        handler = meta["handler"]
        timeout = int(meta.get("timeout_s", 600))
        if asyncio.iscoroutinefunction(handler):
            coro = handler(user, payload, job_id)
        else:
            coro = asyncio.to_thread(handler, user, payload, job_id)
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            # kill any tracked subprocess
            proc = _running_procs.get(job_id)
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            _mark_error(job_id, f"timeout after {timeout}s")
            return
        if result is None:
            _mark_error(job_id, "handler returned None")
            return
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='done', result_json=?, finished_at=?, phase=NULL WHERE id=?",
                (json.dumps(result, ensure_ascii=False), _now_iso(), job_id),
            )
            _log_event(c, job_id, "done")
            c.commit()
    except TransientError as e:
        attempts = int(row.get("attempts") or 0)
        max_retries = int(meta.get("max_retries", 0))
        if attempts < max_retries:
            delay = _retry_delay_s(attempts)
            log.warning(
                "job %s (kind=%s) transient fail attempt=%d/%d, retry in %ds: %s",
                job_id, kind, attempts + 1, max_retries, delay, e,
            )
            _schedule_retry(job_id, delay, str(e)[:400])
        else:
            log.warning("job %s (kind=%s) transient fail, no retries left: %s", job_id, kind, e)
            _mark_error(job_id, str(e))
    except Exception as e:
        log.exception("job %s (kind=%s) failed: %s", job_id, kind, e)
        _mark_error(job_id, str(e))
    finally:
        if kind_acquired and kind_lock and kind_lock.locked():
            kind_lock.release()
        if user_acquired:
            user_sem.release()
        _global_sem.release()
        _running_procs.pop(job_id, None)
        if _wake:
            _wake.set()


def _schedule_retry(job_id: str, delay_s: int, reason: str) -> None:
    """Mark job for retry: status→queued, attempts++, delay via priority shift.

    Uses a future priority (now+delay) so dispatcher re-picks it only after
    the backoff has elapsed. A wake-up timer fires at delay_s to kick dispatcher.
    """
    future_ms = int((time.time() + delay_s) * 1000)
    with _conn() as c:
        r = c.execute(
            "SELECT tier FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        tier = r["tier"] if r else "basic"
        new_prio = _priority_score(tier, future_ms)
        c.execute(
            "UPDATE jobs SET status='queued', attempts=attempts+1, started_at=NULL, "
            "worker_id=NULL, phase=NULL, priority=? WHERE id=?",
            (new_prio, job_id),
        )
        _log_event(c, job_id, "retry", f"in {delay_s}s: {reason}")
        c.commit()

    async def _wake_later():
        try:
            await asyncio.sleep(delay_s)
            assert _heap_lock is not None and _wake is not None
            async with _heap_lock:
                heapq.heappush(_heap, (new_prio, job_id))
                _heap_set.add(job_id)
            _wake.set()
        except asyncio.CancelledError:
            pass

    asyncio.create_task(_wake_later())


def _mark_error(job_id: str, msg: str) -> None:
    try:
        with _conn() as c:
            c.execute(
                "UPDATE jobs SET status='error', error=?, finished_at=?, phase=NULL WHERE id=?",
                (msg[:800], _now_iso(), job_id),
            )
            _log_event(c, job_id, "error", msg[:400])
            c.commit()
    except Exception as e:
        log.exception("mark_error(%s) db failed: %s", job_id, e)


async def _daily_cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(24 * 3600)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            with _conn() as c:
                c.execute(
                    "DELETE FROM jobs WHERE COALESCE(finished_at, submitted_at) < ? "
                    "AND status IN ('done','error','cancelled','interrupted')",
                    (cutoff,),
                )
                c.execute("DELETE FROM job_events WHERE job_id NOT IN (SELECT id FROM jobs)")
                c.commit()
            log.info("orchestrator daily cleanup done")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("cleanup error: %s", e)
