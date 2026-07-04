import pytest
import sqlite3
import datetime
import os
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from db.db import init_db, get_db_connection
from publisher.twitter_client import generate_oauth_header, post_draft_to_twitter
from publisher.scheduler import publish_due_drafts

TEST_DB_PATH = Path(__file__).parent / "test_twitter_publisher.db"

@pytest.fixture
def test_db():
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    
    # Cleanup any sidecar files
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

def test_oauth_header_signature_generation():
    """Test standard OAuth 1.0a header generation format."""
    header = generate_oauth_header(
        method="POST",
        url="https://api.twitter.com/2/tweets",
        params={},
        consumer_key="test_key",
        consumer_secret="test_secret",
        access_token="test_token",
        access_token_secret="test_token_secret"
    )
    assert header.startswith("OAuth ")
    assert 'oauth_consumer_key="test_key"' in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header
    assert 'oauth_signature="' in header

def test_post_draft_to_twitter_dry_run():
    """Test that Twitter draft posting defaults to dry-run and logs output."""
    draft = {
        "text_content": "LinkedIn post",
        "twitter_text_content": "Twitter/X post",
        "hashtags": "#test #agency"
    }
    
    with patch.dict(os.environ, {"DRY_RUN": "true"}):
        resp = post_draft_to_twitter(draft)
        assert resp.status_code == 201
        data = resp.json()
        assert "mock_tweet_" in data["data"]["id"]
        assert "Twitter/X post" in data["data"]["text"]
        assert "#test #agency" in data["data"]["text"]

@patch("publisher.scheduler.post_draft_to_linkedin")
@patch("publisher.twitter_client.requests.post")
def test_publish_due_drafts_success(mock_twitter_post, mock_linkedin_post, test_db):
    """Test that due posts publish to both LinkedIn and Twitter successfully."""
    # 1. Setup mocked HTTP responses
    mock_li_resp = MagicMock()
    mock_li_resp.status_code = 201
    mock_li_resp.headers = {"x-restli-id": "urn:li:share:test_li_123"}
    mock_linkedin_post.return_value = mock_li_resp

    mock_t_resp = MagicMock()
    mock_t_resp.status_code = 201
    mock_t_resp.json.return_value = {"data": {"id": "tweet_12345"}}
    mock_twitter_post.return_value = mock_t_resp

    # 2. Insert test data in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-25', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    
    # Due time is 5 minutes ago
    due_time_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
    
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, twitter_text_content, hashtags, status, voice_profile_hash) "
        "VALUES (?, 'lesson_learned', 'text', 'LinkedIn copy', 'Twitter copy', '#dev', 'approved', 'hash1')",
        (digest_id,)
    )
    draft_id = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO content_queue (draft_id, priority_score, scheduled_time, status) "
        "VALUES (?, 1.0, ?, 'queued')",
        (draft_id, due_time_str)
    )
    queue_id = cursor.lastrowid
    conn.commit()
    
    # Run the tick with DRY_RUN disabled to hit our live mocked methods
    with patch.dict(os.environ, {"DRY_RUN": "false", "TWITTER_CONSUMER_KEY": "a", "TWITTER_CONSUMER_SECRET": "b", "TWITTER_ACCESS_TOKEN": "c", "TWITTER_ACCESS_TOKEN_SECRET": "d"}):
        publish_due_drafts(conn)
        
    # Check updated database records
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    draft_row = cursor.fetchone()
    assert draft_row["status"] == "published"
    
    cursor.execute("SELECT * FROM content_queue WHERE id = ?", (queue_id,))
    queue_row = cursor.fetchone()
    assert queue_row["status"] == "published"
    
    cursor.execute("SELECT * FROM published_posts WHERE draft_id = ?", (draft_id,))
    post_row = cursor.fetchone()
    assert post_row is not None
    assert post_row["linkedin_post_urn"] == "urn:li:share:test_li_123"
    assert post_row["twitter_tweet_id"] == "tweet_12345"
    
    conn.close()

@patch("publisher.scheduler.post_draft_to_linkedin")
@patch("publisher.twitter_client.requests.post")
def test_publish_due_drafts_partial_failure(mock_twitter_post, mock_linkedin_post, test_db):
    """Test that a partial failure (Twitter fails, LinkedIn succeeds) is handled gracefully."""
    # 1. Setup mocked HTTP responses
    mock_li_resp = MagicMock()
    mock_li_resp.status_code = 201
    mock_li_resp.headers = {"x-restli-id": "urn:li:share:test_li_123"}
    mock_linkedin_post.return_value = mock_li_resp

    # Twitter post returns failure
    mock_twitter_post.side_effect = Exception("API connection timed out")

    # 2. Insert test data in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-25', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    
    due_time_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
    
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, twitter_text_content, hashtags, status, voice_profile_hash) "
        "VALUES (?, 'lesson_learned', 'text', 'LinkedIn copy', 'Twitter copy', '#dev', 'approved', 'hash1')",
        (digest_id,)
    )
    draft_id = cursor.lastrowid
    
    cursor.execute(
        "INSERT INTO content_queue (draft_id, priority_score, scheduled_time, status) "
        "VALUES (?, 1.0, ?, 'queued')",
        (draft_id, due_time_str)
    )
    conn.commit()
    
    with patch.dict(os.environ, {"DRY_RUN": "false", "TWITTER_CONSUMER_KEY": "a", "TWITTER_CONSUMER_SECRET": "b", "TWITTER_ACCESS_TOKEN": "c", "TWITTER_ACCESS_TOKEN_SECRET": "d"}):
        publish_due_drafts(conn)
        
    # Check that draft status is published despite Twitter failure
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    draft_row = cursor.fetchone()
    assert draft_row["status"] == "published"
    
    # Confirm DB stores the LinkedIn URN and a NULL/missing Twitter ID
    cursor.execute("SELECT * FROM published_posts WHERE draft_id = ?", (draft_id,))
    post_row = cursor.fetchone()
    assert post_row is not None
    assert post_row["linkedin_post_urn"] == "urn:li:share:test_li_123"
    assert post_row["twitter_tweet_id"] is None
    
    conn.close()
