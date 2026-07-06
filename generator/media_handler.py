import os
import json
import datetime
import subprocess
import tempfile
import logging
import shutil
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from db.db import get_db_connection
from config_loader import LOCAL_TZ

logger = logging.getLogger("linkedin-agent.media_handler")

SCREENSHOTS_DIR = Path("data/screenshots")
MEDIA_DIR = Path("data/media")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"


def get_available_media(date_str: str) -> list[str]:
    """
    Scans the screenshots directory for files starting with YYYY-MM-DD.
    Returns absolute paths of matching image/video files.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = []
    # Find matching files
    for filepath in SCREENSHOTS_DIR.glob(f"{date_str}_*"):
        if filepath.suffix.lower() in (
            ".png",
            ".jpg",
            ".jpeg",
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
        ):
            matches.append(str(filepath.resolve()))
    return sorted(matches)


def generate_activity_chart(date_str: str) -> str | None:
    """
    Queries SQLite for activity counts on the target date,
    generates a premium activity summary chart using matplotlib,
    saves it to data/media/, and returns its absolute path.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # Calculate timezone bounds for target date
    try:
        local_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    start_local = datetime.datetime.combine(
        local_date, datetime.time.min, tzinfo=LOCAL_TZ
    )
    end_local = datetime.datetime.combine(
        local_date, datetime.time.max, tzinfo=LOCAL_TZ
    )
    start_utc = start_local.astimezone(datetime.timezone.utc)
    end_utc = end_local.astimezone(datetime.timezone.utc)
    start_iso = start_utc.isoformat()
    end_iso = end_utc.isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Query count of different activity sources
    cursor.execute(
        "SELECT source, COUNT(*) as count FROM activity_events "
        "WHERE event_time >= ? AND event_time <= ? GROUP BY source",
        (start_iso, end_iso),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    sources = []
    counts = []

    # Map sources to nice labels
    label_map = {
        "git": "GitHub Commits/PRs",
        "note": "Notion Edits",
        "browser": "Research Tabs",
        "calendar": "Meetings/Events",
        "file": "Local File Edits",
    }

    for r in rows:
        src = r["source"]
        label = label_map.get(src, src.capitalize())
        sources.append(label)
        counts.append(r["count"])

    # Generate Chart
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)

    # Custom harmonious color palette
    colors = ["#0077b5", "#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b"][: len(sources)]

    y_pos = np.arange(len(sources))
    bars = ax.barh(y_pos, counts, align="center", color=colors, height=0.55)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sources, fontsize=10, fontweight="bold", color="#333333")
    ax.invert_yaxis()  # top-down

    ax.set_xlabel(
        "Count of Activities", fontsize=10, fontweight="bold", color="#555555"
    )
    ax.set_title(
        f"Developer Activity Breakdown — {date_str}",
        fontsize=12,
        fontweight="bold",
        color="#111111",
        pad=15,
    )

    # Style tweaks
    ax.set_facecolor("#fdfdfd")
    fig.patch.set_facecolor("#ffffff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    # Add values on the bar tips
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + 0.1,
            bar.get_y() + bar.get_height() / 2,
            f" {int(width)}",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
            color="#333333",
        )

    plt.tight_layout()

    output_path = MEDIA_DIR / f"{date_str}_activity_chart.png"
    plt.savefig(
        output_path,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight",
    )
    plt.close()

    return str(output_path.resolve())


# ==================== Remotion Video Generation ====================

# Schema definitions for each composition's props
COMPOSITION_SCHEMAS = {
    "StateMachineAnimation": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "states": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["name", "label"],
                    "additionalProperties": False,
                },
            },
            "transitions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["from", "to", "label"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "states", "transitions"],
        "additionalProperties": False,
    },
    "PipelineFlowAnimation": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "stages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "stages"],
        "additionalProperties": False,
    },
    "ArchitectureRevealAnimation": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                    "required": ["name", "x", "y"],
                    "additionalProperties": False,
                },
            },
            "connections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "integer"},
                        "to": {"type": "integer"},
                    },
                    "required": ["from", "to"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "components", "connections"],
        "additionalProperties": False,
    },
    "MetricsSummaryAnimation": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "metrics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "before": {"type": "number"},
                        "after": {"type": "number"},
                        "unit": {"type": "string"},
                    },
                    "required": ["label", "before", "after", "unit"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "metrics"],
        "additionalProperties": False,
    },
}


