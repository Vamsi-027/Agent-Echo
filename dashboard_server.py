#!/usr/bin/env python3
import http.server
import json
import os
import sys
import logging
import argparse
from pathlib import Path
from db.db import get_db_connection

# Apply Anthropic -> OpenAI fallback patch
import anthropic_fallback
anthropic_fallback.apply_patch()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("dashboard_server")


async def process_chat_message(message: str) -> str:
    from notification.telegram_bot import (
        fallback_intent_parse,
        call_structured_intent,
        parse_relative_datetime_with_llm,
        get_most_recent_pending_draft_id
    )
    from aggregator.daily_digest import run_daily_digest
    from generator.draft_generator import generate_drafts_for_date, generate_topic_draft, approve_draft
    from generator.conceptual_image_selector import extract_image_details
    from generator.media_handler import generate_topic_conceptual_image, generate_remotion_video
    from anthropic import Anthropic
    import json
    import os
    import datetime
    import threading
    from config_loader import LOCAL_TZ

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
            conn.close()
            return f"Drafts generated from today's activity! Generated {len(drafts)} draft(s). Check the Drafts tab to review them."
        except Exception as e:
            conn.close()
            return f"Failed to generate drafts from activity: {e}"

    elif intent == "draft_from_topic":
        topic = parsed.get("topic", text)
        fmt = parsed.get("format_type", "text")
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
        client = Anthropic()
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": f"You are Agent Echo, an autonomous content assistant. Answer this query cleanly and concisely:\n\n{question}"}]
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
        
        try:
            from generator.draft_generator import edit_draft
            new_draft = edit_draft(draft_id, instruction)
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
        client = Anthropic()
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": f"You are Agent Echo, an autonomous developer LinkedIn agent. Converse politely and answer this message: '{text}'"}]
        )
        conn.close()
        return res.content[0].text


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
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                message = payload.get("message", "")
                
                import asyncio
                response_text = asyncio.run(process_chat_message(message))
                
                self.send_json_response(200, {"response": response_text})
            except Exception as e:
                logger.error(f"Error handling /api/chat POST: {e}", exc_info=True)
                self.send_json_error(500, f"Error processing message: {e}")
        else:
            self.send_error(404, "Not Found")

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
                "SELECT cq.id, cq.draft_id, cq.priority_score, cq.scheduled_time, cq.status, d.pillar, d.format_type "
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
