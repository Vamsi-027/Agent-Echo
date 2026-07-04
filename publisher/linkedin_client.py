import os
import json
import logging
import urllib.parse
import requests
import keyring
from pathlib import Path

# Logger setup
logger = logging.getLogger("linkedin-agent.publisher")

SERVICE_NAME = "linkedin-agent"
LINKEDIN_VERSION = os.getenv("LINKEDIN_VERSION", "202606")


def store_tokens(access_token: str, refresh_token: str) -> None:
    """Store credentials securely in the OS keyring."""
    keyring.set_password(SERVICE_NAME, "access_token", access_token)
    keyring.set_password(SERVICE_NAME, "refresh_token", refresh_token)


def get_access_token() -> str | None:
    """Retrieve the access token from the OS keyring."""
    return keyring.get_password(SERVICE_NAME, "access_token")


def get_refresh_token() -> str | None:
    """Retrieve the refresh token from the OS keyring."""
    return keyring.get_password(SERVICE_NAME, "refresh_token")


def headers() -> dict:
    """Build standard LinkedIn API request headers."""
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


def post_text(author_urn: str, text: str) -> requests.Response:
    """Post text commentary directly to LinkedIn Feed API."""
    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    body = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    }

    if is_dry_run:
        logger.info(f"[DRY RUN] Posting text to URN {author_urn}:\n{text}")
        # Create a mock requests.Response
        resp = requests.Response()
        resp.status_code = 201
        resp.headers = {
            "x-restli-id": "urn:li:share:mock_text_post_" + os.urandom(4).hex()
        }
        resp._content = b'{"id": "urn:li:share:mock_text_post"}'
        return resp

    url = "https://api.linkedin.com/rest/posts"
    return requests.post(url, json=body, headers=headers())


def upload_image(author_urn: str, image_path: str) -> str:
    """Perform two-step upload: initialize, then upload bytes."""
    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if is_dry_run:
        logger.info(f"[DRY RUN] Uploading image: {image_path}")
        return "urn:li:image:mock_image_" + os.urandom(4).hex()

    init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
    init_body = {"initializeUploadRequest": {"owner": author_urn}}

    resp = requests.post(init_url, json=init_body, headers=headers())
    resp.raise_for_status()
    init_data = resp.json()

    upload_url = init_data["value"]["uploadUrl"]
    image_urn = init_data["value"]["image"]

    with open(image_path, "rb") as f:
        put_resp = requests.put(
            upload_url,
            data=f.read(),
            headers={"Authorization": f"Bearer {get_access_token()}"},
        )
        put_resp.raise_for_status()

    return image_urn


def upload_carousel(author_urn: str, slide_image_paths: list[str]) -> str:
    """Compose slide images into a PDF and upload via Documents API."""
    import img2pdf

    pdf_path = Path("/tmp/carousel.pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert(slide_image_paths))

    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if is_dry_run:
        logger.info(
            f"[DRY RUN] Uploading carousel PDF generated from {slide_image_paths}"
        )
        return "urn:li:document:mock_doc_" + os.urandom(4).hex()

    init_url = "https://api.linkedin.com/rest/documents?action=initializeUpload"
    init_body = {"initializeUploadRequest": {"owner": author_urn}}

    resp = requests.post(init_url, json=init_body, headers=headers())
    resp.raise_for_status()
    init_data = resp.json()

    upload_url = init_data["value"]["uploadUrl"]
    document_urn = init_data["value"]["document"]

    with open(pdf_path, "rb") as f:
        put_resp = requests.put(
            upload_url,
            data=f.read(),
            headers={"Authorization": f"Bearer {get_access_token()}"},
        )
        put_resp.raise_for_status()

    return document_urn


def get_my_member_urn() -> str:
    """Retrieves the member URN from environment or fetches it from LinkedIn API."""
    env_urn = os.getenv("LINKEDIN_AUTHOR_URN")
    if env_urn and env_urn != "urn:li:person:mock_author_urn":
        return env_urn

    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if is_dry_run:
        return "urn:li:person:mock_author_urn"

    token = get_access_token()
    if not token:
        raise ValueError(
            "Access token not found in keyring. Please run authorization first."
        )

    # Try userinfo (OpenID Connect)
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        r = requests.get(
            "https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10
        )
        if r.status_code == 200:
            sub = r.json().get("sub")
            if sub:
                return f"urn:li:person:{sub}"
    except Exception as e:
        logger.debug(f"Failed to query /v2/userinfo: {e}")

    # Try legacy /v2/me as fallback
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        r = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=10)
        if r.status_code == 200:
            user_id = r.json().get("id")
            if user_id:
                return f"urn:li:person:{user_id}"
    except Exception as e:
        logger.debug(f"Failed to query /v2/me: {e}")

    raise ValueError(
        "Could not retrieve member URN. Please configure 'LINKEDIN_AUTHOR_URN' in your .env file "
        "or verify your LinkedIn Developer Application has 'Sign In with LinkedIn using OpenID Connect' enabled."
    )


