import os
import json
import logging
import time
import uuid
import hmac
import hashlib
import base64
import urllib.parse
import requests

# Logger setup
logger = logging.getLogger("linkedin-agent.publisher.twitter")

def generate_oauth_header(
    method: str,
    url: str,
    params: dict,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
) -> str:
    """Generates standard OAuth 1.0a Authorization header."""
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    
    # Combine query parameters and oauth parameters for signature base
    all_params = {}
    all_params.update(params)
    all_params.update(oauth_params)
    
    def escape(s: str) -> str:
        return urllib.parse.quote(str(s), safe="")
        
    sorted_params = sorted([(escape(k), escape(v)) for k, v in all_params.items()])
    parameter_string = "&".join(f"{k}={v}" for k, v in sorted_params)
    
    base_url = url.split("?")[0]
    signature_base_string = f"{method.upper()}&{escape(base_url)}&{escape(parameter_string)}"
    
    signing_key = f"{escape(consumer_secret)}&{escape(access_token_secret)}".encode("utf-8")
    
    signature = hmac.new(
        signing_key,
        signature_base_string.encode("utf-8"),
        hashlib.sha1
    ).digest()
    
    oauth_params["oauth_signature"] = base64.b64encode(signature).decode("utf-8")
    
    auth_header_parts = []
    for k, v in sorted(oauth_params.items()):
        auth_header_parts.append(f'{escape(k)}="{escape(v)}"')
        
    return "OAuth " + ", ".join(auth_header_parts)

def upload_twitter_media(
    media_path: str,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
) -> str:
    """Uploads media file to Twitter/X v1.1 Media Upload API and returns media_id_string."""
    url = "https://upload.twitter.com/1.1/media/upload.json"
    
    auth_header = generate_oauth_header(
        "POST",
        url,
        {},
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret
    )
    
    headers = {
        "Authorization": auth_header,
    }
    
    with open(media_path, "rb") as f:
        files = {"media": f}
        resp = requests.post(url, files=files, headers=headers)
        
    resp.raise_for_status()
    return resp.json()["media_id_string"]

def post_draft_to_twitter(draft: dict) -> requests.Response:
    """Posts a draft's Twitter content to Twitter/X. Falls back to dry-run if credentials missing."""
    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    
    # Retrieve credentials
    consumer_key = os.getenv("TWITTER_CONSUMER_KEY")
    consumer_secret = os.getenv("TWITTER_CONSUMER_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
    
    has_creds = all([consumer_key, consumer_secret, access_token, access_token_secret])
    text_content = draft.get("twitter_text_content") or draft.get("text_content") or ""
    
    # Append hashtags if present
    full_text = text_content
    if draft.get("hashtags"):
        full_text += f"\n\n{draft['hashtags']}"
        
    media_refs = []
    if draft.get("media_refs_json"):
        try:
            media_refs = json.loads(draft["media_refs_json"])
        except Exception:
            pass
            
    if is_dry_run or not has_creds:
        if not has_creds and not is_dry_run:
            logger.warning("Missing Twitter credentials. Falling back to DRY RUN mode for Twitter.")
            
        logger.info(f"[DRY RUN] Posting tweet (length {len(full_text)}):\n{full_text}")
        if media_refs:
            logger.info(f"[DRY RUN] Attaching media files to tweet: {media_refs}")
            
        # Create a mock requests.Response
        resp = requests.Response()
        resp.status_code = 201
        mock_id = "mock_tweet_" + os.urandom(4).hex()
        resp._content = json.dumps({"data": {"id": mock_id, "text": full_text}}).encode("utf-8")
        resp.headers = {"content-type": "application/json"}
        return resp
        
    # Standard live mode:
    # 1. Handle media uploads if any
    media_ids = []
    if media_refs:
        # Twitter v2 accepts up to 4 images or 1 video
        for path in media_refs[:4]:
            if os.path.exists(path):
                try:
                    media_id = upload_twitter_media(
                        path,
                        consumer_key,
                        consumer_secret,
                        access_token,
                        access_token_secret
                    )
                    media_ids.append(media_id)
                except Exception as e:
                    logger.error(f"Failed to upload media {path} to Twitter: {e}")
                    
    # 2. Build body
    body = {"text": full_text}
    if media_ids:
        body["media"] = {"media_ids": media_ids}
        
    # 3. Post Tweet
    url = "https://api.twitter.com/2/tweets"
    auth_header = generate_oauth_header(
        "POST",
        url,
        {},
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret
    )
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    
    resp = requests.post(url, json=body, headers=headers)
    return resp
