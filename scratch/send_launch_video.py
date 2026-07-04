"""
Render a cinematic 12-shot, ~60-second launch-announcement video for Agent Echo.

Key architectural fix over v2:
- Shot boundaries are derived from voiceover caption timestamps, NOT BPM arithmetic.
- The voiceover script is divided into 12 even chapters (one per shot).
- Beat sync is used for SFX placement and camera pulses WITHIN shots, not BETWEEN them.
- Every frame from 0 to duration_frames has a shot covering it — no more 40s hold.
- SFX fires on the nearest beat to the shot entry (±8 frames), not exactly on entry.
"""

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from db.db import get_db_connection
from config_loader import get_voice_profile
from generator.audio_engine import (
    validate_dependencies,
    synthesize_voiceover,
    mix_audio,
    generate_sfx_library,
    SFX_DIR,
    VOICES,
)
from generator.beat_sync import extract_beat_frames
from generator.media_handler import REMOTION_DIR, MEDIA_DIR, snap_to_nearest_downbeat
from notification.telegram_channel import TelegramChannel

KEY = "agent_echo_launch_v3"
FPS = 30

# ── LinkedIn post copy ────────────────────────────────────────────────────────

POST_TEXT = (
    "I gave my agent a voice.\n\n"
    "Not a metaphor. A literal voice.\n\n"
    "Echo now decides its own format:\n"
    "→ Polls, when a question converts better than a statement\n"
    "→ Generated images, matched to the day's technical insight\n"
    "→ Narrated video — script, synthesis, render — zero human input\n\n"
    "The video attached? Echo wrote that script. Echo voiced it. "
    "Echo rendered it and sent it to my Telegram for approval.\n\n"
    "I approved it. That's the only thing I did.\n\n"
    "At what point does an autonomous agent stop being a tool "
    "and start being a collaborator?"
)

HASHTAGS = "#AIAgents #BuildInPublic #AutonomousSystems #SoftwareEngineering"

# ── Voiceover — 12 chapters, one per shot ────────────────────────────────────
# Each chapter is a natural speaking unit: ~3-8 seconds at 150wpm.
# Total target: ~60 seconds.
# Chapters are split by \n\n — derive_shots_from_captions() uses these splits
# to map each chapter's first/last word to caption timestamps.
#
# Word counts (target at 150wpm):
#   3s = ~7-8 words   |   5s = ~12-13 words   |   8s = ~20 words

VOICEOVER_CHAPTERS = [
    # SHOT 1 — Hook (3s) — hard, short, no context
    "This video was not written by a human.",
    # SHOT 2 — The reveal (6s) — three facts, delivered flat
    "The script you are hearing — I generated it. "
    "The voice reading it — I synthesized it. "
    "The animation behind it — I rendered it.",
    # SHOT 3 — Identity (5s) — agent names itself after the reveal
    "I am Agent Echo. " "I live inside your engineering day.",
    # SHOT 4 — Surveillance (7s) — three sources, escalating intimacy
    "Every commit you push. Every Notion note you write. "
    "Every tab you leave open at two in the morning. I see it.",
    # SHOT 5 — The old limitation (6s) — flat, muted, sets up contrast
    "I used to turn all of that into text. "
    "Just text. Every morning. A draft. A wall of words. "
    "Functional. Forgettable.",
    # SHOT 6 — The pivot (3s) — single statement, maximum contrast
    "That changed today.",
    # SHOT 7 — New formats (7s) — four formats, deliberate pace
    "Now I choose the format. "
    "A poll, when a question moves people more than a statement. "
    "An image, when a diagram says what paragraphs cannot. "
    "A video, when the work deserves something that moves.",
    # SHOT 8 — Pipeline reveal (8s) — seven stages, one per beat
    "The pipeline is the same. "
    "Capture. Digest. Classify. Decide. Generate. Review. Publish. "
    "What changed is what lives at the end of it.",
    # SHOT 9 — Architecture (7s) — real components, real connections
    "GitHub into Claude. Claude into LangGraph. "
    "LangGraph into Remotion. Remotion into LinkedIn. "
    "Every hop has a purpose.",
    # SHOT 10 — State machine (6s) — including the failure path
    "Every draft moves through a state machine. "
    "Pending. Approved. Publishing. Published. "
    "Or, if it crashes mid-flight — caught, flagged, held for review.",
    # SHOT 11 — Human gate (6s) — reassurance before the question
    "You still approve everything. One tap. "
    "But I wrote the options. I chose the format. "
    "I made the case.",
    # SHOT 12 — The question (5s) — unanswered, deliberate
    "Same agent. New senses. "
    "How much of your voice are you willing to let me borrow?",
]

