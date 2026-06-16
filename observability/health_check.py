import datetime
from db.db import get_db_connection

def run_health_check() -> str:
    """
    Runs health audits on the database tables:
    1. Checks if at least one activity_event was recorded in the last 24 hours.
    2. Checks for any drafts stuck in 'publishing' or 'needs_manual_check'.
    3. Checks for any drafts pending review for more than 24 hours.
    4. Audits the last 24 hours of pipeline_runs for failures.
    5. Audits OAuth token expiration metadata.
    
    Returns a formatted markdown summary.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    issues = []
    statuses = []
    
    # 1. Activity Capture Check
    cursor.execute(
        "SELECT COUNT(*) FROM activity_events WHERE event_time >= datetime('now', '-24 hours')"
    )
    recent_events_count = cursor.fetchone()[0]
    if recent_events_count == 0:
        issues.append("⚠️ No activity events recorded in the last 24 hours. Check source watchers.")
    else:
        statuses.append(f"✅ Activity Capture: {recent_events_count} events recorded in last 24h.")
        
    # 2. Drafts Stuck Check
    cursor.execute(
        "SELECT COUNT(*) FROM drafts WHERE status = 'publishing'"
    )
    publishing_count = cursor.fetchone()[0]
    if publishing_count > 0:
        issues.append(f"⚠️ {publishing_count} draft(s) currently in 'publishing' status. Check if stuck.")
        
    cursor.execute(
        "SELECT COUNT(*) FROM drafts WHERE status = 'needs_manual_check'"
    )
    manual_check_count = cursor.fetchone()[0]
    if manual_check_count > 0:
        issues.append(f"🚨 {manual_check_count} draft(s) marked 'needs_manual_check'. Verify on LinkedIn.")
    else:
        statuses.append("✅ Draft State Integrity: No drafts stuck mid-publish.")
        
    # 3. Aging Review Check
    cursor.execute(
        "SELECT COUNT(*) FROM drafts WHERE status = 'pending_review' "
        "AND created_at < datetime('now', '-24 hours')"
    )
    aging_reviews_count = cursor.fetchone()[0]
    if aging_reviews_count > 0:
        issues.append(f"⚠️ {aging_reviews_count} draft(s) have been pending review for >24 hours.")
        
    # 4. Pipeline Failures Check
    cursor.execute(
        "SELECT component, error_message FROM pipeline_runs "
        "WHERE status = 'failed' AND started_at >= datetime('now', '-24 hours')"
    )
    failed_runs = cursor.fetchall()
    if failed_runs:
        for run in failed_runs:
            issues.append(f"🚨 Pipeline failure in '{run['component']}': {run['error_message']}")
    else:
        statuses.append("✅ Pipeline Runs: No pipeline component failures in the last 24h.")
        
    # 5. OAuth Expiration Check
    cursor.execute(
        "SELECT expires_at FROM oauth_token_meta ORDER BY refreshed_at DESC LIMIT 1"
    )
    token_row = cursor.fetchone()
    if token_row:
        try:
            expires_at = datetime.datetime.fromisoformat(token_row["expires_at"])
            remaining = expires_at - datetime.datetime.now(datetime.timezone.utc)
            if remaining.days < 7:
                issues.append(f"🚨 LinkedIn access token expires in {remaining.days} days! Re-authenticate soon.")
            else:
                statuses.append(f"✅ OAuth Credentials: Active token valid for {remaining.days} days.")
        except Exception:
            issues.append("⚠️ Could not parse OAuth token expiration metadata.")
    else:
        # If no token metadata is in database yet, warn but do not error out for Phase 0.5 dry-run
        statuses.append("ℹ️ OAuth Credentials: No token metadata found in DB (running in dry-run mode).")
        
    conn.close()
    
    # Format Health Report
    report = ["=== LinkedIn Content Agent Health Report ==="]
    if statuses:
        report.append("\nSystem Status:")
        report.extend([f"  {s}" for s in statuses])
    if issues:
        report.append("\nActive Issues / Warnings:")
        report.extend([f"  {i}" for i in issues])
    else:
        report.append("\n✅ All systems nominal. No issues detected.")
        
    return "\n".join(report)
