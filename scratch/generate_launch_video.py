"""
Generate a fresh Agent Echo launch video through the real pipeline
(select_visual_type -> build_remotion_props -> EDITOR_SYSTEM -> Remotion render
with the new retry/self-correction loop). No drafts row is created — this
calls generate_remotion_video directly with draft_id=None.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from generator.media_handler import generate_remotion_video

digest = {
    "summary": (
        "Launching Agent Echo — an autonomous, local-first LinkedIn content agent "
        "that watches a developer's daily activity across GitHub, Notion, browser "
        "tabs, and local files, turns it into a daily digest, drafts LinkedIn posts "
        "in the developer's own voice, and asks for one-tap approval before publishing."
    ),
    "highlights_json": json.dumps([
        "Watches GitHub commits/PRs, Notion edits, browser research, and local file changes every 30 minutes",
        "Aggregates the day's activity into a structured digest using Claude",
        "Classifies content into a primary and secondary content pillar automatically",
        "Chooses the right post format on its own: text, image, carousel, video, or poll",
        "Generates fully narrated videos end-to-end: script, voiceover, animation, and render",
        "Routes every draft through a Telegram approve / edit / skip flow",
        "Publishes approved posts to LinkedIn on a scheduled cadence",
        "Retries failed video renders automatically, feeding the error back to Claude to self-correct",
    ]),
    "categories_json": json.dumps({
        "pipeline_stages": ["Capture", "Digest", "Classify", "Format", "Generate", "Review", "Publish"],
        "activity_sources": ["GitHub", "Notion", "Browser", "Local Files"],
        "draft_states": ["pending_review", "approved", "publishing", "published"],
    }),
    "suggested_pillar": "project_milestone",
}

draft_text = (
    "After weeks of building, Agent Echo is live.\n\n"
    "It watches my GitHub commits, Notion notes, browser research, and local file "
    "changes — every single day. At 9pm it turns all of that into a digest, decides "
    "what's worth saying and in what format, writes the draft in my own voice, and "
    "sends it to my phone for one tap of approval.\n\n"
    "Text. Images. Polls. Even fully narrated videos — script, voiceover, and "
    "animation, generated end-to-end with zero manual editing.\n\n"
    "I'm not writing my LinkedIn posts anymore. I'm approving them."
)

output_path = str(project_root / "data" / "media" / "agent_echo_launch.mp4")

print(f"Output -> {output_path}")
success = generate_remotion_video(
    date_str="agent_echo_launch",
    digest=digest,
    output_path=output_path,
    draft_text=draft_text,
    draft_id=None,
)

print("=" * 60)
print("SUCCESS" if success else "FAILED")
print(output_path)
print("=" * 60)