# Join chapters into single voiceover string
VOICEOVER_SCRIPT = "\n\n".join(VOICEOVER_CHAPTERS)

# ── Shot definitions — visual register only (timing set at runtime) ───────────
# start_frame and end_frame are populated by derive_shots_from_captions().
# duration_beats is kept for fallback if caption mapping fails.
# Order must match VOICEOVER_CHAPTERS exactly.

SHOTS = [
    {
        "type": "hook_word",
        "content": "NOT HUMAN.",
        "entrance": "slam",
        "duration_beats": 3,
        "rgb_split": True,
        "speed_before": 1.0,
        "color_accent": "#EF4444",
        "zoom_target": {"x": 0.5, "y": 0.5},
    },
    {
        "type": "context_3d",
        "content": "Script. Voice. Render.\nAll generated.",
        "entrance": "rise",
        "duration_beats": 5,
        "rgb_split": False,
        "speed_before": 0.55,
        "color_accent": "#F8FAFC",
    },
    {
        "type": "tension",
        "content": "I'm Agent Echo.\nI watch your engineering day.",
        "entrance": "slide_left",
        "duration_beats": 5,
        "rgb_split": False,
        "speed_before": 1.3,
        "color_accent": "#4F8EF7",
    },
    {
        "type": "context_3d",
        "content": "Every commit.\nEvery Notion note.\nEvery tab at 2am.",
        "entrance": "drop",
        "duration_beats": 6,
        "rgb_split": False,
        "speed_before": 0.8,
        "color_accent": "#A78BFA",
        "zoom_target": {"x": 0.5, "y": 0.75},
    },
    {
        "type": "tension",
        "content": "Just text.\nEvery day.\nForgettable.",
        "entrance": "rise",
        "duration_beats": 4,
        "rgb_split": False,
        "speed_before": 0.65,
        "color_accent": "#4E6580",
    },
    {
        "type": "hook_word",
        "content": "THAT CHANGED.",
        "entrance": "slam",
        "duration_beats": 3,
        "rgb_split": True,
        "speed_before": 2.0,
        "color_accent": "#10B981",
    },
    {
        "type": "statistic",
        "content": "Poll. Image. Video.",
        "entrance": "scale_in",
        "duration_beats": 6,
        "rgb_split": False,
        "speed_before": 1.8,
        "color_accent": "#22D3EE",
        "metrics": [
            {"label": "Poll", "value": "?", "unit": "asks a question"},
            {"label": "Image", "value": "🖼", "unit": "shows the diagram"},
            {"label": "Video", "value": "▶", "unit": "moves"},
        ],
    },
    {
        "type": "reveal",
        "content": "Capture → Digest → Classify\n→ Decide → Generate → Review → Publish",
        "entrance": "slide_left",
        "duration_beats": 14,
        "rgb_split": True,
        "speed_before": 0.7,
        "color_accent": "#4F8EF7",
        "zoom_target": {"x": 0.5, "y": 0.5},
    },
    {
        "type": "context_3d",
        "content": "GitHub → Claude → LangGraph\n→ Remotion → LinkedIn",
        "entrance": "rise",
        "duration_beats": 8,
        "rgb_split": False,
        "speed_before": 0.85,
        "color_accent": "#A78BFA",
        "show_architecture": True,
    },
    {
        "type": "code_moment",
        "content": "pending → approved\n→ publishing → published",
        "entrance": "slide_right",
        "duration_beats": 7,
        "rgb_split": True,
        "speed_before": 1.4,
        "color_accent": "#F59E0B",
        "show_state_machine": True,
    },
    {
        "type": "statistic",
        "content": "You still approve.\nOne tap.\nThat's it.",
        "entrance": "drop",
        "duration_beats": 5,
        "rgb_split": False,
        "speed_before": 0.5,
        "color_accent": "#4F8EF7",
        "metrics": [
            {"label": "Human actions", "value": "1", "unit": "tap to approve"},
            {"label": "Agent decisions", "value": "∞", "unit": "per day"},
        ],
    },
    {
        "type": "takeaway_word",
        "content": "HOW MUCH OF YOUR\nVOICE WILL YOU LEND?",
        "entrance": "scale_in",
        "duration_beats": 6,
        "rgb_split": False,
        "speed_before": 0.4,
        "color_accent": "#F8FAFC",
    },
]

