# notification/telegram_bot.py
import os
import json
import logging
import asyncio
import datetime
from anthropic import Anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters, ContextTypes
)
import threading
from db.db import get_db_connection
from generator.draft_generator import approve_draft, edit_draft, generate_topic_draft, generate_drafts_for_date
from db.vector_db import search_persona
from config_loader import get_voice_profile, LOCAL_TZ
from notification.state import pending_edits, pending_reschedules, weekly_review_state
from notification.telegram_channel import (
    escape_markdown, get_allowed_users, is_user_allowed,
    start_command, health_check_command, weekly_review_command,
    handle_callback_query, handle_user_text_message
)

logger = logging.getLogger("linkedin-agent.notification.telegram_bot")

ALLOWED_USER_IDS = get_allowed_users()

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "draft_from_activity",
                "draft_from_topic",
                "queue_status",
                "analytics_summary",
                "trigger_pipeline",
                "system_question",
                "approve",
                "skip",
                "edit",
                "reschedule",
                "unknown",
            ],
        },
        "topic": {"type": "string"},
        "format_type": {
            "type": "string",
            "enum": ["text", "image", "video", "poll"]
        },
        "poll_question": {"type": "string"},
        "poll_options": {
            "type": "array",
            "items": {"type": "string"}
        },
        "draft_id": {"type": "integer"},
        "edit_instruction": {"type": "string"},
        "question": {"type": "string"},
        "reschedule_time": {"type": "string"}
    },
    "required": ["intent"],
    "additionalProperties": False,
}

INTENT_SYSTEM = """
You are parsing messages sent to an autonomous LinkedIn content agent called Echo.
Classify the user's intent into one of the defined categories.

Rules:
- "make a post", "generate", "draft", "create something", "generate a draft" → draft_from_activity
- "post about X", "write about Y", "topic: Z", "create a post on X" → draft_from_topic, extract topic.
  Also extract format_type if the user specifies a format (e.g. "with video", "make a video post", "poll post about X", "image post about Y").
  If format is "poll", extract poll_question and poll_options if mentioned.
- "what's scheduled", "queue", "next post", "show queue" → queue_status
- "analytics", "performance", "how are posts doing", "show metrics" → analytics_summary
- "run the pipeline", "force digest", "trigger pipeline" → trigger_pipeline
- "how does X work", "what did you capture", "explain Y" → system_question
- "approve draft X", "approve X", "yes post X" → approve with draft_id
- "skip draft X", "reject X", "skip" → skip with draft_id
- "edit draft X", "change X", "make X more punchy" → edit with instruction and draft_id (if mentioned)
- "reschedule draft X to tomorrow 3pm", "schedule draft X for monday noon", "reschedule X for tomorrow" → reschedule with draft_id and reschedule_time string.
"""

