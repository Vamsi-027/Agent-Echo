# Dashboard Chat History & File Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent multi-session chat history, session create/delete sidebar, and PDF/image/video file attachments to the dashboard Chat tab.

**Architecture:** Two new SQLite tables store conversation history. `dashboard_server.py` gains 5 new HTTP endpoints, a file upload handler, and an updated `process_chat_message` that injects PDF text as context and passes prior turns to Claude for conversational intents. The Chat tab becomes a two-column split layout (220px sidebar + flex chat panel) with a file-attach input bar.

**Tech Stack:** Python stdlib (`http.server`, `pathlib`, `uuid`, `re`), SQLite, `pdfplumber` (new dependency), vanilla JS/HTML/CSS (no framework)

## Global Constraints

- Python >= 3.10; SQLite WAL mode + foreign keys enforced per-connection (`db/db.py`)
- All timestamps UTC ISO8601; tests use `DATABASE_PATH` env var for isolated temp DB
- Test fixtures must delete `.db-wal` and `.db-shm` sidecars in both setup and teardown
- `session_id` in `/api/chat` is optional for backward compatibility
- Session-aware context only for intents: `system_question` and the general fallback
- PDF text truncated to 12,000 chars before passing to Claude
- Uploaded PDFs → `data/uploads/`; images/videos → `data/media/uploads/`
- No browser `confirm()` dialogs (would block the Chrome extension); use inline DOM confirmation

---

## File Map

| File | Change |
|---|---|
| `db/schema.sql` | Append `chat_sessions` and `chat_messages` table definitions |
| `db/migrations/002_chat_history.sql` | Migration script for existing databases |
| `pyproject.toml` | Add `pdfplumber>=0.10.0` |
| `dashboard_server.py` | Add `import re`, 7 helper functions, 5 new routes, updated `process_chat_message` |
| `dashboard.html` | Restructure Chat tab: split layout, sidebar, file attachment input bar |
| `tests/test_chat_sessions.py` | All tests for sessions, file helpers, and persistence |

---

### Task 1: DB Schema — `chat_sessions` and `chat_messages` tables

**Files:**
- Modify: `db/schema.sql`
- Create: `db/migrations/002_chat_history.sql`
- Create: `tests/test_chat_sessions.py`

**Interfaces:**
- Produces: Two SQLite tables used by every subsequent task

- [ ] **Step 1: Write failing tests for table existence and cascade delete**

Create `tests/test_chat_sessions.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat_sessions.py -v
```

Expected: FAIL — tables do not exist yet.

- [ ] **Step 3: Append tables to `db/schema.sql`**

Add after the last existing `CREATE TABLE` block in `db/schema.sql`:

```sql
-- Chat sessions for the dashboard chat UI
CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Messages within a chat session
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    attachments_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Create `db/migrations/002_chat_history.sql`**

```sql
-- Migration: add chat history tables (safe to run on existing databases)

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    attachments_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_chat_sessions.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql db/migrations/002_chat_history.sql tests/test_chat_sessions.py
git commit -m "feat: add chat_sessions and chat_messages schema tables"
```

---

### Task 2: Session CRUD helper functions

**Files:**
- Modify: `dashboard_server.py` (5 module-level functions added before `DashboardRequestHandler`)
- Modify: `tests/test_chat_sessions.py`

**Interfaces:**
- Consumes: `get_db_connection()` from `db.db`
- Produces:
  - `get_chat_sessions(conn) -> list[dict]`
  - `create_chat_session(conn) -> dict`  — keys: `id`, `title`, `created_at`
  - `delete_chat_session(conn, session_id: int) -> bool`
  - `get_session_messages(conn, session_id: int) -> list[dict]`
  - `save_chat_message(conn, session_id: int, role: str, content: str, attachments_json: str | None = None) -> None`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chat_sessions.py` (after the existing tests):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat_sessions.py -v -k "create_and_list or delete or save"
```

Expected: ImportError — functions not defined yet.

- [ ] **Step 3: Add the 5 helper functions to `dashboard_server.py`**

In `dashboard_server.py`, add `import re` after the existing stdlib imports at the top of the file:

```python
import re
```

Then add the following block **before** the `class DashboardRequestHandler` line:

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_chat_sessions.py -v
```

Expected: All 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add dashboard_server.py tests/test_chat_sessions.py
git commit -m "feat: add session CRUD helpers (get/create/delete/messages/save)"
```

---

### Task 3: File upload helpers and PDF extraction

**Files:**
- Modify: `pyproject.toml`
- Modify: `dashboard_server.py` (add 3 helper functions after the session helpers)
- Modify: `tests/test_chat_sessions.py`

**Interfaces:**
- Produces:
  - `extract_pdf_text(pdf_path: str) -> str`
  - `handle_uploaded_file(filename: str, file_data: bytes, mime_type: str) -> dict`
    - Returns `{"type": "pdf"|"image"|"video", "filename": str, "saved_path": str, "extracted_text"?: str}`
  - `parse_multipart_upload(rfile, content_type: str, content_length: int) -> tuple[str | None, bytes | None, str | None]`

- [ ] **Step 1: Add `pdfplumber` to `pyproject.toml`**

In the `dependencies` list in `pyproject.toml`, add:

```toml
    "pdfplumber>=0.10.0",
