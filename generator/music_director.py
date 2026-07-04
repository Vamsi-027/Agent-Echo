import os
import json
import logging
from anthropic import Anthropic
import numpy as np
import librosa

logger = logging.getLogger("linkedin-agent.music_director")

MUSIC_DIR = "/Users/vamsi_cheruku/Desktop/agent-echo/data/audio/music"

MUSIC_PROFILE = {
    # Each profile describes the emotional journey across the video's three acts
    # Track filenames should match these keywords in data/audio/music/
    "tension_resolution": {
        "arc": ["sparse", "building", "resolved"],
        "energy": "medium_high",
        "pillar": ["technical_insight", "lesson_learned"],
        "keywords": ["bug", "fix", "crash", "race condition", "idempotent", "retry"],
    },
    "momentum_triumph": {
        "arc": ["confident", "peak", "triumphant"],
        "energy": "high",
        "pillar": ["project_milestone"],
        "keywords": ["ship", "work", "publish", "milestone", "complete"],
    },
    "contemplative_insight": {
        "arc": ["slow", "reflective", "quiet"],
        "energy": "low",
        "pillar": ["lesson_learned"],
        "keywords": ["learn", "mistake", "rethink", "drift", "gap", "wrong"],
    },
    "curious_exploration": {
        "arc": ["interesting", "building_curiosity", "open"],
        "energy": "medium",
        "pillar": ["industry_commentary"],
        "keywords": ["trend", "pattern", "interesting", "noticed", "wondering"],
    },
    "technical_precision": {
        "arc": ["precise", "methodical", "complete"],
        "energy": "medium",
        "pillar": ["technical_insight"],
        "keywords": ["schema", "architecture", "module", "component", "design"],
    },
}

ARC_ENERGY_TARGETS = {
    # tension_resolution
    "sparse": 0.2,
    "building": 0.6,
    "resolved": 0.4,
    # momentum_triumph
    "confident": 0.7,
    "peak": 0.9,
    "triumphant": 1.0,
    # contemplative_insight
    "slow": 0.2,
    "reflective": 0.3,
    "quiet": 0.1,
    # curious_exploration
    "interesting": 0.5,
    "building_curiosity": 0.6,
    "open": 0.4,
    # technical_precision
    "precise": 0.5,
    "methodical": 0.5,
    "complete": 0.6,
}

def score_track_fit(music_path: str, target_profile: dict) -> float:
    """
    Score how well a music track fits the target emotional profile's energy arc.
    Extracts RMS energy, normalizes it to 0-1, splits into thirds (acts),
    and compares mean actual energies with target profile arc energies.
    Returns a score between 0.0 and 1.0.
    """
    try:
        # Load audio (use mono and resample to standard 22050 Hz for consistency)
        y, sr = librosa.load(music_path, sr=22050, mono=True)
        if len(y) == 0:
            return 0.0
            
        # Extract RMS energy
        rms = librosa.feature.rms(y=y)[0]
        if len(rms) < 3:
            return 0.0
            
        # Normalize RMS to [0.0, 1.0] range
        min_rms = np.min(rms)
        max_rms = np.max(rms)
        if max_rms - min_rms > 1e-5:
            norm_rms = (rms - min_rms) / (max_rms - min_rms)
        else:
            norm_rms = np.zeros_like(rms)
            
        # Divide into thirds
        n = len(norm_rms)
        third = n // 3
        act1 = float(np.mean(norm_rms[:third]))
        act2 = float(np.mean(norm_rms[third:2*third]))
        act3 = float(np.mean(norm_rms[2*third:]))
        
        # Compare actuals with targets
        arc = target_profile.get("arc", [])
        targets = [ARC_ENERGY_TARGETS.get(step, 0.5) for step in arc]
        if len(targets) != 3:
            targets = [0.5, 0.5, 0.5]  # fallback
            
        mae = sum(abs(act - target) for act, target in zip([act1, act2, act3], targets)) / 3.0
        score = max(0.0, 1.0 - mae)
        return score
    except Exception as e:
        logger.warning(f"Error scoring track {music_path}: {e}")
        return 0.0

def classify_music_profile(digest: dict, pillar: str) -> str:
    """
    Claude classifies the emotional register of the day's specific content
    to select a music profile — not just the pillar category.
    """
    schema = {
        "type": "object",
        "properties": {
            "music_profile": {
                "type": "string",
                "enum": list(MUSIC_PROFILE.keys())
            },
            "reasoning": {"type": "string"}
        },
        "required": ["music_profile", "reasoning"],
        "additionalProperties": False
    }

    system = (
        "You are a professional video editor selecting background music for a "
        "30-second technical engineering video. "
        "Select the music profile that best matches the EMOTIONAL ARC of this "
        "specific content — not just the category. "
        f"Available profiles: {list(MUSIC_PROFILE.keys())}. "
        "Consider: Does this content build and resolve tension? "
        "Is it triumphant, contemplative, curious, or precise? "
        "What emotion should the viewer feel at the END?"
    )
    user_content = f"Digest: {json.dumps(digest)}\nPillar: {pillar}"

    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user_content}]
        )
        result = json.loads(response.content[0].text)
        selected_profile = result["music_profile"]
        logger.info(f"Music Director: selected profile '{selected_profile}' because: {result.get('reasoning')}")
        return selected_profile
    except Exception as e:
        logger.warning(f"Music Director classification failed, falling back to technical_precision: {e}")
        return "technical_precision"

def select_music_track(digest: dict, pillar: str) -> tuple[str | None, dict]:
    """
    Select music track from MUSIC_DIR matching selected emotional profile arc.
    """
    profile_name = classify_music_profile(digest, pillar)
    profile = MUSIC_PROFILE[profile_name]
    profile["name"] = profile_name

    if not os.path.isdir(MUSIC_DIR):
        logger.info(f"Music directory {MUSIC_DIR} not found — voiceover only")
        return None, profile

    files = [f for f in os.listdir(MUSIC_DIR) if f.endswith((".mp3", ".wav"))]
    if not files:
        logger.info(f"No music files in {MUSIC_DIR} — voiceover only")
        return None, profile

    # Score each track's fit
    best_track = None
    best_score = -1.0
    for f in files:
        path = os.path.join(MUSIC_DIR, f)
        score = score_track_fit(path, profile)
        logger.info(f"Music Director: track '{f}' scored {score:.3f} for profile '{profile_name}'")
        if score > best_score:
            best_score = score
            best_track = path

    if best_track:
        return best_track, profile

    # Fallback to the first available music track if scoring failed for some reason
    return os.path.join(MUSIC_DIR, files[0]), profile
