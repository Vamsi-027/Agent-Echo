# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**agent-echo** is an autonomous, local-first LinkedIn content agent. It watches your daily developer activity (GitHub, Notion, browser tabs, local files), aggregates it into a daily digest via Claude, generates LinkedIn post drafts, routes them through a Telegram-based review flow, and schedules + publishes approved posts to LinkedIn.

**Key architectural principle:** All state flows through SQLite (single source of truth). Each pipeline stage is idempotent: digest aggregation checks for existing records, draft generation is stateless, publishing uses 2-phase commit (draft marked 'publishing' before LinkedIn API call).

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

## Common Commands

All CLI entry points go through `cli.py` via `python cli.py <subcommand>`.

### Pipeline Testing & Dry-Run

```bash
# Initialize the SQLite database (run once)
python cli.py db-init

# Seed fake activity events (5 days of sample data for testing)
python cli.py seed-fake-events

# Manual end-to-end dry-run (no real posts)
python cli.py digest --date 2026-06-14       # aggregate events → daily_digests table
python cli.py generate --date 2026-06-14     # run LangGraph pipeline → drafts table
python cli.py review                          # list pending_review drafts
python cli.py review --approve <id>          # approve & schedule a draft
python cli.py review --skip <id>             # reject a draft
python cli.py review --edit <id> "instruction"  # regenerate draft variant
python cli.py publish --dry-run              # run publisher tick (DRY_RUN=true, no LinkedIn posts)
```

### Persona Vault & Configuration

```bash
# Index persona files (data/persona_vault/*.txt|.md) into LanceDB for semantic retrieval
python cli.py persona-ingest

# Test TTS voice synthesis
python cli.py test-audio --text "Your text here"

# Generate sound effects library (for video backgrounds)
python cli.py seed-sfx
```

### OAuth & Publishing

```bash
# Complete LinkedIn OAuth flow (required before first publish)
python cli.py authorize

# Publish due drafts (respects posting_cadence.yaml windows)
python cli.py publish
```

### Observability

```bash
# Daily health check: activity events, stuck drafts, OAuth expiry, pipeline errors
python cli.py health-check

# Interactive performance review: log impressions/reactions, get optimization suggestions
python cli.py weekly-review
```

### Running the Daemon

```bash
# Full APScheduler daemon (blocking, runs all jobs on schedule: watchers every 30min, digest at 21:00, etc.)
python orchestrator.py
```

## Testing

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_content_queue.py

# Run a single test
pytest tests/test_agent_graph.py::test_no_activity

# Run with verbose output + show print statements
pytest -vv -s tests/test_agent_graph.py

# Run tests matching pattern (e.g., all "pillar" tests)
pytest -k pillar

# Run with coverage report
pytest --cov=. --cov-report=html tests/
```

**Test isolation pattern:** Tests redirect the database via `DATABASE_PATH` env var to a temp file in `tests/`. Fixtures must delete WAL sidecars (`.db-wal`, `.db-shm`) in both setup and teardown. See `tests/test_content_queue.py` for canonical fixture pattern.

**Common fixture setup:**
```python
@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    init_db()
    yield
    # cleanup
    for f in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
```

## Architecture

### Data Flow (Pipeline)

```
Activity Sources (GitHub, Notion, Browser, Files)
     ↓ [30-min watchers, 8-23 local]
activity_events (SQLite)
     ↓ [daily at 21:00 local]
daily_digests (SQLite)
     ↓ [LangGraph 5-node pipeline]
drafts (status=pending_review)
     ↓ [user approve via CLI/Telegram]
content_queue (status=queued, scheduled_time calculated)
     ↓ [publisher tick every 15 min]
published_posts (LinkedIn_post_urn)
     ↓ [weekly manual feedback loop]
