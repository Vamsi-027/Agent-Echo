import os
import json
import logging
import requests
import datetime
from db.db import get_db_connection

logger = logging.getLogger("linkedin-agent.capture.github")

def fetch_and_store_github_events() -> None:
    """
    Fetches the user's recent GitHub events via the REST API,
    applies exclusions, and stores them in activity_events with SQLite JSON deduplication.
    """
    token = os.getenv("GITHUB_TOKEN")
    username = os.getenv("GITHUB_USERNAME")
    
    if not username:
        logger.warning("GITHUB_USERNAME is not set in .env. Skipping GitHub activity sync.")
        return
        
    url = f"https://api.github.com/users/{username}/events"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if token:
        headers["Authorization"] = f"token {token}"
        
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 401 and token:
            logger.warning("GitHub GITHUB_TOKEN in .env is invalid or expired (401 Unauthorized). Retrying without token header to fetch public events...")
            headers.pop("Authorization", None)
            response = requests.get(url, headers=headers)
        response.raise_for_status()
        events = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch GitHub events: {e}")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    events_logged = 0
    for ev in events:
        ev_id = ev.get("id")
        ev_type = ev.get("type")
        repo_name = ev.get("repo", {}).get("name")
        created_at_raw = ev.get("created_at")  # ISO8601 UTC
        
        # 1. Deduplicate by GitHub Event ID
        cursor.execute(
            "SELECT COUNT(*) FROM activity_events WHERE source = 'git' AND json_extract(detail, '$.github_event_id') = ?",
            (str(ev_id),)
        )
        if cursor.fetchone()[0] > 0:
            continue
            
        # Parse based on event type
        title = None
        detail = {
            "github_event_id": ev_id,
            "repo": repo_name,
            "event_type": ev_type
        }
        
        if ev_type == "PushEvent":
            commits = ev.get("payload", {}).get("commits") or []
            commit_messages = [c.get("message", "").split("\n")[0] for c in commits]
            if commits:
                title = f"Pushed {len(commits)} commit(s) to {repo_name}"
                detail["commits"] = commit_messages
            else:
                title = f"Pushed commits to {repo_name}"
                detail["commits"] = []
            
        elif ev_type == "PullRequestEvent":
            payload = ev.get("payload", {})
            action = payload.get("action")
            pr_title = payload.get("pull_request", {}).get("title")
            title = f"Pull Request {action} in {repo_name}: '{pr_title}'"
            detail["pr_title"] = pr_title
            detail["action"] = action
            
        elif ev_type == "IssuesEvent":
            payload = ev.get("payload", {})
            action = payload.get("action")
            issue_title = payload.get("issue", {}).get("title")
            title = f"Issue {action} in {repo_name}: '{issue_title}'"
            detail["issue_title"] = issue_title
            detail["action"] = action
            
        elif ev_type == "PullRequestReviewEvent":
            payload = ev.get("payload", {})
            pr_title = payload.get("pull_request", {}).get("title")
            title = f"Reviewed Pull Request in {repo_name}: '{pr_title}'"
            detail["pr_title"] = pr_title
            
        if not title:
            # Skip unhandled/minor event types
            continue
            
        cursor.execute(
            "INSERT INTO activity_events (source, event_time, title, detail) VALUES ('git', ?, ?, ?)",
            (created_at_raw, title, json.dumps(detail))
        )
        events_logged += 1
        
    conn.commit()
    conn.close()
    logger.info(f"GitHub capture watcher completed. Logged {events_logged} new event(s).")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_and_store_github_events()
