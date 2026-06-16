import pytest
import sqlite3
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from db.db import init_db, get_db_connection
from feedback.weekly_review import prompt_post_performance, analyze_performance_and_reweight

TEST_DB_PATH = Path(__file__).parent / "test_feedback.db"

@pytest.fixture
def test_db():
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
                
    init_db(db_path=TEST_DB_PATH)
    
    yield TEST_DB_PATH
    
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]
        
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

@patch("builtins.input", side_effect=["100", "5", "2", "1"])
def test_prompt_post_performance(mock_input, test_db):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Insert mock daily digest
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-14', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    
    # 2. Insert mock draft
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, status) "
        "VALUES (?, 'lesson_learned', 'text', 'Test Content Post', 'published')",
        (digest_id,)
    )
    draft_id = cursor.lastrowid
    
    # 3. Insert mock published_posts
    cursor.execute(
        "INSERT INTO published_posts (draft_id, linkedin_post_urn) "
        "VALUES (?, 'urn:li:share:test_post_urn')",
        (draft_id,)
    )
    conn.commit()
    conn.close()
    
    prompt_post_performance()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM performance_log WHERE linkedin_post_urn = 'urn:li:share:test_post_urn'")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["impressions"] == 100
    assert row["reactions"] == 5
    assert row["comments"] == 2
    assert row["reposts"] == 1

@patch("feedback.weekly_review.Anthropic")
def test_analyze_performance_and_reweight(mock_anthropic, test_db):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Insert mock entries to perform a reweight analysis
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-14', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, status) "
        "VALUES (?, 'lesson_learned', 'text', 'Test Content Post', 'published')",
        (digest_id,)
    )
    draft_id = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO published_posts (draft_id, linkedin_post_urn) "
        "VALUES (?, 'urn:li:share:test_post_urn')",
        (draft_id,)
    )
    
    cursor.execute(
        "INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, reposts) "
        "VALUES ('urn:li:share:test_post_urn', 200, 10, 4, 2)"
    )
    conn.commit()
    conn.close()
    
    # Mock Anthropic Client and message response
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Mock Claude Reweight Recommendations")]
    mock_client.messages.create.return_value = mock_message
    mock_anthropic.return_value = mock_client
    
    analyze_performance_and_reweight()
    
    mock_client.messages.create.assert_called_once()
    assert "lesson_learned" in mock_client.messages.create.call_args[1]["messages"][0]["content"]
