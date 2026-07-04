import click
import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from db.db import init_db, get_db_connection


@click.group()
def main():
    """LinkedIn Content Agent CLI - Track A"""
    pass


@main.command("db-init")
@click.option("--db-path", type=click.Path(), help="Custom SQLite database file path")
@click.option(
    "--schema-path", type=click.Path(exists=True), help="Path to schema.sql file"
)
def db_init(db_path, schema_path):
    """Initialize the SQLite database schema."""
    db_p = Path(db_path) if db_path else None
    schema_p = Path(schema_path) if schema_path else None

    click.echo("Initializing database...")
    try:
        init_db(schema_path=schema_p, db_path=db_p)
        click.echo("Database initialized successfully.")
    except Exception as e:
        click.echo(f"Error initializing database: {e}", err=True)


@main.command("seed-fake-events")
def seed_fake_events():
    """Populate activity_events with sample raw activities for testing."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Generate 5 days of events relative to today
    today = datetime.datetime.now(datetime.timezone.utc)

    # We will seed events for the last 5 days
    click.echo("Seeding mock activity events...")

    sample_events = [
        # Day -4 (4 days ago)
        {
            "days_ago": 4,
            "source": "calendar",
            "time_offset_hours": 10,  # 10:00 UTC approx
            "title": "Architecture Sync: Database Migration Plan",
            "detail": {
                "duration_minutes": 60,
                "attendees_count": 5,
                "organizer": "Vamsi",
            },
        },
        {
            "days_ago": 4,
            "source": "git",
            "time_offset_hours": 14,
            "title": "git commit: refactor schema setup to use foreign keys and WAL mode",
            "detail": {
                "repo": "agent-echo",
                "commit_hash": "a1b2c3d",
                "files_changed": ["db/schema.sql", "db/db.py"],
            },
        },
        {
            "days_ago": 4,
            "source": "note",
            "time_offset_hours": 18,
            "title": "Work log: finalized db schema design and verified WAL performance gains",
            "detail": {"category": "dev_log", "priority": "high"},
        },
        # Day -3
        {
            "days_ago": 3,
            "source": "calendar",
            "time_offset_hours": 11,
            "title": "weekly demo: team milestone showcase",
            "detail": {
                "duration_minutes": 45,
                "attendees_count": 12,
                "organizer": "Product Team",
            },
        },
        {
            "days_ago": 3,
            "source": "file",
            "time_offset_hours": 15,
            "title": "file edited: aggregator/daily_digest.py",
            "detail": {
                "project": "agent-echo",
                "lines_added": 120,
                "lines_removed": 15,
            },
        },
        {
            "days_ago": 3,
            "source": "note",
            "time_offset_hours": 19,
            "title": "Work log: implemented Claude structured outputs using output_config format",
            "detail": {
                "category": "dev_log",
                "notes": "Got 100% valid JSON responses from Claude. Very reliable.",
            },
        },
        # Day -2
        {
            "days_ago": 2,
            "source": "calendar",
            "time_offset_hours": 14,
            "title": "Client Review: Feed integration demo",
            "detail": {"duration_minutes": 30, "attendees_count": 3},
        },
        {
            "days_ago": 2,
            "source": "git",
            "time_offset_hours": 16,
            "title": "git commit: feat: integrate Telegram bot for review prompts",
            "detail": {
                "repo": "agent-echo",
                "commit_hash": "c4d5e6f",
                "files_changed": [
                    "notification/router.py",
                    "notification/telegram_channel.py",
                ],
            },
        },
        {
            "days_ago": 2,
            "source": "note",
            "time_offset_hours": 17,
            "title": "Work log: resolved telegram callback debouncing issues on click reviews",
            "detail": {"category": "debugging"},
        },
        # Day -1 (Yesterday)
        {
            "days_ago": 1,
            "source": "file",
            "time_offset_hours": 9,
            "title": "file edited: publisher/linkedin_client.py",
            "detail": {"project": "agent-echo", "lines_added": 85, "lines_removed": 5},
        },
        {
            "days_ago": 1,
            "source": "git",
            "time_offset_hours": 13,
            "title": "git commit: fix: handle 426 upgrade sunset in linkedin publishing lifecycle",
            "detail": {
                "repo": "agent-echo",
                "commit_hash": "f7g8h9i",
                "files_changed": ["publisher/linkedin_client.py"],
            },
        },
        {
            "days_ago": 1,
            "source": "note",
            "time_offset_hours": 20,
            "title": "Work log: fixed a tricky race condition where posts could get double published if scheduler restarted during upload",
            "detail": {"category": "bug_fix", "urgency": "high"},
        },
        # Day 0 (Today)
        {
            "days_ago": 0,
            "source": "calendar",
            "time_offset_hours": 10,
            "title": "Sync: LinkedIn Agent Release Planning",
            "detail": {"duration_minutes": 30, "attendees_count": 4},
        },
        {
            "days_ago": 0,
            "source": "git",
            "time_offset_hours": 12,
            "title": "git commit: test: add test coverage for content queue priority rollover",
            "detail": {
                "repo": "agent-echo",
                "commit_hash": "t1u2v3w",
                "files_changed": ["tests/test_content_queue.py"],
            },
        },
        {
            "days_ago": 0,
            "source": "note",
            "time_offset_hours": 15,
            "title": "Work log: completed local dry-run validation with click CLI.",
            "detail": {"category": "milestone"},
        },
    ]

    for ev in sample_events:
        event_date = today - datetime.timedelta(days=ev["days_ago"])
        event_time = event_date.replace(
            hour=ev["time_offset_hours"], minute=0, second=0, microsecond=0
        )
        iso_time = event_time.isoformat()

        cursor.execute(
            "INSERT INTO activity_events (source, event_time, title, detail) VALUES (?, ?, ?, ?)",
            (ev["source"], iso_time, ev["title"], json.dumps(ev["detail"])),
        )

    conn.commit()
    conn.close()
    click.echo("Successfully seeded database with mock activity events.")


@main.command("seed-sfx")
def seed_sfx():
    """Generate programmatic pop/whoosh/tick/shimmer sound effects."""
    click.echo("Generating SFX library...")
    from generator.audio_engine import generate_sfx_library
    try:
        generate_sfx_library()
        click.echo("SFX library generated successfully.")
    except Exception as e:
        click.echo(f"Error generating SFX library: {e}", err=True)


@main.command("test-audio")
@click.option("--text", help="Custom text script to synthesize")
def test_audio(text):
    """Test ElevenLabs voiceover narration from a technical script."""
    click.echo("Running test voiceover audio generation...")
    from generator.audio_engine import VOICES, select_voice_profile, synthesize_voiceover
    import os
    
    script = text
    if not script:
        script = (
            "Optimized database query latency and Postgres throughput. "
            "Improved the p99 transaction response time from 500 milliseconds down to 120 milliseconds "
            "using robust database connection pooling."
        )
    
    click.echo(f"Voiceover script: \"{script}\"")
    out_path = "data/audio/test_audition.mp3"
    try:
        # Dynamically select the best voice profile
        mock_digest = {
            "summary": "Optimized database query latency and Postgres throughput with connection pooling.",
            "pillar": "technical_insight"
        }
        click.echo("Invoking dynamic voice selector agent (Claude)...")
        voice_id = select_voice_profile("MetricsSummaryAnimation", mock_digest, script)
        
        voice_name = "Unknown"
        for name, info in VOICES.items():
            if info["id"] == voice_id:
                voice_name = name
                break
                
        click.echo(f"Dynamic Selector chose voice: {voice_name} (ID: {voice_id})")
        
        duration, _ = synthesize_voiceover(script, out_path, voice_id=voice_id)
        click.echo(f"Voiceover generated successfully at: {os.path.abspath(out_path)}")
        click.echo(f"Audio duration: {duration:.2f} seconds.")
    except Exception as e:
        click.echo(f"Error generating voiceover: {e}", err=True)


@main.command("digest")
@click.option("--date", help="Target date in YYYY-MM-DD format (defaults to yesterday)")
def digest_cmd(date):
    """Aggregate raw activity events and generate a daily digest."""
    if not date:
        from config_loader import LOCAL_TZ

        now_local = datetime.datetime.now(LOCAL_TZ)
        date_key = (now_local - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_key = date

    click.echo(f"Running digest for date: {date_key}...")
    from generator.agent_graph import aggregate_digest_node

    try:
        initial_state = {
            "date": date_key,
            "digest": None,
            "pillar": None,
            "secondary_pillar": None,
            "format_type": None,
            "persona_context": None,
            "drafts": [],
            "status": "started",
            "error": None,
        }
        result = aggregate_digest_node(initial_state)

        if result.get("status") == "success" and result.get("digest"):
            digest_row = result["digest"]
            click.echo(
                f"Daily digest generated (ID: {digest_row['id']}, Date: {digest_row['date']}, Pillar: {digest_row['suggested_pillar']})"
            )
            click.echo(f"Highlights: {digest_row['highlights_json']}")
        else:
            click.echo(
                f"Digest skipped or failed. Status: {result.get('status')} | Error: {result.get('error') or 'No activity events found'}"
            )
    except Exception as e:
        click.echo(f"Error during digest: {e}", err=True)


@main.command("generate")
@click.option("--date", help="Target date in YYYY-MM-DD format (defaults to yesterday)")
def generate_cmd(date):
    """Generate drafts from a daily digest."""
    click.echo(f"Generating drafts for date: {date or 'yesterday'}...")
    from generator.draft_generator import generate_drafts_for_date

    try:
        drafts = generate_drafts_for_date(date_str=date)
        if drafts:
            click.echo(f"Generated {len(drafts)} drafts:")
            for d in drafts:
                click.echo(
                    f"  - Draft ID: {d['id']} | Pillar: {d['pillar']} | Format: {d['format_type']}"
                )
        else:
            click.echo("No digest found or no drafts generated.")
    except Exception as e:
        click.echo(f"Error during draft generation: {e}", err=True)


@main.command("review")
@click.option("--approve", type=int, help="Approve draft by ID")
@click.option("--skip", type=int, help="Skip/reject draft by ID")
@click.option(
    "--edit",
    nargs=2,
    type=(int, str),
    help="Provide custom instruction to edit a draft (args: draft_id, instruction)",
)
def review_cmd(approve, skip, edit):
    """View and manage drafts pending review."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if approve:
        click.echo(f"Approving draft {approve}...")
        from generator.draft_generator import approve_draft

        try:
            approve_draft(approve)
            click.echo("Draft approved and scheduled.")
        except Exception as e:
            click.echo(f"Error approving draft: {e}", err=True)

    elif skip:
        click.echo(f"Rejecting draft {skip}...")
        try:
            cursor.execute(
                "UPDATE drafts SET status='rejected', updated_at=datetime('now') WHERE id=?",
                (skip,),
            )
            conn.commit()
            click.echo("Draft rejected.")
        except Exception as e:
            click.echo(f"Error rejecting draft: {e}", err=True)

    elif edit:
        draft_id, instruction = edit
        click.echo(f"Editing draft {draft_id} with instruction: '{instruction}'...")
        from generator.draft_generator import edit_draft

        try:
            new_draft = edit_draft(draft_id, instruction)
            click.echo(
                f"New draft variant generated (ID: {new_draft['id']}). Review it via review command."
            )
        except Exception as e:
            click.echo(f"Error editing draft: {e}", err=True)

    else:
        # List all pending drafts
        cursor.execute(
            "SELECT id, pillar, format_type, text_content, created_at FROM drafts WHERE status='pending_review'"
        )
        rows = cursor.fetchall()
        if not rows:
            click.echo("No drafts pending review.")
        else:
            for r in rows:
                click.echo(
                    f"\n========================================\nDraft ID: {r['id']} | Pillar: {r['pillar']} | Format: {r['format_type']} | Created: {r['created_at']}"
                )
                click.echo("----------------------------------------")
                click.echo(r["text_content"])
                click.echo("========================================\n")
    conn.close()


