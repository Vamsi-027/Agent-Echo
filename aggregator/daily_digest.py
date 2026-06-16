import json
import datetime
from zoneinfo import ZoneInfo
from anthropic import Anthropic
from db.db import get_db_connection
from config_loader import LOCAL_TZ, load_pillars

def run_daily_digest(date_str: str | None = None) -> dict | None:
    """
    Retrieves activity events for a given local date, structures them,
    asks Claude to summarize it as a daily digest, and stores it in the database.
    
    If date_str is not provided, targets yesterday's date in local time.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Resolve local date range
    if date_str:
        try:
            local_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}. Must be YYYY-MM-DD.")
    else:
        # Default to yesterday in local timezone
        now_local = datetime.datetime.now(LOCAL_TZ)
        local_date = (now_local - datetime.timedelta(days=1)).date()
    
    date_key = local_date.strftime("%Y-%m-%d")
    
    # Calculate UTC bounds for this local date
    start_local = datetime.datetime.combine(local_date, datetime.time.min, tzinfo=LOCAL_TZ)
    end_local = datetime.datetime.combine(local_date, datetime.time.max, tzinfo=LOCAL_TZ)
    
    start_utc = start_local.astimezone(datetime.timezone.utc)
    end_utc = end_local.astimezone(datetime.timezone.utc)
    
    start_iso = start_utc.isoformat()
    end_iso = end_utc.isoformat()
    
    # 2. Query raw events within bounds
    cursor.execute(
        "SELECT source, event_time, title, detail FROM activity_events "
        "WHERE event_time >= ? AND event_time <= ? ORDER BY event_time ASC",
        (start_iso, end_iso)
    )
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return None
        
    # Group and format events
    raw_events_summary = []
    for row in rows:
        raw_events_summary.append({
            "source": row["source"],
            "time": row["event_time"],
            "title": row["title"],
            "detail": json.loads(row["detail"]) if row["detail"] else {}
        })
        
    raw_summary_text = json.dumps(raw_events_summary, indent=2)
    
    # 3. Request Claude for structured summary
    client = Anthropic()
    
    # Fetch available pillars from config
    pillars_list = load_pillars()
    pillar_enum = [p["id"] for p in pillars_list] + ["none"]
    
    digest_schema = {
        "type": "object",
        "properties": {
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "High-level summary bullet points of the day's achievements or challenges (aim for 2-5)"
            },
            "categories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Category name (e.g., Development, Meetings)"},
                        "details": {"type": "string", "description": "Brief summary of activities in this category"}
                    },
                    "required": ["name", "details"],
                    "additionalProperties": False
                },
                "description": "List of activity categories with their descriptions"
            },
            "suggested_pillar": {
                "type": "string",
                "enum": pillar_enum,
                "description": "The most appropriate content pillar for today's activities"
            }
        },
        "required": ["highlights", "categories", "suggested_pillar"],
        "additionalProperties": False
    }
    
    prompt = (
        "You are an expert technical editor. Summarize the following raw developer activity events for the day into a clean daily digest.\n"
        "Collapse noise (e.g., multiple tiny file edits or minor commits should be grouped into a single category summary line).\n"
        "Pick the best content pillar from the list of pillars.\n\n"
        f"Available Pillars: {json.dumps(pillars_list, indent=2)}\n\n"
        f"Raw Events:\n{raw_summary_text}"
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        output_config={"format": {"type": "json_schema", "schema": digest_schema}},
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Parse results
    structured_data = json.loads(response.content[0].text)
    
    # 4. Insert with version incrementing if date already exists
    cursor.execute("SELECT MAX(version) FROM daily_digests WHERE date = ?", (date_key,))
    max_ver = cursor.fetchone()[0]
    next_version = (max_ver + 1) if max_ver is not None else 1
    
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            date_key,
            next_version,
            raw_summary_text,
            json.dumps(structured_data["highlights"]),
            json.dumps(structured_data["categories"]),
            structured_data["suggested_pillar"]
        )
    )
    
    conn.commit()
    
    # Fetch the newly inserted row
    cursor.execute("SELECT * FROM daily_digests WHERE date = ? AND version = ?", (date_key, next_version))
    inserted_row = dict(cursor.fetchone())
    
    conn.close()
    return inserted_row
