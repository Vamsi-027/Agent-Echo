# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**agent-echo** is an autonomous, local-first LinkedIn content agent. It watches your daily developer activity (GitHub, Notion, browser tabs, local files), aggregates it into a daily digest via Claude, generates LinkedIn post drafts, routes them through a Telegram-based review flow, and schedules + publishes approved posts to LinkedIn.

## Setup

```bash
# Install the package in editable mode with dev extras
pip install -e ".[dev]"

# Copy and populate required env vars (see .env section below)
cp .env .env.local   # if needed
```

**Required `.env` variables:**
- `ANTHROPIC_API_KEY` — Claude API key (used by digest and draft generation)
- `OPENAI_API_KEY` — for LanceDB persona embeddings (`text-embedding-3-small`)
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` — LinkedIn Developer App credentials
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` — Telegram review bot
- `GITHUB_TOKEN`, `GITHUB_USERNAME` — GitHub activity watcher
- `NOTION_API_KEY` — Notion activity watcher
- `LOCAL_TIMEZONE` — IANA timezone string, e.g. `America/Chicago` (defaults to `America/Chicago`)
- `DRY_RUN=true` — prevents real LinkedIn posts; default is `true`

**LinkedIn OAuth tokens are stored in the OS keyring** (via `keyring` library), not in `.env`. Run `python cli.py authorize` once to complete the OAuth flow and persist tokens. The `oauth_token_meta` table only stores expiry metadata; the actual access/refresh tokens live in keyring.

## Commands

All CLI entry points go through `cli.py` via `python cli.py <subcommand>`.

```bash
# Initialize the SQLite database (run once)
python cli.py db-init

# Seed fake activity events for testing (5 days of sample data)
python cli.py seed-fake-events

# End-to-end pipeline (manual dry-run)
python cli.py digest --date 2026-06-14       # aggregate raw events → daily_digests table
python cli.py generate --date 2026-06-14     # run LangGraph pipeline → drafts table
python cli.py review                          # list pending drafts
python cli.py review --approve <id>          # approve a draft (queues it)
python cli.py review --skip <id>             # reject a draft
python cli.py review --edit <id> "instruction"  # regenerate a draft variant
python cli.py publish --dry-run              # run publisher tick (no real post)

# Persona vault (vector RAG context for generation)
python cli.py persona-ingest                 # index data/persona_vault/*.txt|.md into LanceDB

# LinkedIn OAuth setup (run once before going live)
python cli.py authorize

# Observability
python cli.py health-check
python cli.py weekly-review

# Run the full daemon (APScheduler-based, blocking)
python orchestrator.py
```

## Tests

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_content_queue.py

# Run a single test
pytest tests/test_agent_graph.py::test_no_activity
```

**Test isolation pattern:** Tests redirect the database via the `DATABASE_PATH` env var to a temp file in `tests/`. Fixtures must also delete WAL sidecars (`.db-wal`, `.db-shm`) in both setup and teardown. See `tests/test_content_queue.py` for the canonical fixture pattern.

## Architecture

### Data flow

```
Activity Sources (GitHub, Notion, Browser, FileSystem)
    ↓ capture/ watchers (every 30 min, 8–23h local)
activity_events (SQLite)
    ↓ aggregator/daily_digest.py at 21:00 local
daily_digests (SQLite)
    ↓ generator/agent_graph.py LangGraph pipeline
drafts (SQLite)
    ↓ notification/ Telegram bot (review: approve/edit/skip)
content_queue (SQLite)
    ↓ publisher/scheduler.py (tick every 15 min)