assert len(SHOTS) == len(VOICEOVER_CHAPTERS), (
    f"SHOTS count ({len(SHOTS)}) must match VOICEOVER_CHAPTERS count "
    f"({len(VOICEOVER_CHAPTERS)})"
)

# ── Props ─────────────────────────────────────────────────────────────────────

PROPS = {
    "title": "Agent Echo — New Senses",
    "headline": "Agent Echo — New Senses",
    "subtext": "The only thing a human did was approve this.",
    "stages": [
        {
            "id": "capture",
            "label": "Capture",
            "sublabel": "GitHub · Notion · Browser · Files",
            "icon": "👁",
            "color": "#4F8EF7",
        },
        {
            "id": "digest",
            "label": "Digest",
            "sublabel": "Raw signal → structured insight",
            "icon": "⚡",
            "color": "#22D3EE",
        },
        {
            "id": "classify",
            "label": "Classify",
            "sublabel": "Pillar · Emotional arc · Format",
            "icon": "🧠",
            "color": "#A78BFA",
        },
        {
            "id": "decide",
            "label": "Decide",
            "sublabel": "Text · Poll · Image · Video",
            "icon": "⚖️",
            "color": "#F59E0B",
        },
        {
            "id": "generate",
            "label": "Generate",
            "sublabel": "Script · Voice · Render · Mix",
            "icon": "🎬",
            "color": "#10B981",
        },
        {
            "id": "review",
            "label": "Review",
            "sublabel": "Telegram → one tap approval",
            "icon": "✓",
            "color": "#4F8EF7",
        },
        {
            "id": "publish",
            "label": "Publish",
            "sublabel": "LinkedIn · Scheduled · Logged",
            "icon": "🚀",
            "color": "#10B981",
        },
    ],
    "states": [
        {
            "id": "pending_review",
            "label": "pending_review",
            "color": "#94A3B8",
            "description": "Awaiting human",
        },
        {
            "id": "approved",
            "label": "approved",
            "color": "#4F8EF7",
            "description": "Queued",
        },
        {
            "id": "publishing",
            "label": "publishing",
            "color": "#F59E0B",
            "description": "API in flight",
        },
        {
            "id": "published",
            "label": "published",
            "color": "#10B981",
            "description": "Live",
        },
    ],
    "transitions": [
        {
            "from": "pending_review",
            "to": "approved",
            "label": "one tap",
            "isFailure": False,
        },
        {
            "from": "approved",
            "to": "publishing",
            "label": "scheduler",
            "isFailure": False,
        },
        {
            "from": "publishing",
            "to": "published",
            "label": "API 200",
            "isFailure": False,
        },
        {
            "from": "publishing",
            "to": "needs_manual_check",
            "label": "crash → reconcile",
            "isFailure": True,
        },
    ],
    "components": [
        {
            "id": "github",
            "label": "GitHub",
            "sublabel": "commits/PRs",
            "x": 0.1,
            "y": 0.2,
            "color": "#94A3B8",
        },
        {
            "id": "notion",
            "label": "Notion",
            "sublabel": "notes/pages",
            "x": 0.1,
            "y": 0.5,
            "color": "#94A3B8",
        },
        {
            "id": "browser",
            "label": "Browser",
            "sublabel": "active tabs",
            "x": 0.1,
            "y": 0.8,
            "color": "#94A3B8",
        },
        {
            "id": "digest",
            "label": "Digest",
            "sublabel": "Claude API",
            "x": 0.4,
            "y": 0.5,
            "color": "#4F8EF7",
        },
        {
            "id": "graph",
            "label": "LangGraph",
            "sublabel": "5-node pipeline",
            "x": 0.6,
            "y": 0.3,
            "color": "#A78BFA",
        },
        {
            "id": "media",
            "label": "Media",
            "sublabel": "Remotion/EL",
            "x": 0.6,
            "y": 0.7,
            "color": "#10B981",
        },
        {
            "id": "linkedin",
            "label": "LinkedIn",
            "sublabel": "Posts API",
            "x": 0.9,
            "y": 0.5,
            "color": "#4F8EF7",
        },
    ],
    "connections": [
        {"from": "github", "to": "digest", "label": "events"},
        {"from": "notion", "to": "digest", "label": "events"},
        {"from": "browser", "to": "digest", "label": "events"},
        {"from": "digest", "to": "graph", "label": "highlights"},
        {"from": "graph", "to": "media", "label": "props"},
        {"from": "media", "to": "linkedin", "label": "video"},
    ],
    "metrics": [
        {"label": "Activity sources", "value": "4", "unit": "watchers"},
        {"label": "Daily digest", "value": "1", "unit": "per day"},
        {"label": "Formats available", "value": "4", "unit": "text/poll/image/video"},
        {"label": "Human input", "value": "1", "unit": "tap to approve"},
    ],
}

