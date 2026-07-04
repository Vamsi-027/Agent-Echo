import os
import json
import logging
import time
import requests
import asyncio
import threading
from typing import List

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from notification.router import NotificationChannel
from db.db import get_db_connection
from generator.draft_generator import approve_draft, edit_draft

logger = logging.getLogger("linkedin-agent.notification.telegram")

from notification.state import pending_edits, pending_reschedules, weekly_review_state
# Thread callback locks for 5s debounce
callback_locks = {}


def escape_markdown(text: str) -> str:
    """Escapes markdown characters for Telegram Markdown V1."""
    if not text:
        return ""
    # Characters to escape: _, *, [, `
    for char in ["_", "*", "[", "`"]:
        text = text.replace(char, f"\\{char}")
    return text


async def edit_draft_status_message(
    bot: Bot, chat_id: int, message_id: int, is_caption: bool, text: str
):
    """
    Update a sent draft message in place. Video/photo drafts (sendVideo/sendPhoto)
    only carry a caption, not text — editMessageText fails on them with
    "There is no text in the message to edit", so route by message kind.
    """
    if is_caption:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, parse_mode="Markdown"
        )
    else:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown"
        )


def get_draft_message(draft_id: int) -> str:
    """Helper to fetch draft details and format it safely as markdown."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT pillar, format_type, text_content, hashtags, scheduled_time FROM drafts WHERE id=?",
        (draft_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return ""
    escaped_pillar = escape_markdown(row["pillar"])
    escaped_format = escape_markdown(row["format_type"])
    escaped_text = escape_markdown(row["text_content"])
    escaped_hashtags = escape_markdown(row["hashtags"] or "")

    msg = (
        f"📝 *New Draft Generated* (ID: {draft_id})\n"
        f"Pillar: {escaped_pillar}\n"
        f"Format: {escaped_format}\n"
    )

    if row["scheduled_time"]:
        try:
            import datetime
            from config_loader import LOCAL_TZ

            dt_utc = datetime.datetime.fromisoformat(row["scheduled_time"])
            dt_local = dt_utc.astimezone(LOCAL_TZ)
            formatted_time = dt_local.strftime("%Y-%m-%d %I:%M %p %Z")
            msg += f"Schedule Time: {escape_markdown(formatted_time)}\n"
        except Exception as te:
            logger.warning(f"Error parsing scheduled_time: {te}")

    msg += f"----------------------------------------\n" f"{escaped_text}"
    if escaped_hashtags:
        msg += f"\n\n{escaped_hashtags}"
    return msg


def get_allowed_users() -> List[int]:
    """Retrieves allowed user IDs from environment variables."""
    raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    allowed = []
    for uid in raw_ids.split(","):
        uid = uid.strip()
        if uid and uid.isdigit():
            allowed.append(int(uid))
    return allowed


def is_user_allowed(user_id: int) -> bool:
    allowed = get_allowed_users()
    if not allowed:
        return False
    return user_id in allowed


def _build_inline_keyboard(actions: list[str] | None) -> dict | None:
    """Builds a Telegram inline keyboard markup dict from action strings."""
    if not actions:
        return None
    row1 = []
    row2 = []
    for act in actions:
        if act.startswith("approve_"):
            draft_id = act.split("_")[1]
            row1.append({"text": "✅ Approve", "callback_data": act})
            row1.append(
                {"text": "📅 Reschedule", "callback_data": f"reschedule_{draft_id}"}
            )
        elif act.startswith("edit_"):
            row2.append({"text": "✏️ Edit", "callback_data": act})
        elif act.startswith("skip_"):
            row2.append({"text": "❌ Skip", "callback_data": act})

    inline_keyboard = [row for row in (row1, row2) if row]
    return {"inline_keyboard": inline_keyboard} if inline_keyboard else None


class TelegramChannel(NotificationChannel):
    """
    Synchronous notification delivery channel utilizing Telegram's HTTP API.
    Used by the NotificationRouter to dispatch reviews and health checks.
    """

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.bot_token != "placeholder_bot_token")

    def send(self, message: str, actions: list[str] | None = None) -> bool:
        if not self.is_configured():
            logger.debug("Telegram bot token not configured or set to placeholder.")
            return False

        allowed_users = get_allowed_users()
        if not allowed_users:
            logger.warning(
                "No allowed Telegram user IDs configured in TELEGRAM_ALLOWED_USER_IDS."
            )
            return False

        success = False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        reply_markup = _build_inline_keyboard(actions)

        for chat_id in allowed_users:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    success = True
                else:
                    logger.warning(
                        f"Telegram returned error code {resp.status_code}: {resp.text}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to post notification to Telegram chat {chat_id}: {e}"
                )

        return success

    def send_video(
        self, video_path: str, caption: str, actions: list[str] | None = None
    ) -> bool:
        """Sends a video file with a caption and optional inline keyboard via sendVideo."""
        if not self.is_configured():
            logger.debug("Telegram bot token not configured or set to placeholder.")
            return False

        allowed_users = get_allowed_users()
        if not allowed_users:
            logger.warning(
                "No allowed Telegram user IDs configured in TELEGRAM_ALLOWED_USER_IDS."
            )
            return False

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        # Telegram caption hard limit is 1024 chars. If the caption is longer,
        # send a short caption with the video, then the full draft text as a
        # follow-up text message carrying the review buttons.
        video_caption = caption
        followup_text = None
        if len(caption) > 1024:
            video_caption = caption[:1000] + "…"
            followup_text = caption

        reply_markup = _build_inline_keyboard(actions)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendVideo"

        success = False
        for chat_id in allowed_users:
            try:
                with open(video_path, "rb") as vf:
                    data = {
                        "chat_id": str(chat_id),
                        "caption": video_caption,
                        "parse_mode": "Markdown",
                        "supports_streaming": "true",
                    }
                    if reply_markup and not followup_text:
                        data["reply_markup"] = json.dumps(reply_markup)
                    resp = requests.post(
                        url, data=data, files={"video": vf}, timeout=120
                    )
                if resp.status_code == 200:
                    success = True
                else:
                    logger.warning(
                        f"Telegram sendVideo returned error code {resp.status_code}: {resp.text}"
                    )
            except Exception as e:
                logger.error(f"Failed to send video to Telegram chat {chat_id}: {e}")

        if followup_text:
            self.send(followup_text, actions)

        return success


# ==================== Bot Event Handlers ====================


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
        await update.message.reply_text(
            "Unauthorized. Your user ID is not whitelisted."
        )
        return

    await update.message.reply_text(
        "👋 Welcome to LinkedIn Content Agent Bot!\n\n"
        "Available commands:\n"
        "/health_check - View system health check\n"
        "/weekly_review - Start logging metrics for recent posts"
    )


async def health_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return

    await update.message.reply_text("Running health check...")

    # Run health check inside a thread pool to avoid blocking async loop
    from observability.health_check import run_health_check

    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, run_health_check)

    await update.message.reply_text(report)


async def weekly_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return

    chat_id = update.effective_chat.id
    await start_telegram_weekly_review(chat_id, update)


async def start_telegram_weekly_review(chat_id: int, update: Update):
    """Fetches missing posts and starts the metric prompt state machine."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find published posts missing performance logs
    cursor.execute(
        "SELECT p.linkedin_post_urn, p.published_at, d.text_content, d.pillar, d.format_type "
        "FROM published_posts p "
        "JOIN drafts d ON p.draft_id = d.id "
        "LEFT JOIN performance_log pl ON p.linkedin_post_urn = pl.linkedin_post_urn "
        "WHERE pl.id IS NULL "
        "ORDER BY p.published_at ASC"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        await update.message.reply_text(
            "✅ All published posts already have performance metrics recorded."
        )
        return

    weekly_review_state[chat_id] = {"posts": rows, "current_index": 0}

    await update.message.reply_text(
        f"📊 Found {len(rows)} published post(s) missing performance logs. Let's log them now:"
    )
    await prompt_next_weekly_post(chat_id, update)


async def prompt_next_weekly_post(chat_id: int, update: Update):
    state = weekly_review_state.get(chat_id)
    if not state:
        return

    idx = state["current_index"]
    post = state["posts"][idx]

    snippet = (
        post["text_content"][:100] + "..."
        if len(post["text_content"]) > 100
        else post["text_content"]
    )
    prompt_msg = (
        f"📝 *Post {idx + 1}/{len(state['posts'])}*\n"
        f"URN: `{post['linkedin_post_urn']}`\n"
        f"Pillar: {post['pillar']} | Format: {post['format_type']}\n"
        f"Snippet: *\"{snippet}\"*\n\n"
        "Reply with metrics in format: `impressions, reactions, comments, reposts` (e.g. `1200, 30, 4, 1`)."
    )

    if update.message:
        await update.message.reply_text(prompt_msg, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            prompt_msg, parse_mode="Markdown"
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_user_allowed(user_id):
        await query.answer("Unauthorized.")
        return

    data = query.data

    # 5-second debounce check
    now = time.time()
    lock_key = f"{user_id}_{data}"
    if now - callback_locks.get(lock_key, 0.0) < 5.0:
        await query.answer("Duplicate action ignored.", show_alert=False)
        return
    callback_locks[lock_key] = now

    if data.startswith("approve_"):
        draft_id = int(data.split("_")[1])
        await query.answer("Scheduling draft...")

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, approve_draft, draft_id)
            base_msg = await loop.run_in_executor(None, get_draft_message, draft_id)
            if not base_msg:
                base_msg = escape_markdown(query.message.caption or query.message.text)
            await edit_draft_status_message(
                context.bot,
                query.message.chat_id,
                query.message.message_id,
                query.message.caption is not None,
                base_msg + "\n\n🟢 *Approved & Scheduled*",
            )
        except Exception as e:
            logger.error(f"Failed to approve draft {draft_id}: {e}")
            await query.message.reply_text(f"❌ Error approving draft: {e}")

    elif data.startswith("skip_"):
        draft_id = int(data.split("_")[1])
        await query.answer("Skipping draft...")

        def skip():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE drafts SET status='rejected', updated_at=datetime('now') WHERE id=?",
                (draft_id,),
            )
            # A draft can already have a queued content_queue row from a prior
            # approve/reschedule. Without this, the publisher tick only checks
            # content_queue.status — it never re-checks drafts.status — so a
            # rejected draft already in the queue would still get published.
            cursor.execute(
                "UPDATE content_queue SET status='rolled', updated_at=datetime('now') "
                "WHERE draft_id=? AND status='queued'",
                (draft_id,),
            )
            conn.commit()
            conn.close()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, skip)

        base_msg = await loop.run_in_executor(None, get_draft_message, draft_id)
        if not base_msg:
            base_msg = escape_markdown(query.message.caption or query.message.text)
        await edit_draft_status_message(
            context.bot,
            query.message.chat_id,
            query.message.message_id,
            query.message.caption is not None,
            base_msg + "\n\n🔴 *Skipped / Rejected*",
        )

    elif data.startswith("edit_"):
        draft_id = int(data.split("_")[1])
        await query.answer()

        pending_edits[chat_id] = draft_id
        await query.message.reply_text(
            f"✏️ Please reply to this message with your edit instructions for Draft {draft_id}:"
        )

    elif data.startswith("reschedule_"):
        draft_id = int(data.split("_")[1])
        await query.answer()

        pending_reschedules[chat_id] = {
            "draft_id": draft_id,
            "message_id": query.message.message_id,
            "is_caption": query.message.caption is not None,
        }
        await query.message.reply_text(
            f"📅 Please reply with the new scheduled date/time for Draft {draft_id} in local timezone "
            f"format `YYYY-MM-DD HH:MM` (e.g. `2026-06-16 14:30`):"
        )


