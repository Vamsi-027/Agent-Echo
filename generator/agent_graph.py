import json
import datetime
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from anthropic import Anthropic

from db.db import get_db_connection
from config_loader import LOCAL_TZ, load_pillars, get_voice_profile
from aggregator.daily_digest import run_daily_digest
from generator.pillar_classifier import classify_pillar
from generator.format_selector import select_format


class PipelineState(TypedDict):
    date: str
    digest: Optional[Dict[str, Any]]
    pillar: Optional[str]
    secondary_pillar: Optional[str]
    format_type: Optional[str]
    persona_context: Optional[str]
    drafts: List[Dict[str, Any]]
    status: str  # 'success' | 'no_activity' | 'failed'
    error: Optional[str]


# ==================== Node Functions ====================


def aggregate_digest_node(state: PipelineState) -> Dict[str, Any]:
    """Runs the daily digest aggregation step or retrieves an existing digest from the database."""
    date_str = state["date"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM daily_digests WHERE date = ? ORDER BY version DESC LIMIT 1",
        (date_str,),
    )
    existing = cursor.fetchone()
    conn.close()

    if existing:
        return {"status": "success", "digest": dict(existing)}

    try:
        digest_row = run_daily_digest(date_str=date_str)
        if not digest_row:
            return {"status": "no_activity", "digest": None}
        return {"status": "success", "digest": digest_row}
    except Exception as e:
        return {"status": "failed", "error": str(e), "digest": None}


def classify_pillar_node(state: PipelineState) -> Dict[str, Any]:
    """Classifies the daily digest content into a primary and secondary pillar."""
    digest = state["digest"]
    if not digest:
        return {"pillar": "none", "secondary_pillar": None}
    try:
        primary, secondary = classify_pillar(digest)
        return {"pillar": primary, "secondary_pillar": secondary}
    except Exception as e:
        return {"status": "failed", "error": f"Pillar classification failed: {str(e)}"}


def select_format_node(state: PipelineState) -> Dict[str, Any]:
    """Selects the format type based on the content pillar and highlights."""
    digest = state["digest"]
    pillar = state["pillar"]
    if not digest or not pillar or pillar == "none":
        return {"format_type": "text"}
    try:
        from generator.media_handler import get_available_media

        media_available = get_available_media(state["date"])
        format_type = select_format(digest, pillar, media_available)
        return {"format_type": format_type}
    except Exception as e:
        return {"status": "failed", "error": f"Format selection failed: {str(e)}"}


def retrieve_persona_context_node(state: PipelineState) -> Dict[str, Any]:
    """Queries LanceDB for personal experience and stylistic references relevant to today's highlights."""
    digest = state.get("digest")
    if not digest or not digest.get("highlights_json"):
        return {"persona_context": ""}

    try:
        from db.vector_db import search_persona

        highlights_list = json.loads(digest["highlights_json"])
        if not highlights_list:
            return {"persona_context": ""}

        # Combine highlights to form the semantic query
        query_text = " ".join(highlights_list)

        # Retrieve the top 3 matches
        results = search_persona(query_text, limit=3)
        if not results:
            return {"persona_context": "No specific personal context found."}

        context_blocks = []
        for r in results:
            context_blocks.append(
                f"- Context (Source: {r['source']}, Category: {r['category']}):\n  {r['text']}"
            )
        persona_context = "\n\n".join(context_blocks)
        return {"persona_context": persona_context}
    except Exception as e:
        # Gracefully handle vector db query failures so the pipeline doesn't crash
        return {"persona_context": f"Error retrieving personal context: {str(e)}"}


