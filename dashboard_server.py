#!/usr/bin/env python3
import http.server
import json
import os
import re
import sys
import logging
import argparse
from pathlib import Path
from db.db import get_db_connection

# Apply Anthropic -> OpenAI fallback patch
import anthropic_fallback
anthropic_fallback.apply_patch()
from anthropic import Anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("dashboard_server")


async def _process_intent(message: str, session_id=None, attached_media_paths=None) -> str:
    try:
        from notification.telegram_bot import (
            fallback_intent_parse,
            call_structured_intent,
            parse_relative_datetime_with_llm,
            get_most_recent_pending_draft_id,
        )
    except ImportError:
        def fallback_intent_parse(text):
            return None
        async def call_structured_intent(text):
            return {"intent": "unknown"}
        async def parse_relative_datetime_with_llm(text):
            return None
        def get_most_recent_pending_draft_id():
            return None
    from aggregator.daily_digest import run_daily_digest
    from generator.draft_generator import generate_drafts_for_date, generate_topic_draft, approve_draft
    from generator.conceptual_image_selector import extract_image_details
    from generator.media_handler import generate_topic_conceptual_image, generate_remotion_video
    import datetime
    import threading
    from config_loader import LOCAL_TZ

    attached_media_paths = attached_media_paths or []
    text = message.strip()
    parsed = fallback_intent_parse(text)
    if not parsed:
        try:
            parsed = await call_structured_intent(text)
        except Exception as e:
            logger.error(f"Failed to parse intent: {e}")
            parsed = {"intent": "unknown"}

    intent = parsed.get("intent", "unknown")
    logger.info(f"Chat routed intent: {intent}")

    conn = get_db_connection()

    if intent == "draft_from_activity":
        today_str = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        try:
            run_daily_digest(today_str)
            drafts = generate_drafts_for_date(today_str)
            if attached_media_paths:
                media_conn = get_db_connection()
                media_conn.execute(
                    "UPDATE drafts SET media_refs_json = ? "
                    "WHERE status = 'pending_review' AND created_at >= datetime('now', '-1 minute')",
                    (json.dumps(attached_media_paths),)
                )
                media_conn.commit()
                media_conn.close()
            conn.close()
            return f"Drafts generated from today's activity! Generated {len(drafts)} draft(s). Check the Drafts tab to review them."
        except Exception as e:
            conn.close()
            return f"Failed to generate drafts from activity: {e}"

    elif intent == "draft_from_topic":
        topic = parsed.get("topic", text)
        fmt = parsed.get("format_type", "text")
        user_media_override = json.dumps(attached_media_paths) if attached_media_paths else None
        try:
            today_str = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
            drow = conn.execute("SELECT id FROM daily_digests ORDER BY id DESC LIMIT 1").fetchone()
            digest_id = drow[0] if drow else None
            
            # 1. Fetch recent events
            recent_events = conn.execute(
                "SELECT source, title, detail FROM activity_events "
                "ORDER BY event_time DESC LIMIT 20"
            ).fetchall()
            
            # 2. Search persona style vault
            from db.vector_db import search_persona
            results = search_persona(topic, 6)
            persona_chunks = [r["text"] for r in results if r["category"] in ["experience", "opinions", "style"]]
            if not persona_chunks:
                persona_chunks = [r["text"] for r in results]
                
            # 3. Fetch recent posts to avoid repetition
            recent_posts = conn.execute(
                "SELECT text_content FROM drafts WHERE status = 'published' "
                "ORDER BY created_at DESC LIMIT 7"
            ).fetchall()
            
            # 4. Fetch voice profile
            from config_loader import get_voice_profile
            voice_profile_text, voice_profile_hash = get_voice_profile()
            
            # 5. Call generator
            draft_text, hashtags = generate_topic_draft(
                topic,
                [dict(e) for e in recent_events],
                persona_chunks,
                [r["text_content"] for r in recent_posts],
                voice_profile_text
            )
            
            media_refs_json = None
            if fmt == "poll":
                client = Anthropic()
                prompt = (
                    f"Generate a LinkedIn poll question and exactly 2 to 4 options for this topic: '{topic}'.\n"
                    f"Return JSON only: {{\"question\": \"...\", \"options\": [\"opt1\", \"opt2\", ...]}}"
                )
                res = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=200,
                    output_config={"format": {"type": "json_schema", "schema": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["question", "options"],
                        "additionalProperties": False
                    }}},
                    messages=[{"role": "user", "content": prompt}]
                )
                media_refs_json = res.content[0].text
                
            elif fmt == "image":
                if user_media_override:
                    media_refs_json = user_media_override
                else:
                    details = extract_image_details(draft_text)
                    img_path = generate_topic_conceptual_image(details)
                    media_refs_json = json.dumps([img_path])
                
            elif fmt == "video":
                c = conn.cursor()
                c.execute(
                    "INSERT INTO drafts (digest_id, pillar, format_type, text_content, hashtags, status) "
                    "VALUES (?, 'lesson_learned', 'video', ?, ?, 'pending_review')",
                    (digest_id, draft_text, hashtags)
                )
                draft_id = c.lastrowid
                conn.commit()
                conn.close()
                
                # Start video generation task in background thread
                def run_remotion():
                    mock_digest = {
                        "summary": topic,
                        "raw_summary": topic,
                        "highlights_json": json.dumps([topic]),
                        "categories_json": "{}"
                    }
                    output_dir = "data/media"
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = f"{output_dir}/topic_{draft_id}_animation.mp4"
                    generate_remotion_video(f"topic_{draft_id}", mock_digest, output_path, draft_text, draft_id)
                
                if user_media_override:
                    uo_conn = get_db_connection()
                    uo_conn.execute(
                        "UPDATE drafts SET media_refs_json = ? WHERE id = ?",
                        (user_media_override, draft_id),
                    )
                    uo_conn.commit()
                    uo_conn.close()
                else:
                    threading.Thread(target=run_remotion, daemon=True).start()

                review_card = f"""
<div class="chat-card-review">
    <div class="chat-card-title">Draft #{draft_id} Generated (Video)</div>
    <div class="chat-card-meta">
        <span class="chat-card-badge">Pillar: lesson_learned</span>
        <span class="chat-card-badge">Format: video</span>
    </div>
    <div class="chat-card-content">{draft_text}</div>
    <div style="font-family: monospace; font-size: 0.8rem; color: var(--primary);">{hashtags or ""}</div>
    <div style="font-size: 0.78rem; color: var(--text-muted); font-style: italic; margin-top: 4px;">🎥 Audio/Video rendering is running in the background. It will be available in the Drafts tab within 1-2 minutes.</div>
    <div class="chat-action-btn-row">
        <button class="chat-action-btn approve-btn" onclick="sendActionCommand('approve draft {draft_id}')">Approve</button>
        <button class="chat-action-btn" onclick="promptReschedule('{draft_id}')">Reschedule</button>
        <button class="chat-action-btn" onclick="promptEdit('{draft_id}')">Edit</button>
        <button class="chat-action-btn" onclick="sendActionCommand('skip draft {draft_id}')">Skip</button>
    </div>
</div>
"""
                return review_card

            c = conn.cursor()
            c.execute(
                "INSERT INTO drafts (digest_id, pillar, format_type, text_content, hashtags, media_refs_json, status) "
                "VALUES (?, 'lesson_learned', ?, ?, ?, ?, 'pending_review')",
                (digest_id, fmt, draft_text, hashtags, media_refs_json)
            )
            draft_id = c.lastrowid
            conn.commit()
            conn.close()
            
            review_card = f"""
<div class="chat-card-review">
    <div class="chat-card-title">Draft #{draft_id} Generated ({fmt.upper()})</div>
    <div class="chat-card-meta">
        <span class="chat-card-badge">Pillar: lesson_learned</span>
        <span class="chat-card-badge">Format: {fmt}</span>
    </div>
    <div class="chat-card-content">{draft_text}</div>
    <div style="font-family: monospace; font-size: 0.8rem; color: var(--primary);">{hashtags or ""}</div>
    {"<div style='font-size: 0.78rem; color: var(--text-muted); font-style: italic;'>📎 Generated graphic card attached to draft.</div>" if fmt == 'image' else ""}
    {"<div style='font-size: 0.78rem; color: var(--text-muted); font-style: italic;'>📊 Interactive poll card attached to draft.</div>" if fmt == 'poll' else ""}
    <div class="chat-action-btn-row">
        <button class="chat-action-btn approve-btn" onclick="sendActionCommand('approve draft {draft_id}')">Approve</button>
        <button class="chat-action-btn" onclick="promptReschedule('{draft_id}')">Reschedule</button>
        <button class="chat-action-btn" onclick="promptEdit('{draft_id}')">Edit</button>
        <button class="chat-action-btn" onclick="sendActionCommand('skip draft {draft_id}')">Skip</button>
    </div>
</div>
"""
            return review_card
        except Exception as e:
            try: conn.close()
            except: pass
            return f"Failed to generate draft on topic: {e}"

    elif intent == "queue_status":
        rows = conn.execute(
            "SELECT cq.scheduled_time, d.pillar, d.format_type "
            "FROM content_queue cq JOIN drafts d ON cq.draft_id = d.id "
            "WHERE cq.status = 'queued' ORDER BY cq.scheduled_time ASC LIMIT 5"
        ).fetchall()
        conn.close()
        if not rows:
            return "No posts currently scheduled in the queue."
        lines = ["Active Pipeline Queue:"]
        for r in rows:
            lines.append(f"- {r[0][:16].replace('T', ' ')}: {r[1]} ({r[2]})")
        return "\n".join(lines)

    elif intent == "analytics_summary":
        rows = conn.execute(
            "SELECT d.pillar, d.format_type, pl.impressions, pl.reactions, pl.comments "
            "FROM performance_log pl "
            "JOIN published_posts pp ON pl.linkedin_post_urn = pp.linkedin_post_urn "
            "JOIN drafts d ON pp.draft_id = d.id "
            "ORDER BY pl.recorded_at DESC LIMIT 5"
        ).fetchall()
        if not rows:
            conn.close()
            return "No performance logs found to analyze."
        client = Anthropic()
        data_str = json.dumps([dict(r) for r in rows])
        summary = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"Summarize this performance data in 2-3 clean bullets for a minimalist dashboard chat response:\n\n{data_str}",
            }],
        ).content[0].text
        conn.close()
        return summary

    elif intent == "trigger_pipeline":
        today_str = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        try:
            run_daily_digest(today_str)
            conn.close()
            return "Daily pipeline aggregation complete. Generated new daily digest."
        except Exception as e:
            conn.close()
            return f"Pipeline failed: {e}"

    elif intent == "system_question":
        question = parsed.get("question", text)
        prior_turns = []
        if session_id:
            ctx_conn = get_db_connection()
            history = ctx_conn.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT 6",
                (session_id,),
            ).fetchall()
            ctx_conn.close()
            prior_turns = [
                {"role": r["role"], "content": r["content"]}
                for r in reversed(history)
            ]
        client = Anthropic()
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=prior_turns + [
                {"role": "user", "content": f"You are Agent Echo, an autonomous content assistant. Answer this query cleanly and concisely:\n\n{question}"}
            ],
        )
        conn.close()
        return res.content[0].text

    elif intent == "approve":
        draft_id = parsed.get("draft_id") or get_most_recent_pending_draft_id()
        if not draft_id:
            conn.close()
            return "No pending drafts found to approve."
        try:
            approve_draft(draft_id)
            conn.close()
            return f"Draft #{draft_id} approved and queued. ✓"
        except Exception as e:
            conn.close()
            return f"Failed to approve draft #{draft_id}: {e}"

    elif intent == "skip":
        draft_id = parsed.get("draft_id") or get_most_recent_pending_draft_id()
        if not draft_id:
            conn.close()
            return "No pending drafts found to skip."
        conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
        conn.commit()
        conn.close()
        return f"Draft #{draft_id} skipped and rejected."

    elif intent == "reschedule":
        draft_id = parsed.get("draft_id") or get_most_recent_pending_draft_id()
        res_time = parsed.get("reschedule_time", "").strip()
        if not draft_id:
            conn.close()
            return "No draft found to reschedule."
        if not res_time:
            conn.close()
            return f"Please specify a target time to reschedule Draft #{draft_id}."
        
        utc_time = await parse_relative_datetime_with_llm(res_time)
        if not utc_time:
            conn.close()
            return f"Could not parse reschedule time description: '{res_time}'."
        
        conn.execute("UPDATE drafts SET status = 'approved', scheduled_time = ? WHERE id = ?", (utc_time, draft_id))
        conn.execute("INSERT OR REPLACE INTO content_queue (draft_id, scheduled_time, status) VALUES (?, ?, 'queued')", (draft_id, utc_time))
        conn.commit()
        conn.close()
        return f"Draft #{draft_id} scheduled for {utc_time}."

    elif intent == "edit":
        draft_id = parsed.get("draft_id") or get_most_recent_pending_draft_id()
        instruction = parsed.get("edit_instruction", "").strip()
        if not draft_id:
            conn.close()
            return "No draft found to edit."
        if not instruction:
            conn.close()
            return f"Please specify what changes to make to Draft #{draft_id}. E.g.: 'edit draft {draft_id} make it shorter'"

        # Fetch session context for edit intent
        prior_turns = []
        if session_id:
            ctx_conn = get_db_connection()
            history = ctx_conn.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT 6",
                (session_id,)
            ).fetchall()
            ctx_conn.close()
            prior_turns = [{"role": r["role"], "content": r["content"]} for r in reversed(history)]

        try:
            from generator.draft_generator import edit_draft
            new_draft = edit_draft(draft_id, instruction, prior_turns=prior_turns)
            conn.close()
            
            draft_dict = dict(new_draft)
            draft_id = draft_dict["id"]
            fmt = draft_dict.get("format_type", "text")
            draft_text = draft_dict.get("text_content", "")
            hashtags = draft_dict.get("hashtags", "")
            
            review_card = f"""
<div class="chat-card-review">
    <div class="chat-card-title">Draft #{draft_id} Regenerated & Revised</div>
    <div class="chat-card-meta">
        <span class="chat-card-badge">Pillar: {draft_dict.get("pillar")}</span>
        <span class="chat-card-badge">Format: {fmt}</span>
    </div>
    <div class="chat-card-content">{draft_text}</div>
    <div style="font-family: monospace; font-size: 0.8rem; color: var(--primary);">{hashtags or ""}</div>
    <div class="chat-action-btn-row">
        <button class="chat-action-btn approve-btn" onclick="sendActionCommand('approve draft {draft_id}')">Approve</button>
        <button class="chat-action-btn" onclick="promptReschedule('{draft_id}')">Reschedule</button>
        <button class="chat-action-btn" onclick="promptEdit('{draft_id}')">Edit</button>
        <button class="chat-action-btn" onclick="sendActionCommand('skip draft {draft_id}')">Skip</button>
    </div>
</div>
"""
            return review_card
        except Exception as e:
            try: conn.close()
            except: pass
            return f"Failed to edit draft #{draft_id}: {e}"

    else:
        prior_turns = []
        if session_id:
            ctx_conn = get_db_connection()
            history = ctx_conn.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT 6",
                (session_id,),
            ).fetchall()
            ctx_conn.close()
            prior_turns = [
                {"role": r["role"], "content": r["content"]}
                for r in reversed(history)
            ]
        client = Anthropic()
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=prior_turns + [
                {"role": "user", "content": f"You are Agent Echo, an autonomous developer LinkedIn agent. Converse politely and answer this message: '{text}'"}
            ],
        )
        conn.close()
        return res.content[0].text


