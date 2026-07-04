"""Tests for the visual type selector."""

import json
from unittest.mock import MagicMock, patch

from generator.visual_selector import select_visual_type, infer_composition


def _mock_anthropic_response(payload: dict):
    mock_class = MagicMock()
    mock_instance = MagicMock()
    mock_class.return_value = mock_instance
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(payload))]
    mock_instance.messages.create.return_value = mock_response
    return mock_class


class TestSelectVisualType:
    def test_warrants_video_returns_composition(self):
        mock_class = _mock_anthropic_response(
            {
                "warrants_video": True,
                "composition": "StateMachineAnimation",
                "reasoning": "Day centered on a lifecycle/state transition rework.",
            }
        )
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, reasoning = select_visual_type(
                {"summary": "Reworked the order lifecycle state machine"}, "technical_insight"
            )
        assert composition == "StateMachineAnimation"
        assert "lifecycle" in reasoning

    def test_does_not_warrant_video_returns_none(self):
        mock_class = _mock_anthropic_response(
            {
                "warrants_video": False,
                "composition": "none",
                "reasoning": "Mostly meetings and reading today.",
            }
        )
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, reasoning = select_visual_type(
                {"summary": "Attended planning meetings"}, "reflection"
            )
        assert composition is None
        assert "meetings" in reasoning

    def test_composition_none_even_if_warrants_true(self):
        """Schema technically allows warrants_video=True with composition='none' —
        the 'none' composition must always win, since there's nothing to render."""
        mock_class = _mock_anthropic_response(
            {
                "warrants_video": True,
                "composition": "none",
                "reasoning": "Inconsistent model output edge case.",
            }
        )
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, _ = select_visual_type({"summary": "Something"}, "pillar")
        assert composition is None

    def test_empty_digest_returns_none_without_api_call(self):
        mock_class = MagicMock()
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, reasoning = select_visual_type({}, "pillar")
        assert composition is None
        assert "No digest content" in reasoning
        mock_class.assert_not_called()

    def test_none_digest_returns_none_without_api_call(self):
        mock_class = MagicMock()
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, reasoning = select_visual_type(None, "pillar")
        assert composition is None
        mock_class.assert_not_called()

    def test_api_failure_defaults_to_none(self):
        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_instance.messages.create.side_effect = RuntimeError("API down")
        with patch("generator.visual_selector.Anthropic", mock_class):
            composition, reasoning = select_visual_type({"summary": "Something"}, "pillar")
        assert composition is None
        assert "Classification failed" in reasoning


class TestInferComposition:
    def test_returns_composition_id(self):
        mock_class = _mock_anthropic_response(
            {
                "warrants_video": True,
                "composition": "PipelineFlowAnimation",
                "reasoning": "Multi-stage ETL rework.",
            }
        )
        with patch("generator.visual_selector.Anthropic", mock_class):
            result = infer_composition({"summary": "Rebuilt the ETL pipeline"}, "technical_insight")
        assert result == "PipelineFlowAnimation"

    def test_returns_none_for_no_match(self):
        mock_class = _mock_anthropic_response(
            {
                "warrants_video": False,
                "composition": "none",
                "reasoning": "Just a README typo fix.",
            }
        )
        with patch("generator.visual_selector.Anthropic", mock_class):
            result = infer_composition({"summary": "Fixed a typo in the README"}, "minor")
        assert result is None
