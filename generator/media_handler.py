import os
import json
import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from db.db import get_db_connection
from config_loader import LOCAL_TZ

SCREENSHOTS_DIR = Path("data/screenshots")
MEDIA_DIR = Path("data/media")

def get_available_media(date_str: str) -> list[str]:
    """
    Scans the screenshots directory for files starting with YYYY-MM-DD.
    Returns absolute paths of matching image/video files.
    """
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = []
    # Find matching files
    for filepath in SCREENSHOTS_DIR.glob(f"{date_str}_*"):
        if filepath.suffix.lower() in (".png", ".jpg", ".jpeg", ".mp4", ".mov", ".avi", ".mkv"):
            matches.append(str(filepath.resolve()))
    return sorted(matches)

def generate_activity_chart(date_str: str) -> str | None:
    """
    Queries SQLite for activity counts on the target date,
    generates a premium activity summary chart using matplotlib,
    saves it to data/media/, and returns its absolute path.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Calculate timezone bounds for target date
    try:
        local_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
        
    start_local = datetime.datetime.combine(local_date, datetime.time.min, tzinfo=LOCAL_TZ)
    end_local = datetime.datetime.combine(local_date, datetime.time.max, tzinfo=LOCAL_TZ)
    start_utc = start_local.astimezone(datetime.timezone.utc)
    end_utc = end_local.astimezone(datetime.timezone.utc)
    start_iso = start_utc.isoformat()
    end_iso = end_utc.isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query count of different activity sources
    cursor.execute(
        "SELECT source, COUNT(*) as count FROM activity_events "
        "WHERE event_time >= ? AND event_time <= ? GROUP BY source",
        (start_iso, end_iso)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
        
    sources = []
    counts = []
    
    # Map sources to nice labels
    label_map = {
        "git": "GitHub Commits/PRs",
        "note": "Notion Edits",
        "browser": "Research Tabs",
        "calendar": "Meetings/Events",
        "file": "Local File Edits"
    }
    
    for r in rows:
        src = r["source"]
        label = label_map.get(src, src.capitalize())
        sources.append(label)
        counts.append(r["count"])
        
    # Generate Chart
    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    
    # Custom harmonious color palette
    colors = ['#0077b5', '#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b'][:len(sources)]
    
    y_pos = np.arange(len(sources))
    bars = ax.barh(y_pos, counts, align='center', color=colors, height=0.55)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(sources, fontsize=10, fontweight='bold', color='#333333')
    ax.invert_yaxis()  # top-down
    
    ax.set_xlabel('Count of Activities', fontsize=10, fontweight='bold', color='#555555')
    ax.set_title(f'Developer Activity Breakdown — {date_str}', fontsize=12, fontweight='bold', color='#111111', pad=15)
    
    # Style tweaks
    ax.set_facecolor('#fdfdfd')
    fig.patch.set_facecolor('#ffffff')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cccccc')
    ax.spines['bottom'].set_color('#cccccc')
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    
    # Add values on the bar tips
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + 0.1, 
            bar.get_y() + bar.get_height()/2, 
            f' {int(width)}', 
            va='center', 
            ha='left', 
            fontsize=10, 
            fontweight='bold',
            color='#333333'
        )
        
    plt.tight_layout()
    
    output_path = MEDIA_DIR / f"{date_str}_activity_chart.png"
    plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close()
    
    return str(output_path.resolve())
