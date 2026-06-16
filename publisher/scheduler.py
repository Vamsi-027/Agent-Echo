import datetime
import logging
import requests
from db.db import get_db_connection
from publisher.linkedin_client import post_draft_to_linkedin
from notification.router import alert_router

logger = logging.getLogger("linkedin-agent.scheduler")

def reconcile_stuck_publishes(conn) -> None:
    """
    Finds queue items or drafts stuck in the 'publishing' state for more than 5 minutes.
    Marks them as 'needs_manual_check' to prevent infinite locks and double posting.
    """
    cursor = conn.cursor()
    # Find items stuck in publishing state for > 5 minutes
    cursor.execute(
        "SELECT d.id, d.text_content FROM drafts d "
        "JOIN content_queue q ON q.draft_id = d.id "
        "WHERE d.status = 'publishing' "
        "AND d.publishing_started_at < datetime('now', '-5 minutes')"
    )
    stuck_drafts = cursor.fetchall()
    
    for row in stuck_drafts:
        draft_id = row["id"]
        logger.warning(f"Reconciling stuck draft ID {draft_id}.")
        
        cursor.execute(
            "UPDATE drafts SET status = 'needs_manual_check', updated_at = datetime('now') WHERE id = ?",
            (draft_id,)
        )
        cursor.execute(
            "UPDATE content_queue SET status = 'needs_manual_check', updated_at = datetime('now') WHERE draft_id = ?",
            (draft_id,)
        )
        alert_router(f"Draft {draft_id} was stuck mid-publish — check LinkedIn manually before re-approving.")
        
    conn.commit()

def publish_due_drafts(conn) -> None:
    """
    Finds approved drafts in the queue that are scheduled for publication at or before the current time.
    Executes publishing, transitions statuses, handles retries/failures, and creates published post records.
    """
    cursor = conn.cursor()
    
    # Query queue items that are due (scheduled_time <= now)
    cursor.execute(
        "SELECT q.id as queue_id, q.scheduled_time, d.id as draft_id, d.pillar, d.format_type, "
        "d.text_content, d.media_refs_json, d.hashtags "
        "FROM content_queue q "
        "JOIN drafts d ON q.draft_id = d.id "
        "WHERE q.status = 'queued' AND datetime(q.scheduled_time) <= datetime('now') "
        "ORDER BY q.priority_score DESC, q.scheduled_time ASC"
    )
    due_items = cursor.fetchall()
    
    for item in due_items:
        queue_id = item["queue_id"]
        draft_id = item["draft_id"]
        
        logger.info(f"Processing publication for draft ID {draft_id} (queue ID {queue_id}).")
        
        # 1. Update status to 'publishing' to lock the resource (idempotency)
        cursor.execute(
            "UPDATE drafts SET status = 'publishing', publishing_started_at = datetime('now'), "
            "updated_at = datetime('now') WHERE id = ?", (draft_id,)
        )
        cursor.execute(
            "UPDATE content_queue SET status = 'publishing', updated_at = datetime('now') WHERE id = ?", (queue_id,)
        )
        conn.commit()
        
        # Build draft dict for the publisher client
        draft_dict = {
            "id": draft_id,
            "format_type": item["format_type"],
            "text_content": item["text_content"],
            "media_refs_json": item["media_refs_json"],
            "hashtags": item["hashtags"]
        }
        
        try:
            resp = post_draft_to_linkedin(draft_dict)
            
            # Check for version sunset error (426 Upgrade Required)
            if resp.status_code == 426:
                logger.error("LinkedIn API Version Sunset (426) encountered. Rollback statuses.")
                cursor.execute("UPDATE drafts SET status = 'approved', updated_at = datetime('now') WHERE id = ?", (draft_id,))
                cursor.execute("UPDATE content_queue SET status = 'queued', updated_at = datetime('now') WHERE id = ?", (queue_id,))
                conn.commit()
                alert_router("LinkedIn-Version sunset (426) — update LINKEDIN_VERSION and redeploy.")
                break # Sunset blocks all further publishing
                
            resp.raise_for_status()
            
            # Post successful! Extract post URN
            urn = resp.headers.get("x-restli-id") or resp.json().get("id")
            if not urn:
                urn = f"urn:li:share:generated_fallback_{os.urandom(4).hex()}"
                
            cursor.execute("UPDATE drafts SET status = 'published', updated_at = datetime('now') WHERE id = ?", (draft_id,))
            cursor.execute("UPDATE content_queue SET status = 'published', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            cursor.execute("INSERT INTO published_posts (draft_id, linkedin_post_urn) VALUES (?, ?)", (draft_id, urn))
            conn.commit()
            logger.info(f"Draft ID {draft_id} successfully published to LinkedIn (URN: {urn}).")
            
        except requests.HTTPError as e:
            # Handle rate limits
            if e.response is not None and e.response.status_code == 429:
                logger.warning(f"Rate limited (429) publishing draft ID {draft_id}. Rolling back to retry.")
                cursor.execute("UPDATE drafts SET status = 'approved', updated_at = datetime('now') WHERE id = ?", (draft_id,))
                cursor.execute("UPDATE content_queue SET status = 'queued', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            else:
                logger.error(f"HTTP error publishing draft ID {draft_id}: {e}")
                cursor.execute("UPDATE drafts SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (draft_id,))
                cursor.execute("UPDATE content_queue SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (queue_id,))
                alert_router(f"Draft {draft_id} failed to publish: {e}")
            conn.commit()
            
        except Exception as e:
            logger.error(f"Unexpected error publishing draft ID {draft_id}: {e}")
            cursor.execute("UPDATE drafts SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (draft_id,))
            cursor.execute("UPDATE content_queue SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            conn.commit()
            alert_router(f"Draft {draft_id} failed to publish (unexpected error): {e}")

def run_publisher_tick() -> None:
    """Top-level function called by CLI or scheduler trigger."""
    try:
        from publisher.oauth import check_and_refresh_token
        check_and_refresh_token()
    except Exception as e:
        logger.error(f"Error during OAuth token check: {e}", exc_info=True)
        
    conn = get_db_connection()
    try:
        reconcile_stuck_publishes(conn)
        publish_due_drafts(conn)
    finally:
        conn.close()
