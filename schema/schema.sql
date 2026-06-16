-- News + Insight data model (SQLite). Extracted schema, no data.

CREATE TABLE kb_news_items (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            origin TEXT DEFAULT '',
            case_type TEXT DEFAULT '',
            collected_at TEXT DEFAULT ''
        );

CREATE TABLE news_summaries (
            article_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT DEFAULT '',
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            status TEXT NOT NULL,
            summary TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            cancelled_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

CREATE TABLE kb_hypotheses (
            id TEXT PRIMARY KEY,
            statement TEXT NOT NULL,
            rationale TEXT NOT NULL,
            category TEXT DEFAULT '',
            confidence REAL DEFAULT 0,
            validated INTEGER DEFAULT 0,
            evidence_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            run_id TEXT NOT NULL
        , source_kind TEXT DEFAULT 'material', lifecycle_status TEXT NOT NULL DEFAULT 'synthesized', owner_username TEXT, next_check_at TEXT, lifecycle_updated_at TEXT);

CREATE TABLE kb_hypothesis_sources (
            hypothesis_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            excerpt TEXT DEFAULT '',
            is_origin INTEGER DEFAULT 0,
            PRIMARY KEY (hypothesis_id, doc_id)
        );

CREATE TABLE kb_insight_runs (
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

CREATE TABLE kb_insight_docs (
            doc_id TEXT PRIMARY KEY,
            first_run_id TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );

CREATE TABLE kb_docs (
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
        , summary TEXT DEFAULT '', auto_tags TEXT DEFAULT '', tldr TEXT DEFAULT '', enrichment_status TEXT DEFAULT 'pending', enrichment_error TEXT DEFAULT '', moderation_status TEXT DEFAULT 'approved', approved_by TEXT DEFAULT '', approved_at TEXT DEFAULT '');