```

Then install:

```bash
pip install pdfplumber
```

Expected: pdfplumber installs without error.

- [ ] **Step 2: Write failing tests**

Append to `tests/test_chat_sessions.py`:

```python
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
```

Note: `Path` is already imported at the top of the test file via `from pathlib import Path` — add that import if it's not present.

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_chat_sessions.py -v -k "extract_pdf or handle_uploaded"
```

Expected: ImportError — functions not defined.

- [ ] **Step 4: Add the 3 file upload helpers to `dashboard_server.py`**

Add after the session helpers, still before `class DashboardRequestHandler`:

```python
# ─── File Upload Helpers ──────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: str) -> str:
    """Extract plain text from a PDF. Returns empty string on any failure."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        pass
    try:
        import pypdf
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def handle_uploaded_file(filename: str, file_data: bytes, mime_type: str) -> dict:
    """Save an uploaded file to disk and return attachment metadata."""
    import uuid as _uuid
    ext = Path(filename).suffix.lower()
    unique_name = f"{_uuid.uuid4().hex}{ext}"

    if mime_type == "application/pdf" or ext == ".pdf":
        save_dir = Path("data/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_data)
        extracted = extract_pdf_text(str(save_path))
        return {
            "type": "pdf",
            "filename": filename,
            "saved_path": str(save_path),
            "extracted_text": extracted[:12000],
        }
    else:
        save_dir = Path("data/media/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name
        save_path.write_bytes(file_data)
        file_type = "video" if ext in {".mp4", ".mov", ".webm"} else "image"
        return {
            "type": file_type,
            "filename": filename,
            "saved_path": str(save_path),
        }


def parse_multipart_upload(rfile, content_type: str, content_length: int):
    """
    Parse multipart/form-data. Returns (filename, file_data, mime_type) for
    the 'file' field, or (None, None, None) if parsing fails.
    """
    boundary_match = re.search(r"boundary=(.+)", content_type)
    if not boundary_match:
        return None, None, None

    boundary = boundary_match.group(1).strip().encode()
    body = rfile.read(content_length)

    for part in body.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, _, file_data = part.partition(b"\r\n\r\n")
        file_data = file_data.rstrip(b"\r\n")
        headers_str = headers_raw.decode("utf-8", errors="replace")

        if 'name="file"' not in headers_str:
            continue
        fn_match = re.search(r'filename="([^"]+)"', headers_str)
        if not fn_match:
            continue
        filename = fn_match.group(1)
        ct_match = re.search(r"Content-Type:\s*(.+)", headers_str, re.IGNORECASE)
        mime_type = ct_match.group(1).strip() if ct_match else "application/octet-stream"
        return filename, file_data, mime_type

    return None, None, None
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/test_chat_sessions.py -v
```

Expected: All 15 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml dashboard_server.py tests/test_chat_sessions.py
git commit -m "feat: add file upload helpers and PDF text extraction"
```

---

### Task 4: Update `process_chat_message` — attachments, context, persistence

**Files:**
- Modify: `dashboard_server.py` (`process_chat_message` function and the `/api/chat` handler inside `do_POST`)

**Interfaces:**
- Consumes: `get_session_messages`, `save_chat_message`, `create_chat_session`, `get_db_connection`
- Produces: `process_chat_message(message, session_id, attachments)` — same `str` return type; `/api/chat` response now also includes `session_id`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chat_sessions.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock


def _make_mock_client(text="Hello from agent"):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def test_process_chat_message_saves_user_and_agent_messages(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    from dashboard_server import process_chat_message

    with patch("dashboard_server.Anthropic", return_value=_make_mock_client()):
        asyncio.run(process_chat_message("hello", session["id"], []))

    conn = get_db_connection()
    msgs = get_session_messages(conn, session["id"])
    conn.close()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["role"] == "agent"
    assert msgs[1]["content"] == "Hello from agent"


def test_process_chat_message_pdf_context_prepended(test_db):
    conn = get_db_connection()
    session = create_chat_session(conn)
    conn.close()

    attachments = [{
        "type": "pdf",
        "filename": "paper.pdf",
        "saved_path": "data/uploads/x.pdf",
        "extracted_text": "This paper is about RAG systems.",
    }]

    captured = []

    def capture_create(**kwargs):
        captured.extend(kwargs.get("messages", []))
        r = MagicMock()
        r.content = [MagicMock(text="Sure")]
        return r

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = capture_create

    from dashboard_server import process_chat_message

    with patch("dashboard_server.Anthropic", return_value=mock_client):
        asyncio.run(process_chat_message("write a post", session["id"], attachments))

    all_content = " ".join(str(m) for m in captured)
    assert "This paper is about RAG systems." in all_content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat_sessions.py::test_process_chat_message_saves_user_and_agent_messages tests/test_chat_sessions.py::test_process_chat_message_pdf_context_prepended -v
```

Expected: FAIL — `process_chat_message` doesn't accept `session_id` or `attachments`.

- [ ] **Step 3: Update `process_chat_message` signature**