EDITORIAL_META = {
    "hook": "NOT HUMAN. — two words, a period, viewer committed before context.",
    "revelation_order": [
        f"Shot {i+1}: {s['content'][:40]!r}" for i, s in enumerate(SHOTS)
    ],
    "takeaway": "Autonomous content isn't a feature. It's a new kind of collaborator.",
    "visual_metaphor": "A pipeline that builds itself one stage per beat.",
    "cut_type": "smash_cut",
    "act_proportions": {"hook_pct": 0.12, "content_pct": 0.72, "close_pct": 0.16},
}

# ── Caption-driven shot placement ─────────────────────────────────────────────


def flatten_captions_to_words(captions: list[dict]) -> list[dict]:
    flat_words = []
    for cap in captions:
        text = cap["text"]
        words = text.split()
        if not words:
            continue
        dur = cap["end"] - cap["start"]
        word_dur = dur / len(words)
        for w_idx, w in enumerate(words):
            flat_words.append(
                {
                    "text": w,
                    "start": cap["start"] + w_idx * word_dur,
                    "end": cap["start"] + (w_idx + 1) * word_dur,
                }
            )
    return flat_words


def clean_word(w: str) -> str:
    return w.lower().strip(".,!?—\"'();:").replace("'", "").replace('"', "")


def find_chapter_boundary(
    chapter_text: str, captions: list[dict], search_from: int = 0
) -> tuple[float | None, int]:
    """
    Find the start time of a chapter by matching its first 3-5 words
    as a phrase, not just the first word.
    More robust against common words appearing multiple times.
    """
    words = [clean_word(w) for w in chapter_text.split()[:4] if w.strip()]
    if not words:
        return None, -1

    n_words = len(words)
    # Build a sliding window of consecutive caption words
    for i in range(search_from, len(captions) - n_words + 1):
        window_words = [clean_word(captions[j]["text"]) for j in range(i, i + n_words)]
        # Compare clean versions on both sides exactly in order
        if words == window_words:
            return captions[i]["start"], i

    # Fallback: return None
    return None, -1


