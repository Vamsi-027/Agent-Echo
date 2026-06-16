import json
import logging
from db.db import get_db_connection
from config_loader import load_pillars
from anthropic import Anthropic

logger = logging.getLogger("linkedin-agent.feedback")

def prompt_post_performance() -> None:
    """
    Finds published posts missing performance records,
    and prompts the user via console input to record metrics.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query published posts without logs
    cursor.execute(
        "SELECT p.linkedin_post_urn, p.published_at, d.text_content, d.pillar, d.format_type "
        "FROM published_posts p "
        "JOIN drafts d ON p.draft_id = d.id "
        "LEFT JOIN performance_log pl ON p.linkedin_post_urn = pl.linkedin_post_urn "
        "WHERE pl.id IS NULL "
        "ORDER BY p.published_at ASC"
    )
    rows = cursor.fetchall()
    
    if not rows:
        print("\nAll published posts already have performance metrics recorded.")
        conn.close()
        return
        
    print(f"\nFound {len(rows)} published post(s) missing performance logs:")
    
    for row in rows:
        urn = row["linkedin_post_urn"]
        published_at = row["published_at"]
        pillar = row["pillar"]
        format_type = row["format_type"]
        text_snippet = (row["text_content"][:100] + "...") if len(row["text_content"]) > 100 else row["text_content"]
        
        print("\n" + "=" * 50)
        print(f"URN: {urn}")
        print(f"Published At: {published_at}")
        print(f"Pillar: {pillar} | Format: {format_type}")
        print(f"Snippet: {text_snippet}")
        print("-" * 50)
        
        try:
            impressions = int(input("Enter Impressions (default 0): ") or 0)
            reactions = int(input("Enter Reactions (default 0): ") or 0)
            comments = int(input("Enter Comments (default 0): ") or 0)
            reposts = int(input("Enter Reposts (default 0): ") or 0)
        except ValueError:
            print("Invalid input format. Defaulting stats to 0.")
            impressions = reactions = comments = reposts = 0
            
        cursor.execute(
            "INSERT INTO performance_log (linkedin_post_urn, impressions, reactions, comments, reposts) "
            "VALUES (?, ?, ?, ?, ?)",
            (urn, impressions, reactions, comments, reposts)
        )
        conn.commit()
        print("Performance stats logged successfully.")
        
    conn.close()

def analyze_performance_and_reweight() -> None:
    """
    Aggregates performance data, submits a summary to Claude,
    and returns optimization suggestions for future posts.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT pl.impressions, pl.reactions, pl.comments, pl.reposts, d.pillar, d.format_type "
        "FROM performance_log pl "
        "JOIN published_posts p ON pl.linkedin_post_urn = p.linkedin_post_urn "
        "JOIN drafts d ON p.draft_id = d.id"
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("\nNo performance logs found. Log metrics first using 'python cli.py weekly-review'.")
        return
        
    # Group stats by pillar and format
    pillar_stats = {}
    format_stats = {}
    
    for r in rows:
        p = r["pillar"] or "unknown"
        f = r["format_type"] or "unknown"
        
        # Pillar breakdown
        if p not in pillar_stats:
            pillar_stats[p] = {"count": 0, "impressions": 0, "reactions": 0, "comments": 0, "reposts": 0}
        pillar_stats[p]["count"] += 1
        pillar_stats[p]["impressions"] += r["impressions"]
        pillar_stats[p]["reactions"] += r["reactions"]
        pillar_stats[p]["comments"] += r["comments"]
        pillar_stats[p]["reposts"] += r["reposts"]
        
        # Format breakdown
        if f not in format_stats:
            format_stats[f] = {"count": 0, "impressions": 0, "reactions": 0, "comments": 0, "reposts": 0}
        format_stats[f]["count"] += 1
        format_stats[f]["impressions"] += r["impressions"]
        format_stats[f]["reactions"] += r["reactions"]
        format_stats[f]["comments"] += r["comments"]
        format_stats[f]["reposts"] += r["reposts"]
        
    pillars_list = load_pillars()
    
    print("\n" + "=" * 50)
    print("ANALYZING PERFORMANCE METRICS VIA CLAUDE...")
    print("=" * 50)
    
    client = Anthropic()
    
    prompt = (
        "You are an expert LinkedIn growth strategist and content optimizer.\n"
        "Here is the historical performance data of our published posts:\n\n"
        f"Pillar Stats:\n{json.dumps(pillar_stats, indent=2)}\n\n"
        f"Format Stats:\n{json.dumps(format_stats, indent=2)}\n\n"
        f"Pillars YAML Configuration:\n{json.dumps(pillars_list, indent=2)}\n\n"
        "Analyze which content pillars and formatting options generated the highest engagement (reasons, impressions, and reaction ratios).\n"
        "Provide concrete recommendations for:\n"
        "1. Which pillars to write more about (reweighting suggestions).\n"
        "2. Which formatting options work best for specific content types.\n"
        "3. Any stylistic recommendations to improve comments and interaction."
    )
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        print("\n--- Claude Optimization Report ---")
        print(response.content[0].text)
        print("----------------------------------\n")
    except Exception as e:
        logger.error(f"Claude analysis call failed: {e}", exc_info=True)
        print(f"Error querying Claude: {e}")