In `dashboard_server.py`, change:

```python
async def process_chat_message(message: str) -> str:
```

to:

```python
async def process_chat_message(
    message: str,
    session_id: int = None,
    attachments: list = None,
) -> str:
```

- [ ] **Step 4: Add attachment pre-processing inside `process_chat_message`**

Find the line `text = message.strip()` inside `process_chat_message`. Insert the following block **immediately before** that line:

```python
    attachments = attachments or []

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
```

- [ ] **Step 5: Wire `attached_media_paths` into draft creation**

Inside the `elif intent == "draft_from_topic":` block, find:

```python
        fmt = parsed.get("format_type", "text")
```

Add immediately after it:

```python
        user_media_override = json.dumps(attached_media_paths) if attached_media_paths else None
```

Then in the `elif fmt == "image":` branch, replace:

```python
                details = extract_image_details(draft_text)
                img_path = generate_topic_conceptual_image(details)
                media_refs_json = json.dumps([img_path])
```

with:

```python
                if user_media_override:
                    media_refs_json = user_media_override
                else:
                    details = extract_image_details(draft_text)
                    img_path = generate_topic_conceptual_image(details)
                    media_refs_json = json.dumps([img_path])
```

In the `elif fmt == "video":` branch, after `conn.commit()` and before `threading.Thread(target=run_remotion, daemon=True).start()`, replace the thread start line with:

```python
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
```

- [ ] **Step 6: Add session-aware context for `system_question` and the general fallback**

Find the `elif intent == "system_question":` block and replace it with:

```python
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
```

Find the final `else:` (general fallback) block and replace it with:

```python
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
```

- [ ] **Step 7: Add message persistence in `do_POST /api/chat` and pass new params**

In `DashboardRequestHandler.do_POST`, find the `if path == "/api/chat":` block. Replace the inner `try:` block with:

```python
        if path == "/api/chat":
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

                # Persist both turns
                pc = get_db_connection()
                atts_str = json.dumps(attachments) if attachments else None
                save_chat_message(pc, session_id, "user", message, atts_str)
                save_chat_message(pc, session_id, "agent", response_text)
                pc.close()

                self.send_json_response(
                    200, {"response": response_text, "session_id": session_id}
                )
            except Exception as e:
                logger.error(f"Error handling /api/chat POST: {e}", exc_info=True)
                self.send_json_error(500, f"Error processing message: {e}")
```

- [ ] **Step 8: Run all tests**

```bash
pytest tests/test_chat_sessions.py -v
```

Expected: All 17 tests PASSED.

- [ ] **Step 9: Commit**

```bash
git add dashboard_server.py
git commit -m "feat: update process_chat_message with attachments, session context, and persistence"
```

---

### Task 5: New HTTP endpoints in `DashboardRequestHandler`

**Files:**
- Modify: `dashboard_server.py`

**Interfaces:**
- Consumes: `get_chat_sessions`, `create_chat_session`, `delete_chat_session`, `get_session_messages`, `parse_multipart_upload`, `handle_uploaded_file`
- Produces: `GET /api/chats`, `POST /api/chats`, `DELETE /api/chats/<id>`, `GET /api/chats/<id>/messages`, `POST /api/upload`

- [ ] **Step 1: Extend `do_GET` with new chat routes**

In `DashboardRequestHandler.do_GET`, replace:

```python
        if path in ("/", "/index.html"):
            self.serve_html()
        elif path == "/api/data":
            self.serve_api_data()
        else:
            self.send_error(404, "File Not Found")
```

with:

```python
        if path in ("/", "/index.html"):
            self.serve_html()
        elif path == "/api/data":
            self.serve_api_data()
        elif path == "/api/chats":
            self._handle_list_sessions()
        else:
            m = re.match(r"^/api/chats/(\d+)/messages$", path)
            if m:
                self._handle_get_messages(int(m.group(1)))
            else:
                self.send_error(404, "File Not Found")
```

- [ ] **Step 2: Extend `do_POST` with new routes**

In `DashboardRequestHandler.do_POST`, replace:

```python
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chat":
```

with:

```python
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chats":
            self._handle_create_session()
        elif path == "/api/upload":
            self._handle_file_upload()
        elif path == "/api/chat":
```

- [ ] **Step 3: Add `do_DELETE` method**

Add this method to `DashboardRequestHandler` directly after `do_POST`:

```python
    def do_DELETE(self):
        path = self.path.split("?")[0]
        m = re.match(r"^/api/chats/(\d+)$", path)
        if m:
            self._handle_delete_session(int(m.group(1)))
        else:
            self.send_error(404, "Not Found")
```

- [ ] **Step 4: Add the 5 private handler methods**

Add these methods to `DashboardRequestHandler` before `serve_html`:

