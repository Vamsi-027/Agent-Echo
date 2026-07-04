import os
import subprocess
import json
import logging
import shutil
import requests
from anthropic import Anthropic
import numpy as np
from scipy.io import wavfile

logger = logging.getLogger("linkedin-agent.audio_engine")

# ── Startup validation ────────────────────────────────────────────────────────

def validate_dependencies():
    # Prepend Homebrew and standard paths to PATH if missing
    for path in ["/opt/homebrew/bin", "/usr/local/bin"]:
        if path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = path + os.path.pathsep + os.environ.get("PATH", "")
            
    missing = [t for t in ("ffmpeg", "ffprobe", "npx") if not shutil.which(t)]
    if missing:
        raise RuntimeError(f"Missing system tools: {missing}. Run: brew install ffmpeg node")

# ── Voiceover script generation ───────────────────────────────────────────────

def generate_voiceover_script(composition: str, digest: dict, props: dict, draft_text: str | None = None, n_shots: int = 8) -> str:
    client = Anthropic()

    schema = {
        "type": "object",
        "properties": {"script": {"type": "string"}},
        "required": ["script"],
        "additionalProperties": False,
    }
    system = (
        "Write a technical voiceover narration for an animated engineering video. "
        "The voiceover must COMPLEMENT the approved post draft text (if provided) by explaining "
        "WHY the technical change or topic matters and its deeper architectural context, "
        "rather than repeating the draft text or explaining literally what is happening on screen.\n"
        "Rules:\n"
        f"- Structure the script in exactly {n_shots} paragraphs separated by blank lines.\n"
        "- Each paragraph should be 7-20 words and cover one visual concept.\n"
        "- Do not use bullet points, headers, or any formatting other than paragraph breaks.\n"
        "- Natural spoken rhythm — short sentences, deliberate pauses\n"
        "- No markdown, no hashtags, no bullet points, no lists, no headers\n"
        "- No filler openers: never start with 'In this video', 'Today', 'Let me walk you through'\n"
        "- Open with a high-tension, first-person realization or dramatic technical failure (e.g. 'My database was leaking connections', 'A single race condition crashed our production queue')\n"
        "- Technical but conversational — like a senior engineer explaining to a peer\n"
        f"- Animation type: {composition}"
    )
    user = (
        f"Animation props: {json.dumps(props, indent=2)}\n"
        f"Post digest: {json.dumps(digest, indent=2)}\n"
    )
    if draft_text:
        user += f"Approved post draft text: \"{draft_text}\"\n"
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    result = json.loads(response.content[0].text)
    return result["script"]

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get(
    "ELEVENLABS_VOICE_ID",
    "EXAVITQu4vr4xnSDxMaL"   # Sarah — default soothing female voice
)
ELEVENLABS_MODEL_ID = os.environ.get(
    "ELEVENLABS_MODEL_ID",
    "eleven_multilingual_v2"  # best quality; fall back to "eleven_turbo_v2_5" if needed
)

VOICES = {
    "Sarah": {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "description": "Mature, Reassuring, Confident American Female. Best for lessons learned, reflection, or professional announcements."
    },
    "Alice": {
        "id": "Xb7hH8MSUJpSbSDYk0k2",
        "description": "Clear, Engaging British Female Educator. Best for structured technical tutorials, workflows, and walkthroughs."
    },
    "Matilda": {
        "id": "XrExE9yKIg1WjnnlVkGX",
        "description": "Knowledgeable, Professional Alto American Female. Best for deep-dive technical insights and system architecture analyses."
    },
    "Jessica": {
        "id": "cgSgspJ2msm6clMCkdW9",
        "description": "Playful, Bright, Warm American Female. Best for milestone celebrations, exciting news, and casual developer logs."
    },
    "Bella": {
        "id": "hpp4J3VqNfWAUOO0d1Us",
        "description": "Warm, Bright, Professional American Female Narrator. Best for general narration and high-level summaries."
    },
    "Lily": {
        "id": "pFZP5JQG7iQjIQuC4Bku",
        "description": "Velvety, Warm British Female. Best for news, narrative stories, and premium product milestones."
    },
    "Laura": {
        "id": "FGY2WhTYpPnrIDTdsKH5",
        "description": "Enthusiastic, Quirky American Female. Best for styling insights, frontend changes, and lighthearted developer logs."
    }
}

