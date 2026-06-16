import json
import logging
from abc import ABC, abstractmethod
from db.db import get_db_connection

logger = logging.getLogger("linkedin-agent.notification")

class NotificationChannel(ABC):
    """Abstract base for notification backends."""
    @abstractmethod
    def send(self, message: str, actions: list[str] | None = None) -> bool:
        pass
        
    def poll_responses(self) -> list[dict]:
        return []

class NotificationRouter:
    """Manages ordered dispatch of notifications with fallback mechanisms."""
    def __init__(self, channels: list[NotificationChannel]):
        self.channels = channels
        
    def send(self, message: str, actions: list[str] | None = None) -> bool:
        # Try sending through each configured channel in priority order
        for channel in self.channels:
            try:
                if channel.send(message, actions):
                    logger.info(f"Notification successfully delivered via {channel.__class__.__name__}")
                    return True
            except Exception as e:
                logger.warning(f"{channel.__class__.__name__} failed to send notification: {e}")
                continue
                
        # All channels failed (or none configured) - queue locally in SQLite
        logger.error("All notification channels failed. Queueing notification locally in DB.")
        self._queue_locally(message, actions)
        return False
        
    def _queue_locally(self, message: str, actions: list[str] | None = None) -> None:
        """Write notification to pending_reviews table for offline CLI pickup."""
        conn = get_db_connection()
        cursor = conn.cursor()
        actions_str = json.dumps(actions) if actions else None
        
        cursor.execute(
            "INSERT INTO pending_reviews (message, actions_json, status) VALUES (?, ?, 'pending')",
            (message, actions_str)
        )
        conn.commit()
        conn.close()

# Global default router helper for notifications
_default_router = None

def get_default_router() -> NotificationRouter:
    """Gets or initializes the default notification router using local DB CLI queue."""
    global _default_router
    if _default_router is None:
        channels = []
        
        try:
            from notification.telegram_channel import TelegramChannel
            tg = TelegramChannel()
            if tg.is_configured():
                channels.append(tg)
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram channel: {e}")
            
        if not channels:
            # For Phase 0.5 dry-run and when Telegram is not configured, we use a Console/CLI channel
            class ConsoleChannel(NotificationChannel):
                def send(self, message: str, actions: list[str] | None = None) -> bool:
                    # Always log to console and return True to prevent cluttering the database during test runs
                    print(f"\n[NOTIFICATION ROUTER] {message}")
                    if actions:
                        print(f"Available Actions: {actions}")
                    return True
            channels.append(ConsoleChannel())
            
        _default_router = NotificationRouter(channels)
    return _default_router

def alert_router(message: str) -> None:
    """Sends an emergency alert via the default router channels."""
    get_default_router().send(f"🚨 {message}")