```python
    def _handle_list_sessions(self):
        try:
            conn = get_db_connection()
            sessions = get_chat_sessions(conn)
            conn.close()
            self.send_json_response(200, sessions)
        except Exception as e:
            logger.error(f"Error listing sessions: {e}", exc_info=True)
            self.send_json_error(500, str(e))

    def _handle_create_session(self):
        try:
            conn = get_db_connection()
            session = create_chat_session(conn)
            conn.close()
            self.send_json_response(200, session)
        except Exception as e:
            logger.error(f"Error creating session: {e}", exc_info=True)
            self.send_json_error(500, str(e))

    def _handle_delete_session(self, session_id: int):
        try:
            conn = get_db_connection()
            deleted = delete_chat_session(conn, session_id)
            conn.close()
            if deleted:
                self.send_json_response(200, {"deleted": True})
            else:
                self.send_json_error(404, f"Session {session_id} not found")
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
            self.send_json_error(500, str(e))

    def _handle_get_messages(self, session_id: int):
        try:
            conn = get_db_connection()
            messages = get_session_messages(conn, session_id)
            conn.close()
            self.send_json_response(200, messages)
        except Exception as e:
            logger.error(f"Error fetching messages for {session_id}: {e}", exc_info=True)
            self.send_json_error(500, str(e))

    def _handle_file_upload(self):
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))
        try:
            filename, file_data, mime_type = parse_multipart_upload(
                self.rfile, content_type, content_length
            )
            if filename is None:
                self.send_json_error(400, "No 'file' field found in multipart upload")
                return
            metadata = handle_uploaded_file(filename, file_data, mime_type)
            self.send_json_response(200, metadata)
        except Exception as e:
            logger.error(f"File upload error: {e}", exc_info=True)
            self.send_json_error(500, str(e))
```

- [ ] **Step 5: Smoke-test the new endpoints**

```bash
python dashboard_server.py &
sleep 1

# List sessions — expect []
curl -s http://localhost:8080/api/chats | python3 -m json.tool

# Create session — expect {id, title, created_at}
curl -s -X POST http://localhost:8080/api/chats | python3 -m json.tool

# List sessions — expect 1 item
curl -s http://localhost:8080/api/chats | python3 -m json.tool

# Get messages for session 1 — expect []
curl -s http://localhost:8080/api/chats/1/messages | python3 -m json.tool

# Delete session 1 — expect {deleted: true}
curl -s -X DELETE http://localhost:8080/api/chats/1 | python3 -m json.tool

# List sessions — expect []
curl -s http://localhost:8080/api/chats | python3 -m json.tool

kill %1
```

Expected: Each command returns valid JSON as described.

- [ ] **Step 6: Commit**

```bash
git add dashboard_server.py
git commit -m "feat: add session and file upload HTTP endpoints"
```

---

### Task 6: Frontend — split layout and session sidebar

**Files:**
- Modify: `dashboard.html`

**Interfaces:**
- Consumes: `GET /api/chats`, `POST /api/chats`, `DELETE /api/chats/<id>`, `GET /api/chats/<id>/messages`
- Produces: Two-column Chat tab with working session list, create, switch, and delete

- [ ] **Step 1: Replace the Chat tab HTML**

In `dashboard.html`, find the entire `<!-- TAB 6: CHAT -->` block (from `<div id="panel-chat"` to its closing `</div>`) and replace it with:

```html
        <!-- TAB 6: CHAT -->
        <div id="panel-chat" class="tab-panel">
            <div class="chat-split-layout">
                <div class="chat-sidebar">
                    <button class="new-chat-btn" onclick="createNewSession()">＋ New Chat</button>
                    <div class="chat-session-list" id="chat-session-list"></div>
                </div>
                <div class="chat-main-panel">
                    <div class="chat-session-title" id="chat-session-title">New conversation</div>
                    <div class="chat-messages" id="chat-messages">
                        <div class="chat-bubble-container agent">
                            <div class="chat-agent-header">✦ Agent Echo</div>
                            <div>
                                👋 Hello! I am Agent Echo, your autonomous developer content assistant.
                                <br><br>You can ask me to:
                                <br>• <i>"create a post about PostgreSQL indexes"</i>
                                <br>• <i>"approve draft 12"</i> &nbsp;• <i>"skip draft 12"</i>
                                <br>• <i>"reschedule draft 12 for tomorrow 3pm"</i>
                                <br>• <i>"show queue"</i> &nbsp;• <i>"metrics summary"</i>
                                <br>• Attach a PDF and ask me to create a post about it
                                <br>• Attach an image or video to include in your post
                            </div>
                            <div class="chat-bubble-meta agent">SYSTEM INITIALIZED</div>
                        </div>
                    </div>
                    <div class="chat-attachment-chips" id="chat-attachment-chips"></div>
                    <div class="chat-input-bar">
                        <div class="chat-input-pill">
                            <button class="chat-attach-btn" title="Attach file"
                                onclick="document.getElementById('file-upload-input').click()">📎</button>
                            <input type="file" id="file-upload-input" multiple
                                accept=".pdf,.png,.jpg,.jpeg,.gif,.mp4,.mov,.webm"
                                style="display:none" onchange="handleFileSelect(event)">
                            <input type="text" id="chat-input" class="chat-input-field"
                                placeholder="Type a message or command..."
                                onkeypress="handleChatKeyPress(event)">
                            <button onclick="sendChatMessage()" class="chat-send-btn">↑</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
```

- [ ] **Step 2: Replace chat CSS**

