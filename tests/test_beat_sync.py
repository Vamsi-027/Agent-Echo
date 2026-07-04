import os
import pytest
from generator.beat_sync import extract_beat_frames

def test_beat_sync_none_or_missing_path_returns_fallback():
    result = extract_beat_frames(None)
    assert result["tempo"] == 120.0
    assert len(result["beat_frames"]) == 60
    assert len(result["downbeat_frames"]) == 16
    assert result["beat_interval"] == 15

def test_beat_sync_corrupt_file_falls_back(tmp_path):
    corrupt = tmp_path / "bad.mp3"
    corrupt.write_bytes(b"not audio data")
    
    result = extract_beat_frames(str(corrupt))
    # Should return default 120 BPM structure, not raise an exception
    assert result["tempo"] == 120.0
    assert len(result["beat_frames"]) == 60
    assert len(result["downbeat_frames"]) == 16
    assert result["beat_interval"] == 15


def test_find_chapter_boundary():
    from generator.beat_sync import find_chapter_boundary

    captions = [
        {"text": "My", "start": 0.0, "end": 0.2},
        {"text": "database", "start": 0.2, "end": 0.6},
        {"text": "was", "start": 0.6, "end": 0.8},
        {"text": "leaking", "start": 0.8, "end": 1.2},
        {"text": "connections", "start": 1.2, "end": 1.8},
        {"text": "and", "start": 1.8, "end": 2.0},
        {"text": "crashing", "start": 2.0, "end": 2.5},
    ]

    # Test exact phrase match
    start, idx = find_chapter_boundary("My database was leaking", captions, 0)
    assert start == 0.0
    assert idx == 0

    # Test phrase match starting later
    start, idx = find_chapter_boundary("connections and crashing", captions, 0)
    assert start == 1.2
    assert idx == 4

    # Test mismatch fallback
    start, idx = find_chapter_boundary("not matching phrase", captions, 0)
    assert start is None
    assert idx == -1


def test_derive_shots_from_captions():
    from generator.beat_sync import derive_shots_from_captions

    voiceover_script = "My database was leaking.\n\nConnections were crashing."
    captions = [
        {"text": "My", "start": 0.0, "end": 0.2},
        {"text": "database", "start": 0.2, "end": 0.6},
        {"text": "was", "start": 0.6, "end": 0.8},
        {"text": "leaking.", "start": 0.8, "end": 1.2},
        {"text": "Connections", "start": 1.2, "end": 1.8},
        {"text": "were", "start": 1.8, "end": 2.0},
        {"text": "crashing.", "start": 2.0, "end": 2.5},
    ]
    shot_defs = [
        {"type": "hook_word", "content": "LEAKING"},
        {"type": "context_3d", "content": "CRASHING"},
    ]

    shots_timed = derive_shots_from_captions(voiceover_script, captions, shot_defs, fps=30)
    assert len(shots_timed) == 2
    assert shots_timed[0]["start_frame"] == 0
    # The end frame of shot 0 should align with start frame of shot 1 (at 1.2 seconds = 36 frames)
    assert shots_timed[0]["end_frame"] == 36
    assert shots_timed[1]["start_frame"] == 36
    # The last shot should run to the very end of voiceover (2.5 seconds = 75 frames)
    assert shots_timed[1]["end_frame"] == 75

    # Test mismatch ValueError
    with pytest.raises(ValueError, match="doesn't match shot count"):
        derive_shots_from_captions("Single paragraph.", captions, shot_defs, fps=30)

