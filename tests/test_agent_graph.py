import pytest
import sqlite3
import os
import json
from pathlib import Path
from unittest.mock import patch
from generator.agent_graph import (
    compiled_graph,
    route_after_digest,
    route_after_pillar,
    route_after_format,
    aggregate_digest_node,
    classify_pillar_node,
    select_format_node,
    retrieve_persona_context_node,
    generate_visual_node,
)
from db.db import init_db
from langgraph.graph import END

TEST_DB_PATH = Path(__file__).parent / "test_agent_graph.db"


@pytest.fixture
def test_db():
    # Set environment variable to redirect DB paths
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)

    # Clean up sidecars
    for suffix in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH.with_name(TEST_DB_PATH.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    init_db(db_path=TEST_DB_PATH)

    yield TEST_DB_PATH

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


def test_graph_compilation():
    """Verify that the compiled LangGraph object compiles without throwing errors."""
    assert compiled_graph is not None
    # Validate node names present in graph
    assert "aggregate_digest" in compiled_graph.nodes
    assert "classify_pillar" in compiled_graph.nodes
    assert "select_format" in compiled_graph.nodes
    assert "retrieve_persona_context" in compiled_graph.nodes
    assert "generate_drafts" in compiled_graph.nodes
    assert "generate_visual" in compiled_graph.nodes


def test_conditional_routing_after_digest():
    """Verify routing decisions after the daily digest node."""
    # 1. Success case (should route to classify_pillar)
    state_success = {
        "date": "2026-06-14",
        "digest": {"suggested_pillar": "lesson_learned"},
        "status": "success",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_digest(state_success) == "classify_pillar"

    # 2. No activity case (should route to END)
    state_no_act = {
        "date": "2026-06-14",
        "digest": None,
        "status": "no_activity",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_digest(state_no_act) == END

    # 3. Digest suggested pillar is 'none' (should route to END)
    state_none_pillar = {
        "date": "2026-06-14",
        "digest": {"suggested_pillar": "none"},
        "status": "success",
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_digest(state_none_pillar) == END


def test_conditional_routing_after_pillar():
    """Verify routing decisions after the pillar classifier node."""
    # 1. Valid pillar (should route to select_format)
    state_valid_pillar = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "technical_insight",
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_pillar(state_valid_pillar) == "select_format"

    # 2. None pillar (should route to END)
    state_none_pillar = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "none",
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_pillar(state_none_pillar) == END


def test_conditional_routing_after_format():
    """Verify routing decisions after the format selection node."""
    # 1. Success case (should route to retrieve_persona_context)
    state_success = {
        "date": "2026-06-14",
        "digest": {},
        "status": "success",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    assert route_after_format(state_success) == "retrieve_persona_context"

    # 2. Failure case (should route to END)
    state_fail = {
        "date": "2026-06-14",
        "digest": {},
        "status": "failed",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": "Format selection failed",
    }
    assert route_after_format(state_fail) == END


def test_retrieve_persona_context_node_empty():
    """Verify retrieve_persona_context_node behaves correctly when highlights are missing or empty."""
    state = {
        "date": "2026-06-14",
        "digest": None,
        "status": "success",
        "pillar": "lesson_learned",
        "secondary_pillar": None,
        "format_type": "text",
        "persona_context": None,
        "drafts": [],
        "error": None,
    }
    res = retrieve_persona_context_node(state)
    assert res == {"persona_context": ""}


def _visual_state(format_type, drafts=None):
    return {
        "date": "2026-06-14",
        "digest": {"summary": "Some digest"},
        "status": "success",
        "pillar": "technical_insight",
        "secondary_pillar": None,
        "format_type": format_type,
        "persona_context": None,
        "drafts": drafts if drafts is not None else [{"id": 1, "format_type": format_type, "text_content": "draft"}],
        "error": None,
    }


class TestGenerateVisualNodeGate:
    """select_format_node already made a deliberate format decision —
    generate_visual_node must not second-guess text/poll choices by
    attaching media, and must not silently flip them to 'video'."""

    @patch("generator.media_handler.generate_remotion_video")
    def test_skips_text_format_entirely(self, mock_render):
        state = _visual_state("text")
        result = generate_visual_node(state)
        mock_render.assert_not_called()
        assert result == {"drafts": state["drafts"]}

    @patch("generator.media_handler.generate_remotion_video")
    def test_skips_poll_format_entirely(self, mock_render):
        state = _visual_state("poll")
        result = generate_visual_node(state)
        mock_render.assert_not_called()
        assert result == {"drafts": state["drafts"]}

    @patch("generator.media_handler.generate_remotion_video", return_value=True)
    def test_video_render_success_upgrades_format(self, mock_render, test_db):
        state = _visual_state("image")
        with patch("generator.visual_selector.select_visual_type", return_value=("StateMachineAnimation", "reasoning")):
            result = generate_visual_node(state)
        draft = result["drafts"][0]
        assert draft["format_type"] == "video"
        assert json.loads(draft["media_refs_json"]) == [
            str(Path("data/media/2026-06-14_animation.mp4").resolve())
        ]

    @patch("generator.media_handler.generate_activity_chart", return_value="/tmp/chart.png")
    @patch("generator.media_handler.generate_remotion_video", return_value=False)
    def test_image_format_falls_back_to_chart_on_render_failure(self, mock_render, mock_chart, test_db):
        state = _visual_state("image")
        with patch("generator.visual_selector.select_visual_type", return_value=("StateMachineAnimation", "reasoning")):
            result = generate_visual_node(state)
        draft = result["drafts"][0]
        assert draft["format_type"] == "image"
        assert json.loads(draft["media_refs_json"]) == ["/tmp/chart.png"]

    @patch("generator.media_handler.generate_activity_chart")
    @patch("generator.media_handler.generate_remotion_video", return_value=False)
    def test_video_format_degrades_to_text_on_render_failure(self, mock_render, mock_chart, test_db):
        """A static chart standing in for a video that never got made is a worse,
        inconsistent experience than just not having a visual at all."""
        state = _visual_state("video")
        with patch("generator.visual_selector.select_visual_type", return_value=("StateMachineAnimation", "reasoning")):
            result = generate_visual_node(state)
        draft = result["drafts"][0]
        assert draft["format_type"] == "text"
        assert draft["media_refs_json"] is None
        mock_chart.assert_not_called()