def fallback_intent_parse(text: str) -> dict | None:
    text_lower = text.lower().strip()
    import re
    
    # 1. Action commands with IDs (e.g. "reschedule draft 71 for tomorrow")
    resched_match = re.search(
        r"\b(?:reschedule|schedule)\s*(?:draft)?\s*(\d+)\s*(?:for|to|on|at)?\s*(.+)",
        text_lower
    )
    if resched_match:
        return {
            "intent": "reschedule",
            "draft_id": int(resched_match.group(1)),
            "reschedule_time": resched_match.group(2).strip()
        }

    approve_match = re.search(r"\b(?:approve|post|queue|publish)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if approve_match:
        return {"intent": "approve", "draft_id": int(approve_match.group(1))}

    skip_match = re.search(r"\b(?:skip|reject|delete|discard)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if skip_match:
        return {"intent": "skip", "draft_id": int(skip_match.group(1))}

    edit_match = re.search(r"\b(?:edit|change|modify)\s*(?:draft)?\s*(\d+)\b", text_lower)
    if edit_match:
        instruction = ""
        instruction_match = re.search(r"\b(?:edit|change|modify)\s*(?:draft)?\s*\d+\s*(?:to|and)?\s*(.+)", text, re.IGNORECASE)
        if instruction_match:
            instruction = instruction_match.group(1).strip()
        return {"intent": "edit", "draft_id": int(edit_match.group(1)), "edit_instruction": instruction}

    # 2. Simple action commands without IDs
    if text_lower in ("approve", "yes", "confirm"):
        return {"intent": "approve"}
    if text_lower in ("skip", "reject", "no"):
        return {"intent": "skip"}
    if text_lower.startswith("edit ") or text_lower.startswith("change ") or text_lower.startswith("make it "):
        return {"intent": "edit", "edit_instruction": text}
        
    # 3. Specific drafts on topic / visual
    topic_patterns = [
        r"(?:write|post|draft|make a post|create a post|create a draft)\s+(?:about|on|with video of|with a video of|with a visual of|with visual of)\s+(.+)",
        r"topic:\s*(.+)"
    ]
    for pattern in topic_patterns:
        match = re.search(pattern, text_lower)
        if match:
            orig_match = re.search(pattern, text, re.IGNORECASE)
            if orig_match:
                topic = orig_match.group(1).strip()
                topic_lower = topic.lower()
                # Parse format indicators in the topic text
                fmt = "text"
                if "video" in topic_lower or "remotion" in topic_lower or "animation" in topic_lower:
                    fmt = "video"
                elif "image" in topic_lower or "graphic" in topic_lower or "chart" in topic_lower or "visual" in topic_lower:
                    fmt = "image"
                elif "poll" in topic_lower or "survey" in topic_lower:
                    fmt = "poll"
                return {"intent": "draft_from_topic", "topic": topic, "format_type": fmt}
            
    # 4. Draft from activity
    if any(k in text_lower for k in ("make a post", "generate post", "create post", "draft post", "generate draft", "make draft")):
        return {"intent": "draft_from_activity"}
        
    # 5. Queue/scheduled status
    if any(k in text_lower for k in ("queue", "scheduled", "show queue", "next post")):
        return {"intent": "queue_status"}
        
    # 6. Analytics
    if any(k in text_lower for k in ("analytics", "metrics", "performance", "how are posts doing", "how are my posts doing", "posts doing", "post doing")):
        return {"intent": "analytics_summary"}
        
    # 7. Trigger pipeline
    if any(k in text_lower for k in ("run pipeline", "trigger pipeline", "run the pipeline")):
        return {"intent": "trigger_pipeline"}

    # 8. System questions fallback
    if any(k in text_lower for k in ("how does", "what is", "how do i", "explain")):
        return {"intent": "system_question", "question": text}

    return None

async def call_structured_intent(text: str) -> dict:
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        output_config={"format": {"type": "json_schema", "schema": INTENT_SCHEMA}},
        system=INTENT_SYSTEM,
        messages=[{"role": "user", "content": f"Message: {text}"}]
    )
    return json.loads(response.content[0].text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return

    text = update.message.text or ""

    # 1. Stateful routing priority check
    if chat_id in pending_edits or chat_id in pending_reschedules or chat_id in weekly_review_state:
        logger.info(f"Stateful flow active for chat {chat_id}, routing message directly.")
        await handle_user_text_message(update, context)
        return

    # 2. Intent parsing (first local regex fallback, then LLM)
    parsed = fallback_intent_parse(text)
    if not parsed:
        try:
            parsed = await call_structured_intent(text)
        except Exception as e:
            logger.error(f"Failed to parse intent with Claude: {e}")
            parsed = {"intent": "unknown"}

    intent = parsed.get("intent", "unknown")
    logger.info(f"Routed intent: {intent}")

    await update.message.chat.send_action("typing")

    if intent == "draft_from_activity":
        await handle_draft_from_activity(update, context)
    elif intent == "draft_from_topic":
        await handle_draft_from_topic(
            update,
            context,
            parsed.get("topic", text),
            parsed.get("format_type", "text"),
            parsed
        )
    elif intent == "queue_status":
        await handle_queue_status(update, context)
    elif intent == "analytics_summary":
        await handle_analytics_summary(update, context)
    elif intent == "trigger_pipeline":
        await handle_trigger_pipeline(update, context)
    elif intent == "system_question":
        await handle_system_question(update, context, parsed.get("question", text))
    elif intent in ("approve", "skip", "edit"):
        await handle_draft_action(update, context, parsed)
    elif intent == "reschedule":
        await handle_reschedule_intent(update, context, parsed)
    else:
        await update.message.reply_text(
            "I didn't understand that. Try:\n"
            "• \"make a post\" — draft from today's activity\n"
            "• \"write about [topic]\" — draft on a specific topic\n"
            "• \"create an image post about X\" — graphic card post\n"
            "• \"create a poll post on Y\" — interactive poll\n"
            "• \"schedule draft X for tomorrow 3pm\" — reschedule a post\n"
            "• \"what's scheduled\" — see the queue\n"
            "• \"how are my posts doing\" — analytics"
        )

# Implementation of specific handlers using run_in_executor
async def handle_draft_from_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from aggregator.daily_digest import run_daily_digest
    from datetime import date
    loop = asyncio.get_running_loop()

    today = date.today().isoformat()
    conn = get_db_connection()
    digest = conn.execute(
        "SELECT * FROM daily_digests WHERE date = ? ORDER BY version DESC LIMIT 1",
        (today,)
    ).fetchone()

    if not digest:
        await update.message.reply_text("No digest for today yet — compiling activity...")
        digest = await loop.run_in_executor(None, run_daily_digest, today)

    if not digest:
        await update.message.reply_text("No activity captured today yet. Ensure watchers are running.")
        conn.close()
        return

    await update.message.reply_text("Generating drafts from today's activity...")
    drafts = await loop.run_in_executor(None, generate_drafts_for_date, today)
    
    conn.close()
    if not drafts:
        await update.message.reply_text("No drafts generated.")
        return

    for draft in drafts:
        await send_draft_for_review(update, context, dict(draft))

async def run_video_generation_bg(bot, chat_id, draft_id, topic, draft_text):
    from generator.media_handler import generate_remotion_video
    import json
    import os
    
    mock_digest = {
        "summary": topic,
        "raw_summary": topic,
        "highlights_json": json.dumps([topic]),
        "categories_json": "{}"
    }
    date_str = datetime.date.today().isoformat()
    output_dir = "data/media"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/topic_{draft_id}_animation.mp4"
    
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None,
        generate_remotion_video,
        f"topic_{draft_id}",
        mock_digest,
        output_path,
        draft_text,
        draft_id
    )
    
    if success:
        conn = get_db_connection()
        draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        await bot.send_message(chat_id=chat_id, text=f"✨ Video generation for Draft {draft_id} completed!")
        await send_draft_for_review_chat(bot, chat_id, dict(draft))
    else:
        await bot.send_message(chat_id=chat_id, text=f"❌ Video generation for Draft {draft_id} failed. Reviewing text only:")
        conn = get_db_connection()
        conn.execute("UPDATE drafts SET format_type = 'text' WHERE id = ?", (draft_id,))
        conn.commit()
        draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        await send_draft_for_review_chat(bot, chat_id, dict(draft))

async def handle_draft_from_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, format_type: str = "text", parsed: dict = None):
    loop = asyncio.get_running_loop()

    # Check if a matching pending draft already exists (especially helpful for media/video drafts)
    def check_existing():
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT * FROM drafts WHERE status = 'pending_review' ORDER BY id DESC"
        ).fetchall()
        conn.close()
        
        import re
        topic_lower = topic.lower()
        keywords = [w for w in re.split(r'\W+', topic_lower) if len(w) >= 2]
        if not keywords:
            return None
            
        for row in rows:
            text = (row["text_content"] or "").lower()
            media = (row["media_refs_json"] or "").lower()
            pillar = (row["pillar"] or "").lower()
            fmt = (row["format_type"] or "").lower()
            
            if all(kw in text or kw in media or kw in pillar or kw in fmt for kw in keywords):
                return dict(row)
        return None

    existing_draft = await loop.run_in_executor(None, check_existing)
    if existing_draft:
        await update.message.reply_text(
            f"I found an existing pending draft matching \"{topic}\" (Draft {existing_draft['id']}):"
        )
        await send_draft_for_review(update, context, existing_draft)
        return

    await update.message.reply_text(f'Drafting a {format_type} post about "{topic}"...')

    conn = get_db_connection()
    try:
        recent_events = conn.execute(
            "SELECT source, title, detail FROM activity_events "
            "WHERE event_time > datetime('now', '-24 hours') "
            "ORDER BY event_time DESC LIMIT 20"
        ).fetchall()

        # Async search in vector DB
        results = await loop.run_in_executor(None, search_persona, topic, 6)
        persona_chunks = [r["text"] for r in results if r["category"] in ["experience", "opinions", "style"]]
        if not persona_chunks:
            persona_chunks = [r["text"] for r in results]

        recent_posts = conn.execute(
            "SELECT text_content FROM drafts WHERE status = 'published' "
            "ORDER BY created_at DESC LIMIT 7"
        ).fetchall()

        voice_profile_text, voice_profile_hash = get_voice_profile()

        draft_text, hashtags = await loop.run_in_executor(
            None,
            generate_topic_draft,
            topic,
            [dict(e) for e in recent_events],
            persona_chunks,
            [r["text_content"] for r in recent_posts],
            voice_profile_text,
        )

        media_refs_json = None

        if format_type == "poll":
            poll_question = topic[:140]
            poll_options = ["Yes", "No"]
            if parsed and parsed.get("poll_options"):
                poll_options = parsed["poll_options"]
            if parsed and parsed.get("poll_question"):
                poll_question = parsed["poll_question"]

            if not parsed or not parsed.get("poll_options"):
                def generate_poll_details():
                    client = Anthropic()
                    system_prompt = "Generate a relevant LinkedIn poll question (max 140 chars) and exactly 2 to 4 options (max 30 chars each) based on this post."
                    schema = {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}}
                        },
                        "required": ["question", "options"],
                        "additionalProperties": False
                    }
                    response = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=200,
                        output_config={"format": {"type": "json_schema", "schema": schema}},
                        system=system_prompt,
                        messages=[{"role": "user", "content": f"Post: {draft_text}"}]
                    )
                    return json.loads(response.content[0].text)

                try:
                    poll_data = await loop.run_in_executor(None, generate_poll_details)
                    poll_question = poll_data["question"][:140]
                    poll_options = poll_data["options"]
                except Exception as pe:
                    logger.error(f"Failed to generate poll options: {pe}")

            media_refs_json = json.dumps({
                "question": poll_question,
                "options": poll_options,
                "duration_days": 3
            })

        elif format_type == "image":
            from generator.conceptual_image_selector import extract_image_details
            from generator.media_handler import generate_topic_conceptual_image

            img_details = await loop.run_in_executor(None, extract_image_details, draft_text, topic)
            os.makedirs("data/media", exist_ok=True)
            temp_path = f"data/media/temp_topic_card.png"

            await loop.run_in_executor(
                None,
                generate_topic_conceptual_image,
                topic,
                img_details["title"],
                img_details["points"],
                temp_path
            )
            media_refs_json = json.dumps([temp_path])

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO drafts (pillar, format_type, text_content, hashtags, "
            "voice_profile_hash, status, media_refs_json) VALUES (?, ?, ?, ?, ?, 'pending_review', ?)",
            ("industry_commentary", format_type, draft_text, hashtags, voice_profile_hash, media_refs_json),
        )
        draft_id = cursor.lastrowid
        conn.commit()

        if format_type == "image" and media_refs_json:
            media_files = json.loads(media_refs_json)
            final_path = f"data/media/topic_{draft_id}_card.png"
            if os.path.exists(media_files[0]):
                os.rename(media_files[0], final_path)
            cursor.execute("UPDATE drafts SET media_refs_json = ? WHERE id = ?", (json.dumps([final_path]), draft_id))
            conn.commit()

        draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()

        if format_type == "video":
            await update.message.reply_text(f"Draft {draft_id} created. Generating the Remotion video animation in the background...")
            asyncio.create_task(run_video_generation_bg(context.bot, update.effective_chat.id, draft_id, topic, draft_text))
        else:
            await send_draft_for_review_chat(context.bot, update.effective_chat.id, dict(draft), context.user_data)

    except Exception as e:
        logger.error(f"Failed to generate draft on topic: {e}")
        await update.message.reply_text(f"❌ Failed to draft post on topic: {e}")
    finally:
        conn.close()