performance_log (impressions, reactions, etc.)
```

### LangGraph Pipeline (generator/agent_graph.py)

**StateGraph with PipelineState (TypedDict):** date, digest, pillar, format_type, persona_context, drafts, status, error

**5-Node Flow:**

1. **aggregate_digest** — Queries daily_digests for date, reuses if found (idempotent), else calls Claude summarization
2. **classify_pillar** — Routes: no_activity → END | pillar found → select_format
3. **select_format** — Claude picks format (text/image/carousel/video/long_form/poll), routes: format found → retrieve_persona_context | none → END
4. **retrieve_persona_context** — LanceDB semantic search on highlights (fallback: empty string if LanceDB down)
5. **generate_drafts** — Claude generates 1+ variants per format, inserts into drafts table with status=pending_review

**All Claude calls use `output_config={"format": {"type": "json_schema", "schema": {...}}}`** for type-safe responses. Models: claude-sonnet-4-6 (generation), claude-opus-4-6 (weekly review).

### Key State Transitions

**Draft Status Lifecycle:**
- pending_review → (user action) → approved → (scheduler picks up) → publishing → published
- Or: pending_review → skipped, or editing → new variant created

**Idempotency Patterns:**
- Digest: checks if exists for date, reuses (UNIQUE(date, version))
- Activity capture: deduplicates by source-specific ID (GitHub event ID, Notion page + timestamp, browser URL)
- Publishing: 2-phase commit (status='publishing' acts as lock, reconcile_stuck_publishes moves orphaned drafts to needs_manual_check after 5 min)

### Database Schema Highlights

- **activity_events** — Raw captures (source: git|note|browser|file|calendar|email, event_time UTC, JSON detail)
- **daily_digests** — Versioned summaries (date, version, raw_summary, highlights_json, suggested_pillar)
- **drafts** — Generated posts (status: pending_review|approved|publishing|published|failed|needs_manual_check)
- **content_queue** — Publishing queue (scheduled_time UTC, priority_score, status: queued|publishing|published|rolled)
- **published_posts** — LinkedIn/Twitter mappings (draft_id FK, linkedin_post_urn UNIQUE)
- **oauth_token_meta** — Token expiry tracking (actual tokens in OS keyring, not DB)
- **pipeline_runs** — Execution traces (component, status, error_message, timestamps)

**All timestamps in UTC ISO8601, converted to LOCAL_TIMEZONE for display.**

### Configuration Files (YAML + Markdown)

- **config/pillars.yaml** — Content pillar enum (technical_insight, project_milestone, lesson_learned, industry_commentary) with descriptions
- **config/posting_cadence.yaml** — Max 2 posts/weekday, 1 post/weekend, min 3h between, 3 windows (08:00-10:30, 12:00-13:30, 17:00-19:00)
- **config/exclusions.yaml** — Excluded apps, domains, calendar patterns, folders (safe-fail: defaults to excluded if parse fails)
- **config/voice_profile.md** — Tone, formatting rules, tech stack refs, emoji limits. Hashed (SHA-256) in drafts.voice_profile_hash to track version

## Development Patterns

### Adding a New Activity Watcher

1. Create `capture/new_watcher.py` with a `run()` function that returns list of dicts: `[{"source": "...", "event_time": ISO8601_UTC, "title": str, "detail": JSON_dict}, ...]`
2. Deduplicate by storing source-specific IDs in JSON detail (e.g., `"id": GitHub event ID`)
3. Check dedup with: `SELECT COUNT(*) FROM activity_events WHERE JSON_EXTRACT(detail, '$.id') = ?`
4. Add to `orchestrator.py` `run_capture_watchers()` IntervalTrigger
5. Add exclusion filters in `config/exclusions.yaml` if needed
6. Add test in `tests/test_<watcher>.py` with fixture for isolated DB

### Modifying the LangGraph Pipeline

1. Edit `generator/agent_graph.py` — add nodes, routing, state fields
2. Add supporting module in `generator/` (e.g., `generator/new_classifier.py`)
3. **Critical:** Maintain idempotency (check before insert, don't re-run Claude if state exists)
4. Update `PipelineState` TypedDict if adding state fields
5. Test in `tests/test_agent_graph.py` with mocked Claude responses

### Publishing Logic Changes

- **Scheduling:** Edit `generator/draft_generator.py` `approve_draft()` for cadence rules
- **LinkedIn API:** Edit `publisher/linkedin_client.py` (token refresh in `publisher/oauth.py`)
- **Error handling:** Add to `publisher/scheduler.py` `publish_due_drafts()` for retry logic / LinkedIn 426 version sunset handling

### Telegram Bot Modifications

- **Handlers:** Edit `notification/telegram_bot.py` (async handlers for callbacks, state in `notification/state.py`)
- **Formatting:** Edit `notification/telegram_channel.py` `draft_message()` for notification format
- **Persistence:** Store critical state in SQLite pending_reviews table, not in-memory dicts

## Critical Patterns to Preserve

1. **2-Phase Commit for Publishing** — Mark draft status='publishing' BEFORE LinkedIn API call (prevents double-post if scheduler crashes)
2. **Idempotent Digest Aggregation** — Always check for existing digest before re-generating (UNIQUE(date, version))
3. **Timezone Correctness** — Store all timestamps in UTC, convert to LOCAL_TIMEZONE only for display/scheduling
4. **Graceful Degradation** — LanceDB down? Fall back to empty persona_context. Claude JSON malformed? Return error, route to END.
5. **Structured Output (JSON Schema)** — All Claude calls use `output_config={"format": {"type": "json_schema", ...}}`, no fragile string parsing

## Troubleshooting

**Draft generation slow:** Check if LanceDB is indexing persona vault (python cli.py persona-ingest), or if Claude calls are failing silently (check pipeline_runs table).

**"address already in use" on headroom proxy:** Another Claude Code session is running. Restart that session or change port.

**Telegram notifications not arriving:** Check TELEGRAM_BOT_TOKEN is valid, TELEGRAM_ALLOWED_USER_IDS includes your user ID. Test with `python -c "from notification.telegram_channel import TelegramChannel; TelegramChannel().send_text('test')"`.

**Publishing stuck at 'publishing' status:** Run `python cli.py health-check` to detect stuck drafts. If orphaned, manually update: `sqlite3 linkedin_agent.db "UPDATE drafts SET status='needs_manual_check' WHERE status='publishing' AND updated_at < datetime('now', '-5 minutes');"`.

**No activity captured today:** Check watchers are enabled in orchestrator.py, OAuth tokens valid (linkedin_agent_oauth tokens in keyring), and files/Notion/GitHub have recent edits.

**LanceDB embedding errors:** Ensure OPENAI_API_KEY is set and OpenAI text-embedding-3-small model is available. Regenerate: `rm data/persona_db.lance && python cli.py persona-ingest`.

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
| `generator/media_handler.py` | Resolves media files; generates matplotlib activity charts; orchestrates Remotion video renders |
| `generator/visual_selector.py` | Keyword-based selector that maps digest content to a Remotion composition ID or matplotlib fallback |
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

The pipeline uses a `StateGraph` with `PipelineState` (TypedDict). 6 nodes total:

1. `aggregate_digest` → routes to `classify_pillar` if digest exists, else `END`
2. `classify_pillar` → routes to `select_format` if pillar != `"none"`, else `END`
3. `select_format` → routes to `retrieve_persona_context` (on failure → `END`)
4. `retrieve_persona_context` → `generate_drafts`
5. `generate_drafts` → `generate_visual`
6. `generate_visual` → `END`

`compiled_graph` is a **module-level singleton** — importing `generator.agent_graph` triggers compilation. All Claude calls use `output_config={"format": {"type": "json_schema", "schema": ...}}` for structured output (not tool use). Poll drafts use a different schema with `poll_question`, `poll_options`, and `poll_duration` fields.

### Remotion video generation

`generate_visual_node` calls `generator/media_handler.py:generate_remotion_video()` which:
1. Calls `generator/visual_selector.py:select_visual_type()` — keyword-scores the digest summary against four composition rules (`StateMachineAnimation`, `PipelineFlowAnimation`, `ArchitectureRevealAnimation`, `MetricsSummaryAnimation`) to pick the best match
2. Calls `build_remotion_props()` — Claude structured-output call that extracts animation-specific props (states, stages, components, metrics) matching the composition's JSON schema
3. Writes props to a temp JSON file and runs `npx remotion render src/index.ts <composition> <output>` inside `remotion/` (120s timeout)
4. Falls back to a matplotlib activity chart if Remotion returns no file

The React/TypeScript compositions live in `remotion/src/`. To develop them run `npm run studio` inside `remotion/` (requires Node.js).

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
