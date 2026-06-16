import sys
import json
import logging
import subprocess
import datetime
from urllib.parse import urlparse
from db.db import get_db_connection
from config_loader import load_exclusions

logger = logging.getLogger("linkedin-agent.capture.browser")

# AppleScript to query Brave Browser status and active tab properties
APPLESCRIPT = """
tell application "System Events"
    set isRunning to (count of (every process whose name is "Brave Browser")) > 0
end tell
if isRunning then
    tell application "Brave Browser"
        if (count of windows) > 0 then
            try
                set activeTab to active tab of first window
                return (URL of activeTab) & "|||" & (title of activeTab)
            on error
                return "ERROR"
            end try
        else
            return "NO_WINDOWS"
        end if
    end tell
else
    return "NOT_RUNNING"
end if
"""

def get_active_browser_tab() -> tuple[str, str] | None:
    """Executes AppleScript on macOS to retrieve (url, title) of active tab in Brave Browser."""
    if sys.platform != "darwin":
        logger.warning("Browser active tab capture is only supported on macOS.")
        return None
        
    try:
        proc = subprocess.run(
            ["osascript", "-e", APPLESCRIPT],
            capture_output=True,
            text=True,
            check=True
        )
        output = proc.stdout.strip()
        
        if output in ("NOT_RUNNING", "NO_WINDOWS", "ERROR"):
            logger.info(f"Brave Browser status: {output}")
            return None
            
        parts = output.split("|||", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    except Exception as e:
        logger.error(f"Failed to query Brave Browser via AppleScript: {e}")
        
    return None

def is_domain_excluded(url: str, exclusions: dict) -> bool:
    """Checks if the tab's domain matches any exclusions in exclusions.yaml."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return True
            
        excluded_domains = exclusions.get("domains", [])
        for d in excluded_domains:
            d_lower = d.lower()
            # Direct match or subdomain match
            if domain == d_lower or domain.endswith(f".{d_lower}"):
                return True
    except Exception as e:
        logger.warning(f"Error parsing URL '{url}' for exclusion check: {e}")
        return True
    return False

def capture_active_browser_tab() -> None:
    """Queries Brave Browser, filters the tab against exclusions, and stores in SQLite if unique."""
    tab_data = get_active_browser_tab()
    if not tab_data:
        return
        
    url, title = tab_data
    
    # 1. Apply exclusions
    exclusions = load_exclusions()
    if is_domain_excluded(url, exclusions):
        logger.info(f"Excluding browser activity for URL: {url}")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 2. Query last browser event to prevent duplicate logs on the same site
    cursor.execute(
        "SELECT detail FROM activity_events WHERE source = 'browser' "
        "ORDER BY event_time DESC LIMIT 1"
    )
    last_row = cursor.fetchone()
    if last_row:
        try:
            last_detail = json.loads(last_row["detail"])
            if last_detail.get("url") == url:
                # User is still browsing the same URL, skip logging duplicate
                conn.close()
                return
        except Exception:
            pass
            
    # Log the event
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    detail = {
        "url": url,
        "title": title
    }
    
    cursor.execute(
        "INSERT INTO activity_events (source, event_time, title, detail) VALUES ('browser', ?, ?, ?)",
        (now_iso, f"Browsed: '{title}'", json.dumps(detail))
    )
    conn.commit()
    conn.close()
    
    logger.info(f"Logged active Brave Browser tab: '{title}' ({url})")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    capture_active_browser_tab()