def generate_drafts_node(state: PipelineState) -> Dict[str, Any]:
    """Generates the post drafts via Claude, validates character limits, and inserts them into the DB."""
    digest = state["digest"]
    pillar = state["pillar"]
    format_type = state["format_type"]

    if not digest or not pillar or pillar == "none":
        return {"drafts": [], "status": "success"}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        voice_profile_text, voice_profile_hash = get_voice_profile()

        # Query recent drafts to avoid repetition
        cursor.execute(
            "SELECT text_content FROM drafts WHERE status = 'published' "
            "ORDER BY updated_at DESC LIMIT 10"
        )
        recent_published = [
            row["text_content"] for row in cursor.fetchall() if row["text_content"]
        ]

        client = Anthropic()

        if format_type == "poll":
            draft_schema = {
                "type": "object",
                "properties": {
                    "variants": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The post body draft content (commentary explaining/introducing the poll)",
                                },
                                "twitter_text": {
                                    "type": "string",
                                    "description": "The Twitter/X version of the post body draft content introducing/explaining the poll (optimized for Twitter style, maximum 280 characters)",
                                },
                                "hashtags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                    "description": "Relevant hashtags without the # prefix (aim for 2-4)",
                                },
                                "poll_question": {
                                    "type": "string",
                                    "maxLength": 140,
                                    "description": "The poll question itself (max 140 characters)",
                                },
                                "poll_options": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": 4,
                                    "items": {"type": "string", "maxLength": 30},
                                    "description": "List of 2 to 4 poll options (each option max 30 characters)",
                                },
                                "poll_duration": {
                                    "type": "string",
                                    "enum": [
                                        "ONE_DAY",
                                        "THREE_DAYS",
                                        "SEVEN_DAYS",
                                        "FOURTEEN_DAYS",
                                    ],
                                    "description": "Duration of the poll",
                                },
                            },
                            "required": [
                                "text",
                                "twitter_text",
                                "hashtags",
                                "poll_question",
                                "poll_options",
                                "poll_duration",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["variants"],
                "additionalProperties": False,
            }
        else:
            draft_schema = {
                "type": "object",
                "properties": {
                    "variants": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The post body draft content",
                                },
                                "twitter_text": {
                                    "type": "string",
                                    "description": "The Twitter/X version of the post body draft content (optimized for Twitter style, maximum 280 characters)",
                                },
                                "hashtags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                    "description": "Relevant hashtags without the # prefix (aim for 2-4)",
                                },
                            },
                            "required": ["text", "twitter_text", "hashtags"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["variants"],
                "additionalProperties": False,
            }

        persona_context = (
            state.get("persona_context") or "No specific personal context found."
        )

        system_prompt = (
            f"You are the author of highly engaging LinkedIn and Twitter/X profiles.\n\n"
            f"Personal Experience and Stylistic References:\n{persona_context}\n\n"
            f"Voice Profile Constraints:\n{voice_profile_text}\n\n"
            f"Target Pillar: {pillar} (Secondary: {state.get('secondary_pillar') or 'None'})\n"
            f"Target Format: {format_type}\n"
            "Guidelines:\n"
            "- Do not use corporate speak or hype phrases.\n"
            "- Write naturally, sharing insights, metrics, or lessons from today's work.\n"
            "- The LinkedIn post variant (`text` key) must be under 1300 characters.\n"
            "- The Twitter/X post variant (`twitter_text` key) must be a distinct, snappy summary or custom variant under 280 characters optimized for the Twitter/X audience.\n\n"
            "To prevent repeating recently covered themes, here are the posts you published recently:\n"
            f"{json.dumps(recent_published, indent=2)}"
        )

        user_prompt = (
            f"Write 1-2 different post draft variants based on today's digest highlights:\n"
            f"{digest['highlights_json']}\n"
            f"Details:\n{digest['categories_json']}"
        )

        # Determine media references
        media_refs = []
        from pathlib import Path

        if format_type in ("image", "carousel", "video"):
            from generator.media_handler import (
                get_available_media,
                generate_activity_chart,
            )

            raw_media = get_available_media(state["date"])
            if format_type == "video":
                media_refs = [
                    m
                    for m in raw_media
                    if Path(m).suffix.lower() in (".mp4", ".mov", ".avi", ".mkv")
                ]
            else:
                media_refs = [
                    m
                    for m in raw_media
                    if Path(m).suffix.lower() in (".png", ".jpg", ".jpeg")
                ]

            if not media_refs and format_type in ("image", "carousel"):
                # Fallback to generated chart if no screenshots are provided
                chart_path = generate_activity_chart(state["date"])
                if chart_path:
                    media_refs = [chart_path]

        media_refs_json = (
            json.dumps(media_refs)
            if (format_type in ("image", "carousel", "video") and media_refs)
            else None
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            output_config={"format": {"type": "json_schema", "schema": draft_schema}},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_data = json.loads(response.content[0].text)
        variants = response_data["variants"]

        generated_drafts = []
        for var in variants:
            text = var["text"]
            twitter_text = var.get("twitter_text", "")
            hashtags_list = var["hashtags"]
            hashtags_str = " ".join(
                [f"#{h.strip().replace('#', '')}" for h in hashtags_list]
            )

            char_count = len(text)
            if char_count > 3000:
                continue

            if format_type == "poll":
                poll_data = {
                    "question": var["poll_question"],
                    "options": var["poll_options"],
                    "duration": var["poll_duration"],
                }
                var_media_refs_json = json.dumps(poll_data)
            else:
                var_media_refs_json = media_refs_json

            cursor.execute(
                "INSERT INTO drafts (digest_id, pillar, format_type, text_content, twitter_text_content, media_refs_json, hashtags, voice_profile_hash, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review')",
                (
                    digest["id"],
                    pillar,
                    format_type,
                    text,
                    twitter_text,
                    var_media_refs_json,
                    hashtags_str,
                    voice_profile_hash,
                ),
            )
            draft_id = cursor.lastrowid
            generated_drafts.append(
                {
                    "id": draft_id,
                    "pillar": pillar,
                    "format_type": format_type,
                    "text_content": text,
                    "twitter_text_content": twitter_text,
                    "media_refs_json": var_media_refs_json,
                    "hashtags": hashtags_str,
                }
            )

        conn.commit()
        return {"drafts": generated_drafts, "status": "success"}
    except Exception as e:
        return {"status": "failed", "error": f"Draft generation failed: {str(e)}"}
    finally:
        conn.close()


def generate_visual_node(state: PipelineState) -> Dict[str, Any]:
    """Generates visual media (Manim, Remotion video, or chart) for approved drafts."""
    drafts = state.get("drafts", [])
    if not drafts:
        return {"drafts": drafts}

    format_type = state.get("format_type")
    if format_type not in ("video", "image", "carousel"):
        # select_format_node already made a deliberate call for text/poll —
        # don't second-guess it by attaching unrequested media.
        return {"drafts": drafts}

    digest = state.get("digest")
    date_str = state.get("date", "")
    if not digest:
        return {"drafts": drafts}

    from generator.media_handler import (
        generate_remotion_video,
        generate_manim_video,
        generate_activity_chart,
    )
    from generator.visual_selector import select_visual_type

    # Determine which composition/engine to use
    composition, reasoning = select_visual_type(digest, state.get("pillar", ""))

    output_path = f"data/media/{date_str}_animation.mp4"
    video_generated = False

    draft_id = drafts[0].get("id") if drafts else None
    draft_text = drafts[0].get("text_content") if drafts else None

    # Route to the appropriate video engine
    if composition == "ManimAnimation":
        try:
            video_generated = generate_manim_video(
                date_str, digest, output_path,
                draft_text=draft_text, draft_id=draft_id,
            )
        except Exception as e:
            import logging
            logging.getLogger("linkedin-agent.agent_graph").warning(
                f"Manim render failed, falling back to Remotion: {e}"
            )

        # Fall back to Remotion if Manim fails
        if not video_generated:
            import logging
            logging.getLogger("linkedin-agent.agent_graph").info(
                "Manim failed — attempting Remotion fallback"
            )
            try:
                video_generated = generate_remotion_video(
                    date_str, digest, output_path,
                    draft_text=draft_text, draft_id=draft_id,
                )
            except Exception as e:
                logging.getLogger("linkedin-agent.agent_graph").warning(
                    f"Remotion fallback also failed: {e}"
                )
    elif composition:
        # Standard Remotion compositions
        try:
            video_generated = generate_remotion_video(
                date_str, digest, output_path,
                draft_text=draft_text, draft_id=draft_id,
            )
        except Exception as e:
            import logging
            logging.getLogger("linkedin-agent.agent_graph").warning(
                f"Remotion render failed, falling back: {e}"
            )

    if video_generated:
        from pathlib import Path
        abs_video_path = str(Path(output_path).resolve())
        updated_drafts = []
        for draft in drafts:
            draft["media_refs_json"] = json.dumps([abs_video_path])
            draft["format_type"] = "video"
            updated_drafts.append(draft)
        return {"drafts": updated_drafts}

    # No Remotion render. "image"/"carousel" drafts still want a graphic,
    # so a matplotlib activity chart is a reasonable substitute. A "video"
    # draft degrades to plain text instead — a static chart standing in for
    # a video that never got made is a worse, inconsistent reader experience
    # than just not having a visual at all.
    updated_drafts = []
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        chart_path = None
        if format_type in ("image", "carousel"):
            try:
                chart_path = generate_activity_chart(date_str)
            except Exception:
                chart_path = None

        for draft in drafts:
            if format_type in ("image", "carousel") and chart_path:
                draft["media_refs_json"] = json.dumps([chart_path])
                draft["format_type"] = "image"
            elif format_type == "video":
                draft["media_refs_json"] = None
                draft["format_type"] = "text"
            cursor.execute(
                "UPDATE drafts SET media_refs_json = ?, format_type = ? WHERE id = ?",
                (draft.get("media_refs_json"), draft["format_type"], draft["id"]),
            )
            updated_drafts.append(draft)
        conn.commit()
    finally:
        conn.close()

    return {"drafts": updated_drafts}


# ==================== Graph Compilation ====================


def route_after_digest(state: PipelineState) -> str:
    """Routes the workflow conditional on digest completion status."""
    status = state.get("status")
    if status == "success":
        # Check if pillar is valid
        digest = state.get("digest")
        if digest and digest.get("suggested_pillar") == "none":
            return END
        return "classify_pillar"
    return END


def route_after_pillar(state: PipelineState) -> str:
    """Routes the workflow conditional on the classified content pillar."""
    if state.get("status") == "failed":
        return END
    pillar = state.get("pillar")
    if not pillar or pillar == "none":
        return END
    return "select_format"


def route_after_format(state: PipelineState) -> str:
    """Routes to retrieval step or END based on status."""
    if state.get("status") == "failed":
        return END
    return "retrieve_persona_context"


workflow = StateGraph(PipelineState)

# Add nodes
workflow.add_node("aggregate_digest", aggregate_digest_node)
workflow.add_node("classify_pillar", classify_pillar_node)
workflow.add_node("select_format", select_format_node)
workflow.add_node("retrieve_persona_context", retrieve_persona_context_node)
workflow.add_node("generate_drafts", generate_drafts_node)

# Set starting edge
workflow.add_edge(START, "aggregate_digest")

# Set conditional and direct edges
workflow.add_conditional_edges(
    "aggregate_digest",
    route_after_digest,
    {"classify_pillar": "classify_pillar", END: END},
)

workflow.add_conditional_edges(
    "classify_pillar", route_after_pillar, {"select_format": "select_format", END: END}
)

workflow.add_conditional_edges(
    "select_format",
    route_after_format,
    {"retrieve_persona_context": "retrieve_persona_context", END: END},
)

workflow.add_node("generate_visual", generate_visual_node)

workflow.add_edge("retrieve_persona_context", "generate_drafts")
workflow.add_edge("generate_drafts", "generate_visual")
workflow.add_edge("generate_visual", END)

compiled_graph = workflow.compile()
