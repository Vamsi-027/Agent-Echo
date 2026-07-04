"""
Manim (3Blue1Brown-style) animation generator for Agent Echo.

Uses Claude to generate ManimCE Python code from the daily digest,
renders it to MP4, and auto-repairs on failure. The output is a silent
MP4 that gets mixed with voiceover audio downstream.
"""

import os
import re
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from anthropic import Anthropic

logger = logging.getLogger("linkedin-agent.manim_generator")

# ── System prompt for Manim code generation ───────────────────────────────────

MANIM_SYSTEM = """\
You are an expert Manim Community Edition (ManimCE) animator.
You write Python Manim code that creates 3Blue1Brown-style explanatory
animations for software engineering concepts.

Rules:
1. Always use ManimCE syntax (from manim import *), never ManimGL
2. The scene class must be named exactly: AgentEchoScene
3. Use self.play() with meaningful animations — never just self.add()
4. Mathematical objects: NumberLine, Axes, Graph, Arrow, Circle, Square,
   Rectangle, Text, Code, BraceLabel, Table
5. State machines: use RoundedRectangle for states, Arrow for transitions,
   highlight active state with color change (self.play(state.animate.set_fill))
6. Pipeline flows: arrange stages LEFT to RIGHT with Arrow between them,
   animate data as a moving Dot along the arrow path
7. Timing: each key concept gets at least 2 seconds of visibility
8. Colors — use the 3B1B palette on a dark background:
   - Background: BLACK (set via config, not in code)
   - Primary text: WHITE
   - Blue: BLUE_C (#58C4DD)
   - Yellow: YELLOW (#FFFF00)
   - Green: GREEN (#83C167)
   - Red: RED_C (#FC6255)
   - Purple: PURPLE (#9A72AC)
   - Orange: ORANGE (#FF862F)
   - Teal: TEAL (#5CD0B3)
9. Always include self.wait() calls between key moments
10. Do NOT use MathTex or Tex — use Text() for all labels
11. Do NOT import anything other than 'from manim import *'
12. Do NOT use deprecated methods: use .animate syntax for property changes
13. Output ONLY valid Python code — no prose, no markdown fences, no comments
    outside the code
14. Keep the total animation between 15-45 seconds

Example pattern for a state machine:
```python
from manim import *

class AgentEchoScene(Scene):
    def construct(self):
        title = Text("State Machine", font_size=36, color=BLUE_C)
        self.play(Write(title))
        self.wait(0.5)
        self.play(title.animate.to_edge(UP))

        states = VGroup(*[
            VGroup(
                RoundedRectangle(corner_radius=0.2, width=2.5, height=0.8)
                .set_fill(BLUE_E, opacity=0.3)
                .set_stroke(BLUE_C),
                Text(name, font_size=20, color=WHITE)
            )
            for name in ["Pending", "Approved", "Published"]
        ]).arrange(RIGHT, buff=1.5)

        self.play(LaggedStart(*[FadeIn(s, shift=UP*0.3) for s in states], lag_ratio=0.3))
        self.wait(1)

        arrows = VGroup(*[
            Arrow(states[i].get_right(), states[i+1].get_left(), color=TEAL, buff=0.1)
            for i in range(len(states)-1)
        ])
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.4))
        self.wait(2)
```

Example pattern for a pipeline flow:
```python
from manim import *

class AgentEchoScene(Scene):
    def construct(self):
        stages = ["Capture", "Digest", "Classify", "Generate", "Publish"]
        colors = [BLUE_C, TEAL, PURPLE, GREEN, ORANGE]

        boxes = VGroup(*[
            VGroup(
                RoundedRectangle(corner_radius=0.15, width=1.8, height=0.7)
                .set_fill(c, opacity=0.2)
                .set_stroke(c, width=2),
                Text(name, font_size=16, color=WHITE)
            )
            for name, c in zip(stages, colors)
        ]).arrange(RIGHT, buff=0.6).scale(0.9)

        for i, box in enumerate(boxes):
            self.play(FadeIn(box, shift=DOWN*0.3), run_time=0.4)

        arrows = VGroup(*[
            Arrow(boxes[i].get_right(), boxes[i+1].get_left(), color=WHITE, buff=0.05, stroke_width=2)
            for i in range(len(boxes)-1)
        ])
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.2))
        self.wait(1)

        dot = Dot(color=YELLOW).move_to(boxes[0])
        self.play(FadeIn(dot))
        for i in range(len(boxes)-1):
            self.play(dot.animate.move_to(boxes[i+1]), run_time=0.6)
            self.play(boxes[i+1][0].animate.set_fill(colors[i+1], opacity=0.5), run_time=0.3)
        self.wait(2)
```
"""