def select_voice_profile(composition: str, digest: dict, script: str) -> str:
    """
    Use Claude structured output to select the best matching voice ID from the VOICES registry
    based on the composition context and script tone.
    """
    schema = {
        "type": "object",
        "properties": {
            "selected_voice_name": {
                "type": "string",
                "enum": list(VOICES.keys()),
                "description": "The name of the voice that best fits the script's tone."
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this voice matches the content."
            }
        },
        "required": ["selected_voice_name", "reasoning"],
        "additionalProperties": False
    }

    system = (
        "You are a media production director. Your task is to analyze the voiceover script "
        "and content pillar/digest, and select the voice from the list that best matches the tone of the content."
    )

    user = (
        f"Voice Options:\n{json.dumps(VOICES, indent=2)}\n\n"
        f"Animation: {composition}\n"
        f"Script: \"{script}\"\n"
        f"Digest Summary: {digest.get('summary', '')}"
    )

    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        result = json.loads(response.content[0].text)
        selected_name = result["selected_voice_name"]
        selected_id = VOICES[selected_name]["id"]
        logger.info(f"Voice selector: selected profile '{selected_name}' ({selected_id}) because: {result.get('reasoning')}")
        return selected_id
    except Exception as e:
        logger.warning(f"Voice selector failed, falling back to Sarah: {e}")
        return VOICES["Sarah"]["id"]

import base64

def generate_captions_from_alignment(alignment: dict) -> list[dict]:
    """
    Process character-level timings into word-level chunks.
    Groups characters into words by space boundaries, then groups words into
    short phrases (max 4 words or 24 characters per chunk).
    Returns a list of {"text": "...", "start": start_sec, "end": end_sec}.
    """
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    
    if not chars or not starts or not ends or len(chars) != len(starts) or len(chars) != len(ends):
        return []
        
    # Group characters into words
    words = []
    current_word_chars = []
    current_word_start = None
    
    for c, start, end in zip(chars, starts, ends):
        if c.isspace():
            if current_word_chars:
                word_text = "".join(current_word_chars)
                words.append({
                    "text": word_text,
                    "start": current_word_start,
                    "end": end
                })
                current_word_chars = []
                current_word_start = None
        else:
            if current_word_start is None:
                current_word_start = start
            current_word_chars.append(c)
            
    # Add final word
    if current_word_chars:
        word_text = "".join(current_word_chars)
        words.append({
            "text": word_text,
            "start": current_word_start,
            "end": ends[-1]
        })
        
    if not words:
        return []
        
    # Group words into short phrases (max 4 words or 24 characters)
    chunks = []
    current_chunk_words = []
    current_chunk_start = None
    current_chunk_char_len = 0
    current_chunk_end = 0
    
    for w in words:
        word_len = len(w["text"])
        if len(current_chunk_words) >= 4 or (current_chunk_char_len + word_len + len(current_chunk_words) > 24):
            if current_chunk_words:
                chunks.append({
                    "text": " ".join(current_chunk_words),
                    "start": current_chunk_start,
                    "end": current_chunk_end
                })
            current_chunk_words = [w["text"]]
            current_chunk_start = w["start"]
            current_chunk_char_len = word_len
            current_chunk_end = w["end"]
        else:
            if not current_chunk_words:
                current_chunk_start = w["start"]
            current_chunk_words.append(w["text"])
            current_chunk_char_len += word_len
            current_chunk_end = w["end"]
            
    # Flush last chunk
    if current_chunk_words:
        chunks.append({
            "text": " ".join(current_chunk_words),
            "start": current_chunk_start,
            "end": current_chunk_end
        })
        
    return chunks

