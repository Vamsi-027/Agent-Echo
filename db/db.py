import sqlite3
import os
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "linkedin_agent.db"

def get_db_path() -> Path:
    """Get the path to the SQLite database file, configurable via environment."""
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH

def get_db_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Returns a SQLite connection.
    Enforces foreign keys, enables WAL mode, and returns sqlite3.Row objects.
    """
    if db_path is None:
        db_path = get_db_path()
        
    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Enforce foreign key constraints per-connection (SQLite default is OFF)
    conn.execute("PRAGMA foreign_keys = ON;")
    # Optimize performance with WAL mode
    conn.execute("PRAGMA journal_mode = WAL;")
    
    return conn

def init_db(schema_path: Path | None = None, db_path: Path | None = None) -> None:
    """Initializes the database using the provided schema.sql."""
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
        
    conn = get_db_connection(db_path)
    try:
        with open(schema_path, "r") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        
        # Perform dynamic schema updates for existing databases
        cursor = conn.cursor()
        new_columns = {
            "drafts": ["visual_composition", "music_profile", "cut_type", "scene_graph_json", "twitter_text_content"],
            "performance_log": ["visual_composition", "music_profile", "cut_type"],
            "published_posts": ["twitter_tweet_id"],
        }
        for table, cols in new_columns.items():
            cursor.execute(f"PRAGMA table_info({table});")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if existing_cols: # check if table exists
                for col in cols:
                    if col not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT;")
        
        conn.commit()
    finally:
        conn.close()
