import os
import pytest
from pathlib import Path
from db.db import get_db_connection, init_db


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(str(db_path) + suffix)
        except FileNotFoundError:
            pass


def test_chat_sessions_table_exists(test_db):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_chat_messages_table_exists(test_db):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_chat_messages_cascade_delete(test_db):
    conn = get_db_connection()
    conn.execute("INSERT INTO chat_sessions (title) VALUES ('test session')")
    conn.commit()
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, 'user', 'hello')",
        (session_id,),
    )
    conn.commit()
    conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    msgs = conn.execute(
        "SELECT * FROM chat_messages WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    assert len(msgs) == 0


from dashboard_server import (
    get_chat_sessions,
    create_chat_session,
    delete_chat_session,
    get_session_messages,
    save_chat_message,
)


def test_create_and_list_session(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()
    assert "id" in session
    assert session["title"] is None

    conn = get_db_connection()
    sessions = get_chat_sessions(conn)
    conn.close()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session["id"]
    assert sessions[0]["message_count"] == 0


def test_delete_session(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    conn = get_db_connection()
    deleted = delete_chat_session(conn, session["id"])
    conn.close()
    assert deleted is True

    conn = get_db_connection()
    sessions = get_chat_sessions(conn)
    conn.close()
    assert len(sessions) == 0


def test_delete_nonexistent_session(test_db):
    conn = get_db_connection()
    deleted = delete_chat_session(conn, 9999)
    conn.close()
    assert deleted is False


def test_save_and_load_messages(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    conn = get_db_connection()
    save_chat_message(conn, session["id"], "user", "hello world")
    save_chat_message(conn, session["id"], "agent", "hi there")
    conn.close()

    conn = get_db_connection()
    msgs = get_session_messages(conn, session["id"])
    conn.close()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello world"
    assert msgs[1]["role"] == "agent"


def test_save_message_sets_title_on_first_user_message(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    conn = get_db_connection()
    save_chat_message(conn, session["id"], "user", "Create a post about Rust")
    conn.close()

    conn = get_db_connection()
    row = conn.execute(
        "SELECT title FROM chat_sessions WHERE id = ?", (session["id"],)
    ).fetchone()
    conn.close()
    assert row["title"] == "Create a post about Rust"


def test_save_message_truncates_title_to_60_chars(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    conn = get_db_connection()
    save_chat_message(conn, session["id"], "user", "A" * 100)
    conn.close()

    conn = get_db_connection()
    row = conn.execute(
        "SELECT title FROM chat_sessions WHERE id = ?", (session["id"],)
    ).fetchone()
    conn.close()
    assert len(row["title"]) == 60


def test_save_message_does_not_overwrite_existing_title(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    conn = get_db_connection()
    save_chat_message(conn, session["id"], "user", "First message")
    save_chat_message(conn, session["id"], "user", "Second message")
    conn.close()

    conn = get_db_connection()
    row = conn.execute(
        "SELECT title FROM chat_sessions WHERE id = ?", (session["id"],)
    ).fetchone()
    conn.close()
    assert row["title"] == "First message"


def test_sessions_ordered_by_updated_at_desc(test_db):
    import time
    conn = get_db_connection()
    s1 = create_chat_session(conn)
    conn.close()

    time.sleep(0.02)
    conn = get_db_connection()
    s2 = create_chat_session(conn)
    conn.close()

    # Touch s1 last — it should appear first
    time.sleep(0.02)
    conn = get_db_connection()
    save_chat_message(conn, s1["id"], "user", "ping")
    conn.close()

    conn = get_db_connection()
    sessions = get_chat_sessions(conn)
    conn.close()
    assert sessions[0]["id"] == s1["id"]


from dashboard_server import extract_pdf_text, handle_uploaded_file


def test_extract_pdf_text_returns_empty_for_nonexistent_file():
    text = extract_pdf_text("/nonexistent/path/file.pdf")
    assert text == ""


def test_handle_uploaded_file_saves_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "media" / "uploads").mkdir(parents=True)
    result = handle_uploaded_file("photo.png", b'\x89PNG\r\n' + b'\x00' * 50, "image/png")
    assert result["type"] == "image"
    assert result["filename"] == "photo.png"
    assert Path(result["saved_path"]).exists()
    assert "extracted_text" not in result


def test_handle_uploaded_file_saves_video(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "media" / "uploads").mkdir(parents=True)
    result = handle_uploaded_file("clip.mp4", b'\x00' * 50, "video/mp4")
    assert result["type"] == "video"
    assert Path(result["saved_path"]).exists()


def test_handle_uploaded_file_pdf_saves_and_includes_extracted_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "uploads").mkdir(parents=True)
    # Minimal valid PDF (no pages, extract_text returns "")
    minimal_pdf = (
        b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
        b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
        b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n'
        b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n'
        b'0000000058 00000 n \n0000000115 00000 n \n'
        b'trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF'
    )
    result = handle_uploaded_file("doc.pdf", minimal_pdf, "application/pdf")
    assert result["type"] == "pdf"
    assert result["filename"] == "doc.pdf"
    assert "extracted_text" in result
    assert isinstance(result["extracted_text"], str)
    assert Path(result["saved_path"]).exists()
