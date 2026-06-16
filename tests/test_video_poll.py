import os
import json
import pytest
from unittest.mock import MagicMock, patch, ANY
import requests

from publisher.linkedin_client import post_draft_to_linkedin, upload_video
from generator.draft_generator import edit_draft
from generator.agent_graph import generate_drafts_node

@pytest.fixture
def mock_anthropic():
    with patch("generator.agent_graph.Anthropic") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_anthropic_edit():
    with patch("generator.draft_generator.Anthropic") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance

@patch("publisher.linkedin_client.get_access_token", return_value="test_token")
def test_post_poll_draft_dry_run(mock_token):
    # Set DRY_RUN mode
    with patch.dict(os.environ, {"DRY_RUN": "true", "LINKEDIN_AUTHOR_URN": "urn:li:person:123"}):
        draft = {
            "id": 1,
            "format_type": "poll",
            "text_content": "Check out this poll!",
            "media_refs_json": json.dumps({
                "question": "What is your preference?",
                "options": ["A", "B", "C"],
                "duration": "THREE_DAYS"
            }),
            "hashtags": "#test"
        }
        
        resp = post_draft_to_linkedin(draft)
        assert resp.status_code == 201
        assert "urn:li:share:mock_poll_post_" in resp.headers["x-restli-id"]

@patch("publisher.linkedin_client.get_access_token", return_value="test_token")
def test_post_video_draft_dry_run(mock_token):
    with patch.dict(os.environ, {"DRY_RUN": "true"}):
        draft = {
            "id": 2,
            "format_type": "video",
            "text_content": "Check out this video!",
            "media_refs_json": json.dumps(["/path/to/video.mp4"]),
            "hashtags": "#video"
        }
        
        resp = post_draft_to_linkedin(draft)
        assert resp.status_code == 201
        assert "urn:li:share:mock_video_post_" in resp.headers["x-restli-id"]

@patch("publisher.linkedin_client.requests.post")
@patch("publisher.linkedin_client.requests.put")
@patch("publisher.linkedin_client.requests.get")
@patch("publisher.linkedin_client.get_access_token", return_value="test_token")
@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=12345)
def test_upload_video_live(mock_size, mock_exists, mock_token, mock_get, mock_put, mock_post):
    with patch.dict(os.environ, {"DRY_RUN": "false"}):
        # 1. Mock Initialize Response
        mock_init_resp = MagicMock()
        mock_init_resp.json.return_value = {
            "value": {
                "video": "urn:li:video:12345",
                "uploadInstructions": [{"uploadUrl": "https://upload.url"}],
                "uploadToken": "test_upload_token"
            }
        }
        mock_init_resp.status_code = 200
        
        # 2. Mock PUT Response
        mock_put_resp = MagicMock()
        mock_put_resp.headers = {"ETag": "test_etag"}
        mock_put_resp.status_code = 201
        
        # 3. Mock Finalize Response
        mock_finalize_resp = MagicMock()
        mock_finalize_resp.status_code = 200
        
        mock_post.side_effect = [mock_init_resp, mock_finalize_resp]
        
        # 4. Mock Poll Status Response
        mock_poll_resp = MagicMock()
        mock_poll_resp.status_code = 200
        mock_poll_resp.json.return_value = {
            "processingState": "AVAILABLE"
        }
        mock_get.return_value = mock_poll_resp
        from unittest.mock import mock_open
        with patch("builtins.open", mock_open(read_data=b"video_bytes")):
            # Patch time.sleep to not slow down tests
            with patch("time.sleep", MagicMock()):
                video_urn = upload_video("urn:li:person:123", "/path/to/video.mp4")
                
                assert video_urn == "urn:li:video:12345"
                assert mock_post.call_count == 2
                mock_put.assert_called_once_with(
                    "https://upload.url",
                    data=ANY,
                    headers={
                        "Authorization": "Bearer test_token",
                        "Content-Type": "application/octet-stream"
                    }
                )
                mock_get.assert_called_once_with("https://api.linkedin.com/rest/videos/urn:li:video:12345", headers=ANY)
