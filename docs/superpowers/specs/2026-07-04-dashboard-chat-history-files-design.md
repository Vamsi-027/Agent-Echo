# Dashboard Chat — History, Sessions & File Attachments

**Date:** 2026-07-04  
**Status:** Approved  

---

## Overview

Enhance the Agent Echo dashboard's Chat tab with:
- Persistent multi-session conversation history stored in SQLite
- Sidebar showing previous chats with create/delete controls
- File attachment support (PDF, image, video) with per-type handling

---

## 1. Database Schema

Two new tables added to `db/schema.sql` with a corresponding migration in `db/migrations/`.

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,                          -- first 60 chars of first user message
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                  -- 'user' | 'agent'
    content TEXT NOT NULL,
    attachments_json TEXT,               -- JSON array: [{type, filename, saved_path, extracted_text?}]
    created_at TEXT DEFAULT (datetime('now'))
);
```

- Deleting a session cascades to all its messages.
- `chat_sessions.title` is set on first user message (first 60 chars). NULL title means a brand-new empty session.
- `chat_sessions.updated_at` is bumped every time a message is saved into the session.
- `attachments_json` on `chat_messages` stores the metadata for any files attached to that user message.

---

## 2. API Endpoints

All added to `DashboardRequestHandler` in `dashboard_server.py`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/chats` | List sessions: `[{id, title, created_at, updated_at, message_count}]`, ordered by `updated_at DESC` |
| `POST` | `/api/chats` | Create new session, returns `{id, title, created_at}` |
| `DELETE` | `/api/chats/<id>` | Delete session + all messages (CASCADE enforced at DB level) |
| `GET` | `/api/chats/<id>/messages` | Full message list for a session: `[{id, role, content, attachments_json, created_at}]` |
| `POST` | `/api/upload` | Multipart file upload. Returns `{type, filename, saved_path, extracted_text?}` |

**Updated `POST /api/chat` body:**
```json
{
  "message": "Create a post about this paper",
  "session_id": 3,
  "attachments": [
    {
      "type": "pdf",
      "filename": "paper.pdf",
      "saved_path": "data/uploads/abc123.pdf",
      "extracted_text": "Abstract: ..."
    }
  ]
}
```
`session_id` and `attachments` are both optional for backward compatibility. If `session_id` is omitted, a new session is created automatically.

### File upload handling (`POST /api/upload`)

Accepts `multipart/form-data` with a single `file` field.

- **PDF** → saved to `data/uploads/<uuid>.pdf`; text extracted with `pdfplumber` (fallback: `PyPDF2`); `extracted_text` included in response (truncated to 12,000 chars to stay within context limits)
- **Image** (`.png`, `.jpg`, `.jpeg`, `.gif`) → saved to `data/media/uploads/<uuid>.<ext>`; no text extraction
- **Video** (`.mp4`, `.mov`, `.webm`) → saved to `data/media/uploads/<uuid>.<ext>`; no text extraction

Both `data/uploads/` and `data/media/uploads/` are created at server startup if they don't exist.

---

## 3. Backend Logic (`process_chat_message`)

### New signature
```python
async def process_chat_message(
    message: str,
    session_id: int,
    attachments: list[dict]
) -> str:
```

### Attachment pre-processing (before intent routing)

**PDF attachments:**  
Prepend extracted text to the message so Claude reads the document content:
```
[Attached PDF: {filename}]

{extracted_text}

---

{original_message}
```

**Image/video attachments:**  
All image/video `saved_path` values are collected into a list `attached_media_paths`. When the resolved intent generates a draft (`draft_from_topic` or `draft_from_activity`), `media_refs_json` on the new draft row is set to `json.dumps(attached_media_paths)` instead of triggering the Remotion/Manim pipeline. This lets the user attach their own image or video directly to the post. If both PDFs and images/videos are attached in the same message, the PDF provides context for Claude while the images/videos are attached to the draft.

### Session-aware context (Approach B)

For these intents only: `system_question`, `edit`, and the fallback general-response branch — the last 6 `chat_messages` rows for this session are fetched and passed to Claude as prior conversation turns:

```python
history = conn.execute(
    "SELECT role, content FROM chat_messages "
    "WHERE session_id = ? ORDER BY created_at DESC LIMIT 6",
    (session_id,)
).fetchall()
prior_turns = [{"role": r["role"], "content": r["content"]} for r in reversed(history)]
# prior_turns passed as the leading messages in the Claude call
```