async def process_chat_message(
    message: str,
    session_id: int = None,
    attachments: list = None,
) -> str:
    attachments = attachments or []
    _original_message = message

    # Collect image/video paths for use when generating drafts
    attached_media_paths = [
        a["saved_path"]
        for a in attachments
        if a.get("type") in ("image", "video")
    ]

    # Prepend PDF extracted text so Claude reads the document
    pdf_contexts = [
        f'[Attached PDF: {a["filename"]}]\n\n{a["extracted_text"]}'
        for a in attachments
        if a.get("type") == "pdf" and a.get("extracted_text")
    ]
    if pdf_contexts:
        message = "\n\n---\n\n".join(pdf_contexts) + "\n\n---\n\n" + message

    # Warn user if any PDF failed extraction
    failed_pdfs = [
        a["filename"] for a in attachments
        if a.get("type") == "pdf" and not a.get("extracted_text")
    ]
    if failed_pdfs:
        # Prepend warning to message so Claude and the user see it
        warning = "Could not extract text from PDF — try describing its contents instead."
        message = warning + "\n\n" + message

    response = await _process_intent(message, session_id, attached_media_paths)

    if session_id is not None:
        conn = get_db_connection()
        save_chat_message(
            conn, session_id, "user", _original_message,
            json.dumps(attachments) if attachments else None,
        )
        save_chat_message(conn, session_id, "agent", response)
        conn.close()

    return response