In `dashboard.html`'s `<style>` block, find the comment `/* Chat Console - Clean Minimalist Redesign */` and delete everything from that comment down through `.chat-send-btn:active { transform: scale(0.95); }`. Replace with:

```css
        /* Chat Split Layout */
        .chat-split-layout {
            display: flex;
            height: 640px;
            width: 100%;
            overflow: hidden;
        }

        .chat-sidebar {
            width: 220px;
            flex-shrink: 0;
            background: var(--sidebar-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px 0 0 12px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .new-chat-btn {
            margin: 12px;
            padding: 8px 14px;
            background: var(--primary);
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            font-family: var(--font-main);
            transition: background var(--transition-speed);
        }
        .new-chat-btn:hover { background: var(--primary-hover); }

        .chat-session-list {
            flex: 1;
            overflow-y: auto;
            padding: 4px 8px 8px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .chat-session-list::-webkit-scrollbar { width: 4px; }
        .chat-session-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 2px; }

        .session-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            border-radius: 8px;
            cursor: pointer;
            border: 1px solid transparent;
            gap: 6px;
            transition: background var(--transition-speed);
        }
        .session-item:hover { background: #ede9e0; }
        .session-item.active { background: #fff; border-color: var(--primary); }

        .session-item-body { flex: 1; min-width: 0; }
        .session-item-title {
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .session-item-time { font-size: 0.68rem; color: var(--text-muted); margin-top: 2px; }

        .session-delete-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.9rem;
            cursor: pointer;
            padding: 2px 5px;
            border-radius: 4px;
            flex-shrink: 0;
            transition: color var(--transition-speed), background var(--transition-speed);
        }
        .session-delete-btn:hover { color: var(--danger); background: var(--danger-light); }

        .session-delete-confirm {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 0.72rem;
            color: var(--text-secondary);
        }
        .session-delete-confirm button {
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 1px 6px;
            cursor: pointer;
            font-size: 0.72rem;
            font-family: var(--font-main);
        }
        .confirm-yes { background: var(--danger-light); color: var(--danger); border-color: var(--danger) !important; }
        .confirm-no { background: #fff; color: var(--text-secondary); }

        /* Chat Main Panel */
        .chat-main-panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-left: none;
            border-radius: 0 12px 12px 0;
            overflow: hidden;
        }

        .chat-session-title {
            padding: 12px 20px;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border-color);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex-shrink: 0;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .chat-messages::-webkit-scrollbar { width: 5px; }
        .chat-messages::-webkit-scrollbar-thumb { background-color: var(--border-color); border-radius: 3px; }

        .chat-bubble-container {
            display: flex;
            flex-direction: column;
            max-width: 85%;
            font-size: 0.92rem;
            line-height: 1.55;
            word-wrap: break-word;
        }
        .chat-bubble-container.user {
            align-self: flex-end;
            background: #f4f0ea;
            color: var(--text-primary);
            border-radius: 14px 14px 2px 14px;
            border: 1px solid var(--border-color);
            padding: 10px 16px;
        }
        .chat-bubble-container.agent {
            align-self: flex-start;
            background: transparent;
            color: var(--text-primary);
            border-left: 2px solid var(--primary);
            padding: 2px 0 8px 16px;
            max-width: 100%;
        }

        .chat-agent-header {
            font-weight: 700;
            font-size: 0.72rem;
            color: var(--primary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .chat-bubble-meta {
            font-size: 0.7rem;
            margin-top: 6px;
            opacity: 0.6;
            font-family: monospace;
        }
        .chat-bubble-meta.user { text-align: right; color: var(--text-secondary); }
        .chat-bubble-meta.agent { text-align: left; color: var(--text-muted); }

        .chat-attachment-display { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
        .attachment-chip-display {
            font-size: 0.75rem;
            padding: 3px 8px;
            background: #f4f0ea;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            color: var(--text-secondary);
        }

        /* Input area */
        .chat-attachment-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            padding: 0 16px 6px;
            min-height: 0;
        }
        .attachment-chip {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.78rem;
            padding: 4px 10px;
            background: var(--primary-light);
            border: 1px solid rgba(217, 107, 67, 0.25);
            border-radius: 12px;
            color: var(--primary);
            font-weight: 500;
        }
        .attachment-chip.uploading { opacity: 0.6; }
        .attachment-chip-remove {
            background: transparent;
            border: none;
            color: var(--primary);
            cursor: pointer;
            font-size: 0.9rem;
            line-height: 1;
            padding: 0;
        }

        .chat-input-bar { padding: 8px 16px 16px; }
        .chat-input-pill {
            display: flex;
            align-items: center;
            background: #fff;
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 5px 5px 5px 8px;
            gap: 4px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.02);
            transition: border-color var(--transition-speed);
        }
        .chat-input-pill:focus-within {
            border-color: var(--primary);
            box-shadow: 0 4px 20px rgba(217, 107, 67, 0.06);
        }
        .chat-attach-btn {
            background: transparent;
            border: none;
            font-size: 1rem;
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 6px;
            color: var(--text-muted);
            flex-shrink: 0;
            transition: color var(--transition-speed);
        }
        .chat-attach-btn:hover { color: var(--primary); }
        .chat-input-field {
            flex: 1;
            border: none;
            background: transparent;
            outline: none;
            font-size: 0.9rem;
            font-family: var(--font-main);
            color: var(--text-primary);
            padding: 6px 0;
        }
        .chat-send-btn {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: var(--primary);
            color: #fff;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.15rem;
            font-weight: bold;
            flex-shrink: 0;
            transition: background var(--transition-speed), transform 0.1s;
        }
        .chat-send-btn:hover { background: var(--primary-hover); }
        .chat-send-btn:active { transform: scale(0.95); }
```