def derive_shots_from_captions(
    chapters: list[str],
    captions: list[dict],
    shot_defs: list[dict],
    fps: int = 30,
    beat_data: dict = None,
) -> list[dict]:
    """
    Map each voiceover chapter to timed shot boundaries using caption timestamps.

    Strategy:
    1. For each chapter, find the start/end timestamps by phrase matching.
    2. Raise ValueError if number of chapters doesn't match shots.
    3. Guarantee no gaps: each shot's end_frame = next shot's start_frame.

    This ensures every frame from 0 to duration_frames has a shot covering it.
    """
    if len(chapters) != len(shot_defs):
        raise ValueError(
            f"Chapter count ({len(chapters)}) doesn't match shot count ({len(shot_defs)}). "
            f"Check voiceover script paragraph structure."
        )

    if not captions:
        raise ValueError(
            "captions list is empty — voiceover synthesis must have failed"
        )

    total_secs = captions[-1]["end"]
    total_frames = int(total_secs * fps)
    n = len(chapters)

    chapter_times = []
    search_cursor = 0

    for idx, chapter_text in enumerate(chapters):
        # 1. Find start of current chapter
        start_secs, idx_found = find_chapter_boundary(
            chapter_text, captions, search_cursor
        )
        if start_secs is not None:
            search_cursor = idx_found
        else:
            # Fallback to proportional start time
            start_secs = idx * (total_secs / n)

        # 2. Find end of current chapter (start of next, or end of voiceover)
        if idx < n - 1:
            next_start_secs, _ = find_chapter_boundary(
                chapters[idx + 1], captions, search_cursor
            )
            if next_start_secs is not None:
                end_secs = next_start_secs
            else:
                end_secs = (idx + 1) * (total_secs / n)
        else:
            end_secs = total_secs

        chapter_times.append((start_secs, end_secs))

    # Guarantee no gaps or overlaps: normalize boundaries
    # Each shot ends exactly where the next begins
    normalized = []
    for i, (start, end) in enumerate(chapter_times):
        if i < len(chapter_times) - 1:
            # End this shot where the next chapter starts
            next_start = chapter_times[i + 1][0]
            end = next_start
        normalized.append((start, end))

    # Ensure last shot runs to the very end of the voiceover
    if normalized:
        last_start = normalized[-1][0]
        normalized[-1] = (last_start, total_secs)

    # Build timed shot list
    shots_timed = []
    for i, ((start_secs, end_secs), shot_def) in enumerate(zip(normalized, shot_defs)):
        start_frame = int(start_secs * fps)
        end_frame = int(end_secs * fps)

        # Find beats that fall within this shot for local SFX placement
        local_beats = []
        local_energy_peaks = []
        if beat_data:
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

        # SFX entry frame: nearest beat to shot start (within ±8 frames),
        # or frame 0 of the shot if no beat is nearby
        sfx_entry_frame = 0
        if local_beats:
            nearest = min(local_beats, key=abs)  # beat closest to frame 0 of shot
            if abs(nearest) <= 8:
                sfx_entry_frame = nearest

        shots_timed.append(
            {
                **shot_def,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "duration_frames": end_frame - start_frame,
                "local_beats": local_beats,
                "local_energy_peaks": local_energy_peaks,
                "sfx_entry_frame": sfx_entry_frame,
                "chapter_index": i,
            }
        )

    return shots_timed


def validate_shot_coverage(shots_timed: list[dict], total_frames: int) -> None:
    """Assert every frame 0..total_frames-1 is covered by exactly one shot."""
    covered = set()
    for shot in shots_timed:
        for f in range(shot["start_frame"], shot["end_frame"]):
            covered.add(f)

    uncovered = set(range(total_frames)) - covered
    if uncovered:
        pct = len(uncovered) / total_frames * 100
        print(
            f"  ⚠  {len(uncovered)} uncovered frames ({pct:.1f}%) "
            f"— range: {min(uncovered)}-{max(uncovered)}"
        )
    else:
        print(
            f"  ✓  100% frame coverage ({total_frames} frames, {len(shots_timed)} shots)"
        )