def _build_scene_graph(
    engine: str,
    composition: str,
    shots: list[dict],
    props: dict,
    output_path: str | None,
    render_status: str,
    error_log: str | None,
    retry_count: int,
) -> str:
    """
    Serialize the scene graph persisted on drafts.scene_graph_json.

    A "block" is the renderable unit (one subprocess call, one output file);
    "shots" are the per-beat timing/overlay metadata nested inside whichever
    block rendered them. Every draft produces exactly one block today —
    mixing engines within a video means emitting more than one block later,
    which this shape supports without a second migration.
    """
    shots_with_ids = []
    seen_ids: set[str] = set()
    for i, s in enumerate(shots or []):
        shot_id = s.get("id") or f"shot_{i}"
        if shot_id in seen_ids:
            shot_id = f"{shot_id}_{i}"
        seen_ids.add(shot_id)
        shots_with_ids.append({**s, "id": shot_id})
    block_id = "block_0"
    block = {
        "id": block_id,
        "order": 0,
        "engine": engine,
        "composition_id": composition,
        "shot_ids": [s["id"] for s in shots_with_ids],
        "render_status": render_status,
        "output_path": output_path,
        "error_log": error_log,
        "retry_count": retry_count,
    }
    return json.dumps({
        "blocks": [block],
        "shots": shots_with_ids,
        "props_by_block": {block_id: props},
        "final_output_path": output_path,
        "stitch_status": "single_block",
    })


def build_remotion_props(
    composition: str,
    digest: dict,
    error_feedback: str | None = None,
    draft_text: str | None = None,
) -> dict | None:
    """
    Use Claude structured output to extract animation properties
    from the daily digest and optional draft text, matching the target composition's schema.

    If error_feedback is passed (the stderr/stdout tail from a failed render
    attempt), it's appended to the prompt so Claude can self-correct on retry.
    """
    schema = COMPOSITION_SCHEMAS.get(composition)
    if not schema:
        logger.error(f"No schema found for composition: {composition}")
        return None

    try:
        from anthropic import Anthropic

        client = Anthropic()

        highlights = digest.get("highlights_json", "[]")
        categories = digest.get("categories_json", "{}")
        summary = digest.get("summary", "")

        system_prompt = (
            f"You are a technical animation data extractor. Given a developer's "
            f"daily work digest and an optional post draft text, extract the key information needed to render a "
            f"'{composition}' animation. Focus on the actual technical content — "
            f"real component names, state names, pipeline stages, or metrics "
            f"from the digest or the post draft text. Do NOT use generic names like "
            f"'Init', 'Load', 'Execute' or 'Latency', 'Throughput' unless they are the primary subject of the text. "
            f"Instead, extract names, components, or metrics that represent the actual content of the post. "
            f"Keep titles concise (under 60 chars). "
            f"For ArchitectureRevealAnimation, x/y values must be between 0.0 and 1.0."
        )

        user_prompt = (
            f"Extract animation properties for a '{composition}' from this digest and post draft:\n\n"
            f"Summary: {summary}\n"
            f"Highlights: {highlights}\n"
            f"Categories: {categories}"
        )
        if draft_text:
            user_prompt += f"\nPost Draft Text:\n{draft_text}"

        if error_feedback:
            user_prompt += (
                f"\n\nThe previous render attempt with these props failed. "
                f"Render error:\n{error_feedback}\n\n"
                f"Adjust the props to avoid this failure — e.g. fill in any "
                f"empty or missing arrays, fix out-of-range values, or "
                f"simplify content that may have caused the crash."
            )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        props = json.loads(response.content[0].text)
        logger.info(f"Built Remotion props for {composition}: {list(props.keys())}")
        return props

    except Exception as e:
        logger.error(f"Failed to build Remotion props: {e}")
        return None