async def handle_user_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not is_user_allowed(user_id):
        return

    text = update.message.text.strip()

    # 1. Handle edit instructions
    if chat_id in pending_edits:
        draft_id = pending_edits.pop(chat_id)
        await update.message.reply_text("🔄 Generating revised draft via Claude...")

        loop = asyncio.get_running_loop()
        try:
            new_draft = await loop.run_in_executor(None, edit_draft, draft_id, text)

            # Send revised draft back
            escaped_pillar = escape_markdown(new_draft["pillar"])
            escaped_format = escape_markdown(new_draft["format_type"])
            escaped_text = escape_markdown(new_draft["text_content"])
            escaped_hashtags = escape_markdown(new_draft.get("hashtags") or "")
            msg = (
                f"📝 *New Draft Variant Generated* (ID: {new_draft['id']})\n"
                f"Pillar: {escaped_pillar}\n"
                f"Format: {escaped_format}\n"
                f"----------------------------------------\n"
                f"{escaped_text}"
            )
            if escaped_hashtags:
                msg += f"\n\n{escaped_hashtags}"

            from notification.telegram_bot import send_draft_for_review_chat
            await send_draft_for_review_chat(context.bot, chat_id, dict(new_draft))
        except Exception as e:
            logger.error(f"Edit generation failed: {e}")
            await update.message.reply_text(f"❌ Failed to edit draft: {e}")

    # 2. Handle reschedule instructions
    elif chat_id in pending_reschedules:
        state = pending_reschedules.pop(chat_id)
        draft_id = state["draft_id"]
        msg_id = state["message_id"]
        is_caption = state.get("is_caption", False)

        await update.message.reply_text("🔄 Rescheduling draft...")

        loop = asyncio.get_running_loop()
        try:
            import datetime
            from config_loader import LOCAL_TZ

            parsed_dt = None
            formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M:%S"]
            for fmt in formats:
                try:
                    parsed_dt = datetime.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

            if not parsed_dt:
                from notification.telegram_bot import parse_relative_datetime_with_llm
                utc_str = await parse_relative_datetime_with_llm(text)
                if not utc_str:
                    raise ValueError(
                        "Format must be YYYY-MM-DD HH:MM (e.g. 2026-06-16 14:30) or natural text (e.g. tomorrow 3pm)"
                    )
            else:
                local_dt = parsed_dt.replace(tzinfo=LOCAL_TZ)
                utc_dt = local_dt.astimezone(datetime.timezone.utc)
                utc_str = utc_dt.isoformat()

            def db_reschedule():
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE drafts SET status = 'approved', scheduled_time = ?, updated_at = datetime('now') WHERE id = ?",
                    (utc_str, draft_id),
                )
                cursor.execute(
                    "SELECT id FROM content_queue WHERE draft_id = ?", (draft_id,)
                )
                queue_row = cursor.fetchone()
                if queue_row:
                    cursor.execute(
                        "UPDATE content_queue SET scheduled_time = ?, status = 'queued', updated_at = datetime('now') WHERE id = ?",
                        (utc_str, queue_row["id"]),
                    )
                else:
                    import random

                    priority = round(random.uniform(0.5, 1.0), 2)
                    cursor.execute(
                        "INSERT INTO content_queue (draft_id, priority_score, scheduled_time, status) "
                        "VALUES (?, ?, ?, 'queued')",
                        (draft_id, priority, utc_str),
                    )
                conn.commit()
                conn.close()

            await loop.run_in_executor(None, db_reschedule)

            base_msg = await loop.run_in_executor(None, get_draft_message, draft_id)
            if not base_msg:
                base_msg = escape_markdown(update.message.text)

            await edit_draft_status_message(
                context.bot,
                chat_id,
                msg_id,
                is_caption,
                base_msg + "\n\n🟢 *Approved & Rescheduled*",
            )
            await update.message.reply_text("✅ Post rescheduled successfully!")
        except Exception as e:
            logger.error(f"Reschedule failed: {e}")
            await update.message.reply_text(f"❌ Failed to reschedule draft: {e}")

    # 3. Handle weekly performance review stats
    elif chat_id in weekly_review_state:
        state = weekly_review_state[chat_id]
        idx = state["current_index"]
        post = state["posts"][idx]

        # Parse: impressions, reactions, comments, reposts
        parts = text.split(",")
        if len(parts) != 4:
            await update.message.reply_text(
                "⚠️ Invalid format. Please reply in format: `impressions, reactions, comments, reposts` (e.g. `2000, 40, 5, 2`)."
            )
            return

        try:
            metrics = [int(p.strip()) for p in parts]
        except ValueError:
            await update.message.reply_text(
                "⚠️ Metrics must be integers. Try again in format: `impressions, reactions, comments, reposts`."
            )
            return

        # Log to DB
        def save_metrics():
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, ?)",
                (
                    post["linkedin_post_urn"],
                    metrics[0],
                    metrics[1],
                    metrics[2],
                    metrics[3],
                ),
            )
            conn.commit()
            conn.close()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, save_metrics)

        # Proceed to next post
        state["current_index"] += 1

        if state["current_index"] < len(state["posts"]):
            await prompt_next_weekly_post(chat_id, update)
        else:
            # Complete! Run Claude Analysis
            weekly_review_state.pop(chat_id)
            await update.message.reply_text(
                "🔄 All stats recorded. Initiating Claude optimization report..."
            )

            from feedback.weekly_review import analyze_performance_and_reweight

            # We want to redirect analyze_performance_and_reweight console prints, or mock/intercept it
            # To capture its Claude output, let's write a small helper to run Claude analysis and return the report
            # Or run it and query DB. Actually we can invoke it and direct output.
            # Let's write a helper or import it.
            # We can capture sys.stdout or run it directly. Let's do a redirect of stdout or run a custom logic.
            # Wait, let's intercept analyze_performance_and_reweight output:
            import io
            import sys

            f = io.StringIO()
            with redirect_stdout(f):
                await loop.run_in_executor(None, analyze_performance_and_reweight)
            out = f.getvalue()

            await update.message.reply_text(
                "📊 *Claude Performance & Reweighting Report*\n\n" + out
            )
            await update.message.reply_text("🎉 Weekly review complete!")