- [ ] **Step 3: Add session management JavaScript**

In `dashboard.html`'s `<script>` block, add the following immediately after the `let state = {...}` declaration:

```javascript
        // Chat session state
        let activeChatSessionId = null;
        let pendingAttachments = [];

        async function loadChatSessions() {
            try {
                const res = await fetch('/api/chats');
                const sessions = await res.json();
                renderSessionList(sessions);
                if (sessions.length > 0 && activeChatSessionId === null) {
                    await switchSession(sessions[0].id, sessions[0].title);
                }
            } catch (e) {
                console.error('Failed to load chat sessions:', e);
            }
        }

        function renderSessionList(sessions) {
            const list = document.getElementById('chat-session-list');
            if (!sessions.length) {
                list.innerHTML = '<div style="font-size:0.78rem;color:var(--text-muted);padding:8px 10px;">No conversations yet</div>';
                return;
            }
            list.innerHTML = sessions.map(s => {
                const title = s.title || 'New conversation';
                const truncated = title.length > 28 ? title.slice(0, 28) + '…' : title;
                const isActive = s.id === activeChatSessionId;
                return `<div class="session-item ${isActive ? 'active' : ''}" id="session-item-${s.id}"
                    onclick="switchSession(${s.id}, ${JSON.stringify(title)})">
                  <div class="session-item-body">
                    <div class="session-item-title">${escapeHtml(truncated)}</div>
                    <div class="session-item-time">${relativeTime(s.updated_at)}</div>
                  </div>
                  <button class="session-delete-btn"
                    onclick="event.stopPropagation();confirmDeleteSession(${s.id})" title="Delete">×</button>
                </div>`;
            }).join('');
        }

        function relativeTime(isoStr) {
            if (!isoStr) return '';
            const diff = Date.now() - new Date(isoStr + 'Z').getTime();
            const mins = Math.floor(diff / 60000);
            if (mins < 1) return 'just now';
            if (mins < 60) return `${mins}m ago`;
            const hrs = Math.floor(mins / 60);
            if (hrs < 24) return `${hrs}h ago`;
            return `${Math.floor(hrs / 24)}d ago`;
        }

        function escapeHtml(str) {
            return String(str)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        async function createNewSession() {
            const res = await fetch('/api/chats', { method: 'POST' });
            const session = await res.json();
            activeChatSessionId = session.id;
            document.getElementById('chat-session-title').textContent = 'New conversation';
            document.getElementById('chat-messages').innerHTML = `
                <div class="chat-bubble-container agent">
                    <div class="chat-agent-header">✦ Agent Echo</div>
                    <div>New conversation started. What would you like to do?</div>
                    <div class="chat-bubble-meta agent">READY</div>
                </div>`;
            messageIdCounter = 0;
            pendingAttachments = [];
            document.getElementById('chat-attachment-chips').innerHTML = '';
            await loadChatSessions();
        }

        async function switchSession(sessionId, title) {
            activeChatSessionId = sessionId;
            document.getElementById('chat-session-title').textContent = title || 'New conversation';
            pendingAttachments = [];
            document.getElementById('chat-attachment-chips').innerHTML = '';
            document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
            const activeEl = document.getElementById(`session-item-${sessionId}`);
            if (activeEl) activeEl.classList.add('active');

            try {
                const res = await fetch(`/api/chats/${sessionId}/messages`);
                const messages = await res.json();
                const container = document.getElementById('chat-messages');
                if (!messages.length) {
                    container.innerHTML = `<div class="chat-bubble-container agent">
                        <div class="chat-agent-header">✦ Agent Echo</div>
                        <div>👋 Hello! I am Agent Echo. What would you like to create today?</div>
                        <div class="chat-bubble-meta agent">READY</div>
                    </div>`;
                    return;
                }
                container.innerHTML = '';
                messageIdCounter = 0;
                messages.forEach(msg => {
                    const div = document.createElement('div');
                    div.id = `chat-msg-${++messageIdCounter}`;
                    div.className = `chat-bubble-container ${msg.role}`;
                    const timeStr = msg.created_at ? msg.created_at.substring(11, 16) : '';
                    let attHtml = '';
                    if (msg.attachments_json) {
                        try {
                            const atts = JSON.parse(msg.attachments_json);
                            if (atts && atts.length) {
                                const icons = { pdf: '📄', image: '🖼', video: '🎥' };
                                attHtml = `<div class="chat-attachment-display">${atts.map(a =>
                                    `<span class="attachment-chip-display">${icons[a.type] || '📎'} ${escapeHtml(a.filename)}</span>`
                                ).join('')}</div>`;
                            }
                        } catch(e) {}
                    }
                    if (msg.role === 'agent') {
                        div.innerHTML = `<div class="chat-agent-header">✦ Agent Echo</div>
                            <div>${msg.content}</div>
                            <div class="chat-bubble-meta agent">${timeStr}</div>`;
                    } else {
                        div.innerHTML = `<div>${escapeHtml(msg.content)}</div>
                            ${attHtml}
                            <div class="chat-bubble-meta user">${timeStr}</div>`;
                    }
                    container.appendChild(div);
                });
                container.scrollTop = container.scrollHeight;
            } catch (e) {
                console.error('Failed to load messages:', e);
            }
        }

        function confirmDeleteSession(sessionId) {
            const item = document.getElementById(`session-item-${sessionId}`);
            if (!item) return;
            const deleteBtn = item.querySelector('.session-delete-btn');
            if (deleteBtn) deleteBtn.style.display = 'none';
            const confirm = document.createElement('div');
            confirm.className = 'session-delete-confirm';
            confirm.innerHTML = `Delete?
                <button class="confirm-yes" onclick="executeDeleteSession(${sessionId})">Yes</button>
                <button class="confirm-no" onclick="loadChatSessions()">No</button>`;
            item.appendChild(confirm);
        }

        async function executeDeleteSession(sessionId) {
            await fetch(`/api/chats/${sessionId}`, { method: 'DELETE' });
            if (activeChatSessionId === sessionId) {
                activeChatSessionId = null;
                document.getElementById('chat-session-title').textContent = 'New conversation';
                document.getElementById('chat-messages').innerHTML = `<div class="chat-bubble-container agent">
                    <div class="chat-agent-header">✦ Agent Echo</div>
                    <div>Conversation deleted. Start a new one with the button on the left.</div>
                    <div class="chat-bubble-meta agent">READY</div>
                </div>`;
            }
            await loadChatSessions();
        }
```

