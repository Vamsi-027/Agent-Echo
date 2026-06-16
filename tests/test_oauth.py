import pytest
import sqlite3
import datetime
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from db.db import init_db
from publisher.oauth import (
    get_auth_url,
    exchange_code_for_token,
    refresh_access_token,
    save_token_meta,
    check_and_refresh_token
)

TEST_DB_PATH = Path(__file__).parent / "test_oauth.db"

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

@patch.dict(os.environ, {
    "LINKEDIN_CLIENT_ID": "test_client_id",
    "LINKEDIN_CLIENT_SECRET": "test_client_secret"
})
def test_get_auth_url():
    url, state = get_auth_url()
    assert "test_client_id" in url
    assert "state=" in url
    assert len(state) > 0

@patch.dict(os.environ, {
    "LINKEDIN_CLIENT_ID": "test_client_id",
    "LINKEDIN_CLIENT_SECRET": "test_client_secret"
})
@patch("requests.post")
def test_exchange_code_for_token(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "mock_access_token",
        "expires_in": 3600,
        "refresh_token": "mock_refresh_token",
        "refresh_token_expires_in": 7200
    }
    mock_post.return_value = mock_response
    
    res = exchange_code_for_token("test_code")
    
    assert res["access_token"] == "mock_access_token"
    mock_post.assert_called_once()
    assert "accessToken" in mock_post.call_args[0][0]

def test_save_token_meta(test_db):
    save_token_meta(expires_in=3600, refresh_token_expires_in=7200)
    
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM oauth_token_meta")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["expires_at"] is not None
    assert row["refresh_expires_at"] is not None

@patch.dict(os.environ, {
    "DRY_RUN": "false",
    "LINKEDIN_CLIENT_ID": "test_client_id",
    "LINKEDIN_CLIENT_SECRET": "test_client_secret"
})
@patch("publisher.oauth.get_refresh_token", return_value="mock_refresh_token")
@patch("publisher.oauth.store_tokens")
@patch("requests.post")
def test_check_and_refresh_token_due(mock_post, mock_store, mock_get_refresh, test_db):
    # Setup token metadata that is already expired or expiring within 7 days
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    # 5 days from now (which is < 7 days)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    exp_time = (now_utc + datetime.timedelta(days=5)).isoformat()
    cursor.execute("INSERT INTO oauth_token_meta (expires_at) VALUES (?)", (exp_time,))
    conn.commit()
    conn.close()
    
    # Mock POST for refresh
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_access_token",
        "expires_in": 5184000,
        "refresh_token": "new_refresh_token",
        "refresh_token_expires_in": 31536000
    }
    mock_post.return_value = mock_response
    
    check_and_refresh_token()
    
    # Assert refresh token api request was made
    mock_post.assert_called_once()
    mock_store.assert_called_once_with("new_access_token", "new_refresh_token")
