import os
import sys
import time
import socket
import threading
import sqlite3
import pytest
import requests
from unittest.mock import patch
from pathlib import Path
from db.db import init_db

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def mock_db_env():
    import tempfile
    
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()
    
    with patch.dict(os.environ, {"DATABASE_PATH": db_path}):
        init_db(db_path=Path(db_path))
        
        # Seed dummy data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activity_events (source, event_time, title, detail) VALUES "
            "('git', '2026-07-04T12:00:00Z', 'Committed code changes', '{\"id\":\"123\"}')"
        )
        cursor.execute(
            "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
            "VALUES ('2026-07-04', 1, 'Raw summary', '[]', '{}', 'technical_insight')"
        )
        cursor.execute(
            "INSERT INTO drafts (id, digest_id, pillar, format_type, text_content, status) VALUES "
            "(1, 1, 'technical_insight', 'text', 'Draft text content', 'pending_review')"
        )
        conn.commit()
        conn.close()
        
        yield db_path
        
    try:
        os.unlink(db_path)
    except OSError:
        pass


def get_free_port():
    s = socket.socket()
    s.bind(('localhost', 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.anyio
async def test_dashboard_server_endpoints(mock_db_env):
    from dashboard_server import run_server
    
    port = get_free_port()
    
    # Run the server in a daemon background thread
    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "localhost", "port": port},
        daemon=True
    )
    server_thread.start()
    
    # Wait a brief moment for the server to bind
    time.sleep(0.5)
    
    base_url = f"http://localhost:{port}"
    
    # 1. Test HTML index serving
    response = requests.get(f"{base_url}/")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    assert "Agent Echo" in response.text
    
    # 2. Test JSON API serving
    api_response = requests.get(f"{base_url}/api/data")
    assert api_response.status_code == 200
    assert "application/json" in api_response.headers["Content-Type"]
    
    data = api_response.json()
    assert "stats" in data
    assert "events" in data
    assert "drafts" in data
    
    # Validate stats values
    assert data["stats"]["events_count"] == 1
    assert data["stats"]["drafts_pending"] == 1
    
    # Validate events contents
    assert len(data["events"]) == 1
    assert data["events"][0]["source"] == "git"
    assert data["events"][0]["title"] == "Committed code changes"
    
    # 3. Test Invalid path
    invalid_response = requests.get(f"{base_url}/invalid-path")
    assert invalid_response.status_code == 404


@pytest.mark.anyio
@patch("generator.draft_generator.approve_draft")
async def test_dashboard_server_chat(mock_approve, mock_db_env):
    from dashboard_server import run_server
    
    port = get_free_port()
    
    # Run the server in a daemon background thread
    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "localhost", "port": port},
        daemon=True
    )
    server_thread.start()
    
    # Wait a brief moment for the server to bind
    time.sleep(0.5)
    
    base_url = f"http://localhost:{port}"
    
    # Send a POST chat request to approve draft 1
    chat_payload = {"message": "approve draft 1"}
    chat_response = requests.post(f"{base_url}/api/chat", json=chat_payload)
    
    assert chat_response.status_code == 200
    assert "application/json" in chat_response.headers["Content-Type"]
    
    data = chat_response.json()
    assert "response" in data
    assert "Draft #1 approved and queued" in data["response"]
    
    # Assert generator approve_draft function was called
    mock_approve.assert_called_once_with(1)


@pytest.mark.anyio
@patch("db.vector_db.search_persona")
@patch("generator.draft_generator.generate_topic_draft")
async def test_dashboard_chat_create_post(mock_gen, mock_search, mock_db_env):
    mock_search.return_value = [{"text": "persona chunk 1", "category": "experience"}]
    mock_gen.return_value = ("Here is a drafted post text about Fable 5.", "#fable5 #gaming")
    
    from dashboard_server import run_server
    port = get_free_port()
    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "localhost", "port": port},
        daemon=True
    )
    server_thread.start()
    time.sleep(0.5)
    
    base_url = f"http://localhost:{port}"
    
    # Send a POST chat request to create a post about Fable 5
    chat_payload = {"message": "Create a post about Fable 5"}
    chat_response = requests.post(f"{base_url}/api/chat", json=chat_payload)
    
    assert chat_response.status_code == 200
    data = chat_response.json()
    assert "response" in data
    assert "chat-card-review" in data["response"]
    assert "Generated" in data["response"]
    
    # Verify it got inserted into database drafts table
    from db.db import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) FROM drafts WHERE text_content LIKE '%Fable 5%'").fetchone()
    assert row[0] == 1
    conn.close()