from contextlib import contextmanager


@contextmanager
def redirect_stdout(new_target):
    import sys

    old_target = sys.stdout
    sys.stdout = new_target
    try:
        yield new_target
    finally:
        sys.stdout = old_target


# ==================== Application Initialization ====================


def run_telegram_bot_daemon():
    """Initializes and runs the Telegram bot event listener in polling mode."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "placeholder_bot_token":
        logger.warning(
            "TELEGRAM_BOT_TOKEN is placeholder or not set. Bot listener will not be started."
        )
        return None

    application = ApplicationBuilder().token(token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health_check", health_check_command))
    application.add_handler(CommandHandler("weekly_review", weekly_review_command))

    # Register query callbacks
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Register message handler for text replies
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text_message)
    )

    logger.info("Initializing Telegram bot listener polling...")

    # Run polling. stop_signals=None is required to run in background thread.
    t = threading.Thread(
        target=application.run_polling,
        kwargs={"stop_signals": None, "close_loop": False},
        daemon=True,
    )
    t.start()
    return t


def run_telegram_bot_foreground():
    """Initializes and runs the Telegram bot event listener in blocking foreground mode."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "placeholder_bot_token":
        logger.warning("TELEGRAM_BOT_TOKEN is placeholder or not set.")
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env.")

    application = ApplicationBuilder().token(token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health_check", health_check_command))
    application.add_handler(CommandHandler("weekly_review", weekly_review_command))

    # Register query callbacks
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Register message handler for text replies
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text_message)
    )

    logger.info("Starting Telegram bot listener in foreground...")
    print("Telegram bot starting... Press Ctrl+C to stop.")
    application.run_polling()