- [ ] **Step 4: Call `loadChatSessions` when switching to the Chat tab**

In the `switchTab` function, extend the tab-specific logic:

```javascript
            if (tabId === 'overview') {
                setTimeout(buildOverviewChart, 100);
            } else if (tabId === 'analytics') {
                setTimeout(buildPerformanceChart, 100);
            } else if (tabId === 'chat') {
                loadChatSessions();
            }
```

- [ ] **Step 5: Initialize sessions on page load**

Find `fetchSystemData();` near the bottom of the script block and add after it:

```javascript
        loadChatSessions();
```

- [ ] **Step 6: Manual test**

```bash
python dashboard_server.py
```

Open http://localhost:8080, click Chat tab. Verify:
- Sidebar with "＋ New Chat" button renders (220px left column)
- Clicking "＋ New Chat" creates a new session and adds it to the list
- Clicking a session in the sidebar highlights it and shows its messages (empty for new session)
- Clicking `×` shows inline "Delete? Yes / No" — no browser dialog
- Confirming removes the session; if it was active, message area resets

- [ ] **Step 7: Commit**

```bash
git add dashboard.html
git commit -m "feat: add chat split layout and session sidebar"
```

---

### Task 7: Frontend — file attachment input bar

**Files:**
- Modify: `dashboard.html`

**Interfaces:**
- Consumes: `POST /api/upload` (Task 5), updated `sendChatMessage` with `session_id` + `attachments`

- [ ] **Step 1: Add file upload and chip management functions**

In `dashboard.html`'s `<script>` block, add after `executeDeleteSession`:

```javascript
        async function handleFileSelect(event) {
            const files = Array.from(event.target.files);
            event.target.value = '';
            for (const file of files) {
                await uploadFile(file);
            }
        }

        async function uploadFile(file) {
            const chipId = `chip-${Date.now()}-${Math.random().toString(36).slice(2)}`;
            addAttachmentChip(chipId, file.name, true);
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                if (!res.ok) throw new Error(await res.text());
                const metadata = await res.json();
                pendingAttachments.push(metadata);
                updateChip(chipId, file.name, metadata.type);
            } catch (e) {
                updateChipError(chipId, file.name);
                console.error('Upload failed:', e);
            }
        }

        function addAttachmentChip(chipId, filename, isUploading) {
            const chips = document.getElementById('chat-attachment-chips');
            const chip = document.createElement('div');
            chip.id = chipId;
            chip.className = `attachment-chip${isUploading ? ' uploading' : ''}`;
            chip.innerHTML = `⏳ ${escapeHtml(filename)}`;
            chips.appendChild(chip);
        }

        function updateChip(chipId, filename, fileType) {
            const icons = { pdf: '📄', image: '🖼️', video: '🎥' };
            const chip = document.getElementById(chipId);
            if (!chip) return;
            chip.className = 'attachment-chip';
            chip.innerHTML = `${icons[fileType] || '📎'} ${escapeHtml(filename)}
                <button class="attachment-chip-remove"
                    onclick="removeAttachmentChip('${chipId}', ${JSON.stringify(filename)})">×</button>`;
        }

        function updateChipError(chipId, filename) {
            const chip = document.getElementById(chipId);
            if (!chip) return;
            chip.style.cssText = 'background:var(--danger-light);border-color:var(--danger);color:var(--danger)';
            chip.innerHTML = `❌ ${escapeHtml(filename)}
                <button class="attachment-chip-remove" onclick="this.parentElement.remove()">×</button>`;
        }

        function removeAttachmentChip(chipId, filename) {
            const chip = document.getElementById(chipId);
            if (chip) chip.remove();
            pendingAttachments = pendingAttachments.filter(a => a.filename !== filename);
        }
```