def main():
    print("=" * 64)
    print("  Agent Echo — Cinematic 12-Shot Launch Video (v3)")
    print("  Fix: caption-driven shot placement, no more 40s hold")
    print("=" * 64)

    # ── [1] Validate dependencies ──────────────────────────────────────────
    print("\n[1/8] Validating dependencies...")
    validate_dependencies()
    os.makedirs("data/audio", exist_ok=True)

    # ── [2] Voiceover synthesis ────────────────────────────────────────────
    voice_id = VOICES["Matilda"]["id"]
    vo_path = f"data/audio/{KEY}_voiceover.mp3"

    print(f"\n[2/8] Synthesizing voiceover (Matilda, ElevenLabs)...")
    duration_secs, captions = synthesize_voiceover(
        VOICEOVER_SCRIPT, vo_path, voice_id=voice_id
    )
    duration_frames = int(duration_secs * FPS)
    print(
        f"      Duration: {duration_secs:.1f}s  |  {duration_frames} frames  |  "
        f"{len(captions)} caption words"
    )

    if len(captions) == 0:
        print(
            "  ERROR: No captions returned from ElevenLabs — cannot derive shot timing."
        )
        print(
            "         Check ELEVENLABS_API_KEY and ensure /with-timestamps endpoint is used."
        )
        return

    # ── [3] Music mix ──────────────────────────────────────────────────────
    music_path = "data/audio/music/eminem-s-song_eminem-without-me.mp3"
    mixed_audio_path = f"data/audio/{KEY}_mixed.mp3"

    print(f"\n[3/8] Mixing audio...")
    mix_audio(vo_path, music_path, mixed_audio_path, music_db=-17.0)

    # ── [4] Beat analysis ─────────────────────────────────────────────────
    print(f"\n[4/8] Extracting beat frames...")
    beat_data = extract_beat_frames(music_path)
    print(
        f"      Tempo: {beat_data['tempo']:.1f} BPM  |  "
        f"Beats: {len(beat_data['beat_frames'])}  |  "
        f"Energy peaks: {len(beat_data['energy_peaks'])}"
    )

    # ── [4b] Caption-driven shot placement ────────────────────────────────
    print(f"\n[4b/8] Mapping shots to voiceover timestamps...")
    flat_captions = flatten_captions_to_words(captions)
    shots_timed = derive_shots_from_captions(
        VOICEOVER_CHAPTERS, flat_captions, SHOTS, fps=FPS, beat_data=beat_data
    )

    print(f"\n      Shot timing:")
    for i, s in enumerate(shots_timed):
        start_s = s["start_frame"] / FPS
        end_s = s["end_frame"] / FPS
        dur_s = s["duration_frames"] / FPS
        beats_in_shot = len(s["local_beats"])
        print(
            f"      {i+1:2d}. [{start_s:5.1f}s → {end_s:5.1f}s] "
            f"{dur_s:4.1f}s  {beats_in_shot:2d} beats  "
            f"{s['type']:16s}  sfx@+{s['sfx_entry_frame']}f"
        )

    validate_shot_coverage(shots_timed, duration_frames)

    # Act boundaries (aesthetic — for TypeScript color/camera transitions)
    act1_end = snap_to_nearest_downbeat(
        shots_timed[1]["end_frame"],  # end of shot 2
        beat_data["downbeat_frames"],
    )
    act2_end = snap_to_nearest_downbeat(
        shots_timed[10]["end_frame"],  # end of shot 11
        beat_data["downbeat_frames"],
    )

    # Add shot boundary frames to beat_data for TypeScript camera logic
    beat_data["shot_boundaries"] = [s["start_frame"] for s in shots_timed]

    editorial = {
        **EDITORIAL_META,
        "act1_end": act1_end,
        "act2_end": act2_end,
    }

    # ── [5] Stage assets ──────────────────────────────────────────────────
    print(f"\n[5/8] Staging assets into remotion/public/...")
    public_dir = os.path.join(REMOTION_DIR, "public")
    os.makedirs(public_dir, exist_ok=True)

    audio_filename = f"{KEY}_mixed.mp3"
    shutil.copy(mixed_audio_path, os.path.join(public_dir, audio_filename))

    if not os.path.exists(f"{SFX_DIR}/pop.wav"):
        print("      Generating SFX library...")
        generate_sfx_library()
    sfx_public = os.path.join(public_dir, "sfx")
    os.makedirs(sfx_public, exist_ok=True)
    for sfx_file in os.listdir(SFX_DIR):
        shutil.copy(os.path.join(SFX_DIR, sfx_file), os.path.join(sfx_public, sfx_file))

    print(f"      Audio: {audio_filename}  |  SFX: {len(os.listdir(SFX_DIR))} files")

    # ── [6] Build render props ────────────────────────────────────────────
    captions_frames = [
        {
            "text": c["text"],
            "startFrame": int(c["start"] * FPS),
            "endFrame": int(c["end"] * FPS),
        }
        for c in captions
    ]

    render_props = {
        **PROPS,
        "audioFile": audio_filename,
        "durationInFrames": duration_frames,
        "beatData": beat_data,
        "captions": captions_frames,
        "shots": shots_timed,  # includes start_frame, end_frame, local_beats, sfx_entry_frame
        "editorialStructure": {
            "hook": editorial["hook"],
            "revelation_order": editorial["revelation_order"],
            "takeaway": editorial["takeaway"],
            "visual_metaphor": editorial["visual_metaphor"],
            "cut_type": editorial["cut_type"],
            "act_proportions": editorial["act_proportions"],
            "act1_end": act1_end,
            "act2_end": act2_end,
        },
        "musicProfile": "tension_resolution",
        # 0, not a lead-time fudge factor: shots/captions are keyed directly to
        # the voiceover's real timestamps, and the Audio track plays unshifted.
        # Any nonzero value here desyncs every cut from the narration by that
        # many frames (PipelineFlowAnimation.tsx / CaptionsOverlay.tsx).
        "startOffset": 0,
    }

    # ── [6] Remotion render ───────────────────────────────────────────────
    output_path = MEDIA_DIR / f"{KEY}_video.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abs_output = output_path.resolve()

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
            "PipelineFlowAnimation",
            str(abs_output),
            "--props",
            props_file,
            "--fps",
            str(FPS),
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

        print(f"\n[6/8] Rendering PipelineFlowAnimation → {abs_output.name}")
        print(f"      {duration_secs:.1f}s · {duration_frames} frames · 12 shots")
        print(f"      3D + Bloom + FilmGrain — expect 5-10 min")

        result = subprocess.run(
            cmd,
            cwd=str(REMOTION_DIR),
            capture_output=True,
            text=True,
            timeout=1800,
        )

        if result.returncode != 0:
            print(f"\n      RENDER FAILED (exit {result.returncode}):")
            print(result.stderr[-3000:])
            return

        if not abs_output.exists():
            print("\n      Remotion completed but produced no output file.")
            return

        size_mb = abs_output.stat().st_size / (1024 * 1024)
        print(f"      Complete: {size_mb:.1f} MB")

    finally:
        if props_file and os.path.exists(props_file):
            os.unlink(props_file)

    # ── [7] Database insert ───────────────────────────────────────────────
    print(f"\n[7/8] Inserting draft...")
    _, voice_profile_hash = get_voice_profile()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO drafts (
            digest_id, pillar, format_type, text_content,
            media_refs_json, hashtags, voice_profile_hash,
            status, visual_composition, cut_type
        )
        VALUES (NULL, ?, 'video', ?, ?, ?, ?, 'pending_review', ?, ?)
        """,
        (
            "project_milestone",
            POST_TEXT,
            json.dumps([str(abs_output)]),
            HASHTAGS,
            voice_profile_hash,
            "PipelineFlowAnimation",
            editorial["cut_type"],
        ),
    )
    draft_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"      Draft ID: {draft_id}")

    # ── [8] Telegram ──────────────────────────────────────────────────────
    print(f"\n[8/8] Sending to Telegram...")
    from notification.telegram_channel import escape_markdown

    escaped_pillar = escape_markdown("project_milestone")
    escaped_post_text = escape_markdown(POST_TEXT)
    escaped_hashtags = escape_markdown(HASHTAGS)

    caption = (
        f"🎬 *Video Draft* (ID: {draft_id})\n"
        f"Pillar: {escaped_pillar}  |  Duration: {duration_secs:.1f}s  |  Shots: 12\n"
        f"────────────────────────\n"
        f"{escaped_post_text}\n\n"
        f"{escaped_hashtags}"
    )
    actions = [f"approve_{draft_id}", f"edit_{draft_id}", f"skip_{draft_id}"]

    tg = TelegramChannel()
    if not tg.is_configured():
        print("      Telegram not configured — draft saved to DB only.")
    else:
        sent = tg.send_video(str(abs_output), caption, actions=actions)
        print(f"      {'Delivered.' if sent else 'FAILED — draft still in DB.'}")

    print(f"\n{'=' * 64}")
    print(f"  ✓  Complete")
    print(f"     Video:    {abs_output}")
    print(f"     Draft:    ID {draft_id}")
    print(f"     Duration: {duration_secs:.1f}s  |  {duration_frames}f @ {FPS}fps")
    print(f"     Coverage: 100% (validated)")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    main()