# ── Code generation ───────────────────────────────────────────────────────────


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if Claude wraps its output."""
    code = code.strip()
    if code.startswith("```"):
        # Remove opening fence (```python or ```)
        code = re.sub(r"^```\w*\n?", "", code)
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


def generate_manim_code(
    digest: dict,
    pillar: str,
    captions: list[dict] | None = None,
) -> str:
    """
    Ask Claude to write Manim Python code from the day's digest.

    If captions (word-level timestamps from ElevenLabs) are provided,
    the timing guide is included so self.wait() calls match the voiceover.
    """
    client = Anthropic()

    highlights = digest.get("highlights_json", "[]")
    if isinstance(highlights, str):
        try:
            highlights_list = json.loads(highlights)
        except json.JSONDecodeError:
            highlights_list = [highlights]
    else:
        highlights_list = highlights

    highlights_text = "\n".join(f"- {h}" for h in highlights_list)
    summary = digest.get("raw_summary", "") or digest.get("summary", "")

    user_content = (
        f"Create a 20-30 second Manim animation explaining this engineering content.\n\n"
        f"Pillar: {pillar}\n"
        f"Summary: {summary}\n"
        f"Key highlights:\n{highlights_text}\n\n"
        f"The animation should make the core technical insight visually obvious "
        f"to a software engineer watching this on LinkedIn. "
        f"Focus on the most interesting/surprising aspect of the content."
    )

    # If we have voiceover timing, pass it so animations sync with narration
    if captions:
        total_duration = captions[-1]["end"] if captions else 30.0
        # Sample every 3rd word for a timing guide — enough for calibration
        timing_lines = [
            f"- '{c['text']}' at {c['start']:.1f}s"
            for c in captions[::3]
        ]
        timing_guide = "\n".join(timing_lines[:30])  # cap at 30 lines

        user_content += (
            f"\n\nVoiceover timing (sample):\n{timing_guide}\n\n"
            f"Use self.wait() calls to match animation duration to the voiceover. "
            f"The total animation must be exactly {total_duration:.1f} seconds."
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=MANIM_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    code = response.content[0].text
    return _strip_markdown_fences(code)


# ── Code repair ───────────────────────────────────────────────────────────────


def repair_manim_code(broken_code: str, error_output: str) -> str:
    """Ask Claude to fix broken Manim code given the error message."""
    client = Anthropic()

    # Truncate error to last 800 chars — the relevant traceback is at the end
    error_tail = error_output[-800:] if len(error_output) > 800 else error_output

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=(
            "You are a Manim debugging expert. Fix the broken ManimCE code below.\n"
            "Rules:\n"
            "- Return ONLY valid Python code, no prose, no markdown fences\n"
            "- The scene class must be named AgentEchoScene\n"
            "- Use only ManimCE syntax (from manim import *)\n"
            "- Do NOT use MathTex or Tex — use Text() instead\n"
            "- Do NOT use deprecated methods\n"
            "- Preserve the original animation intent"
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Fix this Manim Python code. Here is the error:\n\n"
                f"```\n{error_tail}\n```\n\n"
                f"Here is the broken code:\n\n"
                f"```python\n{broken_code}\n```\n\n"
                f"Return ONLY the fixed Python code."
            ),
        }],
    )

    code = response.content[0].text
    return _strip_markdown_fences(code)


# ── Rendering with self-repair ────────────────────────────────────────────────


def render_manim_video(
    manim_code: str,
    output_path: str,
    max_retries: int = 3,
    quality: str = "h",
) -> bool:
    """
    Write Manim code to a temp file, render it, and auto-repair on failure.

    Args:
        manim_code: Valid Python source with an AgentEchoScene class.
        output_path: Absolute path for the output MP4.
        max_retries: Number of render + repair cycles before giving up.
        quality: Manim quality flag — 'l' (480p), 'm' (720p), 'h' (1080p).

    Returns:
        True if rendering succeeded and the output file exists.
    """
    abs_output = Path(output_path).resolve()
    abs_output.parent.mkdir(parents=True, exist_ok=True)

    current_code = manim_code

    for attempt in range(max_retries):
        scene_file = None
        try:
            # Write code to a temp file in the project directory
            # (avoids issues with /tmp path resolution in some manim versions)
            with tempfile.NamedTemporaryFile(
                suffix=".py",
                mode="w",
                delete=False,
                prefix="manim_scene_",
            ) as f:
                f.write(current_code)
                scene_file = f.name

            # Build the manim render command.
            # Pin resolution/fps to match Remotion's output spec (1080x1080 @30fps)
            # so Manim and Remotion clips can later be concatenated without a
            # scale/retime pass — Manim's own -q presets default to 16:9 @60fps.
            cmd = [
                "manim", "render",
                scene_file,
                "AgentEchoScene",
                f"-q{quality}",
                "-r", "1080,1080",
                "--fps", "30",
                "--format", "mp4",
                "--disable_caching",
            ]

            logger.info(
                f"Manim render attempt {attempt + 1}/{max_retries}: "
                f"{scene_file} -> {abs_output}"
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                # Manim puts output in media/videos/<filename>/...
                # We need to find the actual output and move it
                rendered_path = _find_rendered_file(scene_file)
                if rendered_path and Path(rendered_path).exists():
                    import shutil
                    shutil.move(str(rendered_path), str(abs_output))
                    logger.info(
                        f"Manim render succeeded on attempt {attempt + 1}: "
                        f"{abs_output} ({abs_output.stat().st_size} bytes)"
                    )
                    return True
                else:
                    logger.warning(
                        f"Manim reported success but output not found. "
                        f"stdout: {result.stdout[-300:]}"
                    )

            # Render failed — log and attempt repair
            error_text = result.stderr + result.stdout
            logger.warning(
                f"Manim render failed (attempt {attempt + 1}): "
                f"{error_text[-500:]}"
            )

            if attempt < max_retries - 1:
                logger.info("Attempting Claude-assisted code repair...")
                current_code = repair_manim_code(current_code, error_text)

        except subprocess.TimeoutExpired:
            logger.warning(f"Manim render timed out (attempt {attempt + 1})")
        except Exception as e:
            logger.error(f"Manim render error (attempt {attempt + 1}): {e}")
        finally:
            if scene_file and os.path.exists(scene_file):
                os.unlink(scene_file)

    logger.error(f"Manim render failed after {max_retries} attempts")
    return False


def _find_rendered_file(scene_file: str) -> str | None:
    """
    Locate the MP4 output that manim produced.

    Manim writes to: media/videos/<stem>/<quality>/AgentEchoScene.mp4
    The exact quality subfolder depends on the -q flag:
      -ql -> 480p15, -qm -> 720p30, -qh -> 1080p60
    """
    stem = Path(scene_file).stem
    media_base = Path("media") / "videos" / stem

    if not media_base.exists():
        # Also check relative to the scene file's directory
        media_base = Path(scene_file).parent / "media" / "videos" / stem
        if not media_base.exists():
            return None

    # Search all quality subdirectories for AgentEchoScene.mp4
    for quality_dir in media_base.iterdir():
        if quality_dir.is_dir():
            candidate = quality_dir / "AgentEchoScene.mp4"
            if candidate.exists():
                return str(candidate)

    return None


# ── Audio mixing for Manim videos ────────────────────────────────────────────


def mix_manim_with_audio(
    video_path: str,
    voiceover_path: str,
    music_path: str | None,
    output_path: str,
    music_db: float = -22.0,
) -> bool:
    """
    Combine the silent Manim MP4 with voiceover (and optionally music) via ffmpeg.

    The Manim video is the visual track; voiceover is primary audio.
    If music_path is provided, it's mixed in at music_db volume.
    If the Manim video is shorter than the audio, it loops/holds the last frame.
    If it's longer, the video is trimmed to audio length.
    """
    import shutil

    if not shutil.which("ffmpeg"):
        logger.error("ffmpeg not found — cannot mix audio")
        return False

    abs_output = Path(output_path).resolve()
    abs_output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if music_path and Path(music_path).exists():
            # Mix voiceover + music, then combine with video
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(voiceover_path),
                "-i", str(music_path),
                "-filter_complex",
                f"[2:a]volume={music_db}dB[music];"
                f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(abs_output),
            ]
        else:
            # Just combine video + voiceover
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(voiceover_path),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(abs_output),
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg mix failed: {result.stderr[-500:]}")
            return False

        if abs_output.exists() and abs_output.stat().st_size > 0:
            logger.info(f"Audio mix complete: {abs_output}")
            return True

        logger.error("ffmpeg produced no output file")
        return False

    except subprocess.TimeoutExpired:
        logger.error("ffmpeg mix timed out")
        return False
    except Exception as e:
        logger.error(f"Audio mix error: {e}")
        return False