async def handle_queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    queued = conn.execute(
        "SELECT d.id, d.format_type, d.pillar, cq.scheduled_time "
        "FROM content_queue cq JOIN drafts d ON cq.draft_id = d.id "
        "WHERE cq.scheduled_time > datetime('now') "
        "ORDER BY cq.scheduled_time ASC LIMIT 5"
    ).fetchall()

    recent = conn.execute(
        "SELECT d.pillar, d.format_type, pp.published_at "
        "FROM published_posts pp JOIN drafts d ON pp.draft_id = d.id "
        "ORDER BY pp.published_at DESC LIMIT 3"
    ).fetchall()
    conn.close()

    lines = ["*Queue*"]
    if queued:
        for row in queued:
            lines.append(f"  • Draft {row['id']} ({row['format_type']}) — {row['scheduled_time']}")
    else:
        lines.append("  Nothing scheduled.")

    lines += ["\n*Recently published*"]
    for row in recent:
        lines.append(f"  • {row['pillar']} ({row['format_type']}) — {row['published_at'][:10]}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def handle_analytics_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT d.pillar, d.format_type, d.visual_composition, "
        "pl.impressions, pl.reactions, pl.comments "
        "FROM performance_log pl "
        "JOIN published_posts pp ON pl.linkedin_post_urn = pp.linkedin_post_urn "
        "JOIN drafts d ON pp.draft_id = d.id "
        "ORDER BY pl.recorded_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No performance data yet. Use weekly review to log metrics.")
        return

    def call_claude():
        client = Anthropic()
        data_str = json.dumps([dict(r) for r in rows], indent=2)
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"Summarize this LinkedIn performance data in 3-4 bullet points. Highlight what is working and one concrete recommendation. Be direct:\n\n{data_str}",
            }],
        ).content[0].text

    loop = asyncio.get_running_loop()
    summary = await loop.run_in_executor(None, call_claude)
    await update.message.reply_text(summary)

