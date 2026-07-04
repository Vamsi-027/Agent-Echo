"""
Tests for the Manim animation generator module.

Tests code generation, markdown stripping, repair flow, and the render
function's file discovery logic.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from generator.manim_generator import (
    _strip_markdown_fences,
    generate_manim_code,
    repair_manim_code,
    _find_rendered_file,
)


class TestStripMarkdownFences:
    """Test the markdown fence stripping utility."""

    def test_plain_code_unchanged(self):
        code = "from manim import *\nclass AgentEchoScene(Scene): pass"
        assert _strip_markdown_fences(code) == code

    def test_strips_python_fence(self):
        code = "```python\nfrom manim import *\nclass AgentEchoScene(Scene): pass\n```"
        expected = "from manim import *\nclass AgentEchoScene(Scene): pass"
        assert _strip_markdown_fences(code) == expected

    def test_strips_plain_fence(self):
        code = "```\nfrom manim import *\n```"
        expected = "from manim import *"
        assert _strip_markdown_fences(code) == expected

    def test_handles_whitespace(self):
        code = "  ```python\nfrom manim import *\n```  "
        result = _strip_markdown_fences(code)
        assert "```" not in result
        assert "from manim import *" in result


class TestGenerateManimCode:
    """Test Claude-based Manim code generation."""

    @patch("generator.manim_generator.Anthropic")
    def test_generates_code_from_digest(self, mock_anthropic_cls):
        """Verify the function calls Claude with proper system prompt and returns code."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        expected_code = (
            "from manim import *\n\n"
            "class AgentEchoScene(Scene):\n"
            "    def construct(self):\n"
            "        self.play(Write(Text('Hello')))\n"
            "        self.wait(2)"
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=expected_code)]
        mock_client.messages.create.return_value = mock_response

        digest = {
            "highlights_json": json.dumps(["Added retry logic", "Fixed race condition"]),
            "raw_summary": "Implemented retry logic with exponential backoff.",
        }

        result = generate_manim_code(digest, pillar="technical_insight")

        assert "AgentEchoScene" in result
        assert "from manim import *" in result
        mock_client.messages.create.assert_called_once()

        # Verify system prompt is passed
        call_kwargs = mock_client.messages.create.call_args
        assert "system" in call_kwargs.kwargs
        assert "ManimCE" in call_kwargs.kwargs["system"]

    @patch("generator.manim_generator.Anthropic")
    def test_includes_timing_when_captions_provided(self, mock_anthropic_cls):
        """Verify caption timing is passed to Claude when available."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="from manim import *\nclass AgentEchoScene(Scene): pass")]
        mock_client.messages.create.return_value = mock_response

        captions = [
            {"text": "Hello", "start": 0.0, "end": 0.5},
            {"text": "world", "start": 0.5, "end": 1.0},
            {"text": "test", "start": 1.0, "end": 1.5},
        ]

        generate_manim_code(
            {"highlights_json": "[]", "raw_summary": "Test"},
            pillar="technical_insight",
            captions=captions,
        )

        call_kwargs = mock_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "Voiceover timing" in user_content
        assert "1.5 seconds" in user_content or "exactly 1.5" in user_content

    @patch("generator.manim_generator.Anthropic")
    def test_strips_fences_from_response(self, mock_anthropic_cls):
        """Verify markdown fences are removed from Claude's response."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text="```python\nfrom manim import *\nclass AgentEchoScene(Scene): pass\n```"
        )]
        mock_client.messages.create.return_value = mock_response

        result = generate_manim_code(
            {"highlights_json": "[]", "raw_summary": "Test"},
            pillar="technical_insight",
        )

        assert not result.startswith("```")
        assert not result.endswith("```")


class TestRepairManimCode:
    """Test the code repair function."""

    @patch("generator.manim_generator.Anthropic")
    def test_passes_error_to_claude(self, mock_anthropic_cls):
        """Verify the error output is sent to Claude for repair."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        fixed_code = "from manim import *\nclass AgentEchoScene(Scene): pass"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fixed_code)]
        mock_client.messages.create.return_value = mock_response

        broken_code = "from manim import *\nclass Foo(Scene): pass"
        error = "NameError: name 'Foo' is not defined"

        result = repair_manim_code(broken_code, error)

        assert result == fixed_code
        call_kwargs = mock_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "NameError" in user_content
        assert "Foo" in user_content


class TestFindRenderedFile:
    """Test the rendered file discovery logic."""

    def test_finds_file_in_standard_location(self, tmp_path):
        """Verify discovery of mp4 in the standard manim output structure."""
        # Create the standard manim output structure
        quality_dir = tmp_path / "media" / "videos" / "manim_scene_test" / "1080p60"
        quality_dir.mkdir(parents=True)
        output_file = quality_dir / "AgentEchoScene.mp4"
        output_file.write_bytes(b"fake mp4")

        scene_file = str(tmp_path / "manim_scene_test.py")

        # Patch to search from tmp_path
        import os
        original_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            result = _find_rendered_file(scene_file)
            assert result is not None
            assert "AgentEchoScene.mp4" in result
        finally:
            os.chdir(original_cwd)

    def test_returns_none_when_no_output(self, tmp_path):
        """Verify None returned when no output exists."""
        scene_file = str(tmp_path / "nonexistent_scene.py")
        result = _find_rendered_file(scene_file)
        assert result is None


class TestVisualSelectorRouting:
    """Test that ManimAnimation is a valid composition choice."""

    def test_manim_in_compositions(self):
        from generator.visual_selector import COMPOSITIONS
        assert "ManimAnimation" in COMPOSITIONS

    def test_schema_includes_manim(self):
        from generator.visual_selector import SCHEMA
        enum_values = SCHEMA["properties"]["composition"]["enum"]
        assert "ManimAnimation" in enum_values
