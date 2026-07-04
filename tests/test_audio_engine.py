import os
import pytest
import json
import numpy as np
from unittest.mock import patch, MagicMock
from pathlib import Path

from generator.audio_engine import (
    generate_voiceover_script,
    synthesize_voiceover,
    get_audio_duration,
    generate_sfx_library,
    mix_audio,
    select_voice_profile,
)

# Sample test data
sample_digest = {
    "summary": "Optimized latency from 500ms to 120ms with psycopg3 pooling.",
    "highlights_json": '["Configured Postgres connection pooler"]',
}
sample_props = {"title": "Metrics Summary", "metrics": [{"label": "Latency", "before": 500, "after": 120, "unit": "ms"}]}


@patch("generator.audio_engine.Anthropic")
def test_voiceover_script_word_count(mock_anthropic):
    """Verify that script generation correctly calls the Anthropic client."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps({"script": "Optimized database query latency and Postgres database throughput. We successfully improved the p99 transaction response time from 500 milliseconds down to 120 milliseconds using database connection pooling. This reduces connection overhead and speeds up the entire API pipeline under high concurrency workloads, ensuring smooth performance."}))]
    mock_client.messages.create.return_value = mock_resp
    
    script = generate_voiceover_script("MetricsSummaryAnimation", sample_digest, sample_props)
    
    assert "Optimized database" in script
    words = len(script.split())
    assert 40 <= words <= 100


@patch("generator.audio_engine.requests.post")
@patch("generator.audio_engine.get_audio_duration", return_value=15.5)
def test_elevenlabs_success(mock_duration, mock_post, tmp_path):
    """Test successful ElevenLabs TTS synthesis."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "audio_base64": "ZmFrZV9tcDNfYnl0ZXM=",  # base64 encoded "fake_mp3_bytes"
        "alignment": {
            "characters": ["T", "e", "s", "t"],
            "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3],
            "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4]
        }
    }
    mock_post.return_value = mock_resp
    
    out_file = str(tmp_path / "voiceover.mp3")
    
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key"}):
        dur, captions = synthesize_voiceover("Test script narration text.", out_file)
        
        assert dur == 15.5
        assert len(captions) == 1
        assert captions[0]["text"] == "Test"
        assert os.path.exists(out_file)
        with open(out_file, "rb") as f:
            assert f.read() == b"fake_mp3_bytes"


@patch("generator.audio_engine.requests.post")
def test_elevenlabs_failure_falls_back(mock_post, tmp_path):
    """Verify that ElevenLabs and OpenAI failure falls back to silent audio generation successfully."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_post.return_value = mock_resp
    
    out_file = str(tmp_path / "voiceover.mp3")
    
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "fake_key", "OPENAI_API_KEY": "fake_key"}):
        duration, captions = synthesize_voiceover("Test script narration text.", out_file)
        assert duration > 0
        assert len(captions) > 0
        assert os.path.exists(out_file)



def test_sfx_library_generation(tmp_path):
    """Verify numpy-synthesized WAV files are created successfully in the library."""
    temp_sfx_dir = str(tmp_path / "sfx")
    
    with patch("generator.audio_engine.SFX_DIR", temp_sfx_dir):
        generate_sfx_library()
        
        for sfx in ("pop.wav", "whoosh.wav", "tick.wav", "shimmer.wav"):
            assert os.path.exists(os.path.join(temp_sfx_dir, sfx))
            # Check file sizes are positive
            assert os.path.getsize(os.path.join(temp_sfx_dir, sfx)) > 0


@patch("generator.audio_engine.subprocess.run")
@patch("generator.audio_engine.get_audio_duration", return_value=12.0)
def test_mix_audio_voiceover_only(mock_duration, mock_run, tmp_path):
    """Test mixing when background music is None (direct copy)."""
    vo_file = tmp_path / "vo.mp3"
    vo_file.write_bytes(b"vo_bytes")
    
    out_file = str(tmp_path / "mixed.mp3")
    
    success = mix_audio(str(vo_file), None, out_file)
    assert success is True
    assert os.path.exists(out_file)
    with open(out_file, "rb") as f:
        assert f.read() == b"vo_bytes"


@patch("generator.audio_engine.subprocess.run")
@patch("generator.audio_engine.get_audio_duration", return_value=12.0)
def test_mix_audio_with_music(mock_duration, mock_run, tmp_path):
    """Test mixing voiceover with music file using ffmpeg filter."""
    vo_file = tmp_path / "vo.mp3"
    vo_file.write_bytes(b"vo_bytes")
    
    music_file = tmp_path / "minimal_tech.mp3"
    music_file.touch()
    
    out_file = str(tmp_path / "mixed.mp3")
    
    # Mock subprocess run to simulate successful ffmpeg run
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc
    
    success = mix_audio(str(vo_file), str(music_file), out_file)
    assert success is True
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "amix" in args[args.index("-filter_complex") + 1]


@patch("generator.audio_engine.subprocess.run")
def test_duration_measurement(mock_run):
    """Verify ffprobe duration parsing works correctly."""
    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps({
        "streams": [
            {"duration": "24.500"}
        ]
    })
    mock_run.return_value = mock_proc
    
    dur = get_audio_duration("/path/to/audio.mp3")
    assert dur == 24.5


@patch("generator.audio_engine.Anthropic")
def test_select_voice_profile_success(mock_anthropic):
    """Verify that select_voice_profile correctly requests and returns the voice ID from Claude's structured response."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps({
        "selected_voice_name": "Laura",
        "reasoning": "Laura matches style updates best"
    }))]
    mock_client.messages.create.return_value = mock_resp
    
    voice_id = select_voice_profile("MetricsSummaryAnimation", sample_digest, "Test script content.")
    
    # Laura's ID is FGY2WhTYpPnrIDTdsKH5
    assert voice_id == "FGY2WhTYpPnrIDTdsKH5"


@patch("generator.audio_engine.Anthropic")
def test_select_voice_profile_failure_fallback(mock_anthropic):
    """Verify that select_voice_profile falls back to Sarah's ID if Claude API fails."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("Anthropic API Error")
    
    voice_id = select_voice_profile("MetricsSummaryAnimation", sample_digest, "Test script content.")
    
    # Sarah's ID is EXAVITQu4vr4xnSDxMaL
    assert voice_id == "EXAVITQu4vr4xnSDxMaL"


def test_female_only_voices():
    """Ensure that the VOICES registry contains only female voices and does not contain Adam."""
    from generator.audio_engine import VOICES
    assert "Adam" not in VOICES
    for name, info in VOICES.items():
        assert "Female" in info["description"] or "female" in info["description"].lower()