async def handle_trigger_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from aggregator.daily_digest import run_daily_digest
    from datetime import date
    loop = asyncio.get_running_loop()

    today = date.today().isoformat()
    await update.message.reply_text("Running daily pipeline...")

    try:
        await loop.run_in_executor(None, run_daily_digest, today)
        await update.message.reply_text("Digest complete. Generating drafts...")
        drafts = await loop.run_in_executor(None, generate_drafts_for_date, today)
        if drafts:
            for draft in drafts:
                await send_draft_for_review(update, context, dict(draft))
        else:
            await update.message.reply_text("No drafts generated.")
    except Exception as e:
        await update.message.reply_text(f"Pipeline failed: {e}")

async def handle_system_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str):
    conn = get_db_connection()
    stats = {
        "activity_events_today": conn.execute("SELECT COUNT(*) FROM activity_events WHERE event_time > datetime('now', 'start of day')").fetchone()[0],
        "pending_drafts": conn.execute("SELECT COUNT(*) FROM drafts WHERE status = 'pending_review'").fetchone()[0],
        "queued_posts": conn.execute("SELECT COUNT(*) FROM content_queue WHERE scheduled_time > datetime('now')").fetchone()[0],
        "published_total": conn.execute("SELECT COUNT(*) FROM published_posts").fetchone()[0],
    }
    conn.close()

    claude_md_path = os.path.join(os.path.dirname(__file__), "..", "CLAUDE.md")
    try:
        with open(claude_md_path) as f:
            claude_md = f.read()
    except FileNotFoundError:
        claude_md = "CLAUDE.md not found."

    def call_claude():
        client = Anthropic()
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=(
                "You are Agent Echo, an autonomous LinkedIn content agent. "
                "Answer the user's question about yourself using the provided context.\n\n"
                f"Documentation:\n{claude_md[:3000]}\n\n"
                f"Live stats:\n{json.dumps(stats, indent=2)}"
            ),
            messages=[{"role": "user", "content": question}],
        ).content[0].text

    loop = asyncio.get_running_loop()
    answer = await loop.run_in_executor(None, call_claude)
    await update.message.reply_text(answer)