EDITOR_SYSTEM = """
You are a professional motion graphics editor with 10 years experience
making dopamine-optimized, high-paced technical short-form video reels for engineering audiences.
The timeline is structured as a sequence of shots (pattern interrupts every 2-3 seconds) instead of acts.

For this specific content, make editorial decisions:

1. HOOK (single line, max 80 chars): The most attention-grabbing hook. Never introduce yourself.
   Start with a high-tension, first-person dramatic realization or technical failure (e.g. "My database was leaking connections", "One wrong database call cost us $10k").
2. SHOTS: A list of 4 to 8 shots that divide the video duration.
   Each shot needs a unique "id": a short lowercase snake_case slug describing
   its content (e.g. "the_bug", "root_cause", "the_fix", "result") — this is
   used later to reference and re-edit a single shot without touching the rest.
   Each shot must be mapped to a beat-count duration (e.g. 1 to 4 beats).
   Choose appropriate visual styles/entrances, speed ramping, or RGB splits for transitions.
   Constraint: Use effects (like rgb_split or zoom_punch or speed_before < 1.0) selectively — at most once or twice per video, and never stacked on the same frame.
3. TAKEAWAY (single principle, max 120 chars): What the viewer remembers. A principle, not a summary.
4. CUT TYPE: hard_cut, smash_cut, fade_black, push_forward, push_back.

Return structured JSON only.
"""