def post_draft_to_linkedin(draft: dict) -> requests.Response:
    """
    Dispatches publishing based on draft's format_type.
    """
    author_urn = get_my_member_urn()
    format_type = draft["format_type"]
    text_content = draft["text_content"]

    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    # Extract tags/hashtags if present
    full_text = text_content
    if draft.get("hashtags"):
        full_text += f"\n\n{draft['hashtags']}"

    if format_type == "text" or format_type == "long_form":
        return post_text(author_urn, full_text)

    elif format_type == "image":
        media_refs = (
            json.loads(draft["media_refs_json"]) if draft.get("media_refs_json") else []
        )
        image_path = media_refs[0] if media_refs else None

        if is_dry_run:
            logger.info(
                f"[DRY RUN] Image post draft {draft['id']} containing image: {image_path}"
            )
            resp = requests.Response()
            resp.status_code = 201
            resp.headers = {
                "x-restli-id": "urn:li:share:mock_image_post_" + os.urandom(4).hex()
            }
            resp._content = b'{"id": "urn:li:share:mock_image_post"}'
            return resp

        if not image_path:
            raise ValueError(
                f"Draft {draft['id']} of format 'image' has no media_refs."
            )

        image_urn = upload_image(author_urn, image_path)

        body = {
            "author": author_urn,
            "commentary": full_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "content": {"media": {"id": image_urn, "title": "Uploaded Image"}},
        }
        return requests.post(
            "https://api.linkedin.com/rest/posts", json=body, headers=headers()
        )

    elif format_type == "carousel":
        media_refs = (
            json.loads(draft["media_refs_json"]) if draft.get("media_refs_json") else []
        )

        if is_dry_run:
            logger.info(
                f"[DRY RUN] Carousel post draft {draft['id']} containing {len(media_refs)} slides"
            )
            resp = requests.Response()
            resp.status_code = 201
            resp.headers = {
                "x-restli-id": "urn:li:share:mock_carousel_post_" + os.urandom(4).hex()
            }
            resp._content = b'{"id": "urn:li:share:mock_carousel_post"}'
            return resp

        if not media_refs:
            raise ValueError(
                f"Draft {draft['id']} of format 'carousel' has no media_refs."
            )

        doc_urn = upload_carousel(author_urn, media_refs)

        body = {
            "author": author_urn,
            "commentary": full_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "content": {"media": {"id": doc_urn, "title": "Slide Presentation"}},
        }
        return requests.post(
            "https://api.linkedin.com/rest/posts", json=body, headers=headers()
        )

    elif format_type == "video":
        media_refs = (
            json.loads(draft["media_refs_json"]) if draft.get("media_refs_json") else []
        )
        video_path = media_refs[0] if media_refs else None

        if is_dry_run:
            logger.info(
                f"[DRY RUN] Video post draft {draft['id']} containing video: {video_path}"
            )
            resp = requests.Response()
            resp.status_code = 201
            resp.headers = {
                "x-restli-id": "urn:li:share:mock_video_post_" + os.urandom(4).hex()
            }
            resp._content = b'{"id": "urn:li:share:mock_video_post"}'
            return resp

        if not video_path:
            raise ValueError(
                f"Draft {draft['id']} of format 'video' has no media_refs."
            )

        video_urn = upload_video(author_urn, video_path)

        body = {
            "author": author_urn,
            "commentary": full_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "content": {"media": {"id": video_urn, "title": "Uploaded Video"}},
        }
        return requests.post(
            "https://api.linkedin.com/rest/posts", json=body, headers=headers()
        )

    elif format_type == "poll":
        poll_data = (
            json.loads(draft["media_refs_json"]) if draft.get("media_refs_json") else {}
        )
        question = poll_data.get("question")
        options_list = poll_data.get("options", [])
        duration = poll_data.get("duration", "THREE_DAYS")

        if is_dry_run:
            logger.info(
                f"[DRY RUN] Poll post draft {draft['id']}: Q: '{question}' | Options: {options_list} | Duration: {duration}"
            )
            resp = requests.Response()
            resp.status_code = 201
            resp.headers = {
                "x-restli-id": "urn:li:share:mock_poll_post_" + os.urandom(4).hex()
            }
            resp._content = b'{"id": "urn:li:share:mock_poll_post"}'
            return resp

        if not question or not options_list:
            raise ValueError(
                f"Draft {draft['id']} of format 'poll' has missing question or options in media_refs_json."
            )

        options = [{"text": opt} for opt in options_list]

        body = {
            "author": author_urn,
            "commentary": full_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "content": {
                "poll": {
                    "question": question,
                    "options": options,
                    "settings": {"duration": duration},
                }
            },
        }
        return requests.post(
            "https://api.linkedin.com/rest/posts", json=body, headers=headers()
        )

    else:
        raise NotImplementedError(f"Format type '{format_type}' not supported yet.")


