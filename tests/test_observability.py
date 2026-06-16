import pytest
import sqlite3
import os
from pathlib import Path

from db.db import init_db, get_db_connection
from observability.tracer import trace_pipeline_run

TEST_DB_PATH = Path(__file__).parent / "test_obs_runs.db"

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

def test_trace_pipeline_run_success(test_db):
    with trace_pipeline_run("test_success_component"):
        # run some dummy task
        x = 1 + 1
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pipeline_runs WHERE component = 'test_success_component'")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["status"] == "success"
    assert row["completed_at"] is not None
    assert row["error_message"] is None

def test_trace_pipeline_run_failure(test_db):
    with pytest.raises(ValueError, match="Mock Error"):
        with trace_pipeline_run("test_fail_component"):
            raise ValueError("Mock Error")
            
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pipeline_runs WHERE component = 'test_fail_component'")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    assert "Mock Error" in row["error_message"]