# ─── Chat Session Helpers ─────────────────────────────────────────────────────

def get_chat_sessions(conn):
    """Return all sessions ordered by most-recently-updated first."""
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at, "
        "(SELECT COUNT(*) FROM chat_messages WHERE session_id = chat_sessions.id) AS message_count "
        "FROM chat_sessions ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def create_chat_session(conn):
    """Insert a new session with null title; return its row as a dict."""
    conn.execute("INSERT INTO chat_sessions (title) VALUES (NULL)")
    conn.commit()
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute(
        "SELECT id, title, created_at FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return dict(row)


def delete_chat_session(conn, session_id):
    """Delete session and all its messages (CASCADE). Return True if a row was deleted."""
    cursor = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_session_messages(conn, session_id):
    """Return all messages for a session in chronological order."""
    rows = conn.execute(
        "SELECT id, session_id, role, content, attachments_json, created_at "
        "FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_chat_message(conn, session_id, role, content, attachments_json=None):
    """Save a message, bump session.updated_at, and set title from first user message."""
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content, attachments_json) "
        "VALUES (?, ?, ?, ?)",
        (session_id, role, content, attachments_json),
    )
    conn.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?",
        (session_id,),
    )
    if role == "user":
        existing = conn.execute(
            "SELECT title FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if existing and existing["title"] is None:
            title = content.replace("\n", " ")[:60]
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id)
            )
    conn.commit()


