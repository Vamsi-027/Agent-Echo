-- Migration 001: Initial Schema Setup
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_time TEXT NOT NULL,
    title TEXT,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    raw_summary TEXT,
    highlights_json TEXT,
    categories_json TEXT,
    suggested_pillar TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(date, version)
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_id INTEGER REFERENCES daily_digests(id) ON DELETE SET NULL,
    pillar TEXT,
    format_type TEXT,
    text_content TEXT,
    media_refs_json TEXT,
    hashtags TEXT,
    voice_profile_hash TEXT,
    status TEXT DEFAULT 'pending_review',
    review_notes TEXT,
    scheduled_time TEXT,
    publishing_started_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id) ON DELETE CASCADE,
    priority_score REAL DEFAULT 0.0,
    scheduled_time TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS published_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
    linkedin_post_urn TEXT UNIQUE NOT NULL,
    published_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oauth_token_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expires_at TEXT NOT NULL,
    refresh_expires_at TEXT,
    refreshed_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_post_urn TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    reactions INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    recorded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS pending_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    actions_json TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_status_time ON drafts(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_activity_events_time ON activity_events(event_time);
CREATE INDEX IF NOT EXISTS idx_published_posts_draft ON published_posts(draft_id);
CREATE INDEX IF NOT EXISTS idx_digests_date ON daily_digests(date);
CREATE INDEX IF NOT EXISTS idx_content_queue_status_time ON content_queue(status, scheduled_time);
