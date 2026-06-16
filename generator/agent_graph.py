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
        (date_str,)
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
        recent_published = [row["text_content"] for row in cursor.fetchall() if row["text_content"]]
        
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
                                    "description": "The post body draft content (commentary explaining/introducing the poll)"
                                },
                                "hashtags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                    "description": "Relevant hashtags without the # prefix (aim for 2-4)"
                                },
                                "poll_question": {
                                    "type": "string",
                                    "maxLength": 140,
                                    "description": "The poll question itself (max 140 characters)"
                                },
                                "poll_options": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": 4,
                                    "items": {
                                        "type": "string",
                                        "maxLength": 30
                                    },
                                    "description": "List of 2 to 4 poll options (each option max 30 characters)"
                                },
                                "poll_duration": {
                                    "type": "string",
                                    "enum": ["ONE_DAY", "THREE_DAYS", "SEVEN_DAYS", "FOURTEEN_DAYS"],
                                    "description": "Duration of the poll"
                                }
                            },
                            "required": ["text", "hashtags", "poll_question", "poll_options", "poll_duration"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["variants"],
                "additionalProperties": False
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
                                    "description": "The post body draft content"
                                },
                                "hashtags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 1,
                                    "description": "Relevant hashtags without the # prefix (aim for 2-4)"
                                }
                            },
                            "required": ["text", "hashtags"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["variants"],
                "additionalProperties": False
            }
        
        persona_context = state.get("persona_context") or "No specific personal context found."
        
        system_prompt = (
            f"You are the author of a highly engaging LinkedIn profile.\n\n"
            f"Personal Experience and Stylistic References:\n{persona_context}\n\n"
            f"Voice Profile Constraints:\n{voice_profile_text}\n\n"
            f"Target Pillar: {pillar} (Secondary: {state.get('secondary_pillar') or 'None'})\n"
            f"Target Format: {format_type}\n"
            "Guidelines:\n"
            "- Do not use corporate speak or hype phrases.\n"
            "- Write naturally, sharing insights, metrics, or lessons from today's work.\n"
            "- The post variant must be under 1300 characters.\n\n"
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
            from generator.media_handler import get_available_media, generate_activity_chart
            raw_media = get_available_media(state["date"])
            if format_type == "video":
                media_refs = [m for m in raw_media if Path(m).suffix.lower() in (".mp4", ".mov", ".avi", ".mkv")]
            else:
                media_refs = [m for m in raw_media if Path(m).suffix.lower() in (".png", ".jpg", ".jpeg")]
                
            if not media_refs and format_type in ("image", "carousel"):
                # Fallback to generated chart if no screenshots are provided
                chart_path = generate_activity_chart(state["date"])
                if chart_path:
                    media_refs = [chart_path]
        
        media_refs_json = json.dumps(media_refs) if (format_type in ("image", "carousel", "video") and media_refs) else None
 
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            output_config={"format": {"type": "json_schema", "schema": draft_schema}},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        response_data = json.loads(response.content[0].text)
        variants = response_data["variants"]
        
        generated_drafts = []
        for var in variants:
            text = var["text"]
            hashtags_list = var["hashtags"]
            hashtags_str = " ".join([f"#{h.strip().replace('#', '')}" for h in hashtags_list])
            
            char_count = len(text)
            if char_count > 3000:
                continue
                
            if format_type == "poll":
                poll_data = {
                    "question": var["poll_question"],
                    "options": var["poll_options"],
                    "duration": var["poll_duration"]
                }
                var_media_refs_json = json.dumps(poll_data)
            else:
                var_media_refs_json = media_refs_json
                
            cursor.execute(
                "INSERT INTO drafts (digest_id, pillar, format_type, text_content, media_refs_json, hashtags, voice_profile_hash, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review')",
                (digest["id"], pillar, format_type, text, var_media_refs_json, hashtags_str, voice_profile_hash)
            )
            draft_id = cursor.lastrowid
            generated_drafts.append({
                "id": draft_id,
                "pillar": pillar,
                "format_type": format_type,
                "text_content": text,
                "media_refs_json": var_media_refs_json,
                "hashtags": hashtags_str
            })
            
        conn.commit()
        return {"drafts": generated_drafts, "status": "success"}
    except Exception as e:
        return {"status": "failed", "error": f"Draft generation failed: {str(e)}"}
    finally:
        conn.close()

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
    {
        "classify_pillar": "classify_pillar",
        END: END
    }
)

workflow.add_conditional_edges(
    "classify_pillar",
    route_after_pillar,
    {
        "select_format": "select_format",
        END: END
    }
)

workflow.add_conditional_edges(
    "select_format",
    route_after_format,
    {
        "retrieve_persona_context": "retrieve_persona_context",
        END: END
    }
)

workflow.add_edge("retrieve_persona_context", "generate_drafts")
workflow.add_edge("generate_drafts", END)

compiled_graph = workflow.compile()