All other intents (`approve`, `skip`, `reschedule`, `draft_from_topic`, `draft_from_activity`, `queue_status`, `analytics_summary`, `trigger_pipeline`) remain fully stateless — they don't need conversation context and shouldn't incur the extra token cost.

### Persistence

After `process_chat_message` resolves:
1. Save user message to `chat_messages` (role=`user`, include `attachments_json`)
2. Save agent response to `chat_messages` (role=`agent`)
3. `UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?`
4. If this is the first user message in the session: `UPDATE chat_sessions SET title = ? WHERE id = ?` (first 60 chars of message, strip newlines)

---

## 4. Frontend Layout & UX (`dashboard.html`)

### Chat tab restructure

`#panel-chat` becomes a two-column flex layout inside the existing `.main-container`:

```
┌─────────────────┬──────────────────────────────────────┐
│  CONVERSATIONS  │  [Active session title]               │
│  + New Chat     │                                       │
│  ─────────────  │  Agent: Hello! I am Agent Echo...     │
│  Chat 1      ×  │                                       │
│  Chat 2      ×  │  You: create a post about...          │
│  Chat 3  (●)  × │       📄 paper.pdf                    │
│                 │  Agent: [draft card with actions]     │
│                 │                                       │
│                 │  ┌──────────────────────────────────┐ │
│                 │  │ 📎 [📄 paper.pdf ×] [type...] ↑ │ │
│                 │  └──────────────────────────────────┘ │
└─────────────────┴──────────────────────────────────────┘
```

### Sidebar (220px fixed width)

- **"＋ New Chat"** button at top: calls `POST /api/chats`, switches to the new empty session
- Session list sorted by `updated_at DESC`
- Each row: truncated title (max 28 chars) + relative timestamp + `×` delete button
- Active session highlighted with left border in `--primary` color
- On load: fetch `/api/chats`, auto-select the most recent session, load its messages

### Message area

- On session switch: fetch `/api/chats/<id>/messages`, re-render all messages
- User messages with attachments show a file chip beneath the message text: `📄 paper.pdf` or `🖼 photo.jpg` or `🎥 video.mp4`
- New-session welcome message (the Agent Echo intro) is rendered client-side only, not stored in DB

### Input bar changes

- **Paperclip button** (`📎`) left of the text field: opens a hidden `<input type="file" accept=".pdf,.png,.jpg,.jpeg,.gif,.mp4,.mov,.webm" multiple>`
- On file select: each file is immediately uploaded via `POST /api/upload` (multipart fetch)
- While uploading: spinner chip shown (`⏳ uploading...`)
- After upload: chip shows `📄 filename.pdf ×` (or `🖼`/`🎥` by type); `×` removes the attachment
- Multiple files can be attached simultaneously; each gets its own chip above the input field
- On send: all ready attachment metadata objects are included in the `/api/chat` payload

---

## 5. Error Handling

- `POST /api/upload` fails → chip shows `❌ upload failed` in red; user can retry or dismiss
- `pdfplumber` extraction fails → fall back to `PyPDF2`; if both fail, return `extracted_text: ""` with a warning in the chat response: *"Could not extract text from PDF — try describing its contents instead."*
- Session not found on load → show empty state with "Start a new chat" prompt
- Delete confirmation: clicking `×` on a session shows an inline `"Delete?" [Yes] [No]` toggle (no browser `confirm()` dialog, which would block the extension)

---

## 6. Files Changed

| File | Change |
|---|---|
| `db/schema.sql` | Add `chat_sessions` and `chat_messages` tables |
| `db/migrations/003_chat_history.sql` | Migration script for existing databases |
| `db/db.py` | `init_db()` already runs schema.sql; no change needed |
| `dashboard_server.py` | New endpoints, updated `process_chat_message` signature, file upload handler |
| `dashboard.html` | Split chat layout, sidebar, file attachment input bar |
| `requirements` / `pyproject.toml` | Add `pdfplumber` dependency |

---

## 7. Out of Scope

- PDF page images / visual rendering (text extraction only)
- Manual session renaming
- Session search / filtering
- Attachment storage quota or cleanup
- Sending images directly to Claude's vision API (attachment files go to drafts as media, not to Claude's vision)
