"""KB SQLite schema init, connection, permission checks, row → dict."""
import sqlite3
from datetime import datetime, timezone

from fastapi import HTTPException

from core.config import KB_DB_PATH
from core.users import _find_user


def _kb_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(KB_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _kb_init() -> None:
    """Create schema if missing; run in-place migrations. Idempotent."""
    with _kb_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS kb_docs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            file_ext TEXT,
            mime TEXT,
            size INTEGER DEFAULT 0,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            author TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
            id UNINDEXED, title, content, tags, tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE INDEX IF NOT EXISTS idx_kb_author ON kb_docs(author);
        CREATE INDEX IF NOT EXISTS idx_kb_created ON kb_docs(created_at);

        CREATE TABLE IF NOT EXISTS kb_hypotheses (
            id TEXT PRIMARY KEY,
            statement TEXT NOT NULL,
            rationale TEXT NOT NULL,
            category TEXT DEFAULT '',
            confidence REAL DEFAULT 0,
            validated INTEGER DEFAULT 0,
            evidence_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            run_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kb_hypothesis_sources (
            hypothesis_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            excerpt TEXT DEFAULT '',
            is_origin INTEGER DEFAULT 0,
            PRIMARY KEY (hypothesis_id, doc_id)
        );
        CREATE INDEX IF NOT EXISTS idx_kbh_src_doc ON kb_hypothesis_sources(doc_id);
        CREATE INDEX IF NOT EXISTS idx_kbh_run ON kb_hypotheses(run_id);
        CREATE TABLE IF NOT EXISTS kb_news_items (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            origin TEXT DEFAULT '',
            case_type TEXT DEFAULT '',
            collected_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS kb_insight_runs (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            author TEXT NOT NULL,
            docs_total INTEGER DEFAULT 0,
            hypotheses_total INTEGER DEFAULT 0,
            validated_total INTEGER DEFAULT 0,
            error TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS kb_insight_docs (
            doc_id TEXT PRIMARY KEY,
            first_run_id TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kb_feedback (
            id              TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            author_username TEXT NOT NULL,
            author_priority TEXT DEFAULT '',
            page_url        TEXT DEFAULT '',
            text            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'new',
            status_updated_at TEXT DEFAULT '',
            status_updated_by TEXT DEFAULT '',
            ai_status       TEXT NOT NULL DEFAULT 'pending',
            ai_priority     TEXT DEFAULT '',
            ai_comment      TEXT DEFAULT '',
            ai_job_id       TEXT DEFAULT '',
            ai_updated_at   TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_fb_created   ON kb_feedback(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fb_aistatus  ON kb_feedback(ai_status);
        CREATE INDEX IF NOT EXISTS idx_fb_status    ON kb_feedback(status);

        CREATE TABLE IF NOT EXISTS kb_feedback_comments (
            id              TEXT PRIMARY KEY,
            feedback_id     TEXT NOT NULL,
            author_username TEXT NOT NULL,
            text            TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fbc_fb     ON kb_feedback_comments(feedback_id);
        CREATE INDEX IF NOT EXISTS idx_fbc_at     ON kb_feedback_comments(created_at);
        """)
        # Idempotent migration of new feedback columns
        fb_cols = {r[1] for r in c.execute("PRAGMA table_info(kb_feedback)")}
        if "author_priority" not in fb_cols:
            c.execute("ALTER TABLE kb_feedback ADD COLUMN author_priority TEXT DEFAULT ''")
        if "status" not in fb_cols:
            c.execute("ALTER TABLE kb_feedback ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
        if "status_updated_at" not in fb_cols:
            c.execute("ALTER TABLE kb_feedback ADD COLUMN status_updated_at TEXT DEFAULT ''")
        if "status_updated_by" not in fb_cols:
            c.execute("ALTER TABLE kb_feedback ADD COLUMN status_updated_by TEXT DEFAULT ''")
        cols = {r[1] for r in c.execute("PRAGMA table_info(kb_docs)")}
        for col, ddl in [
            ("summary",           "ALTER TABLE kb_docs ADD COLUMN summary TEXT DEFAULT ''"),
            ("auto_tags",         "ALTER TABLE kb_docs ADD COLUMN auto_tags TEXT DEFAULT ''"),
            ("tldr",              "ALTER TABLE kb_docs ADD COLUMN tldr TEXT DEFAULT ''"),
            ("enrichment_status", "ALTER TABLE kb_docs ADD COLUMN enrichment_status TEXT DEFAULT 'pending'"),
            ("enrichment_error",  "ALTER TABLE kb_docs ADD COLUMN enrichment_error TEXT DEFAULT ''"),
            ("moderation_status", "ALTER TABLE kb_docs ADD COLUMN moderation_status TEXT DEFAULT 'approved'"),
            ("approved_by",       "ALTER TABLE kb_docs ADD COLUMN approved_by TEXT DEFAULT ''"),
            ("approved_at",       "ALTER TABLE kb_docs ADD COLUMN approved_at TEXT DEFAULT ''"),
        ]:
            if col not in cols:
                c.execute(ddl)
        c.execute(
            "UPDATE kb_docs SET moderation_status='approved' "
            "WHERE moderation_status IS NULL OR moderation_status=''"
        )
        h_cols = {r[1] for r in c.execute("PRAGMA table_info(kb_hypotheses)")}
        if "source_kind" not in h_cols:
            c.execute("ALTER TABLE kb_hypotheses ADD COLUMN source_kind TEXT DEFAULT 'material'")
            c.execute("UPDATE kb_hypotheses SET source_kind='material' WHERE source_kind IS NULL OR source_kind=''")
        # ── Insight lifecycle: status / owner / next_check / updated_at ─────────
        if "lifecycle_status" not in h_cols:
            c.execute("ALTER TABLE kb_hypotheses ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'synthesized'")
        if "owner_username" not in h_cols:
            c.execute("ALTER TABLE kb_hypotheses ADD COLUMN owner_username TEXT")
        if "next_check_at" not in h_cols:
            c.execute("ALTER TABLE kb_hypotheses ADD COLUMN next_check_at TEXT")
        if "lifecycle_updated_at" not in h_cols:
            c.execute("ALTER TABLE kb_hypotheses ADD COLUMN lifecycle_updated_at TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_hyp_owner    ON kb_hypotheses(owner_username)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_hyp_status   ON kb_hypotheses(lifecycle_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_hyp_check    ON kb_hypotheses(next_check_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_kb_hyp_cat_stat ON kb_hypotheses(category, lifecycle_status)")
        # One-shot backfill for rows added before this migration: existing
        # validated → 'validated', everyone else → 'synthesized'.
        c.execute(
            "UPDATE kb_hypotheses "
            "   SET lifecycle_status = CASE WHEN validated = 1 THEN 'validated' ELSE 'synthesized' END, "
            "       lifecycle_updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
            " WHERE lifecycle_updated_at IS NULL"
        )
        # Backfill kb_insight_docs from existing hypothesis sources so legacy
        # runs don't re-analyze docs that were already processed.
        processed_now = {r[0] for r in c.execute("SELECT doc_id FROM kb_insight_docs")}
        legacy_sources = {r[0] for r in c.execute(
            "SELECT DISTINCT doc_id FROM kb_hypothesis_sources WHERE doc_id IS NOT NULL AND doc_id != ''"
        )}
        missing = legacy_sources - processed_now
        if missing:
            now_iso = datetime.now(timezone.utc).isoformat()
            for did in missing:
                c.execute(
                    "INSERT OR IGNORE INTO kb_insight_docs (doc_id, first_run_id, processed_at) "
                    "VALUES (?, ?, ?)",
                    (did, "legacy-backfill", now_iso),
                )


def _kb_can_read(user: str) -> bool:
    u = _find_user(user) or {}
    if u.get("is_admin"):
        return True
    secs = u.get("sections") or []
    return "kb" in secs


def _kb_require_read(user: str) -> None:
    if not _kb_can_read(user):
        raise HTTPException(403, "Раздел «Инсайт-хаб» недоступен для вашей роли")


def _kb_can_upload(user: str) -> bool:
    return _kb_can_read(user)


def _kb_require_upload(user: str) -> None:
    if not _kb_can_upload(user):
        raise HTTPException(403, "Раздел «Инсайт-хаб» недоступен для вашей роли")


def _kb_can_moderate(user: str) -> bool:
    u = _find_user(user) or {}
    return bool(u.get("is_admin")) or bool(u.get("kb_moderate"))


def _kb_require_moderate(user: str) -> None:
    if not _kb_can_moderate(user):
        raise HTTPException(403, "Нужны права на модерацию Инсайт-хаба")


def _kb_row_to_dict(row, *, include_content: bool = False) -> dict:
    keys = row.keys()
    def g(k, default=""):
        return (row[k] if k in keys else default) or default
    d = {
        "id": row["id"],
        "title": row["title"],
        "source_type": row["source_type"],
        "source_ref": row["source_ref"] or "",
        "file_ext": row["file_ext"] or "",
        "mime": row["mime"] or "",
        "size": int(row["size"] or 0),
        "tags": [t for t in (row["tags"] or "").split(",") if t.strip()],
        "auto_tags": [t for t in g("auto_tags").split(",") if t.strip()],
        "author": row["author"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "tldr": g("tldr"),
        "enrichment_status": g("enrichment_status") or "done",
        "enrichment_error": g("enrichment_error"),
        "moderation_status": g("moderation_status") or "approved",
        "approved_by": g("approved_by"),
        "approved_at": g("approved_at"),
    }
    if include_content:
        d["content"] = row["content"] or ""
        d["summary"] = g("summary")
    return d