def build_editorial_and_shots(
    composition: str,
    digest: dict,
    voiceover_script: str,
    n_shots: int,
    m_elements: int,
    draft_text: str | None = None,
) -> dict | None:
    """
    Use Claude structured output to generate shot metadata matching the
    number of paragraphs in the voiceover script.
    """
    try:
        from anthropic import Anthropic

        client = Anthropic()

        # Build schema to force Claude to output the exact types expected by Remotion
        schema = {
            "type": "object",
            "properties": {
                "hook": {
                    "type": "string",
                    "description": "An attention-grabbing hook phrase (under 80 chars) for opening the video.",
                },
                "takeaway": {
                    "type": "string",
                    "description": "A single technical takeaway or principle (under 120 chars) for the closing shot.",
                },
                "cut_type": {
                    "type": "string",
                    "enum": ["hard_cut", "smash_cut", "fade_black", "push_forward", "push_back"],
                    "description": "Transition cut style at boundaries.",
                },
                "shots": {
                    "type": "array",
                    "minItems": n_shots,
                    "maxItems": n_shots,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["hook_word", "context_3d", "tension", "reveal", "statistic", "takeaway_word"],
                                "description": "Type of layout to render for this shot.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Text overlay shown on screen during this shot. Keep short (max 2-3 lines, max 8-10 words). Use newlines \\n for multi-line formatting.",
                            },
                            "entrance": {
                                "type": "string",
                                "enum": ["slam", "zoom_punch", "slide_left", "slide_right", "rise", "drop", "scale_in"],
                                "description": "Entrance animation style.",
                            },
                            "duration_beats": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Duration in musical beats (typically 3 to 6).",
                            },
                            "rgb_split": {
                                "type": "boolean",
                                "description": "Whether to trigger chromatic aberration/glitch effect at start of shot.",
                            },
                            "speed_before": {
                                "type": "number",
                                "description": "Speed ramping factor for incoming transition (usually 0.5 to 2.0, default 1.0).",
                            },
                            "color_accent": {
                                "type": "string",
                                "description": "Hex color code for accent highlights (e.g. #4F8EF7, #10B981, #A78BFA).",
                            },
                        },
                        "required": ["type", "content", "entrance", "duration_beats", "rgb_split", "speed_before", "color_accent"],
                        "additionalProperties": False,
                    },
                    "description": f"Must contain exactly N={n_shots} shots, in order matching the voiceover paragraphs.",
                },
            },
            "required": ["hook", "takeaway", "cut_type", "shots"],
            "additionalProperties": False,
        }

        # Format system prompt
        system_prompt = (
            f"{EDITOR_SYSTEM}\n\n"
            f"CRITICAL DESIGN CONSTRAINTS:\n"
            f"1. You must generate exactly N={n_shots} shots. The length of the 'shots' array must be exactly {n_shots}.\n"
            f"2. Each shot in the list corresponds to one paragraph in the voiceover script in the exact same order.\n"
            f"3. To align with the 3D visual elements in the '{composition}' composition, there must be exactly "
            f"M={m_elements} body shots (shots of type other than 'hook_word' and 'takeaway_word') in the list.\n"
            f"   - These M body shots should occupy the intermediate positions (typically shots index 1 to M).\n"
            f"   - Shot 0 (the first shot) should have type 'hook_word' or 'context_3d'.\n"
            f"   - Shot N-1 (the last shot) should have type 'takeaway_word' and contain the closing takeaway text."
        )

        user_prompt = (
            f"Select visual edits and shot content for a '{composition}' video based on this voiceover script:\n\n"
            f"Voiceover script ({n_shots} paragraphs):\n{voiceover_script}\n\n"
            f"Digest summary: {digest.get('summary', '') or digest.get('raw_summary', '')}\n"
            f"Draft text: {draft_text or 'None'}"
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        editorial = json.loads(response.content[0].text)
        logger.info(f"Built editorial structure and shot list: {len(editorial['shots'])} shots")
        return editorial

    except Exception as e:
        logger.error(f"Failed to build editorial structure and shots: {e}")
        return None


def get_editor_context() -> str:
    """
    Query SQLite for recent published post history, performance metrics,
    and pillar sequence to provide context for the editor brain.
    """
    recent_summaries = ""
    top_perf_summary = ""
    pillar_seq = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Recent posts (last 7 days)
        cursor.execute(
            "SELECT text_content, pillar FROM drafts "
            "WHERE status = 'published' AND updated_at >= datetime('now', '-7 days') "
            "LIMIT 7"
        )
        recent = cursor.fetchall()
        recent_summaries = "\n".join([f"- Pillar: {r['pillar']}, Text: {r['text_content'][:100]}..." for r in recent])
        
        # Top performance
        cursor.execute(
            "SELECT l.impressions, l.reactions, d.pillar, d.format_type "
            "FROM performance_log l "
            "JOIN published_posts p ON l.linkedin_post_urn = p.linkedin_post_urn "
            "JOIN drafts d ON p.draft_id = d.id "
            "ORDER BY l.impressions DESC LIMIT 5"
        )
        top_perf = cursor.fetchall()
        top_perf_summary = "\n".join([
            f"- Pillar: {t['pillar']}, Format: {t['format_type']}, Impressions: {t['impressions']}, Reactions: {t['reactions']}"
            for t in top_perf
        ])
        
        # Recent pillars
        cursor.execute(
            "SELECT DISTINCT pillar FROM drafts "
            "WHERE status = 'published' "
            "ORDER BY updated_at DESC LIMIT 10"
        )
        recent_pillars = cursor.fetchall()
        pillar_seq = ", ".join([r['pillar'] for r in recent_pillars])
        
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to load editor context: {e}")
        
    return f"""Recent posts (last 7 days):
{recent_summaries or "None"}

Performance data (top performing formats & pillars):
{top_perf_summary or "None"}

Pillar history (avoid repeating same sequence):
{pillar_seq or "None"}"""

def snap_to_nearest_downbeat(target_frame: int, downbeats: list[int]) -> int:
    if not downbeats:
        return target_frame
    return min(downbeats, key=lambda f: abs(f - target_frame))


def generate_manim_video(
    date_str: str,
    digest: dict,
    output_path: str,
    draft_text: str | None = None,
    draft_id: int | None = None,
) -> bool:
    """
    Generate a Manim (3Blue1Brown-style) animation video with voiceover.

    Pipeline:
    1. Generate voiceover script via Claude
    2. Synthesize voiceover with ElevenLabs (timestamps for sync)
    3. Generate Manim Python code via Claude (with timing from captions)
    4. Render Manim scene to silent MP4 (with self-repair loop)
    5. Mix video + voiceover + optional music via ffmpeg
    6. Update draft in DB if draft_id is provided

    Returns True if the final mixed video exists at output_path.
    """
    from generator.audio_engine import (
        validate_dependencies,
        generate_voiceover_script,
        synthesize_voiceover,
        select_voice_profile,
    )
    from generator.manim_generator import (
        generate_manim_code,
        render_manim_video,
        mix_manim_with_audio,
    )

    try:
        validate_dependencies()
    except Exception as e:
        logger.error(f"Dependency validation failed: {e}")
        return False

    pillar = digest.get("suggested_pillar") or digest.get("pillar", "")

    # Build minimal props for voiceover script generation
    props = {
        "title": digest.get("summary", "Technical Insight")[:80],
        "highlights": digest.get("highlights_json", "[]"),
    }

    # ── Audio generation ──────────────────────────────────────────────────
    try:
        os.makedirs("data/audio", exist_ok=True)

        # Dynamic chapter count based on highlight density
        highlights_list = json.loads(digest.get("highlights_json") or "[]")
        n_shots = max(4, min(8, len(highlights_list) + 2))

        script = generate_voiceover_script(
            "ManimAnimation", digest, props,
            draft_text=draft_text, n_shots=n_shots,
        )

        voice_id = select_voice_profile("ManimAnimation", digest, script)
        vo_path = f"data/audio/{date_str}_manim_voiceover.mp3"

        duration_secs, captions = synthesize_voiceover(
            script, vo_path, voice_id=voice_id,
        )

        logger.info(
            f"Voiceover: {duration_secs:.1f}s, {len(captions)} caption words"
        )

    except Exception as e:
        logger.error(f"Audio generation failed for Manim video: {e}")
        return False

    # ── Manim code generation & render ────────────────────────────────────
    try:
        manim_code = generate_manim_code(
            digest, pillar, captions=captions,
        )
        logger.info(f"Generated Manim code: {len(manim_code)} chars")

        silent_video_path = f"data/media/{date_str}_manim_silent.mp4"
        render_success = render_manim_video(
            manim_code, silent_video_path, max_retries=3,
        )

        if not render_success:
            logger.error("Manim render failed after all retries")
            return False

    except Exception as e:
        logger.error(f"Manim code generation/render failed: {e}")
        return False

    # ── Mix video + audio ─────────────────────────────────────────────────
    try:
        mix_success = mix_manim_with_audio(
            video_path=silent_video_path,
            voiceover_path=vo_path,
            music_path=None,  # No music for explanatory Manim videos by default
            output_path=output_path,
        )

        if not mix_success:
            logger.error("Failed to mix Manim video with voiceover")
            return False

    except Exception as e:
        logger.error(f"Audio mixing failed: {e}")
        return False

    # ── Update DB ─────────────────────────────────────────────────────────
    abs_output = Path(output_path).resolve()
    if draft_id and abs_output.exists():
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE drafts SET media_refs_json = ?, format_type = ?, "
                "visual_composition = ?, scene_graph_json = ? WHERE id = ?",
                (
                    json.dumps([str(abs_output)]),
                    "video",
                    "ManimAnimation",
                    _build_scene_graph(
                        engine="manim",
                        composition="AgentEchoScene",
                        shots=[],  # Manim has no shot-list structure yet — one continuous scene
                        props={"manim_code": manim_code},
                        output_path=str(abs_output),
                        render_status="ok",
                        error_log=None,
                        retry_count=0,
                    ),
                    draft_id,
                ),
            )
            conn.commit()
            conn.close()
            logger.info(f"Updated draft {draft_id} with Manim video path")
        except Exception as dbe:
            logger.warning(f"Failed to update draft {draft_id}: {dbe}")

    file_size = abs_output.stat().st_size if abs_output.exists() else 0
    logger.info(
        f"Manim video complete: {abs_output} ({file_size} bytes, "
        f"{duration_secs:.1f}s)"
    )

    # Clean up silent intermediate file
    try:
        silent_path = Path(silent_video_path)
        if silent_path.exists():
            silent_path.unlink()
    except Exception:
        pass

    return True

