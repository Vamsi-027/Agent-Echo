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
    import os
    
    # Query queue items that are due (scheduled_time <= now)
    cursor.execute(
        "SELECT q.id as queue_id, q.scheduled_time, d.id as draft_id, d.pillar, d.format_type, "
        "d.text_content, d.twitter_text_content, d.media_refs_json, d.hashtags "
        "FROM content_queue q "
        "JOIN drafts d ON q.draft_id = d.id "
        "WHERE q.status = 'queued' AND d.status = 'approved' "
        "AND datetime(q.scheduled_time) <= datetime('now') "
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
            "twitter_text_content": item["twitter_text_content"],
            "media_refs_json": item["media_refs_json"],
            "hashtags": item["hashtags"]
        }
        
        linkedin_urn = None
        twitter_id = None
        linkedin_failed = False
        twitter_failed = False
        linkedin_error_msg = ""
        twitter_error_msg = ""
        version_sunset = False

        # 1. Publish to LinkedIn
        try:
            resp = post_draft_to_linkedin(draft_dict)
            
            # Check for version sunset error (426 Upgrade Required)
            if resp.status_code == 426:
                version_sunset = True
                linkedin_error_msg = "LinkedIn-Version sunset (426)"
            else:
                resp.raise_for_status()
                linkedin_urn = resp.headers.get("x-restli-id") or resp.json().get("id")
                if not linkedin_urn:
                    linkedin_urn = f"urn:li:share:generated_fallback_{os.urandom(4).hex()}"
        except Exception as e:
            linkedin_failed = True
            linkedin_error_msg = str(e)
            logger.error(f"LinkedIn publishing failed for draft {draft_id}: {e}")

        # If LinkedIn failed due to sunset, roll back immediately and abort tick
        if version_sunset:
            logger.error("LinkedIn API Version Sunset (426) encountered. Rollback statuses.")
            cursor.execute("UPDATE drafts SET status = 'approved', updated_at = datetime('now') WHERE id = ?", (draft_id,))
            cursor.execute("UPDATE content_queue SET status = 'queued', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            conn.commit()
            alert_router("LinkedIn-Version sunset (426) — update LINKEDIN_VERSION and redeploy.")
            break

        # 2. Publish to Twitter
        try:
            from publisher.twitter_client import post_draft_to_twitter
            t_resp = post_draft_to_twitter(draft_dict)
            t_resp.raise_for_status()
            t_data = t_resp.json()
            twitter_id = t_data.get("data", {}).get("id")
            if not twitter_id:
                twitter_id = f"mock_tweet_fallback_{os.urandom(4).hex()}"
        except Exception as e:
            twitter_failed = True
            twitter_error_msg = str(e)
            logger.error(f"Twitter publishing failed for draft {draft_id}: {e}")

        # 3. Assess results
        # If both failed:
        if not linkedin_urn and not twitter_id:
            logger.error(f"Both platforms failed to publish draft ID {draft_id}.")
            cursor.execute("UPDATE drafts SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (draft_id,))
            cursor.execute("UPDATE content_queue SET status = 'failed', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            conn.commit()
            alert_router(f"Draft {draft_id} failed to publish on both platforms. LinkedIn: {linkedin_error_msg}. Twitter: {twitter_error_msg}")
        else:
            # At least one succeeded!
            # Ensure we have a non-null placeholder for LinkedIn URN in case of legacy NOT NULL constraints
            save_linkedin_urn = linkedin_urn or f"urn:li:share:failed_placeholder_{os.urandom(4).hex()}"
            
            cursor.execute("UPDATE drafts SET status = 'published', updated_at = datetime('now') WHERE id = ?", (draft_id,))
            cursor.execute("UPDATE content_queue SET status = 'published', updated_at = datetime('now') WHERE id = ?", (queue_id,))
            cursor.execute(
                "INSERT INTO published_posts (draft_id, linkedin_post_urn, twitter_tweet_id) VALUES (?, ?, ?)",
                (draft_id, save_linkedin_urn, twitter_id)
            )
            conn.commit()
            
            # Check and alert for partial failures
            if not linkedin_urn:
                logger.warning(f"Draft ID {draft_id} published to Twitter but failed on LinkedIn: {linkedin_error_msg}")
                alert_router(f"Draft {draft_id} published to Twitter but failed on LinkedIn: {linkedin_error_msg}")
            elif not twitter_id:
                logger.warning(f"Draft ID {draft_id} published to LinkedIn but failed on Twitter: {twitter_error_msg}")
                alert_router(f"Draft {draft_id} published to LinkedIn but failed on Twitter: {twitter_error_msg}")
            else:
                logger.info(f"Draft ID {draft_id} successfully published to both LinkedIn and Twitter.")

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