@main.command("publish")
@click.option(
    "--dry-run",
    is_flag=True,
    default=None,
    help="Force dry run (bypasses .env setting)",
)
def publish_cmd(dry_run):
    """Run publisher tick to schedule and post due drafts."""
    if dry_run is not None:
        os.environ["DRY_RUN"] = "true" if dry_run else "false"
    is_dry = os.getenv("DRY_RUN", "true").lower() == "true"
    click.echo(f"Running publisher tick (DRY_RUN={is_dry})...")

    from publisher.scheduler import run_publisher_tick

    try:
        run_publisher_tick()
        click.echo("Publisher tick completed.")
    except Exception as e:
        click.echo(f"Error during publishing: {e}", err=True)


@main.command("health-check")
def health_check_cmd():
    """Verify system health, DB connections, key stores, and queue status."""
    click.echo("Running daily health check...")
    from observability.health_check import run_health_check

    try:
        health_summary = run_health_check()
        click.echo(health_summary)
    except Exception as e:
        click.echo(f"Health check failed: {e}", err=True)


@main.command("persona-ingest")
def persona_ingest_cmd():
    """Chunk and index text/markdown files in data/persona_vault/ into LanceDB."""
    click.echo("Starting Persona Vault ingestion...")
    vault_dir = Path("data/persona_vault")
    if not vault_dir.exists():
        click.echo("Error: data/persona_vault/ directory does not exist.", err=True)
        return

    files = list(vault_dir.glob("*.txt")) + list(vault_dir.glob("*.md"))
    if not files:
        click.echo("No .txt or .md files found in data/persona_vault/.")
        return

    from db.vector_db import init_vector_table, add_persona_chunks

    click.echo("Initializing vector database table...")
    try:
        init_vector_table()
    except Exception as e:
        click.echo(f"Failed to initialize database: {e}", err=True)
        return

    chunks = []
    for fpath in files:
        click.echo(f"Processing {fpath.name}...")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            # Split content into paragraph chunks
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

            # Categorize loosely based on filename
            category = "general"
            if "resume" in fpath.name.lower() or "cv" in fpath.name.lower():
                category = "experience"
            elif "style" in fpath.name.lower() or "post" in fpath.name.lower():
                category = "style"
            elif "opinion" in fpath.name.lower() or "taste" in fpath.name.lower():
                category = "opinions"

            for p in paragraphs:
                chunks.append({"text": p, "source": fpath.name, "category": category})
        except Exception as e:
            click.echo(f"Error reading {fpath.name}: {e}", err=True)

    if not chunks:
        click.echo("No content chunks found to index.")
        return

    click.echo(f"Generating embeddings for {len(chunks)} text chunks...")
    try:
        add_persona_chunks(chunks)
        click.echo("Successfully indexed and stored all persona context in LanceDB.")
    except Exception as e:
        click.echo(f"Error generating/storing embeddings: {e}", err=True)


