import pytest
import os
import shutil
import sqlite3
import datetime
from pathlib import Path
from unittest.mock import patch

from db.db import init_db
from generator.media_handler import get_available_media, generate_activity_chart

TEST_DB_PATH = Path(__file__).parent / "test_media.db"
TEST_SCREENSHOTS_DIR = Path(__file__).parent / "test_screenshots"
TEST_MEDIA_DIR = Path(__file__).parent / "test_media_dir"

@pytest.fixture
def mock_env():
    # Redirect DB and directories
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    
    # Cleanup sidecars
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
                
    init_db(db_path=TEST_DB_PATH)
    
    # Clean and redirect screenshot & media paths
    if TEST_SCREENSHOTS_DIR.exists():
        shutil.rmtree(TEST_SCREENSHOTS_DIR)
    TEST_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)
    TEST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    
    with patch("generator.media_handler.SCREENSHOTS_DIR", TEST_SCREENSHOTS_DIR), \
         patch("generator.media_handler.MEDIA_DIR", TEST_MEDIA_DIR):
        yield
        
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
                
    if TEST_SCREENSHOTS_DIR.exists():
        shutil.rmtree(TEST_SCREENSHOTS_DIR)
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)

def test_get_available_media(mock_env):
    date_str = "2026-06-14"
    
    # Create mock screenshots
    (TEST_SCREENSHOTS_DIR / f"{date_str}_shot1.png").touch()
    (TEST_SCREENSHOTS_DIR / f"{date_str}_shot2.jpg").touch()
    (TEST_SCREENSHOTS_DIR / "2026-06-15_shot3.png").touch()  # diff date
    
    media = get_available_media(date_str)
    assert len(media) == 2
    assert "shot1.png" in media[0]
    assert "shot2.jpg" in media[1]

def test_generate_activity_chart(mock_env):
    date_str = "2026-06-14"
    
    # Seed mock activity events
    # We will seed one Git event and one Notion event
    conn = sqlite3.connect(str(TEST_DB_PATH))
    cursor = conn.cursor()
    
    local_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    from config_loader import LOCAL_TZ
    event_time_1 = datetime.datetime.combine(local_date, datetime.time(10, 0), tzinfo=LOCAL_TZ).astimezone(datetime.timezone.utc).isoformat()
    event_time_2 = datetime.datetime.combine(local_date, datetime.time(14, 0), tzinfo=LOCAL_TZ).astimezone(datetime.timezone.utc).isoformat()
    
    cursor.execute(
        "INSERT INTO activity_events (source, event_time, title, detail) VALUES ('git', ?, 'Git Commit', '{}')",
        (event_time_1,)
    )
    cursor.execute(
        "INSERT INTO activity_events (source, event_time, title, detail) VALUES ('note', ?, 'Notion Page', '{}')",
        (event_time_2,)
    )
    conn.commit()
    conn.close()
    
    chart_path = generate_activity_chart(date_str)
    assert chart_path is not None
    assert Path(chart_path).exists()
    assert f"{date_str}_activity_chart.png" in chart_path