def get_most_recent_pending_draft_id() -> int | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id FROM drafts WHERE status = 'pending_review' "
        "ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["id"] if row else None

async def handle_draft_action(update: Update, context: ContextTypes.DEFAULT_TYPE, parsed: dict):
    intent = parsed["intent"]
    draft_id = parsed.get("draft_id")

    if not draft_id:
        draft_id = context.user_data.get("last_draft_id")
    if not draft_id:
        draft_id = get_most_recent_pending_draft_id()

    if not draft_id:
        await update.message.reply_text("No pending draft found.")
        return

    if intent == "approve":
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, approve_draft, draft_id)
        await update.message.reply_text(f"Draft {draft_id} approved and queued. ✓")
    elif intent == "skip":
        def db_skip():
            conn = get_db_connection()
            conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
            conn.commit()
            conn.close()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, db_skip)
        await update.message.reply_text(f"Draft {draft_id} skipped.")
    elif intent == "edit":
        instruction = parsed.get("edit_instruction", "")
        if not instruction:
            await update.message.reply_text("What should I change? Tell me and I'll regenerate.")
            context.user_data["pending_edit_draft_id"] = draft_id
            pending_edits[update.effective_chat.id] = draft_id
            return
        await regenerate_with_instruction(update, context, draft_id, instruction)

