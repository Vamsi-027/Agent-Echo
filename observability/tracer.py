import contextlib
import traceback
import datetime
from db.db import get_db_connection

@contextlib.contextmanager
def trace_pipeline_run(component_name: str):
    """
    Context manager to track pipeline execution runs in SQLite.
    Creates a pipeline_runs row on enter, and updates it on exit (success or failure).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Insert initial run metadata
    cursor.execute(
        "INSERT INTO pipeline_runs (component, status, started_at) VALUES (?, 'running', datetime('now'))",
        (component_name,)
    )
    conn.commit()
    run_id = cursor.lastrowid
    conn.close()
    
    try:
        yield
        
        # Update on success
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET status = 'success', completed_at = datetime('now') WHERE id = ?",
            (run_id,)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        # Update on failure with error message and traceback
        tb = traceback.format_exc()
        error_msg = f"{str(e)}\n{tb}"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET status = 'failed', error_message = ?, completed_at = datetime('now') WHERE id = ?",
            (error_msg, run_id)
        )
        conn.commit()
        conn.close()
        
        raise e
