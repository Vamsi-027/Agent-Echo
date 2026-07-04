import os
import pytest
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
