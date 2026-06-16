import os
import secrets
import requests
import datetime
import logging
from db.db import get_db_connection
from publisher.linkedin_client import store_tokens, get_refresh_token

logger = logging.getLogger("linkedin-agent.publisher.oauth")

SCOPES = "openid profile email w_member_social"

def get_auth_url() -> tuple[str, str]:
    """
    Generates the LinkedIn authorization URL and a secure state string.
    Returns: (auth_url, state)
    """
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    redirect_uri = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")
    if not client_id or client_id == "placeholder_client_id":
        raise ValueError("LINKEDIN_CLIENT_ID is not configured in .env.")
        
    state = secrets.token_urlsafe(16)
    auth_url = (
        "https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code&client_id={client_id}"
        f"&redirect_uri={redirect_uri}&scope={SCOPES.replace(' ', '%20')}&state={state}"
    )
    return auth_url, state

def exchange_code_for_token(code: str) -> dict:
    """
    Exchanges OAuth code for access and refresh tokens.
    """
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    redirect_uri = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")
    
    if not client_id or client_id == "placeholder_client_id":
        raise ValueError("LINKEDIN_CLIENT_ID is not configured in .env.")
    if not client_secret or client_secret == "placeholder_client_secret":
        raise ValueError("LINKEDIN_CLIENT_SECRET is not configured in .env.")
        
    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data

def refresh_access_token() -> dict:
    """
    Uses the stored refresh token to get a new access token.
    """
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    
    if not client_id or client_id == "placeholder_client_id":
        raise ValueError("LINKEDIN_CLIENT_ID is not configured in .env.")
    if not client_secret or client_secret == "placeholder_client_secret":
        raise ValueError("LINKEDIN_CLIENT_SECRET is not configured in .env.")
        
    refresh_token = get_refresh_token()
    if not refresh_token:
        raise ValueError("No refresh token found in keyring.")
        
    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data

def save_token_meta(expires_in: int, refresh_token_expires_in: int | None = None) -> None:
    """
    Saves expiry metadata to the oauth_token_meta table in SQLite.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Expiry calculation in UTC
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    expires_at = (now_utc + datetime.timedelta(seconds=expires_in)).isoformat()
    
    refresh_expires_at = None
    if refresh_token_expires_in:
        refresh_expires_at = (now_utc + datetime.timedelta(seconds=refresh_token_expires_in)).isoformat()
        
    cursor.execute("DELETE FROM oauth_token_meta")
    cursor.execute(
        "INSERT INTO oauth_token_meta (expires_at, refresh_expires_at) VALUES (?, ?)",
        (expires_at, refresh_expires_at)
    )
    conn.commit()
    conn.close()

def check_and_refresh_token() -> None:
    """
    Checks if the access token is close to expiry (< 7 days) and refreshes it.
    If DRY_RUN is active, checks are skipped/logged only.
    """
    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if is_dry_run:
        logger.info("Dry-run mode active. Skipping OAuth token refresh check.")
        return
        
    # Check current meta
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT expires_at FROM oauth_token_meta ORDER BY refreshed_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        logger.warning("No token metadata found. Skipping auto-refresh.")
        return
        
    try:
        expires_at = datetime.datetime.fromisoformat(row["expires_at"])
    except Exception as e:
        logger.error(f"Failed to parse expires_at timestamp: {e}")
        return
        
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # If expiring in less than 7 days, refresh it
    if (expires_at - now_utc).total_seconds() < 7 * 24 * 3600:
        logger.info("Access token is expiring in less than 7 days. Triggering refresh...")
        try:
            resp = refresh_access_token()
            acc_token = resp["access_token"]
            # Refresh token can optionally be returned or remain same
            ref_token = resp.get("refresh_token") or get_refresh_token()
            
            store_tokens(acc_token, ref_token)
            
            expires_in = resp["expires_in"]
            ref_expires_in = resp.get("refresh_token_expires_in")
            
            save_token_meta(expires_in, ref_expires_in)
            logger.info("Access token successfully refreshed.")
        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}", exc_info=True)
