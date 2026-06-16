import os
import yaml
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).parent

# Timezone resolver
LOCAL_TZ_NAME = os.getenv("LOCAL_TIMEZONE", "America/Chicago")
try:
    LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("America/Chicago")

def load_exclusions() -> dict:
    path = PROJECT_ROOT / "config" / "exclusions.yaml"
    if not path.exists():
        return {"apps": [], "domains": [], "calendar_title_patterns": [], "folders": []}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def load_posting_cadence() -> dict:
    path = PROJECT_ROOT / "config" / "posting_cadence.yaml"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def load_pillars() -> list:
    path = PROJECT_ROOT / "config" / "pillars.yaml"
    if not path.exists():
        return []
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        return data.get("pillars", []) if isinstance(data, dict) else []

def get_voice_profile() -> tuple[str, str]:
    """Returns a tuple of (voice_profile_content, sha256_hash)."""
    path = PROJECT_ROOT / "config" / "voice_profile.md"
    if not path.exists():
        return "", ""
    with open(path, "r") as f:
        content = f.read()
    
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, sha256
