import json
import random
import datetime
from zoneinfo import ZoneInfo
from anthropic import Anthropic
from db.db import get_db_connection
from config_loader import LOCAL_TZ, get_voice_profile, load_posting_cadence
from generator.pillar_classifier import classify_pillar
from generator.format_selector import select_format

def generate_drafts_for_date(date_str: str | None = None) -> list[dict]:
    """
    Invokes the compiled LangGraph pipeline for the given date, which aggregates
    events, classifies pillars, selects formatting, generates drafts, and returns them.
    """
    # 1. Resolve date
    if not date_str:
        now_local = datetime.datetime.now(LOCAL_TZ)
        date_key = (now_local - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_key = date_str
        
    from generator.agent_graph import compiled_graph
    
    initial_state = {
        "date": date_key,
        "digest": None,
        "pillar": None,
        "secondary_pillar": None,
        "format_type": None,
        "persona_context": None,
        "drafts": [],
        "status": "started",
        "error": None
    }
    
    final_state = compiled_graph.invoke(initial_state)
    
    if final_state.get("status") == "failed":
        raise RuntimeError(f"LangGraph execution failed: {final_state.get('error')}")
        
    return final_state.get("drafts", [])

def approve_draft(draft_id: int) -> None:
    """
    Approves a draft, updates its status, and schedules it in the content queue.
    Uses the posting cadence configuration to calculate the next valid scheduled time.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch draft details
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    draft = cursor.fetchone()
    if not draft:
        conn.close()
        raise ValueError(f"Draft {draft_id} not found.")
        
    if draft["status"] != "pending_review":
        conn.close()
        raise ValueError(f"Draft {draft_id} is in status '{draft['status']}', cannot approve.")
        
    # 2. Load posting cadence config
    cadence_config = load_posting_cadence()["cadence"]
    max_weekday = cadence_config["max_posts_per_day"]["weekday"]
    max_weekend = cadence_config["max_posts_per_day"]["weekend"]
    min_hours = cadence_config["min_hours_between_posts"]
    posting_windows = cadence_config["posting_windows"]
    jitter_range = cadence_config["jitter_minutes"]
    
    # 3. Determine base search start time
    # Find the latest scheduled post in queue
    cursor.execute(
        "SELECT MAX(scheduled_time) FROM content_queue WHERE status = 'queued'"
    )
    latest_scheduled_str = cursor.fetchone()[0]
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if latest_scheduled_str:
        latest_scheduled = datetime.datetime.fromisoformat(latest_scheduled_str)
        # Search start is at least min_hours after latest scheduled post
        search_start = max(now_utc, latest_scheduled + datetime.timedelta(hours=min_hours))
    else:
        search_start = now_utc
        
    # Convert search start to local timezone
    search_start_local = search_start.astimezone(LOCAL_TZ)
    
    # 4. Find the next available slot
    scheduled_local_time = None
    test_date = search_start_local.date()
    
    # Iterate through days looking for slots
    for day_offset in range(14): # search up to 2 weeks out
        current_date = search_start_local.date() + datetime.timedelta(days=day_offset)
        
        # Check weekday vs weekend post limits
        is_weekend = current_date.weekday() >= 5
        max_posts = max_weekend if is_weekend else max_weekday
        
        # Count already scheduled posts for this date (in local time)
        # To do this safely, construct bounds for current_date in local timezone, convert to UTC strings
        start_local = datetime.datetime.combine(current_date, datetime.time.min, tzinfo=LOCAL_TZ)
        end_local = datetime.datetime.combine(current_date, datetime.time.max, tzinfo=LOCAL_TZ)
        start_utc_str = start_local.astimezone(datetime.timezone.utc).isoformat()
        end_utc_str = end_local.astimezone(datetime.timezone.utc).isoformat()
        
        cursor.execute(
            "SELECT COUNT(*) FROM content_queue WHERE status = 'queued' "
            "AND scheduled_time >= ? AND scheduled_time <= ?",
            (start_utc_str, end_utc_str)
        )
        scheduled_count = cursor.fetchone()[0]
        
        if scheduled_count >= max_posts:
            # Day is full, skip to next day
            continue
            
        # Day has room! Check posting windows
        # Sort windows by time to check chronologically
        sorted_windows = sorted(posting_windows, key=lambda w: w["start"])
        
        for win in sorted_windows:
            win_start_time = datetime.datetime.strptime(win["start"], "%H:%M").time()
            win_end_time = datetime.datetime.strptime(win["end"], "%H:%M").time()
            
            # Combine current_date with window start
            win_start_dt = datetime.datetime.combine(current_date, win_start_time, tzinfo=LOCAL_TZ)
            win_end_dt = datetime.datetime.combine(current_date, win_end_time, tzinfo=LOCAL_TZ)
            
            # We must schedule after the search start time
            if win_start_dt < search_start_local:
                # If window has already passed or started before search_start, check if search_start fits in it
                if search_start_local < win_end_dt:
                    slot_base = search_start_local
                else:
                    continue
            else:
                slot_base = win_start_dt
                
            # Apply random jitter (minutes)
            jitter_minutes = random.randint(-jitter_range, jitter_range)
            scheduled_local_time = slot_base + datetime.timedelta(minutes=jitter_minutes)
            
            # Double check it is still within the day and hasn't slipped in the past
            if scheduled_local_time.astimezone(datetime.timezone.utc) < now_utc:
                scheduled_local_time = now_utc + datetime.timedelta(minutes=5) # fallback if jitter pushed it to the past
                
            break
            
        if scheduled_local_time:
            break
            
    if not scheduled_local_time:
        # Fallback if no window found (should not happen within 14 days)
        scheduled_local_time = search_start_local + datetime.timedelta(hours=min_hours)
        
    scheduled_utc = scheduled_local_time.astimezone(datetime.timezone.utc)
    scheduled_utc_str = scheduled_utc.isoformat()
    
    # 5. Insert into queue and update draft status
    cursor.execute(
        "UPDATE drafts SET status = 'approved', scheduled_time = ?, updated_at = datetime('now') WHERE id = ?",
        (scheduled_utc_str, draft_id)
    )
    
    # Calculate a mock priority score based on pillar/format variety
    priority = round(random.uniform(0.5, 1.0), 2)
    
    cursor.execute(
        "INSERT INTO content_queue (draft_id, priority_score, scheduled_time, status) "
        "VALUES (?, ?, ?, 'queued')",
        (draft_id, priority, scheduled_utc_str)
    )
    
    conn.commit()
    conn.close()

def edit_draft(draft_id: int, instruction: str) -> dict:
    """
    Submits a revision instruction to Claude to regenerate a draft variant,
    saving the new variant in the DB and updating the old draft's status.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch original draft
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    original = cursor.fetchone()
    if not original:
        conn.close()
        raise ValueError(f"Draft {draft_id} not found.")
        
    voice_profile_text, voice_profile_hash = get_voice_profile()
    
    client = Anthropic()
    
    if original["format_type"] == "poll":
        edit_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The revised LinkedIn post body text"},
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of hashtags"
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
    else:
        edit_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The revised LinkedIn post body text"},
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of hashtags"
                }
            },
            "required": ["text", "hashtags"],
            "additionalProperties": False
        }
    
    system_prompt = (
        f"You are a professional editor revising a draft post to match the author's voice profile.\n\n"
        f"Voice Profile Guidelines:\n{voice_profile_text}\n\n"
        f"Selected Pillar: {original['pillar']}\n"
        f"Format Type: {original['format_type']}"
    )
    
    user_prompt = (
        f"Original Draft:\n{original['text_content']}\n\n"
        f"Revision Request: {instruction}\n\n"
        "Please rewrite the post incorporating the revision request, while maintaining the character count limit (<1300 chars)."
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        output_config={"format": {"type": "json_schema", "schema": edit_schema}},
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    response_data = json.loads(response.content[0].text)
    revised_text = response_data["text"]
    hashtags_list = response_data["hashtags"]
    hashtags_str = " ".join([f"#{h.strip().replace('#', '')}" for h in hashtags_list])
    
    if original["format_type"] == "poll":
        poll_data = {
            "question": response_data["poll_question"],
            "options": response_data["poll_options"],
            "duration": response_data["poll_duration"]
        }
        media_refs_json = json.dumps(poll_data)
    else:
        media_refs_json = original["media_refs_json"]
        
    # Update original draft to status 'edited'
    cursor.execute(
        "UPDATE drafts SET status = 'edited', review_notes = ?, updated_at = datetime('now') WHERE id = ?",
        (instruction, draft_id)
    )
    
    # Create new draft row
    cursor.execute(
        "INSERT INTO drafts (digest_id, pillar, format_type, text_content, media_refs_json, hashtags, voice_profile_hash, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review')",
        (original["digest_id"], original["pillar"], original["format_type"], revised_text, media_refs_json, hashtags_str, voice_profile_hash)
    )
    new_draft_id = cursor.lastrowid
    
    conn.commit()
    
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (new_draft_id,))
    new_draft_row = dict(cursor.fetchone())
    
    conn.close()
    return new_draft_row
