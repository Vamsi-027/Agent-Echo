import os
import time
import pytest
from pathlib import Path
from db.db import init_db, get_db_connection
from capture.file_watcher import FileWatcherHandler, PROJECT_ROOT

TEST_DB_PATH = Path(__file__).parent / "test_file_watcher.db"

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

def test_file_watcher_exclusions():
    handler = FileWatcherHandler()
    
    # 1. Non-excluded file
    assert not handler._is_excluded(PROJECT_ROOT / "capture" / "file_watcher.py")
    
    # 2. Excluded directories
    assert handler._is_excluded(PROJECT_ROOT / ".git" / "config")
    assert handler._is_excluded(PROJECT_ROOT / ".venv" / "bin" / "python")
    assert handler._is_excluded(PROJECT_ROOT / "__pycache__" / "file_watcher.cpython-310.pyc")
    
    # 3. Excluded file suffixes
    assert handler._is_excluded(PROJECT_ROOT / "linkedin_agent.db")
    assert handler._is_excluded(PROJECT_ROOT / "test.log")
    
    # 4. Excluded data folder
    assert handler._is_excluded(PROJECT_ROOT / "data" / "screenshots" / "2026-06-15_1.png")

def test_file_watcher_logging_and_debounce(test_db):
    # Set high debounce time to easily test debounce
    handler = FileWatcherHandler(debounce_seconds=10.0)
    
    test_file = PROJECT_ROOT / "capture" / "dummy_file_to_watch.py"
    
    # Log modified event
    handler._log_event(str(test_file), "edited")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_events WHERE source = 'file'")
    events = cursor.fetchall()
    conn.close()
    
    assert len(events) == 1
    assert events[0]["title"] == "file edited: capture/dummy_file_to_watch.py"
    
    # Try logging modified event again immediately (should be debounced)
    handler._log_event(str(test_file), "edited")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_events WHERE source = 'file'")
    events = cursor.fetchall()
    conn.close()
    
    assert len(events) == 1  # Still 1 event because it was debounced

    # Log deleted event for same file (different action, should not debounce)
    handler._log_event(str(test_file), "deleted")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_events WHERE source = 'file' AND title LIKE '%deleted%'")
    events = cursor.fetchall()
    conn.close()
    
    assert len(events) == 1
