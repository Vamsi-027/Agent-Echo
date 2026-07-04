# notification/state.py
import logging

logger = logging.getLogger("linkedin-agent.notification.state")

# Global states for conversation flow
# Maps chat_id to draft_id
pending_edits: dict = {}
# Maps chat_id to {"draft_id": draft_id, "message_id": message_id}
pending_reschedules: dict = {}
# Maps chat_id to {"posts": [...], "current_index": 0}
weekly_review_state: dict = {}
