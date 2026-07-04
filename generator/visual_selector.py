"""
Visual type selector for the Agent Echo content pipeline.

Uses Claude to judge whether a day's digest warrants a technical animation
video, and if so, which Remotion composition fits the content's structure.
Binary keyword matching was replaced here because substring presence can't
tell a passing mention from a day the work was actually about that concept,
and can't recognize the same concept described in different words.
"""

import json
import logging

from anthropic import Anthropic

logger = logging.getLogger("linkedin-agent.visual_selector")

COMPOSITIONS = [
    "StateMachineAnimation",
    "PipelineFlowAnimation",
    "ArchitectureRevealAnimation",
    "MetricsSummaryAnimation",
    "ManimAnimation",
]

SYSTEM_PROMPT = (
    "You decide whether a day's engineering activity warrants a technical "
    "animation video for LinkedIn, and which rendering engine fits best.\n\n"
    "Warrant a video when: the day involved something with clear "
    "spatial/causal structure that is harder to explain in text than in a "
    "diagram — state machines, data flows, architectural relationships, "
    "performance comparisons, algorithms, concurrency bugs.\n\n"
    "Do NOT warrant a video when: the day was mostly meetings, reading, "
    "minor edits, or the content is better as a text reflection.\n\n"
    "Composition guide:\n"
    "- ManimAnimation: BEST for explanatory technical content with precise "
    "spatial or causal structure — state machine walkthroughs where arrows "
    "draw themselves, pipeline data flows with particles moving between stages, "
    "algorithm visualizations, race condition timelines, metrics curves and "
    "number lines, throughput comparisons, before/after diagrams. Use this "
    "when the core insight is 'how something works' or 'why something failed'. "
    "Think 3Blue1Brown style.\n"
    "- StateMachineAnimation: state/transition diagrams, lifecycle flows, "
    "status machines, crash recovery scenarios (Remotion 3D cards)\n"
    "- PipelineFlowAnimation: multi-stage data pipelines, capture-to-publish "
    "flows, ETL processes, orchestration (Remotion 3D blocks)\n"
    "- ArchitectureRevealAnimation: component relationships, module "
    "dependencies, schema design, API structure (Remotion 3D)\n"
    "- MetricsSummaryAnimation: performance numbers, before/after "
    "comparisons, throughput/latency data (Remotion cards)\n"
    "- none: content is better as text or image\n\n"
    "Decision rule: if the post is explaining HOW something works "
    "(causal, spatial, mathematical), prefer ManimAnimation. "
    "If the post is announcing THAT something happened "
    "(milestone, lesson, opinion, launch), prefer a Remotion composition."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "warrants_video": {"type": "boolean"},
        "composition": {
            "type": "string",
            "enum": COMPOSITIONS + ["none"],
        },
        "reasoning": {"type": "string"},
    },
    "required": ["warrants_video", "composition", "reasoning"],
    "additionalProperties": False,
}


def select_visual_type(digest: dict, pillar: str = "") -> tuple[str | None, str]:
    """
    Judge whether `digest` warrants a Remotion animation, and which one.

    Returns (composition_name, reasoning) or (None, reasoning).
    """
    if not digest:
        return None, "No digest content to evaluate."

    user_content = (
        f"Digest:\n{json.dumps(digest, indent=2, default=str)}\n"
        f"Pillar: {pillar}"
    )

    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        result = json.loads(response.content[0].text)
    except Exception as e:
        logger.warning(f"Visual type classification failed, defaulting to none: {e}")
        return None, f"Classification failed: {e}"

    if not result["warrants_video"] or result["composition"] == "none":
        return None, result["reasoning"]

    logger.info(
        f"Visual selector: chose '{result['composition']}' — {result['reasoning']}"
    )
    return result["composition"], result["reasoning"]


def infer_composition(digest: dict, pillar: str = "") -> str | None:
    """Convenience wrapper that returns only the composition ID (or None)."""
    composition, _ = select_visual_type(digest, pillar)
    return composition