published_posts (SQLite) + LinkedIn Feed API
```

### Key modules

| Module | Responsibility |
|---|---|
| `orchestrator.py` | APScheduler daemon; wires all jobs to cron/interval triggers |
| `cli.py` | Click CLI for manual control of every pipeline stage |
| `config_loader.py` | Loads `config/*.yaml` and resolves `LOCAL_TZ` |
| `aggregator/daily_digest.py` | Queries `activity_events`, calls Claude with JSON schema output, writes `daily_digests` |
| `generator/agent_graph.py` | LangGraph `StateGraph` with 5 nodes: digest → classify → format → persona → generate |
| `generator/draft_generator.py` | Entry point called by CLI/orchestrator; runs compiled LangGraph graph |
| `generator/pillar_classifier.py` | Claude call to pick primary + secondary content pillar |
| `generator/format_selector.py` | Selects post format (`text`, `image`, `carousel`, `video`, `poll`) |
| `generator/media_handler.py` | Resolves media files from `data/screenshots/` and `data/media/` |
| `db/db.py` | SQLite connection factory; WAL mode + foreign keys enforced per-connection |
| `db/vector_db.py` | LanceDB wrapper; OpenAI embeddings stored at `data/persona_db.lance` |
| `publisher/linkedin_client.py` | LinkedIn REST API calls; tokens via OS keyring (`keyring` library) |
| `publisher/oauth.py` | 3-legged OAuth flow helpers; `check_and_refresh_token()` runs before every publisher tick |
| `publisher/scheduler.py` | Reads `content_queue`, posts due items, respects `DRY_RUN` |
| `notification/router.py` | `NotificationRouter` abstraction; dispatches to configured channels |
| `notification/telegram_channel.py` | Telegram bot with inline keyboard for approve/edit/skip; 5s callback debounce; runs in a background thread |
| `capture/` | Source-specific watchers: `github_watcher`, `notion_watcher`, `browser_watcher`, `file_watcher` |
| `feedback/weekly_review.py` | Prompt for post metrics; Claude call to reweight pillar scores |
| `observability/health_check.py` | Audits DB tables, OAuth expiry, stuck queue items |
| `observability/tracer.py` | `trace_pipeline_run()` context manager; writes to `pipeline_runs` table |

### Configuration files (`config/`)

- `pillars.yaml` — content pillar definitions (id + name + description); Claude uses the enum at digest time
- `posting_cadence.yaml` — time windows and slot rules for scheduling posts
- `exclusions.yaml` — apps, domains, calendar title patterns, and folders to exclude from capture
- `voice_profile.md` — natural language style guide injected into every draft generation prompt; its SHA-256 hash is stored on each draft row (`voice_profile_hash`) so you can track which profile version produced a draft

### LangGraph pipeline (`generator/agent_graph.py`)

The pipeline uses a `StateGraph` with `PipelineState` (TypedDict). Conditional routing:
1. `aggregate_digest` → routes to `classify_pillar` if digest exists, else `END`
2. `classify_pillar` → routes to `select_format` if pillar != `"none"`, else `END`
3. `select_format` → routes to `retrieve_persona_context`
4. `retrieve_persona_context` → `generate_drafts` → `END`

`compiled_graph` is a **module-level singleton** — importing `generator.agent_graph` triggers compilation. All Claude calls use `output_config={"format": {"type": "json_schema", "schema": ...}}` for structured output (not tool use). Poll drafts use a different schema with `poll_question`, `poll_options`, and `poll_duration` fields.

### Database (`linkedin_agent.db`)

SQLite with WAL mode. Schema lives in `db/schema.sql`; migrations in `db/migrations/`. Main tables:
- `activity_events` — raw captures (source, event_time UTC ISO8601, title, detail JSON)
- `daily_digests` — aggregated highlights with versioning (`UNIQUE(date, version)`)
- `drafts` — generated content; status lifecycle: `pending_review → approved → publishing → published | failed | needs_manual_check`
- `content_queue` — scheduled publish times with priority scores
- `published_posts` — LinkedIn URN mapping
- `pending_reviews` — local fallback queue for failed Telegram deliveries
- `pipeline_runs` — observability traces
- `oauth_token_meta` — token expiration tracking (actual tokens are in OS keyring)

Default DB path: `linkedin_agent.db` at project root. Override with `DATABASE_PATH` env var.

### Publisher idempotency

`publisher/scheduler.py` uses a two-phase commit pattern to prevent double-posting. When a draft is picked up, its status is immediately set to `publishing` (a distributed lock). If it stays in `publishing` for more than 5 minutes, `reconcile_stuck_publishes()` moves it to `needs_manual_check` and sends an alert. A LinkedIn 426 (version sunset) response halts all further publishing until the API version is updated.

### Persona vault (RAG)

Place `.txt` or `.md` files in `data/persona_vault/`. Run `python cli.py persona-ingest` to chunk and embed them into LanceDB at `data/persona_db.lance`. Files with `resume`/`cv` in the name → `experience` category; `style`/`post` → `style`; `opinion`/`taste` → `opinions`. These chunks are retrieved at generation time to ground drafts in personal context.
