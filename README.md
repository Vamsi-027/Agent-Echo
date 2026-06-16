# Agent-Echo 🤖🎙️

Agent-Echo is an autonomous, local-first LinkedIn content agent. It monitors your daily developer activities (GitHub commits, Notion notes, browser history, and local file changes), synthesizes them into daily highlights using Claude, compiles custom post drafts using a LangGraph pipeline, and handles review and publishing via a Telegram bot and scheduler.

---

## 🏗️ Architecture & Data Flow

Agent-Echo operates as a pipeline running on local schedules to keep your content pipeline automated and natural:

```
Activity Sources (GitHub, Notion, Browser, FileSystem)
    │
    ▼ [capture/ watchers] — Runs every 30 min (8:00 - 23:00 local)
activity_events (SQLite)
    │
    ▼ [aggregator/daily_digest.py] — Triggered at 21:00 local
daily_digests (SQLite)
    │
    ▼ [generator/agent_graph.py] — LangGraph 5-node Pipeline (Digest → Classify → Format → Persona → Generate)
drafts (SQLite)
    │
    ▼ [notification/ telegram_channel] — Telegram Review Bot (Approve / Edit / Skip)
content_queue (SQLite)
    │
    ▼ [publisher/scheduler.py] — Runs every 15 min (Double-post protection / OAuth auto-refresh)
published_posts (SQLite) + LinkedIn Feed API
```

---

## ✨ Features

- **Local-First Watchers**: Efficient background tracking of developer workflows (GitHub events, Notion workspaces, active Chrome tabs, and local workspace directories).
- **LangGraph Draft Generator**: A robust structured generative graph using Claude to classify content pillars, select format types (text, carousel, poll, etc.), pull relevant style context, and draft updates.
- **Interactive Telegram Review**: Real-time notifications for new drafts. Approve, edit with instruction, or skip drafts directly from inline Telegram keyboard controls.
- **Double-Post Protection**: Two-phase commit lock mechanism to ensure posts are never duplicated or published out of order.
- **Persona Vault (RAG)**: Ingests CVs, resumes, style samples, and essays into a LanceDB vector database to ground posts in your true style and professional voice.
- **Built-in Observability**: Trace pipeline executions, log errors, track API consumption, and audit database health through a unified Click CLI.

---

## 🚀 Setup & Installation

### 1. Installation
Clone the repository and install it in editable mode along with developer tools:
```bash
# Set up a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install package and dev dependencies
pip install -e ".[dev]"
```

### 2. Configuration (`.env`)
Create a `.env` file in the root directory and populate it:
```env
# AI Models Keys
ANTHROPIC_API_KEY=your-anthropic-key     # For daily digest & draft generation
OPENAI_API_KEY=your-openai-key           # For LanceDB embeddings (text-embedding-3-small)

# Watchers Credentials
GITHUB_USERNAME=your-username
GITHUB_TOKEN=your-github-token           # Classic token with repo/read scopes
NOTION_API_KEY=your-notion-key           # Notion integration token

# Publishing & Notifications
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ALLOWED_USER_IDS=your-user-id
LOCAL_TIMEZONE=America/Chicago           # Your IANA timezone
DRY_RUN=false                            # Set to true to simulate LinkedIn publishing
```

### 3. Initialize Databases
Set up the local SQLite database and index the persona vault documents:
```bash
# Initialize SQLite tables
python cli.py db-init

# Ingest style guidelines, resumes, and essays to the vector DB
python cli.py persona-ingest
```

---

## 🛠️ Commands Reference

All manual triggers and administrative tasks go through `cli.py`:

```bash
# Seed 5 days of dummy events for testing/dry-runs
python cli.py seed-fake-events

# Manually trigger daily digest generation
python cli.py digest --date 2026-06-14

# Run draft generation pipeline for a specific date
python cli.py generate --date 2026-06-14

# List pending drafts and review them locally
python cli.py review
python cli.py review --approve <draft_id>
python cli.py review --skip <draft_id>
python cli.py review --edit <draft_id> "Make the tone more technical"

# Check scheduler queue and tick publishing
python cli.py publish --dry-run

# Authorize LinkedIn Application (runs OAuth setup and stores token in keyring)
python cli.py authorize

# Observability diagnostics
python cli.py health-check
python cli.py weekly-review
```

### 🕒 Running the Background Daemon
Start the local AP Scheduler daemon to begin background watching, digest building, and publishing tasks:
```bash
python orchestrator.py
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run tests on specific features
pytest tests/test_agent_graph.py
pytest tests/test_content_queue.py
```

---

## 📂 Project Structure

| Directory/File | Description |
|---|---|
| `capture/` | Raw developer activity watchers (GitHub, Notion, browser tabs, files). |
| `aggregator/` | Compiles raw captures into concise daily digests. |
| `generator/` | LangGraph agent flow (Classify → Format → Context retrieve → Generation). |
| `db/` | Database setup (SQLite configurations and LanceDB vector wrapper). |
| `notification/` | Telegram channel notifier and callback handlers. |
| `publisher/` | Handles 3-legged LinkedIn OAuth, token refreshing, and publishing schedules. |
| `observability/` | Diagnostics, telemetry pipelines, and weekly evaluations. |
| `config/` | Pillar definitions, posting times, exclusions, and voice profile guides. |
| `cli.py` | Main interaction CLI. |
| `orchestrator.py` | Main daemon runner. |