@main.command("authorize")
def authorize_cmd():
    """Run interactive 3-legged OAuth flow to connect your LinkedIn account."""
    click.echo("Initiating LinkedIn OAuth flow...")
    from publisher.oauth import get_auth_url, exchange_code_for_token, save_token_meta
    from publisher.linkedin_client import store_tokens

    try:
        auth_url, state = get_auth_url()
    except Exception as e:
        click.echo(f"Initialization failed: {e}", err=True)
        return

    click.echo(
        "\n1. Open the following URL in your web browser and authorize the application:"
    )
    click.echo(f"\n   {auth_url}\n")
    click.echo(
        "2. After authorizing, you will be redirected to localhost (which will fail to load or show a blank page)."
    )
    click.echo(
        "3. Copy the entire redirect URL from your browser's address bar or just the 'code' query parameter."
    )

    redirect_input = click.prompt(
        "\nPaste the redirect URL or authorization code here"
    ).strip()

    # Parse the authorization code
    code = redirect_input
    if "code=" in redirect_input:
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(redirect_input)
            params = parse_qs(parsed.query)
            if "code" in params:
                code = params["code"][0]
            else:
                click.echo(
                    "Error: Could not extract authorization 'code' from the URL.",
                    err=True,
                )
                return
        except Exception as e:
            click.echo(f"Error parsing redirect URL: {e}", err=True)
            return

    click.echo("Exchanging authorization code for tokens...")
    try:
        resp = exchange_code_for_token(code)
        access_token = resp["access_token"]
        refresh_token = resp.get("refresh_token")

        # Save tokens in Keyring
        store_tokens(access_token, refresh_token or "")

        # Save token meta in SQLite
        expires_in = resp["expires_in"]
        refresh_token_expires_in = resp.get("refresh_token_expires_in")
        save_token_meta(expires_in, refresh_token_expires_in)

        click.echo("\nAuthorization successful!")
        click.echo(f"Access token saved. Expires in {expires_in // 86400} days.")
        if refresh_token:
            click.echo(
                f"Refresh token saved. Expires in {refresh_token_expires_in // 86400} days."
            )
        else:
            click.echo(
                "Warning: No refresh token returned. Long-term automatic updates may require re-auth."
            )

        # Try to resolve member URN
        try:
            from publisher.linkedin_client import get_my_member_urn

            member_urn = get_my_member_urn()
            click.echo(f"\nLinkedIn Member URN: {member_urn}")
            click.echo("Please add the following to your .env file:")
            click.echo(f"LINKEDIN_AUTHOR_URN={member_urn}")
        except Exception as urn_err:
            click.echo(f"\nWarning: Could not fetch Member URN: {urn_err}")
    except Exception as e:
        click.echo(f"Failed to complete authorization: {e}", err=True)