def generate_fallback_captions(script: str, duration_secs: float) -> list[dict]:
    """
    Generate fallback captions when TTS alignment is unavailable.
    Splits the script into roughly equal word chunks based on the overall duration.
    """
    words = script.split()
    if not words:
        return []
        
    # Chunk words (max 4 words per chunk)
    word_chunks = [words[i:i+4] for i in range(0, len(words), 4)]
    num_chunks = len(word_chunks)
    if num_chunks == 0:
        return []
        
    chunk_duration = duration_secs / num_chunks
    captions = []
    for idx, chunk in enumerate(word_chunks):
        start = idx * chunk_duration
        end = (idx + 1) * chunk_duration
        captions.append({
            "text": " ".join(chunk),
            "start": round(start, 2),
            "end": round(end, 2)
        })
    return captions

def save_srt_file(captions: list[dict], srt_path: str):
    """
    Format and write captions into a standard SubRip (.srt) subtitle file.
    """
    def format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            for idx, cap in enumerate(captions):
                f.write(f"{idx + 1}\n")
                f.write(f"{format_time(cap['start'])} --> {format_time(cap['end'])}\n")
                f.write(f"{cap['text']}\n\n")
    except Exception as e:
        logger.warning(f"Failed to write SRT file to {srt_path}: {e}")

def synthesize_voiceover(script: str, output_path: str, voice_id: str | None = None) -> tuple[float, list[dict]]:
    """
    Synthesize voiceover via ElevenLabs with timestamps. Returns (duration, captions).
    Uses model_id from ELEVENLABS_MODEL_ID.
    """
    # Reload keys/voice IDs dynamically in case they were set in .env after module load
    api_key = os.environ.get("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY)
    
    if not voice_id:
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_ID)
    if not voice_id:
        voice_id = "EXAVITQu4vr4xnSDxMaL"  # default to Sarah
        
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", ELEVENLABS_MODEL_ID)

    captions = []
    duration = 0.0

    try:
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured in the environment.")

        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": script,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.45,          # slightly lower = more natural variation
                    "similarity_boost": 0.80,   # high = stays true to voice character
                    "style": 0.35,              # moderate expressivity
                    "use_speaker_boost": True,  # enhances clarity at lower volumes
                },
                "output_format": "mp3_44100_192",  # 192kbps, 44.1kHz — production quality
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs HTTP status {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        audio_base64 = data.get("audio_base64", "")
        audio_bytes = base64.b64decode(audio_base64)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        duration = get_audio_duration(output_path)
        alignment = data.get("alignment", {})
        captions = generate_captions_from_alignment(alignment)

    except Exception as e:
        logger.warning(f"ElevenLabs TTS failed ({e}). Trying OpenAI TTS fallback...")
        try:
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY is not configured in the environment.")

            # Map ElevenLabs voice to OpenAI voice
            openai_voice = os.environ.get("OPENAI_FALLBACK_VOICE")
            if not openai_voice:
                if voice_id in ["cgSgspJ2msm6clMCkdW9", "Jessica", "FGY2WhTYpPnrIDTdsKH5", "Laura"]:
                    openai_voice = "nova"  # bright, energetic
                elif voice_id in ["EXAVITQu4vr4xnSDxMaL", "Sarah", "Xb7hH8MSUJpSbSDYk0k2", "Alice", "XrExE9yKIg1WjnnlVkGX", "Matilda"]:
                    openai_voice = "alloy"  # neutral, mature, professional
                elif voice_id in ["pFZP5JQG7iQjIQuC4Bku", "Lily", "hpp4J3VqNfWAUOO0d1Us", "Bella"]:
                    openai_voice = "shimmer"  # warm, female
                else:
                    openai_voice = "alloy"  # default safe fallback

            resp = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": script,
                    "voice": openai_voice,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI HTTP status {resp.status_code}: {resp.text[:200]}")

            audio_bytes = resp.content
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            duration = get_audio_duration(output_path)
            captions = []  # Will trigger generate_fallback_captions later

        except Exception as oe:
            logger.warning(f"OpenAI TTS failed ({oe}). Falling back to local silent voiceover generation.")
            words_count = len(script.split())
            duration = max(5.0, round(words_count / 2.2, 1))

            # Generate silent audio using ffmpeg
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100",
                "-t", str(duration),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                output_path
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
            except Exception as fe:
                logger.error(f"Ffmpeg silent audio generation failed: {fe}")
                raise fe

    if not captions:
        captions = generate_fallback_captions(script, duration)

    srt_path = os.path.splitext(output_path)[0] + ".srt"
    save_srt_file(captions, srt_path)

    return duration, captions


# ── Duration measurement (ffprobe, no extra deps) ─────────────────────────────

def get_audio_duration(path: str) -> float:
    validate_dependencies()
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True, check=True
    )
    info = json.loads(result.stdout)
    if "streams" in info and len(info["streams"]) > 0 and "duration" in info["streams"][0]:
        return float(info["streams"][0]["duration"])
        
    # Fallback to container format info
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, check=True
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])