# ─── File Upload Helpers ──────────────────────────────────────────────────────

def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes. Returns empty string on any failure."""
    import io
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return text[:12000]
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text[:12000]
    except Exception:
        return ""


def handle_uploaded_file(filename: str, file_bytes: bytes) -> dict:
    """Save an uploaded file to disk and return attachment metadata."""
    import uuid as _uuid
    ext = Path(filename).suffix.lower()
    unique_name = f"{_uuid.uuid4().hex}{ext}"

    if ext == ".pdf":
        save_dir = Path("data/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_bytes)
        extracted = extract_pdf_text(file_bytes)
        return {
            "type": "pdf",
            "filename": filename,
            "saved_path": str(save_path),
            "extracted_text": extracted,
        }
    elif ext in {".png", ".jpg", ".jpeg", ".gif"}:
        save_dir = Path("data/media/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_bytes)
        return {
            "type": "image",
            "filename": filename,
            "saved_path": str(save_path),
        }
    elif ext in {".mp4", ".mov", ".webm"}:
        save_dir = Path("data/media/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_bytes)
        return {
            "type": "video",
            "filename": filename,
            "saved_path": str(save_path),
        }
    else:
        save_dir = Path("data/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_bytes)
        return {
            "type": "unknown",
            "filename": filename,
            "saved_path": str(save_path),
        }


def parse_multipart_upload(content_type: str, body: bytes) -> tuple:
    """
    Parse multipart/form-data. Returns (filename, file_bytes) for the 'file'
    field, or (None, None) if parsing fails.
    """
    boundary_match = re.search(r"boundary=([^\s;]+)", content_type)
    if not boundary_match:
        return None, None

    boundary = boundary_match.group(1).strip().encode()

    for part in body.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, _, file_data = part.partition(b"\r\n\r\n")
        # Strip the single trailing CRLF that multipart adds — do NOT use rstrip (corrupts binary)
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]
        elif file_data.endswith(b"\n"):
            file_data = file_data[:-1]
        headers_str = headers_raw.decode("utf-8", errors="replace")

        if 'name="file"' not in headers_str:
            continue
        fn_match = re.search(r'filename="([^"]+)"', headers_str)
        if not fn_match:
            continue
        filename = fn_match.group(1)
        return filename, file_data

    return None, None


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Redirect request logs to logging framework instead of stderr
        logger.info("%s - - %s" % (self.address_string(), format % args))

    def do_GET(self):
        # Normalize path
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self.serve_html()
        elif path == "/api/data":
            self.serve_api_data()
        elif path == "/api/chats":
            self._handle_list_sessions()
        elif path.startswith("/media/"):
            # Serve static media assets
            rel_path = path[7:]
            if ".." in rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
                self.send_error(400, "Invalid Path")
                return
            
            target_file = Path("data/media") / rel_path
            if not target_file.exists() or not target_file.is_file():
                self.send_error(404, "File Not Found")
                return
            
            suffix = target_file.suffix.lower()
            content_type = "application/octet-stream"
            if suffix in (".png",):
                content_type = "image/png"
            elif suffix in (".jpg", ".jpeg"):
                content_type = "image/jpeg"
            elif suffix in (".gif",):
                content_type = "image/gif"
            elif suffix in (".mp4",):
                content_type = "video/mp4"
            elif suffix in (".webm",):
                content_type = "video/webm"
            elif suffix in (".mp3",):
                content_type = "audio/mpeg"
            elif suffix in (".wav",):
                content_type = "audio/wav"
            
            try:
                with open(target_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Error serving media file: {e}")
        else:
            m = re.match(r"^/api/chats/(\d+)/messages$", path)
            if m:
                self._handle_get_messages(int(m.group(1)))
            else:
                self.send_error(404, "File Not Found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chats":
            self._handle_create_session()
        elif path == "/api/queue/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                queue_id = payload.get("queue_id")
                if not queue_id:
                    self.send_json_error(400, "Missing queue_id")
                    return
                
                conn = get_db_connection()
                row = conn.execute("SELECT draft_id FROM content_queue WHERE id = ?", (queue_id,)).fetchone()
                if not row:
                    conn.close()
                    self.send_json_error(404, f"Queue item #{queue_id} not found")
                    return
                
                draft_id = row[0]
                # Delete from content_queue
                conn.execute("DELETE FROM content_queue WHERE id = ?", (queue_id,))
                # Mark draft back to pending_review so user doesn't lose it
                conn.execute("UPDATE drafts SET status = 'pending_review' WHERE id = ?", (draft_id,))
                conn.commit()
                conn.close()
                self.send_json_response(200, {"success": True, "message": f"Queue item #{queue_id} cancelled and returned to drafts."})
            except Exception as e:
                logger.error(f"Error deleting queue item: {e}", exc_info=True)
                self.send_json_error(500, str(e))

        elif path == "/api/queue/edit":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                queue_id = payload.get("queue_id")
                text_content = payload.get("text_content")
                hashtags = payload.get("hashtags", "")
                scheduled_time_str = payload.get("scheduled_time")
                
                if not queue_id:
                    self.send_json_error(400, "Missing queue_id")
                    return
                
                conn = get_db_connection()
                row = conn.execute("SELECT draft_id FROM content_queue WHERE id = ?", (queue_id,)).fetchone()
                if not row:
                    conn.close()
                    self.send_json_error(404, f"Queue item #{queue_id} not found")
                    return
                
                draft_id = row[0]
                
                # Update text content and hashtags on drafts
                conn.execute(
                    "UPDATE drafts SET text_content = ?, hashtags = ? WHERE id = ?",
                    (text_content, hashtags, draft_id)
                )
                
                # Try parsing relative time if scheduled_time is provided
                if scheduled_time_str:
                    scheduled_time_str = scheduled_time_str.strip()
                    parsed_time = None
                    
                    # If it matches absolute format like YYYY-MM-DD HH:MM:SS or with T
                    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", scheduled_time_str):
                        parsed_time = scheduled_time_str.replace(' ', 'T')
                        # format it as YYYY-MM-DDTHH:MM:SS
                        if len(parsed_time) == 16:
                            parsed_time += ":00"
                    else:
                        # Fallback parsing relative using telegram helper (if available)
                        try:
                            from notification.telegram_bot import parse_relative_datetime_with_llm
                            import asyncio
                            parsed_time = asyncio.run(parse_relative_datetime_with_llm(scheduled_time_str))
                        except Exception as e:
                            logger.error(f"Error parsing relative datetime '{scheduled_time_str}': {e}")
                    
                    if parsed_time:
                        conn.execute(
                            "UPDATE content_queue SET scheduled_time = ? WHERE id = ?",
                            (parsed_time, queue_id)
                        )
                        conn.execute(
                            "UPDATE drafts SET scheduled_time = ? WHERE id = ?",
                            (parsed_time, draft_id)
                        )
                    else:
                        conn.close()
                        self.send_json_error(400, f"Could not parse scheduled time: '{scheduled_time_str}'")
                        return

                conn.commit()
                conn.close()
                self.send_json_response(200, {"success": True, "message": f"Queue item #{queue_id} updated successfully."})
            except Exception as e:
                logger.error(f"Error editing queue item: {e}", exc_info=True)
                self.send_json_error(500, str(e))

        elif path == "/api/drafts/edit":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                draft_id = payload.get("draft_id")
                text_content = payload.get("text_content")
                hashtags = payload.get("hashtags", "")
                
                if not draft_id:
                    self.send_json_error(400, "Missing draft_id")
                    return
                
                conn = get_db_connection()
                conn.execute(
                    "UPDATE drafts SET text_content = ?, hashtags = ? WHERE id = ?",
                    (text_content, hashtags, draft_id)
                )
                conn.commit()
                conn.close()
                self.send_json_response(200, {"success": True, "message": f"Draft #{draft_id} updated successfully."})
            except Exception as e:
                logger.error(f"Error editing draft: {e}", exc_info=True)
                self.send_json_error(500, str(e))

        elif path == "/api/drafts/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                draft_id = payload.get("draft_id")
                
                if not draft_id:
                    self.send_json_error(400, "Missing draft_id")
                    return
                
                conn = get_db_connection()
                conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
                conn.commit()
                conn.close()
                self.send_json_response(200, {"success": True, "message": f"Draft #{draft_id} deleted."})
            except Exception as e:
                logger.error(f"Error deleting draft: {e}", exc_info=True)
                self.send_json_error(500, str(e))

        elif path == "/api/drafts/approve":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                draft_id = payload.get("draft_id")
                custom_time = payload.get("scheduled_time")
                
                if not draft_id:
                    self.send_json_error(400, "Missing draft_id")
                    return
                
                from generator.draft_generator import approve_draft
                conn = get_db_connection()
                
                if custom_time:
                    custom_time = custom_time.strip()
                    parsed_time = None
                    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", custom_time):
                        parsed_time = custom_time.replace(' ', 'T')
                        if len(parsed_time) == 16:
                            parsed_time += ":00"
                    else:
                        try:
                            from notification.telegram_bot import parse_relative_datetime_with_llm
                            import asyncio
                            parsed_time = asyncio.run(parse_relative_datetime_with_llm(custom_time))
                        except Exception as e:
                            logger.error(f"Error parsing relative datetime '{custom_time}': {e}")
                    
                    if parsed_time:
                        conn.execute("UPDATE drafts SET status = 'approved', scheduled_time = ? WHERE id = ?", (parsed_time, draft_id))
                        conn.execute("INSERT OR REPLACE INTO content_queue (draft_id, scheduled_time, status) VALUES (?, ?, 'queued')", (draft_id, parsed_time))
                        conn.commit()
                        conn.close()
                        self.send_json_response(200, {"success": True, "message": f"Draft #{draft_id} scheduled for {parsed_time}."})
                        return
                    else:
                        conn.close()
                        self.send_json_error(400, f"Could not parse scheduled time: '{custom_time}'")
                        return
                
                conn.close()
                approve_draft(draft_id)
                self.send_json_response(200, {"success": True, "message": f"Draft #{draft_id} approved and queued."})
            except Exception as e:
                logger.error(f"Error approving draft: {e}", exc_info=True)
                self.send_json_error(500, str(e))

        elif path == "/api/upload":
            self._handle_file_upload()
        elif path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                message = payload.get("message", "")
                session_id = payload.get("session_id")
                attachments = payload.get("attachments", [])

                # Auto-create session if none provided
                if not session_id:
                    sc = get_db_connection()
                    session_id = create_chat_session(sc)["id"]
                    sc.close()

                import asyncio
                response_text = asyncio.run(
                    process_chat_message(message, session_id, attachments)
                )

                self.send_json_response(
                    200, {"response": response_text, "session_id": session_id}
                )
            except Exception as e:
                logger.error(f"Error handling /api/chat POST: {e}", exc_info=True)
                self.send_json_error(500, f"Error processing message: {e}")
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        path = self.path.split("?")[0]
        m = re.match(r"^/api/chats/(\d+)$", path)
        if m:
            self._handle_delete_session(int(m.group(1)))
        else:
            self.send_error(404, "Not Found")

    def _handle_list_sessions(self):
        conn = get_db_connection()
        try:
            sessions = get_chat_sessions(conn)
            self.send_json_response(200, sessions)
        except Exception as e:
            logger.error("Error listing sessions: %s", e, exc_info=True)
            self.send_json_error(500, str(e))
        finally:
            conn.close()

    def _handle_create_session(self):
        conn = get_db_connection()
        try:
            session = create_chat_session(conn)
            self.send_json_response(201, session)
        except Exception as e:
            logger.error("Error creating session: %s", e, exc_info=True)
            self.send_json_error(500, str(e))
        finally:
            conn.close()

    def _handle_delete_session(self, session_id: int):
        conn = get_db_connection()
        try:
            deleted = delete_chat_session(conn, session_id)
            if deleted:
                self.send_json_response(200, {"deleted": True})
            else:
                self.send_json_error(404, f"Session {session_id} not found")
        except Exception as e:
            logger.error("Error deleting session %s: %s", session_id, e, exc_info=True)
            self.send_json_error(500, str(e))
        finally:
            conn.close()

    def _handle_get_messages(self, session_id: int):
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                self.send_json_error(404, "Session not found")
                return
            messages = get_session_messages(conn, session_id)
            self.send_json_response(200, messages)
        except Exception as e:
            logger.error("Error getting messages: %s", e, exc_info=True)
            self.send_json_error(500, str(e))
        finally:
            conn.close()

    def _handle_file_upload(self):
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))
        try:
            body = self.rfile.read(content_length)
            filename, file_data = parse_multipart_upload(content_type, body)
            if filename is None:
                self.send_json_error(400, "No 'file' field found in multipart upload")
                return
            metadata = handle_uploaded_file(filename, file_data)
            self.send_json_response(200, metadata)
        except Exception as e:
            logger.error(f"File upload error: {e}", exc_info=True)
            self.send_json_error(500, str(e))

    def serve_html(self):
        html_path = Path(__file__).parent / "dashboard.html"
        if not html_path.exists():
            self.send_error(500, "Dashboard template dashboard.html not found.")
            return

        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content.encode("utf-8"))))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except Exception as e:
            logger.error(f"Error serving index HTML: {e}", exc_info=True)
            self.send_error(500, f"Internal Server Error: {e}")

    def serve_api_data(self):
        try:
            conn = get_db_connection()
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}", exc_info=True)
            self.send_json_error(500, f"Database Connection Error: {e}")
            return

        try:
            # 1. Fetch statistics
            stats = {}
            
            # Events counts
            row = conn.execute("SELECT COUNT(*) FROM activity_events").fetchone()
            stats["events_count"] = row[0] if row else 0
            
            row = conn.execute(
                "SELECT COUNT(*) FROM activity_events WHERE event_time >= datetime('now', '-1 day')"
            ).fetchone()
            stats["events_24h"] = row[0] if row else 0
            
            # Drafts counts
            row = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()
            stats["drafts_count"] = row[0] if row else 0
            
            row = conn.execute("SELECT COUNT(*) FROM drafts WHERE status = 'pending_review'").fetchone()
            stats["drafts_pending"] = row[0] if row else 0
            
            # Queue counts
            row = conn.execute("SELECT COUNT(*) FROM content_queue WHERE status = 'queued'").fetchone()
            stats["queue_count"] = row[0] if row else 0
            
            # Published counts
            row = conn.execute("SELECT COUNT(*) FROM drafts WHERE status = 'published'").fetchone()
            stats["published_count"] = row[0] if row else 0
            
            # Performance impressions sum
            row = conn.execute("SELECT COALESCE(SUM(impressions), 0) FROM performance_log").fetchone()
            stats["total_impressions"] = row[0] if row else 0

            # 2. Fetch latest 100 activity events per source to prevent file watcher events from drowning out others
            events = []
            for src in ("git", "note", "browser", "file", "calendar"):
                rows = conn.execute(
                    "SELECT id, source, event_time, title, detail FROM activity_events "
                    "WHERE source = ? ORDER BY event_time DESC LIMIT 100", (src,)
                ).fetchall()
                for r in rows:
                    events.append(dict(r))
            # Sort unified event list chronologically descending
            events.sort(key=lambda x: x.get("event_time") or "", reverse=True)

            # 3. Fetch latest 50 drafts
            drafts = []
            rows = conn.execute(
                "SELECT id, digest_id, pillar, format_type, text_content, media_refs_json, hashtags, status, scheduled_time "
                "FROM drafts ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            for r in rows:
                drafts.append(dict(r))

            # 4. Fetch content queue
            queue = []
            rows = conn.execute(
                "SELECT cq.id, cq.draft_id, cq.priority_score, cq.scheduled_time, cq.status, "
                "d.pillar, d.format_type, d.text_content, d.hashtags, d.media_refs_json "
                "FROM content_queue cq "
                "JOIN drafts d ON cq.draft_id = d.id "
                "WHERE cq.status = 'queued' "
                "ORDER BY cq.scheduled_time ASC"
            ).fetchall()
            for r in rows:
                queue.append(dict(r))

            # 5. Fetch performance logs
            performance = []
            rows = conn.execute(
                "SELECT id, linkedin_post_urn, impressions, reactions, comments, recorded_at "
                "FROM performance_log ORDER BY recorded_at ASC"
            ).fetchall()
            for r in rows:
                performance.append(dict(r))

            # 6. Fetch pipeline trace runs
            runs = []
            rows = conn.execute(
                "SELECT id, component, status, error_message, started_at, completed_at "
                "FROM pipeline_runs ORDER BY started_at DESC LIMIT 50"
            ).fetchall()
            for r in rows:
                runs.append(dict(r))

            conn.close()

            response_data = {
                "stats": stats,
                "events": events,
                "drafts": drafts,
                "queue": queue,
                "performance": performance,
                "runs": runs
            }

            self.send_json_response(200, response_data)

        except Exception as e:
            logger.error(f"Error compiling API data: {e}", exc_info=True)
            try:
                conn.close()
            except Exception:
                pass
            self.send_json_error(500, f"Internal Server Error: {e}")

    def send_json_response(self, status_code, data):
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Failed to send JSON response: {e}")

    def send_json_error(self, status_code, message):
        self.send_json_response(status_code, {"error": message})


def run_server(host="localhost", port=8080):
    server_address = (host, port)
    Path("data/uploads").mkdir(parents=True, exist_ok=True)
    Path("data/media/uploads").mkdir(parents=True, exist_ok=True)
    # Using ThreadingHTTPServer for concurrent, non-blocking requests if page is polling
    # In older python versions ThreadingHTTPServer may not exist, fallback to HTTPServer
    try:
        httpd_class = http.server.ThreadingHTTPServer
    except AttributeError:
        httpd_class = http.server.HTTPServer

    logger.info(f"Starting server on http://{host}:{port}")
    httpd = httpd_class(server_address, DashboardRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
    finally:
        httpd.server_close()
        logger.info("Server port released.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Echo Dashboard Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to run the dashboard server (default: 8080)")
    parser.add_argument("--host", type=str, default="localhost", help="Host address (default: localhost)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
