PRAGMA foreign_keys = ON;

-- Raw activity events recorded by watchers
CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                  -- 'calendar' | 'git' | 'file' | 'browser' | 'note' | 'email' | 'coding_session'
    event_time TEXT NOT NULL,              -- ISO8601 UTC
    title TEXT,
    detail TEXT,                           -- JSON blob, source-specific
    created_at TEXT DEFAULT (datetime('now'))
);

-- Daily digests summarizing activity events
CREATE TABLE IF NOT EXISTS daily_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                    -- YYYY-MM-DD local date
    version INTEGER DEFAULT 1,             -- increments if regenerated
    raw_summary TEXT,
    highlights_json TEXT,                  -- JSON array of strings
    categories_json TEXT,                  -- JSON object of details
    suggested_pillar TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(date, version)
);

-- Drafts generated from daily digests
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_id INTEGER REFERENCES daily_digests(id) ON DELETE SET NULL,
    pillar TEXT,
    format_type TEXT,                      -- 'text' | 'image' | 'carousel' | 'video' | 'long_form'
    text_content TEXT,
    media_refs_json TEXT,                  -- JSON array of file paths
    hashtags TEXT,                         -- Comma or space separated hashtags
    voice_profile_hash TEXT,
    status TEXT DEFAULT 'pending_review',  -- pending_review | approved | edited | rejected | publishing | published | failed | needs_manual_check
    review_notes TEXT,
    scheduled_time TEXT,                   -- UTC ISO8601 calculated from cadence rules
    publishing_started_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Posting queue for approved drafts
CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id) ON DELETE CASCADE,
    priority_score REAL DEFAULT 0.0,
    scheduled_time TEXT NOT NULL,          -- UTC ISO8601
    status TEXT DEFAULT 'queued',          -- queued | publishing | published | rolled
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Published post mappings
CREATE TABLE IF NOT EXISTS published_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
    linkedin_post_urn TEXT UNIQUE NOT NULL,
    published_at TEXT DEFAULT (datetime('now'))
);

-- OAuth token metadata (keys are kept in OS keyring)
CREATE TABLE IF NOT EXISTS oauth_token_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expires_at TEXT NOT NULL,              -- UTC ISO8601
    refresh_expires_at TEXT,               -- UTC ISO8601
    refreshed_at TEXT DEFAULT (datetime('now'))
);

-- Performance metrics log
CREATE TABLE IF NOT EXISTS performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_post_urn TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    reactions INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    recorded_at TEXT DEFAULT (datetime('now'))
);

-- Pipeline runs tracking
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,               -- 'capture' | 'digest' | 'generator' | 'publisher' | 'feedback'
    status TEXT NOT NULL,                  -- 'started' | 'completed' | 'failed'
    error_message TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

-- Notifications queued locally when delivery channels fail
CREATE TABLE IF NOT EXISTS pending_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    actions_json TEXT,                     -- JSON array of strings: e.g. ["approve", "skip", "edit"]
    status TEXT DEFAULT 'pending',         -- pending | processed
    created_at TEXT DEFAULT (datetime('now'))
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_drafts_status_time ON drafts(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_activity_events_time ON activity_events(event_time);
CREATE INDEX IF NOT EXISTS idx_published_posts_draft ON published_posts(draft_id);
CREATE INDEX IF NOT EXISTS idx_digests_date ON daily_digests(date);
CREATE INDEX IF NOT EXISTS idx_content_queue_status_time ON content_queue(status, scheduled_time);
