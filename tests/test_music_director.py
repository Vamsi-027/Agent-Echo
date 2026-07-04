import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from generator.music_director import select_music_track, classify_music_profile, score_track_fit

sample_digest = {
    "summary": "Optimized latency from 500ms to 120ms with psycopg3 pooling.",
    "pillar": "technical_insight",
}

@patch("generator.music_director.Anthropic")
def test_classify_music_profile_success(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text='{"music_profile": "technical_precision", "reasoning": "Fits schema work"}')]
    mock_client.messages.create.return_value = mock_resp
    
    profile = classify_music_profile(sample_digest, "technical_insight")
    assert profile == "technical_precision"

def test_music_director_empty_folder_returns_none(tmp_path, monkeypatch):
    with patch("generator.music_director.classify_music_profile", return_value="technical_precision"):
        monkeypatch.setattr("generator.music_director.MUSIC_DIR", str(tmp_path))
        track, profile = select_music_track(sample_digest, "technical_insight")
        assert track is None
        assert profile["energy"] in ("low", "medium", "medium_high", "high")

@patch("generator.music_director.librosa.load")
@patch("generator.music_director.librosa.feature.rms")
def test_score_track_fit_success(mock_rms, mock_load):
    # Mock loaded audio
    mock_load.return_value = (np.ones(22050), 22050)
    # Mock rms: 10 values
    mock_rms.return_value = [np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])]
    
    # Target profile: momentum_triumph (arc: ["confident", "peak", "triumphant"] which maps to [0.7, 0.9, 1.0])
    target_profile = {"arc": ["confident", "peak", "triumphant"]}
    score = score_track_fit("dummy_path.mp3", target_profile)
    
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