def upload_video(author_urn: str, video_path: str) -> str:
    """Perform multi-step video upload: initialize, upload bytes, finalize, and poll for availability."""
    import time

    is_dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if is_dry_run:
        logger.info(f"[DRY RUN] Uploading video: {video_path}")
        return "urn:li:video:mock_video_" + os.urandom(4).hex()

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at path: {video_path}")

    file_size = os.path.getsize(video_path)

    # 1. Initialize Upload
    init_url = "https://api.linkedin.com/rest/videos?action=initializeUpload"
    init_body = {
        "initializeUploadRequest": {
            "owner": author_urn,
            "fileSizeBytes": file_size,
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }
    }

    resp = requests.post(init_url, json=init_body, headers=headers())
    resp.raise_for_status()
    init_data = resp.json()

    video_urn = init_data["value"]["video"]
    upload_instructions = init_data["value"]["uploadInstructions"]
    upload_token = init_data["value"].get("uploadToken", "")

    # 2. Upload Video Binary — LinkedIn splits large files into multiple parts
    # (e.g. 4MB each), each with its own uploadUrl and byte range. Uploading
    # the whole file to a single part's URL overflows that part's limit and
    # LinkedIn responds 413 Payload Too Large.
    with open(video_path, "rb") as f:
        file_bytes = f.read()

    etags = []
    for part in upload_instructions:
        chunk = file_bytes[part["firstByte"] : part["lastByte"] + 1]
        put_resp = requests.put(
            part["uploadUrl"],
            data=chunk,
            headers={
                "Authorization": f"Bearer {get_access_token()}",
                "Content-Type": "application/octet-stream",
            },
        )
        put_resp.raise_for_status()
        etag = put_resp.headers.get("ETag") or put_resp.headers.get("etag")
        etags.append(etag or "mock-etag")

    # 3. Finalize Upload
    finalize_url = "https://api.linkedin.com/rest/videos?action=finalizeUpload"
    finalize_body = {
        "finalizeUploadRequest": {
            "video": video_urn,
            "uploadToken": upload_token,
            "uploadedPartIds": etags,
        }
    }

    fin_resp = requests.post(finalize_url, json=finalize_body, headers=headers())
    fin_resp.raise_for_status()

    # 4. Poll for status (max 12 times, 5s interval -> 60s total)
    # The URN must be percent-encoded in the path (colons aren't valid
    # unescaped there) or LinkedIn returns 400 ILLEGAL_ARGUMENT.
    encoded_video_urn = urllib.parse.quote(video_urn, safe="")
    for attempt in range(12):
        time.sleep(5)
        status_url = f"https://api.linkedin.com/rest/videos/{encoded_video_urn}"
        status_resp = requests.get(status_url, headers=headers())
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            state = status_data.get("processingState") or status_data.get("status")
            logger.info(f"Polling video status attempt {attempt+1}: {state}")
            if state == "AVAILABLE":
                return video_urn
            elif state == "FAILED":
                raise ValueError("LinkedIn video processing failed.")
        else:
            logger.warning(f"Failed to poll video status: {status_resp.status_code}")

    raise TimeoutError(
        "LinkedIn video processing timed out (still not AVAILABLE after 60s)."
    )
