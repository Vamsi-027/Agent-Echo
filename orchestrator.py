import os
import logging
import datetime
from dotenv import load_dotenv

# Load env variables first
load_dotenv()

from config_loader import LOCAL_TZ
from capture.browser_watcher import capture_active_browser_tab
from capture.github_watcher import fetch_and_store_github_events
from capture.notion_watcher import fetch_and_store_notion_pages
from generator.draft_generator import generate_drafts_for_date
from publisher.scheduler import run_publisher_tick
from notification.router import alert_router
from observability.health_check import run_health_check
from observability.tracer import trace_pipeline_run

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("linkedin-agent.orchestrator")

def run_capture_watchers():
    with trace_pipeline_run("capture_watchers"):
        logger.info("Executing periodic capture watchers...")
        errors = []
        
        # Brave Browser tab capture
        try:
            capture_active_browser_tab()
        except Exception as e:
            logger.error(f"Error running Brave Browser watcher: {e}", exc_info=True)
            errors.append(f"Browser: {e}")
            
        # GitHub events sync
        try:
            fetch_and_store_github_events()
        except Exception as e:
            logger.error(f"Error running GitHub events watcher: {e}", exc_info=True)
            errors.append(f"GitHub: {e}")
            
        # Notion pages sync
        try:
            fetch_and_store_notion_pages()
        except Exception as e:
            logger.error(f"Error running Notion pages watcher: {e}", exc_info=True)
            errors.append(f"Notion: {e}")
            
        if errors:
            raise RuntimeError(f"Watchers failed: {'; '.join(errors)}")

def run_daily_pipeline():
    with trace_pipeline_run("generation_pipeline"):
        today_str = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        logger.info(f"Triggering daily generation pipeline for date: {today_str}")
        try:
            drafts = generate_drafts_for_date(today_str)
            logger.info(f"Daily generation pipeline finished. Generated {len(drafts)} draft(s).")
            if drafts:
                from notification.router import get_default_router
                router = get_default_router()
                from notification.telegram_channel import escape_markdown
                for draft in drafts:
                    escaped_pillar = escape_markdown(draft['pillar'])
                    escaped_format = escape_markdown(draft['format_type'])
                    escaped_text = escape_markdown(draft['text_content'])
                    escaped_hashtags = escape_markdown(draft.get("hashtags") or "")
                    msg = (
                        f"📝 *New Draft Generated* (ID: {draft['id']})\n"
                        f"Pillar: {escaped_pillar}\n"
                        f"Format: {escaped_format}\n"
                        f"----------------------------------------\n"
                        f"{escaped_text}"
                    )
                    if escaped_hashtags:
                        msg += f"\n\n{escaped_hashtags}"
                    
                    actions = [f"approve_{draft['id']}", f"edit_{draft['id']}", f"skip_{draft['id']}"]
                    router.send(msg, actions)
        except Exception as e:
            logger.error(f"Error during daily generation pipeline: {e}", exc_info=True)
            raise e

def run_publisher_job():
    with trace_pipeline_run("publishing_tick"):
        logger.info("Executing publisher queue check tick...")
        try:
            run_publisher_tick()
        except Exception as e:
            logger.error(f"Error during publisher tick: {e}", exc_info=True)
            raise e

def run_daily_health_check():
    with trace_pipeline_run("health_check"):
        logger.info("Executing daily health check...")
        try:
            report = run_health_check()
            alert_router(report)
            logger.info("Daily health check completed and report dispatched.")
        except Exception as e:
            logger.error(f"Error during health check: {e}", exc_info=True)
            raise e

def main():
    logger.info(f"Starting orchestration daemon (Timezone: {LOCAL_TZ})...")
    
    # Start Telegram Bot daemon if configured
    try:
        from notification.telegram_channel import run_telegram_bot_daemon
        run_telegram_bot_daemon()
    except Exception as e:
        logger.error(f"Failed to start Telegram bot daemon: {e}", exc_info=True)
        
    observer = None
    try:
        from capture.file_watcher import start_file_watcher
        observer = start_file_watcher()
    except Exception as e:
        logger.error(f"Failed to start file watcher: {e}", exc_info=True)
        
    scheduler = BlockingScheduler(timezone=LOCAL_TZ)
    
    # 1. Periodically check watchers every 30 minutes during waking hours (8:00 AM - 11:00 PM)
    scheduler.add_job(
        run_capture_watchers,
        CronTrigger(hour="8-23", minute="0,30", timezone=LOCAL_TZ),
        id="activity_watchers"
    )
    
    # 2. Run the Daily Aggregation & Generation pipeline at 21:00 local time
    scheduler.add_job(
        run_daily_pipeline,
        CronTrigger(hour=21, minute=0, timezone=LOCAL_TZ),
        id="daily_pipeline"
    )
    
    # 3. Periodically run the publisher tick every 15 minutes
    scheduler.add_job(
        run_publisher_job,
        IntervalTrigger(minutes=15, timezone=LOCAL_TZ),
        id="publisher_tick"
    )
    
    # 4. Run the daily health check at 08:00 local time
    scheduler.add_job(
        run_daily_health_check,
        CronTrigger(hour=8, minute=0, timezone=LOCAL_TZ),
        id="health_check"
    )
    
    logger.info("Scheduler jobs registered:")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        logger.info(f" - Job '{job.id}': {next_run} (Trigger: {job.trigger})")
        
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Orchestration daemon stopped cleanly.")
    finally:
        if observer:
            logger.info("Stopping file watcher...")
            try:
                observer.stop()
                observer.join()
            except Exception as e:
                logger.error(f"Error stopping file watcher: {e}")

if __name__ == "__main__":
    main()
