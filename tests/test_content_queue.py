import pytest
import sqlite3
import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from db.db import init_db, get_db_connection
from generator.draft_generator import approve_draft
from config_loader import LOCAL_TZ

TEST_DB_PATH = Path(__file__).parent / "test_linkedin_agent.db"

@pytest.fixture
def test_db():
    # Set environment variable to redirect all DB connections to the test DB
    import os
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    
    # Setup test database - remove database and WAL/SHM sidecars
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
                
    init_db(db_path=TEST_DB_PATH)
    
    yield TEST_DB_PATH
    
    # Teardown
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]
        
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

def test_database_initialization(test_db):
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    assert "activity_events" in tables
    assert "daily_digests" in tables
    assert "drafts" in tables
    assert "content_queue" in tables
    conn.close()

def test_draft_scheduling(test_db):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Insert mock daily digest
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-14', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    
    # 2. Insert mock drafts pending review
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, hashtags, status) "
        "VALUES (?, 'lesson_learned', 'text', 'Test content draft 1', '#test', 'pending_review')",
        (digest_id,)
    )
    draft_id_1 = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, hashtags, status) "
        "VALUES (?, 'lesson_learned', 'text', 'Test content draft 2', '#test', 'pending_review')",
        (digest_id,)
    )
    draft_id_2 = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    # 3. Approve first draft
    approve_draft(draft_id_1)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM content_queue WHERE draft_id = ?", (draft_id_1,))
    queue_row_1 = cursor.fetchone()
    assert queue_row_1 is not None
    assert queue_row_1["status"] == "queued"
    
    # Check scheduled time is valid ISO format
    scheduled_time_1 = datetime.datetime.fromisoformat(queue_row_1["scheduled_time"])
    assert scheduled_time_1.tzinfo is not None # must be timezone aware
    
    # 4. Approve second draft - must be scheduled at least 3 hours after the first draft
    conn.close()
    approve_draft(draft_id_2)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM content_queue WHERE draft_id = ?", (draft_id_2,))
    queue_row_2 = cursor.fetchone()
    assert queue_row_2 is not None
    
    scheduled_time_2 = datetime.datetime.fromisoformat(queue_row_2["scheduled_time"])
    
    # Verify the difference between scheduled times is at least 3 hours (10800 seconds)
    time_diff = (scheduled_time_2 - scheduled_time_1).total_seconds()
    assert abs(time_diff) >= 3 * 3600
    
    conn.close()
