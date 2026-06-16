import os
import json
import logging
import requests
import datetime
from db.db import get_db_connection

logger = logging.getLogger("linkedin-agent.capture.notion")

def extract_notion_page_title(page_obj: dict) -> str:
    """Helper to traverse Notion's nested property schema and extract the page title."""
    properties = page_obj.get("properties", {})
    for prop_name, prop_val in properties.items():
        if prop_val.get("type") == "title":
            title_list = prop_val.get("title", [])
            if title_list:
                return "".join([t.get("plain_text", "") for t in title_list])
    return "Untitled Page"

def fetch_and_store_notion_pages() -> None:
    """
    Queries Notion's Search API for recently edited pages in the workspace,
    and stores them as 'note' activity events.
    """
    token = os.getenv("NOTION_API_KEY")
    if not token:
        logger.warning("NOTION_API_KEY is not set in .env. Skipping Notion activity sync.")
        return
        
    url = "https://api.notion.com/v1/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    payload = {
        "filter": {"value": "page", "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        pages = data.get("results", [])
    except Exception as e:
        logger.error(f"Failed to query Notion Search API: {e}")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    events_logged = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    for page in pages:
        page_id = page.get("id")
        last_edited_raw = page.get("last_edited_time")  # ISO8601 UTC
        page_url = page.get("url")
        
        # Parse last edited time and ignore if older than 24 hours
        try:
            # strip 'Z' and parse
            dt_str = last_edited_raw.replace("Z", "+00:00")
            last_edited_dt = datetime.datetime.fromisoformat(dt_str)
            if (now_utc - last_edited_dt).total_seconds() > 24 * 3600:
                # Search is sorted by last edited time; once we hit an old page, we can stop
                break
        except Exception:
            pass
            
        # 1. Deduplicate by Notion Page ID and last edited timestamp
        cursor.execute(
            "SELECT COUNT(*) FROM activity_events WHERE source = 'note' "
            "AND json_extract(detail, '$.notion_page_id') = ? "
            "AND json_extract(detail, '$.last_edited_time') = ?",
            (page_id, last_edited_raw)
        )
        if cursor.fetchone()[0] > 0:
            continue
            
        title = extract_notion_page_title(page)
        event_title = f"Edited Notion note: '{title}'"
        
        detail = {
            "notion_page_id": page_id,
            "last_edited_time": last_edited_raw,
            "url": page_url,
            "title": title
        }
        
        cursor.execute(
            "INSERT INTO activity_events (source, event_time, title, detail) VALUES ('note', ?, ?, ?)",
            (last_edited_raw, event_title, json.dumps(detail))
        )
        events_logged += 1
        
    conn.commit()
    conn.close()
    logger.info(f"Notion capture watcher completed. Logged {events_logged} new page edit event(s).")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_and_store_notion_pages()