@main.command("weekly-review")
def weekly_review_cmd():
    """Prompt for metrics on recently published posts and get performance insights."""
    from feedback.weekly_review import (
        prompt_post_performance,
        analyze_performance_and_reweight,
    )

    prompt_post_performance()
    click.echo("\nRunning performance analysis...")
    analyze_performance_and_reweight()


@main.command("run-pipeline")
@click.option("--date", help="Target date in YYYY-MM-DD format (defaults to today)")
def run_pipeline_cmd(date):
    """Run the end-to-end activity capture, digest aggregation, draft generation, and review dispatch."""
    from config_loader import LOCAL_TZ

    if not date:
        date_str = datetime.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    else:
        date_str = date

    click.echo(f"1. Scanning and capturing activities...")
    from orchestrator import run_capture_watchers

    try:
        run_capture_watchers()
        click.echo("Capture completed.")
    except Exception as e:
        click.echo(f"Warning/Error capturing activities: {e}")

    click.echo(
        f"\n2. Running digest aggregation and draft generation for {date_str}..."
    )
    try:
        if date:
            from generator.draft_generator import generate_drafts_for_date
            from notification.router import get_default_router

            drafts = generate_drafts_for_date(date_str)
            click.echo(f"Pipeline finished. Generated {len(drafts)} draft(s).")
            if drafts:
                router = get_default_router()
                from notification.telegram_channel import escape_markdown

                for draft in drafts:
                    escaped_pillar = escape_markdown(draft["pillar"])
                    escaped_format = escape_markdown(draft["format_type"])
                    escaped_text = escape_markdown(draft["text_content"])
                    escaped_hashtags = escape_markdown(draft.get("hashtags") or "")
                    msg = (
                        f"📝 *New Draft Generated* (ID: {draft['id']})\n"
                        f"Pillar: {escaped_pillar}\n"
                        f"Format: {escaped_format}\n"
                        f"----------------------------------------\n"
                        f"{escaped_text}"
                    )
                    if escaped_hashtags:
                        msg += f"\n\n{escaped_hashtags}"
                    actions = [
                        f"approve_{draft['id']}",
                        f"edit_{draft['id']}",
                        f"skip_{draft['id']}",
                    ]
                    router.send(msg, actions)
        else:
            from orchestrator import run_daily_pipeline

            run_daily_pipeline()
            click.echo(
                "Pipeline completed. Drafts dispatched to configured notification channels."
            )
    except Exception as e:
        click.echo(f"Error running pipeline: {e}", err=True)


@main.command("telegram-bot")
def telegram_bot_cmd():
    """Run the Telegram review bot listener in the foreground."""
    click.echo("Starting Telegram bot listener...")
    try:
        from notification.telegram_bot import run_telegram_bot_foreground

        run_telegram_bot_foreground()
    except Exception as e:
        click.echo(f"Failed to start Telegram bot: {e}", err=True)


if __name__ == "__main__":
    main()