def _clean_word_local(w: str) -> str:
    return w.lower().strip(".,!?—\"'();:").replace("'", "").replace('"', "")


def _find_chapter_boundary_local(
    chapter_text: str, captions: list[dict], search_from: int = 0
) -> tuple[float | None, int]:
    words = [_clean_word_local(w) for w in chapter_text.split()[:4] if w.strip()]
    if not words:
        return None, -1
    n_words = len(words)
    for i in range(search_from, len(captions) - n_words + 1):
        window_words = [_clean_word_local(captions[j]["text"]) for j in range(i, i + n_words)]
        if words == window_words:
            return captions[i]["start"], i
    return None, -1


def generate_remotion_video(
    date_str: str,
    digest: dict,
    output_path: str,
    draft_text: str | None = None,
    draft_id: int | None = None
) -> bool:
    """
    Render a video locally using the inbuilt Remotion compositions
    (StateMachineAnimation, PipelineFlowAnimation, ArchitectureRevealAnimation, MetricsSummaryAnimation)
    with voiceover, beat tracking, sfx, and automated shot synchronization.
    """
    import os
    import sys
    import json
    import time
    import shutil
    import tempfile
    import subprocess
    from pathlib import Path

    from generator.audio_engine import (
        validate_dependencies,
        generate_voiceover_script,
        synthesize_voiceover,
        select_voice_profile,
        mix_audio,
    )
    from generator.music_director import select_music_track
    from generator.beat_sync import extract_beat_frames
    from generator.visual_selector import select_visual_type

    # 1. Validate dependencies
    try:
        validate_dependencies()
    except Exception as e:
        logger.error(f"Remotion dependency validation failed: {e}")
        return False

    # 2. Determine target Remotion composition
    pillar = digest.get("suggested_pillar") or digest.get("pillar", "")
    composition, reasoning = select_visual_type(digest, pillar)

    # Fallback mappings for Remotion compositions if visual selector returned none or Manim
    if not composition or composition == "none" or composition == "ManimAnimation":
        if pillar == "technical_insight":
            composition = "ArchitectureRevealAnimation"
        elif pillar == "project_milestone":
            composition = "PipelineFlowAnimation"
        elif pillar == "lesson_learned":
            composition = "MetricsSummaryAnimation"
        else:
            composition = "StateMachineAnimation"

    logger.info(f"Selected Remotion composition: {composition} (reasoning: {reasoning})")

    # 3. Generate visual props from Claude
    props = build_remotion_props(composition, digest, draft_text=draft_text)
    if not props:
        logger.error("Failed to build Remotion props.")
        return False

    # 4. Count elements in the composition to dictate paragraph/shot count (M)
    if composition == "StateMachineAnimation":
        m_elements = len(props.get("states", []))
    elif composition == "PipelineFlowAnimation":
        m_elements = len(props.get("stages", []))
    elif composition == "ArchitectureRevealAnimation":
        m_elements = len(props.get("components", []))
    elif composition == "MetricsSummaryAnimation":
        m_elements = len(props.get("metrics", []))
    else:
        m_elements = 3

    if m_elements <= 0:
        m_elements = 3

    # Total shots/chapters = M body elements + 1 hook + 1 takeaway
    n_shots = m_elements + 2

    # 5. Audio generation (Narration script + ElevenLabs/OpenAI synthesis)
    try:
        os.makedirs("data/audio", exist_ok=True)
        script = generate_voiceover_script(
            composition, digest, props,
            draft_text=draft_text, n_shots=n_shots
        )
        voice_id = select_voice_profile(composition, digest, script)
        vo_path = f"data/audio/{date_str}_remotion_voiceover.mp3"

        duration_secs, captions = synthesize_voiceover(
            script, vo_path, voice_id=voice_id
        )
        logger.info(f"Voiceover synthesized: {duration_secs:.1f}s, {len(captions)} words")
    except Exception as e:
        logger.error(f"Remotion voiceover audio generation failed: {e}")
        return False

    # 6. Background music selection and mixing
    music_path, music_profile = select_music_track(digest, pillar)
    mixed_audio_filename = f"{date_str}_remotion_mixed.mp3"
    mixed_audio_path = f"data/audio/{mixed_audio_filename}"

    try:
        mix_audio(vo_path, music_path, mixed_audio_path, music_db=-18.0)
    except Exception as e:
        logger.error(f"Remotion audio mixing failed: {e}")
        return False

    # 7. Beat sync analysis
    beat_data = extract_beat_frames(music_path, video_fps=30)

    # 8. Editorial metadata and shot list generation
    editorial_data = build_editorial_and_shots(
        composition, digest, script, n_shots, m_elements, draft_text
    )
    if not editorial_data:
        logger.error("Failed to build editorial structure and shots.")
        return False

    # 9. Timing shots mapping using caption timestamps
    chapters = [p.strip() for p in script.split("\n\n") if p.strip()]
    if len(chapters) != n_shots:
        if len(chapters) < n_shots:
            chapters = chapters + [""] * (n_shots - len(chapters))
        else:
            chapters = chapters[:n_shots]

    shots_raw = editorial_data.get("shots", [])
    if len(shots_raw) != n_shots:
        if len(shots_raw) < n_shots:
            shots_raw = shots_raw + [{
                "type": "tension",
                "content": "",
                "entrance": "slam",
                "duration_beats": 4,
                "rgb_split": False,
                "speed_before": 1.0,
                "color_accent": "#4F8EF7"
            }] * (n_shots - len(shots_raw))
        else:
            shots_raw = shots_raw[:n_shots]

    # Flatten word captions
    flat_words = []
    for cap in captions:
        text = cap["text"]
        words = text.split()
        if not words:
            continue
        dur = cap["end"] - cap["start"]
        word_dur = dur / len(words)
        for w_idx, w in enumerate(words):
            flat_words.append({
                "text": w,
                "start": cap["start"] + w_idx * word_dur,
                "end": cap["start"] + (w_idx + 1) * word_dur
            })

    total_secs = captions[-1]["end"] if captions else duration_secs
    total_frames = int(total_secs * 30)

    chapter_times = []
    search_cursor = 0

    for idx, chapter_text in enumerate(chapters):
        start_secs, idx_found = _find_chapter_boundary_local(chapter_text, flat_words, search_cursor)
        if start_secs is not None:
            search_cursor = idx_found
        else:
            start_secs = idx * (total_secs / n_shots)

        if idx < n_shots - 1:
            next_start_secs, _ = _find_chapter_boundary_local(chapters[idx + 1], flat_words, search_cursor)
            if next_start_secs is not None:
                end_secs = next_start_secs
            else:
                end_secs = (idx + 1) * (total_secs / n_shots)
        else:
            end_secs = total_secs
        chapter_times.append((start_secs, end_secs))

    normalized = []
    for i, (start, end) in enumerate(chapter_times):
        if i < len(chapter_times) - 1:
            end = chapter_times[i + 1][0]
        normalized.append((start, end))
    if normalized:
        normalized[-1] = (normalized[-1][0], total_secs)

    shots_timed = []
    for i, ((start_secs, end_secs), shot_def) in enumerate(zip(normalized, shots_raw)):
        start_frame = int(start_secs * 30)
        end_frame = int(end_secs * 30)

        local_beats = [
            f - start_frame
            for f in beat_data.get("beat_frames", [])
            if start_frame <= f < end_frame
        ]
        local_energy_peaks = [
            f - start_frame
            for f in beat_data.get("energy_peaks", [])
            if start_frame <= f < end_frame
        ]

        sfx_entry_frame = 0
        if local_beats:
            nearest = min(local_beats, key=abs)
            if abs(nearest) <= 8:
                sfx_entry_frame = nearest

        shots_timed.append({
            **shot_def,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_frames": end_frame - start_frame,
            "local_beats": local_beats,
            "local_energy_peaks": local_energy_peaks,
            "sfx_entry_frame": sfx_entry_frame,
            "chapter_index": i
        })

    # 10. Copy mixed audio and sfx into remotion/public/
    public_dir = REMOTION_DIR / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(mixed_audio_path, public_dir / mixed_audio_filename)

    if not os.path.exists("data/audio/sfx/pop.wav"):
        from generator.audio_engine import generate_sfx_library
        generate_sfx_library()

    sfx_public = public_dir / "sfx"
    sfx_public.mkdir(parents=True, exist_ok=True)
    for sfx_file in os.listdir("data/audio/sfx"):
        shutil.copy(os.path.join("data/audio/sfx", sfx_file), sfx_public / sfx_file)

    # 11. Calculate act boundaries (snapped to downbeats)
    act1_end = snap_to_nearest_downbeat(
        shots_timed[1]["end_frame"] if len(shots_timed) > 1 else total_frames // 3,
        beat_data["downbeat_frames"]
    )
    act2_end = snap_to_nearest_downbeat(
        shots_timed[-2]["end_frame"] if len(shots_timed) > 2 else 2 * total_frames // 3,
        beat_data["downbeat_frames"]
    )

    beat_data["shot_boundaries"] = [s["start_frame"] for s in shots_timed]

    # 12. Compile final Remotion render properties
    captions_frames = [
        {
            "text": c["text"],
            "startFrame": int(c["start"] * 30),
            "endFrame": int(c["end"] * 30),
        }
        for c in captions
    ]

    render_props = {
        **props,
        "audioFile": mixed_audio_filename,
        "durationInFrames": total_frames,
        "beatData": beat_data,
        "captions": captions_frames,
        "shots": shots_timed,
        "editorialStructure": {
            "hook": editorial_data["hook"],
            "revelation_order": [s["content"] for s in shots_timed],
            "takeaway": editorial_data["takeaway"],
            "visual_metaphor": "An animation representing developer milestones.",
            "cut_type": editorial_data["cut_type"],
            "act_proportions": {"hook_pct": 0.15, "content_pct": 0.70, "close_pct": 0.15},
            "act1_end": act1_end,
            "act2_end": act2_end,
        },
        "startOffset": 0,
    }

    # 13. Execute npx remotion render locally
    abs_output = Path(output_path).resolve()
    abs_output.parent.mkdir(parents=True, exist_ok=True)

    props_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(render_props, f)
            props_file = f.name

        cmd = [
            "npx",
            "remotion",
            "render",
            "src/index.ts",
            composition,
            str(abs_output),
            "--props",
            props_file,
            "--fps",
            "30",
            "--width",
            "1080",
            "--height",
            "1080",
            "--codec",
            "h264",
            "--crf",
            "18",
            "--log",
            "error",
        ]

        logger.info(f"Rendering Remotion composition {composition} to {abs_output.name}...")
        result = subprocess.run(
            cmd,
            cwd=str(REMOTION_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            logger.error(f"Remotion render failed with exit code {result.returncode}. Stderr: {result.stderr}")
            return False

        if not abs_output.exists():
            logger.error("Remotion render completed but produced no output file.")
            return False

        logger.info(f"Remotion video generation successful: {abs_output}")
    except Exception as e:
        logger.error(f"Failed to execute local Remotion rendering command: {e}")
        return False
    finally:
        if props_file and os.path.exists(props_file):
            try:
                os.unlink(props_file)
            except Exception:
                pass

    # 14. Update DB on success
    if draft_id:
        try:
            conn = get_db_connection()
            cursor = conn.conn.cursor() if hasattr(conn, "conn") else conn.cursor()
            cursor.execute(
                "UPDATE drafts SET media_refs_json = ?, format_type = ?, visual_composition = ?, scene_graph_json = ? WHERE id = ?",
                (
                    json.dumps([str(abs_output)]),
                    "video",
                    composition,
                    _build_scene_graph(
                        engine="remotion",
                        composition=composition,
                        shots=shots_timed,
                        props=props,
                        output_path=str(abs_output),
                        render_status="ok",
                        error_log=None,
                        retry_count=0,
                    ),
                    draft_id,
                ),
            )
            conn.commit()
            conn.close()
            logger.info(f"Successfully updated draft {draft_id} with local Remotion path and metadata")
        except Exception as dbe:
            logger.warning(f"Failed to update draft row {draft_id} in DB: {dbe}")

    return True


def generate_topic_conceptual_image(
    topic: str, title: str, points: list[str], output_path: str
) -> str:
    """
    Generates a premium dark-themed visual card representing a topic's conceptual points,
    saving it to output_path.
    """
    import os
    from pathlib import Path
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    bg_color = "#0F172A"       # slate-900
    card_bg_color = "#1E293B"  # slate-800
    accent_color = "#38BDF8"   # cyan-400
    text_primary = "#F8FAFC"   # slate-50
    text_secondary = "#94A3B8" # slate-400
    
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.get_xaxis().set_visible(False)
    ax.get_yaxis().set_visible(False)
    
    card = FancyBboxPatch(
        (-0.9, -0.9), 1.8, 1.8,
        boxstyle="round,pad=0.03,rounding_size=0.1",
        ec=accent_color,
        fc=card_bg_color,
        lw=2.5
    )
    ax.add_patch(card)
    
    ax.text(
        0, 0.55,
        title.upper(),
        ha="center",
        va="center",
        color=accent_color,
        fontsize=16,
        fontweight="bold",
        wrap=True
    )
    
    ax.plot([-0.7, 0.7], [0.4, 0.4], color="#334155", lw=1.5)
    
    y_pos = 0.2
    for i, pt in enumerate(points[:3]):
        ax.plot([-0.7], [y_pos], marker="o", color=accent_color, markersize=8)
        ax.text(
            -0.6, y_pos,
            pt,
            ha="left",
            va="center",
            color=text_primary,
            fontsize=13,
            fontweight="medium",
            wrap=True
        )
        y_pos -= 0.35
        
    ax.text(
        0, -0.75,
        "AGENT ECHO 🤖🎙️",
        ha="center",
        va="center",
        color=text_secondary,
        fontsize=10,
        fontweight="bold"
    )
    
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    plt.tight_layout()
    plt.savefig(
        output_path,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight"
    )
    plt.close()
    return output_path




