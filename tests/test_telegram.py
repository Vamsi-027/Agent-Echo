import os
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from notification.telegram_channel import (
    TelegramChannel,
    is_user_allowed,
    get_allowed_users,
    start_command,
    health_check_command,
    handle_callback_query,
    handle_user_text_message
)

@pytest.fixture
def clean_env():
    with patch.dict(os.environ, {}):
        yield

def test_telegram_channel_configuration(clean_env):
    os.environ["TELEGRAM_BOT_TOKEN"] = "placeholder_bot_token"
    channel = TelegramChannel()
    assert not channel.is_configured()
    
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-DEF"
    channel = TelegramChannel()
    assert channel.is_configured()

def test_is_user_allowed(clean_env):
    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "12345,67890"
    assert is_user_allowed(12345)
    assert is_user_allowed(67890)
    assert not is_user_allowed(99999)

@patch("notification.telegram_channel.requests.post")
def test_telegram_channel_send(mock_post, clean_env):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-DEF"
    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "12345"
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp
    
    channel = TelegramChannel()
    success = channel.send("Hello World", actions=["approve_1", "skip_1"])
    
    assert success
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "sendMessage" in args[0]
    payload = kwargs["json"]
    assert payload["chat_id"] == 12345
    assert payload["text"] == "Hello World"
    assert "reply_markup" in payload

@pytest.mark.anyio
async def test_start_command_unauthorized():
    update = MagicMock()
    update.effective_user.id = 99999
    update.message.reply_text = AsyncMock()
    
    with patch("notification.telegram_channel.is_user_allowed", return_value=False):
        await start_command(update, None)
        update.message.reply_text.assert_called_once_with("Unauthorized. Your user ID is not whitelisted.")

@pytest.mark.anyio
async def test_start_command_authorized():
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    
    with patch("notification.telegram_channel.is_user_allowed", return_value=True):
        await start_command(update, None)
        assert update.message.reply_text.call_count == 1
        args, kwargs = update.message.reply_text.call_args
        assert "Welcome" in args[0]

@pytest.mark.anyio
@patch("notification.telegram_channel.approve_draft")
async def test_callback_query_approve(mock_approve):
    query = MagicMock()
    query.data = "approve_42"
    query.message.text = "Draft content"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    
    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 12345
    
    with patch("notification.telegram_channel.is_user_allowed", return_value=True):
        await handle_callback_query(update, None)
        query.answer.assert_called_once_with("Scheduling draft...")
        mock_approve.assert_called_once_with(42)
        query.edit_message_text.assert_called_once()
        assert "Approved & Scheduled" in query.edit_message_text.call_args[1]["text"]

@pytest.mark.anyio
async def test_callback_query_edit():
    query = MagicMock()
    query.data = "edit_42"
    query.answer = AsyncMock()
    query.message.reply_text = AsyncMock()
    
    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 12345
    update.effective_chat.id = 5555
    
    with patch("notification.telegram_channel.is_user_allowed", return_value=True):
        from notification.telegram_channel import pending_edits
        pending_edits.clear()
        await handle_callback_query(update, None)
        query.answer.assert_called_once()
        assert pending_edits[5555] == 42
        query.message.reply_text.assert_called_once_with("✏️ Please reply to this message with your edit instructions for Draft 42:")
