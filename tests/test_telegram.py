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
    handle_user_text_message,
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
        update.message.reply_text.assert_called_once_with(
            "Unauthorized. Your user ID is not whitelisted."
        )


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
    query.message.caption = None  # text message, not a video/photo draft
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 12345

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()

    with patch("notification.telegram_channel.is_user_allowed", return_value=True):
        await handle_callback_query(update, context)
        query.answer.assert_called_once_with("Scheduling draft...")
        mock_approve.assert_called_once_with(42)
        context.bot.edit_message_text.assert_called_once()
        context.bot.edit_message_caption.assert_not_called()
        assert "Approved & Scheduled" in context.bot.edit_message_text.call_args[1]["text"]


@pytest.mark.anyio
@patch("notification.telegram_channel.approve_draft")
async def test_callback_query_approve_video_draft_uses_caption_edit(mock_approve):
    """Video/photo drafts only carry a caption — editing must use edit_message_caption,
    not edit_message_text (which raises "There is no text in the message to edit")."""
    query = MagicMock()
    query.data = "approve_99"
    query.message.caption = "Draft content"
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    update.effective_user.id = 12345

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()

    with patch("notification.telegram_channel.is_user_allowed", return_value=True):
        await handle_callback_query(update, context)
        context.bot.edit_message_caption.assert_called_once()
        context.bot.edit_message_text.assert_not_called()
        assert "Approved & Scheduled" in context.bot.edit_message_caption.call_args[1]["caption"]


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
        query.message.reply_text.assert_called_once_with(
            "✏️ Please reply to this message with your edit instructions for Draft 42:"
        )


@pytest.fixture
def mock_db_env():
    import tempfile
    from pathlib import Path
    from db.db import init_db
    
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()
    
    with patch.dict(os.environ, {"DATABASE_PATH": db_path}):
        init_db(db_path=Path(db_path))
        yield db_path
        
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.mark.anyio
@patch("notification.telegram_bot.Anthropic")
async def test_parse_relative_datetime_with_llm(mock_anthropic):
    from notification.telegram_bot import parse_relative_datetime_with_llm
    
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"datetime": "2026-07-05 15:00:00"}')]
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic.return_value = mock_client
    
    utc_str = await parse_relative_datetime_with_llm("tomorrow 3pm")
    assert utc_str is not None
    assert "2026-07-0" in utc_str


@pytest.mark.anyio
@patch("notification.telegram_bot.parse_relative_datetime_with_llm", return_value="2026-07-05T20:00:00Z")
async def test_handle_reschedule_intent_successful(mock_parse_time, mock_db_env):
    from notification.telegram_bot import handle_reschedule_intent
    import sqlite3
    
    # Setup dummy draft
    conn = sqlite3.connect(mock_db_env)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_digests (date, version, raw_summary, highlights_json, categories_json, suggested_pillar) "
        "VALUES ('2026-06-14', 1, '{}', '[]', '[]', 'lesson_learned')"
    )
    digest_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO drafts (id, digest_id, pillar, format_type, text_content, hashtags, status) VALUES (555, ?, 'lesson_learned', 'video', 'Text content', '#hash', 'pending_review')",
        (digest_id,)
    )
    conn.commit()
    conn.close()
    
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    parsed = {"intent": "reschedule", "draft_id": 555, "reschedule_time": "tomorrow 3pm"}
    await handle_reschedule_intent(update, context, parsed)
    
    # Assert DB is rescheduled
    conn = sqlite3.connect(mock_db_env)
    cursor = conn.cursor()
    cursor.execute("SELECT status, scheduled_time FROM drafts WHERE id = 555")
    row = cursor.fetchone()
    cursor.execute("SELECT scheduled_time, status FROM content_queue WHERE draft_id = 555")
    qrow = cursor.fetchone()
    conn.close()
    
    assert row[0] == "approved"
    assert row[1] == "2026-07-05T20:00:00Z"
    assert qrow is not None
    assert qrow[0] == "2026-07-05T20:00:00Z"
    assert qrow[1] == "queued"


@pytest.mark.anyio
@patch("notification.telegram_bot.Anthropic")
@patch("notification.telegram_bot.search_persona", return_value=[])
@patch("notification.telegram_bot.generate_topic_draft", return_value=("Post text content", "#hashtags"))
async def test_handle_draft_from_topic_poll(mock_draft, mock_search, mock_anthropic, mock_db_env):
    from notification.telegram_bot import handle_draft_from_topic
    import sqlite3
    
    # Setup mock Claude response for poll details
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"question": "Tabs or spaces?", "options": ["Tabs", "Spaces"]}')]
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic.return_value = mock_client
    
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.bot = AsyncMock()
    
    await handle_draft_from_topic(update, context, topic="Tabs vs Spaces", format_type="poll")
    
    # Assert draft inserted as poll
    conn = sqlite3.connect(mock_db_env)
    cursor = conn.cursor()
    cursor.execute("SELECT format_type, media_refs_json FROM drafts ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "poll"
    poll_data = json.loads(row[1])
    assert poll_data["question"] == "Tabs or spaces?"
    assert poll_data["options"] == ["Tabs", "Spaces"]
    
    # Verify native send_poll call
    context.bot.send_poll.assert_called_once_with(
        chat_id=update.effective_chat.id,
        question="Tabs or spaces?",
        options=["Tabs", "Spaces"],
        is_anonymous=False
    )


@pytest.mark.anyio
@patch("notification.telegram_bot.search_persona", return_value=[])
@patch("notification.telegram_bot.generate_topic_draft", return_value=("Post text content", "#hashtags"))
@patch("generator.conceptual_image_selector.extract_image_details", return_value={"title": "test card title", "points": ["p1", "p2", "p3"]})
@patch("generator.media_handler.generate_topic_conceptual_image")
async def test_handle_draft_from_topic_image(mock_gen_img, mock_extract, mock_draft, mock_search, mock_db_env):
    from notification.telegram_bot import handle_draft_from_topic
    import sqlite3
    
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    await handle_draft_from_topic(update, context, topic="MySQL Indexing", format_type="image")
    
    # Assert draft inserted as image with media ref
    conn = sqlite3.connect(mock_db_env)
    cursor = conn.cursor()
    cursor.execute("SELECT format_type, media_refs_json FROM drafts ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "image"
    media_refs = json.loads(row[1])
    assert "topic_" in media_refs[0]
    assert "card.png" in media_refs[0]