- [ ] **Step 2: Replace `sendChatMessage` to include session and attachments**

Find the existing `sendChatMessage` function and replace it entirely:

```javascript
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const text = input.value.trim();
            if (!text && pendingAttachments.length === 0) return;
            input.value = '';

            // Auto-create session if none active
            if (!activeChatSessionId) {
                const res = await fetch('/api/chats', { method: 'POST' });
                const session = await res.json();
                activeChatSessionId = session.id;
                document.getElementById('chat-session-title').textContent = 'New conversation';
                await loadChatSessions();
            }

            const attachmentsCopy = [...pendingAttachments];
            pendingAttachments = [];
            document.getElementById('chat-attachment-chips').innerHTML = '';

            // Build attachment display HTML for user bubble
            let attHtml = '';
            if (attachmentsCopy.length) {
                const icons = { pdf: '📄', image: '🖼️', video: '🎥' };
                attHtml = `<div class="chat-attachment-display">${attachmentsCopy.map(a =>
                    `<span class="attachment-chip-display">${icons[a.type] || '📎'} ${escapeHtml(a.filename)}</span>`
                ).join('')}</div>`;
            }

            appendMessageWithAttachments('user', text || '(attachment)', attHtml);
            const typingId = appendMessage('agent', '⚡ <i>Agent Echo is thinking...</i>');

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        session_id: activeChatSessionId,
                        attachments: attachmentsCopy,
                    }),
                });
                removeMessage(typingId);
                if (response.ok) {
                    const data = await response.json();
                    appendMessage('agent', data.response || 'No response received.');
                    await loadChatSessions(); // refresh sidebar title
                    fetchSystemData();
                } else {
                    const data = await response.json();
                    appendMessage('agent', `❌ Error: ${data.error || 'Failed to process message.'}`);
                }
            } catch (err) {
                removeMessage(typingId);
                appendMessage('agent', `❌ Network error: ${err.message}`);
            }
        }
```

- [ ] **Step 3: Add `appendMessageWithAttachments` helper**

Add after the existing `appendMessage` function:

```javascript
        function appendMessageWithAttachments(sender, text, attachmentHtml) {
            const container = document.getElementById('chat-messages');
            const msgId = `chat-msg-${++messageIdCounter}`;
            const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const div = document.createElement('div');
            div.id = msgId;
            div.className = `chat-bubble-container ${sender}`;
            div.innerHTML = `<div>${escapeHtml(text)}</div>
                ${attachmentHtml}
                <div class="chat-bubble-meta ${sender}">${timeStr}</div>`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return msgId;
        }
```

- [ ] **Step 4: Update `sendActionCommand` to pass `session_id`**

Replace the existing `sendActionCommand` function:

```javascript
        async function sendActionCommand(cmd) {
            appendMessage('user', cmd);
            const typingId = appendMessage('agent', '⚡ <i>Agent Echo is processing...</i>');
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: cmd,
                        session_id: activeChatSessionId,
                        attachments: [],
                    }),
                });
                removeMessage(typingId);
                if (response.ok) {
                    const data = await response.json();
                    appendMessage('agent', data.response || "No response received.");
                    fetchSystemData();
                } else {
                    const data = await response.json();
                    appendMessage('agent', `❌ Error: ${data.error || "Failed to process command."}`);
                }
            } catch (err) {
                removeMessage(typingId);
                appendMessage('agent', `❌ Network error: ${err.message}`);
            }
        }
```

- [ ] **Step 5: End-to-end manual test**

```bash
python dashboard_server.py
```

Open http://localhost:8080, go to Chat tab. Test each flow:

1. **Text message** — type "hello" and press Enter. Confirm message appears, agent responds, session title updates in sidebar to "hello".
2. **PDF attachment** — click 📎, select any `.pdf`. Confirm upload chip appears (⏳ → 📄 filename.pdf ×). Type "write a post about this document" and send. Confirm attachment chip shown in user bubble. Agent should acknowledge the PDF.
3. **Image attachment** — click 📎, select a `.jpg` or `.png`. Confirm 🖼 chip. Type "create an image post with this photo" and send.
4. **Remove chip before sending** — attach a file, click `×` on its chip. Confirm chip disappears. Send without it.
5. **Session switch** — click "＋ New Chat", send a message, click back on the previous session. Confirm its full message history reloads.
6. **Delete** — click `×` on a session, confirm "Yes". Confirm session removed from sidebar, message area resets.

- [ ] **Step 6: Run full test suite to catch regressions**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASSED. No regressions in existing test files.

- [ ] **Step 7: Commit**

```bash
git add dashboard.html
git commit -m "feat: add file attachment input bar with upload chips and session-aware sending"
```
