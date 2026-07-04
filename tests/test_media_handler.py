import pytest
import os
import shutil
import sqlite3
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

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


@patch("shutil.copy")
@patch("os.makedirs")
@patch("os.path.exists", return_value=True)
@patch("os.listdir", return_value=["pop.wav", "whoosh.wav"])
@patch("subprocess.run")
@patch("generator.media_handler.build_remotion_props")
@patch("generator.media_handler.build_editorial_and_shots")
@patch("generator.visual_selector.select_visual_type")
def test_generate_remotion_video_local(
    mock_select_vis,
    mock_build_ed,
    mock_build_props,
    mock_subrun,
    mock_listdir,
    mock_exists,
    mock_makedirs,
    mock_copy,
    mock_env,
):
    from generator.media_handler import generate_remotion_video
    import json
    
    # 1. Setup mocks
    mock_select_vis.return_value = ("PipelineFlowAnimation", "test reasoning")
    mock_build_props.return_value = {
        "title": "Pipeline Flow",
        "stages": [{"name": "Ingest", "description": "stage 1"}]
    }
    mock_build_ed.return_value = {
        "hook": "test hook",
        "takeaway": "test takeaway",
        "cut_type": "smash_cut",
        "shots": [
            {"type": "hook_word", "content": "hook", "entrance": "slam", "duration_beats": 4, "rgb_split": False, "speed_before": 1.0, "color_accent": "#4F8EF7"},
            {"type": "context_3d", "content": "body", "entrance": "rise", "duration_beats": 4, "rgb_split": False, "speed_before": 1.0, "color_accent": "#4F8EF7"},
            {"type": "takeaway_word", "content": "takeaway", "entrance": "scale_in", "duration_beats": 4, "rgb_split": False, "speed_before": 1.0, "color_accent": "#4F8EF7"}
        ]
    }
    
    # Setup subprocess.run mock to touch the output file on execution
    def subrun_side_effect(cmd, **kwargs):
        out_file = cmd[5]
        Path(out_file).touch()
        ret = MagicMock()
        ret.returncode = 0
        return ret
        
    mock_subrun.side_effect = subrun_side_effect
    
    # Setup database draft row
    import sqlite3
    conn = sqlite3.connect(os.environ["DATABASE_PATH"])
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-14', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO drafts (id, digest_id, pillar, format_type, text_content, hashtags, status) VALUES (999, ?, 'lesson_learned', 'video', 'Text content', '#hash', 'pending_review')",
        (digest_id,)
    )
    conn.commit()
    conn.close()
    
    # 2. Patch dependencies in audio_engine, music_director, and beat_sync
    with patch("generator.audio_engine.validate_dependencies") as mock_val_dep, \
         patch("generator.audio_engine.generate_voiceover_script") as mock_vo_script, \
         patch("generator.audio_engine.synthesize_voiceover") as mock_syn_vo, \
         patch("generator.audio_engine.select_voice_profile") as mock_voice_prof, \
         patch("generator.audio_engine.mix_audio") as mock_mix_aud, \
         patch("generator.music_director.select_music_track") as mock_music_track, \
         patch("generator.beat_sync.extract_beat_frames") as mock_beat_frames:
         
        mock_vo_script.return_value = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        mock_voice_prof.return_value = "voice_123"
        mock_syn_vo.return_value = (15.0, [{"text": "word", "start": 0.0, "end": 1.0}])
        mock_music_track.return_value = ("music.mp3", {})
        mock_mix_aud.return_value = True
        mock_beat_frames.return_value = {
            "tempo": 120.0,
            "beat_frames": [15, 30, 45],
            "downbeat_frames": [60],
            "energy_peaks": [],
            "beat_interval": 15
        }
        
        output_file = str(TEST_MEDIA_DIR / "test_local_out.mp4")
        digest = {"summary": "Brief summary", "highlights_json": json.dumps(["point 1", "point 2"])}
        
        # 3. Call function
        success = generate_remotion_video(
            date_str="2026-06-14",
            digest=digest,
            output_path=output_file,
            draft_text="post text",
            draft_id=999
        )
        
        assert success is True
        assert Path(output_file).exists()
        
        # 4. Verify draft row was updated in the DB
        conn = sqlite3.connect(os.environ["DATABASE_PATH"])
        cursor = conn.cursor()
        cursor.execute("SELECT media_refs_json, format_type, visual_composition FROM drafts WHERE id = 999")
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert json.loads(row[0]) == [str(Path(output_file).resolve())]
        assert row[1] == "video"
        assert row[2] == "PipelineFlowAnimation"