async def parse_relative_datetime_with_llm(time_str: str) -> str | None:
    """Uses Claude to convert a relative time string to ISO 8601 UTC string."""
    from datetime import datetime, timezone
    import json
    from config_loader import LOCAL_TZ
    
    now_local = datetime.now(LOCAL_TZ)
    now_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    
    client = Anthropic()
    prompt = (
        f"Current local time is: {now_str}\n"
        f"Convert the user's date/time description to a standard format 'YYYY-MM-DD HH:MM:SS' in local timezone.\n"
        f"User time text: '{time_str}'\n\n"
        f"Return a JSON object only: {{\"datetime\": \"YYYY-MM-DD HH:MM:SS\"}}. "
        f"If the text is invalid or ambiguous, return {{\"datetime\": null}}."
    )
    try:
        loop = asyncio.get_running_loop()
        def call_claude():
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=100,
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object",
                    "properties": {"datetime": {"type": ["string", "null"]}},
                    "required": ["datetime"],
                    "additionalProperties": False
                }}},
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text
            
        res_text = await loop.run_in_executor(None, call_claude)
        res = json.loads(res_text)
        parsed = res.get("datetime")
        if parsed:
            dt_local = datetime.strptime(parsed, "%Y-%m-%d %H:%M:%S").replace(tzinfo=LOCAL_TZ)
            return dt_local.astimezone(timezone.utc).isoformat()
    except Exception as e:
        logger.error(f"Failed to parse relative time with LLM: {e}")
    return None

async def handle_reschedule_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, parsed: dict):
    draft_id = parsed.get("draft_id")
    res_time = parsed.get("reschedule_time", "").strip()
    
    if not draft_id:
        draft_id = context.user_data.get("last_draft_id")
    if not draft_id:
        draft_id = get_most_recent_pending_draft_id()
        
    if not draft_id:
        await update.message.reply_text("No draft found to reschedule.")
        return
        
    if not res_time:
        pending_reschedules[update.effective_chat.id] = {
            "draft_id": draft_id,
            "message_id": update.message.message_id,
            "is_caption": False
        }
        await update.message.reply_text(
            f"📅 Please reply with the new scheduled date/time for Draft {draft_id} in local timezone "
            f"format `YYYY-MM-DD HH:MM` (e.g. `2026-06-16 14:30`):"
        )
        return
        
    await update.message.reply_text("🔄 Rescheduling draft...")
    utc_str = await parse_relative_datetime_with_llm(res_time)
    if not utc_str:
        await update.message.reply_text(f"❌ Could not parse reschedule time '{res_time}'. Please use YYYY-MM-DD HH:MM.")
        return
        
    loop = asyncio.get_running_loop()
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
    await update.message.reply_text(f"✅ Draft {draft_id} successfully scheduled/rescheduled!")

async def regenerate_with_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: int, instruction: str):
    await update.message.reply_text("Regenerating revised draft...")
    loop = asyncio.get_running_loop()
    try:
        new_draft = await loop.run_in_executor(None, edit_draft, draft_id, instruction)
        await send_draft_for_review(update, context, dict(new_draft))
    except Exception as e:
        logger.error(f"Failed to edit draft: {e}")
        await update.message.reply_text(f"Edit failed: {e}")