# ── SFX generation (numpy synthesis — no downloads needed) ────────────────────

SFX_DIR = "/Users/vamsi_cheruku/Desktop/agent-echo/data/audio/sfx"

def _write_wav(samples: np.ndarray, rate: int, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    max_val = np.max(np.abs(samples))
    if max_val > 0:
        normalized = np.int16(samples / max_val * 32767)
    else:
        normalized = np.int16(samples)
    wavfile.write(path, rate, normalized)

def generate_sfx_library():
    """Generate all SFX files once. Call from cli.py seed-sfx."""
    rate = 44100

    # Pop — 800Hz sine burst, 80ms, exponential decay
    t = np.linspace(0, 0.08, int(rate * 0.08))
    pop = np.sin(2 * np.pi * 800 * t) * np.exp(-40 * t)
    _write_wav(pop, rate, f"{SFX_DIR}/pop.wav")

    # Whoosh — filtered noise sweep 200→2000Hz, 150ms
    t = np.linspace(0, 0.15, int(rate * 0.15))
    freq = np.linspace(200, 2000, len(t))
    phase = np.cumsum(2 * np.pi * freq / rate)
    whoosh = np.sin(phase) * np.random.uniform(0.8, 1.0, len(t))
    whoosh *= np.hanning(len(whoosh))
    _write_wav(whoosh, rate, f"{SFX_DIR}/whoosh.wav")

    # Tick — 1200Hz click, 30ms
    t = np.linspace(0, 0.03, int(rate * 0.03))
    tick = np.sin(2 * np.pi * 1200 * t) * np.exp(-80 * t)
    _write_wav(tick, rate, f"{SFX_DIR}/tick.wav")

    # Shimmer — detuned sine pair with reverb tail, 300ms
    t = np.linspace(0, 0.3, int(rate * 0.3))
    shimmer = (
        np.sin(2 * np.pi * 4000 * t) * 0.5 +
        np.sin(2 * np.pi * 4002 * t) * 0.5    # ±2Hz beating effect
    ) * np.exp(-8 * t)
    _write_wav(shimmer, rate, f"{SFX_DIR}/shimmer.wav")

    logger.info(f"SFX library generated at {SFX_DIR}/")

# Music selection has been fully migrated to music_director.py

# ── Audio mixing (ffmpeg only, no pydub) ─────────────────────────────────────

def mix_audio(
    voiceover_path: str,
    music_path: str | None,
    output_path: str,
    music_db: float = -18.0,
) -> bool:
    """
    Mix voiceover + optional background music using ffmpeg.
    Music is volume-adjusted, faded in (1s) and faded out (2s) to match voiceover length.
    Output: 192kbps AAC MP3.
    """
    validate_dependencies()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not music_path or not os.path.exists(music_path):
        # Voiceover only — just copy to output
        shutil.copy(voiceover_path, output_path)
        return True

    vo_duration = get_audio_duration(voiceover_path)
    music_volume = 10 ** (music_db / 20)   # dB → linear

    cmd = [
        "ffmpeg", "-y",
        "-i", voiceover_path,
        "-stream_loop", "-1", "-i", music_path,   # loop music to match voiceover length
        "-filter_complex",
        (
            f"[1:a]volume={music_volume:.4f},"
            f"afade=t=in:st=0:d=1,"                # 1s fade in
            f"afade=t=out:st={vo_duration - 2:.2f}:d=2,"   # 2s fade out
            f"atrim=duration={vo_duration:.3f}[music];"
            "[0:a][music]amix=inputs=2:duration=first:normalize=0[out]"
        ),
        "-map", "[out]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-q:a", "0",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.warning(f"Audio mix failed: {result.stderr[:400]}")
        return False
    return True
