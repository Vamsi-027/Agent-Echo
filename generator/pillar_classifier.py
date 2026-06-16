import json
from anthropic import Anthropic
from db.db import get_db_connection
from config_loader import load_pillars

def classify_pillar(digest_row: dict) -> tuple[str, str | None]:
    """
    Given a daily digest, classifies it into a primary and optional secondary pillar,
    taking into account the last 14 days of pillar history to avoid repetition.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch recent pillar history (last 14 days of drafts that were approved/published)
    cursor.execute(
        "SELECT pillar FROM drafts "
        "WHERE status IN ('approved', 'published') "
        "AND created_at >= datetime('now', '-14 days') "
        "ORDER BY created_at DESC"
    )
    history = [row["pillar"] for row in cursor.fetchall() if row["pillar"]]
    conn.close()
    
    pillars_list = load_pillars()
    pillar_ids = [p["id"] for p in pillars_list]
    
    client = Anthropic()
    
    classification_schema = {
        "type": "object",
        "properties": {
            "primary_pillar": {
                "type": "string",
                "enum": pillar_ids + ["none"],
                "description": "The primary pillar for this content, or 'none' if not worthy"
            },
            "secondary_pillar": {
                "type": "string",
                "enum": pillar_ids + ["none"],
                "description": "An optional secondary pillar, or 'none' if not applicable"
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation for the choice, referencing the history or content strength"
            }
        },
        "required": ["primary_pillar", "reasoning"],
        "additionalProperties": False
    }
    
    prompt = (
        "You are an editor selecting content topics for a technical LinkedIn account.\n"
        "Your goal is to decide which content pillar today's daily digest belongs to, "
        "while ensuring variety by reviewing recently used pillars.\n\n"
        f"Available Pillars:\n{json.dumps(pillars_list, indent=2)}\n\n"
        f"Pillars used in the last 14 days (most recent first):\n{json.dumps(history)}\n\n"
        f"Today's Daily Digest:\n"
        f"Suggested Pillar: {digest_row['suggested_pillar']}\n"
        f"Highlights:\n{digest_row['highlights_json']}\n"
        f"Categories:\n{digest_row['categories_json']}\n\n"
        "Please select the primary and optional secondary pillar."
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        output_config={"format": {"type": "json_schema", "schema": classification_schema}},
        messages=[{"role": "user", "content": prompt}]
    )
    
    result = json.loads(response.content[0].text)
    
    primary = result["primary_pillar"]
    secondary = result.get("secondary_pillar")
    if secondary == "none":
        secondary = None
        
    return primary, secondary