async def send_draft_for_review_chat(bot, chat_id, draft: dict, user_data: dict = None):
    draft_id = draft["id"]
    text = draft.get("text_content", "")
    hashtags = draft.get("hashtags", "")
    pillar = draft.get("pillar", "")
    fmt = draft.get("format_type", "text")
    char_count = len(text)

    if user_data is not None:
        user_data["last_draft_id"] = draft_id

    caption = (
        f"📝 *Draft {draft_id}*\n"
        f"`{pillar}` · `{fmt}` · `{char_count} chars`\n"
        f"────────────────────────\n"
        f"{escape_markdown(text)}\n\n"
        f"`{escape_markdown(hashtags)}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Approve", callback_data=f"approve_{draft_id}"),
            InlineKeyboardButton("📅 Reschedule", callback_data=f"reschedule_{draft_id}"),
        ],
        [
            InlineKeyboardButton("✏ Edit",    callback_data=f"edit_{draft_id}"),
            InlineKeyboardButton("✗ Skip",    callback_data=f"skip_{draft_id}"),
        ]
    ])

    media_refs_str = draft.get("media_refs_json")
    poll_data = None
    media_files = []
    if media_refs_str:
        try:
            decoded = json.loads(media_refs_str)
            if isinstance(decoded, dict):
                poll_data = decoded
            elif isinstance(decoded, list):
                media_files = decoded
        except Exception:
            pass

    has_sent_media = False
    if media_files and isinstance(media_files, list) and os.path.exists(media_files[0]):
        file_path = media_files[0]
        if fmt in ("video", "video_poll"):
            video_caption = caption
            followup_text = None
            if len(caption) > 1024:
                video_caption = caption[:1000] + "…"
                followup_text = caption

            try:
                with open(file_path, "rb") as vf:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=vf,
                        caption=video_caption,
                        parse_mode="Markdown",
                        reply_markup=keyboard if not followup_text else None,
                        supports_streaming=True
                    )
                if followup_text:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=followup_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                has_sent_media = True
            except Exception as e:
                logger.error(f"Failed to send video file inline: {e}")

        elif fmt == "image":
            photo_caption = caption
            followup_text = None
            if len(caption) > 1024:
                photo_caption = caption[:1000] + "…"
                followup_text = caption

            try:
                with open(file_path, "rb") as pf:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=pf,
                        caption=photo_caption,
                        parse_mode="Markdown",
                        reply_markup=keyboard if not followup_text else None
                    )
                if followup_text:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=followup_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                has_sent_media = True
            except Exception as e:
                logger.error(f"Failed to send photo file inline: {e}")

    if not has_sent_media:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    # 3. If it is a poll format, send a native interactive Telegram poll
    if fmt == "poll" and poll_data and "question" in poll_data and "options" in poll_data:
        try:
            await bot.send_poll(
                chat_id=chat_id,
                question=poll_data["question"],
                options=poll_data["options"],
                is_anonymous=False
            )
        except Exception as pe:
            logger.error(f"Failed to send native Telegram poll: {pe}")

async def send_draft_for_review(update: Update, context: ContextTypes.DEFAULT_TYPE, draft: dict):
    context.user_data["last_draft_id"] = draft["id"]
    await send_draft_for_review_chat(context.bot, update.effective_chat.id, draft, context.user_data)

def run_telegram_bot_daemon():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "placeholder_bot_token":
        logger.warning("TELEGRAM_BOT_TOKEN not set or placeholder.")
        return None

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health_check", health_check_command))
    application.add_handler(CommandHandler("weekly_review", weekly_review_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot listener polling...")
    t = threading.Thread(
        target=application.run_polling,
        kwargs={"stop_signals": None, "close_loop": False, "drop_pending_updates": True},
        daemon=True,
    )
    t.start()
    return t

def run_telegram_bot_foreground():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "placeholder_bot_token":
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health_check", health_check_command))
    application.add_handler(CommandHandler("weekly_review", weekly_review_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot listener in foreground...")
    application.run_polling(drop_pending_updates=True)
