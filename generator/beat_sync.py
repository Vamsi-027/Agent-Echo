import os
import logging
import librosa
import numpy as np

logger = logging.getLogger("linkedin-agent.beat_sync")

def extract_beat_frames(music_path: str | None, video_fps: int = 30) -> dict:
    """
    Analyze music file and return beat timing data for use in Remotion props.
    Returns beat frame numbers, tempo, and downbeat positions.
    Handles fallbacks cleanly for None, missing, or corrupted files.
    """
    # ── Fallback Defaults ─────────────────────────────────────────────────────
    default_tempo = 120.0
    default_interval = int(60.0 / default_tempo * video_fps)  # 15 frames
    default_beats = [i * default_interval for i in range(1, 61)]
    default_downbeats = [i * default_interval * 4 for i in range(1, 17)]
    
    default_data = {
        "tempo": default_tempo,
        "beat_frames": default_beats,
        "downbeat_frames": default_downbeats,
        "energy_peaks": [],
        "beat_interval": default_interval,
    }

    if not music_path or not os.path.exists(music_path):
        logger.info("No music track supplied or file missing. Using fallback beat tracking data.")
        return default_data

    try:
        # Load audio (sr=None uses the native sampling rate)
        y, sr = librosa.load(music_path, sr=None)
        
        # Beat tracking
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        # Ensure tempo is scalar float
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0]) if len(tempo) > 0 else default_tempo
        else:
            tempo = float(tempo)
            
        if tempo <= 0:
            tempo = default_tempo

        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        beat_video_frames = [int(t * video_fps) for t in beat_times]

        # Downbeat tracking (every 4th beat = stronger visual event)
        downbeat_video_frames = beat_video_frames[::4]

        # Energy envelope — for camera pulse on loud moments
        rms = librosa.feature.rms(y=y)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
        energy_peaks = []
        mean_rms = np.mean(rms)
        for i in range(1, len(rms) - 1):
            if rms[i] > rms[i-1] and rms[i] > rms[i+1] and rms[i] > mean_rms * 1.5:
                energy_peaks.append(int(rms_times[i] * video_fps))

        # Array bounds guarding and padding
        beat_interval = 60.0 / tempo * video_fps
        last_beat = beat_video_frames[-1] if beat_video_frames else 0
        last_downbeat = downbeat_video_frames[-1] if downbeat_video_frames else 0

        padded_beats = beat_video_frames + [int(last_beat + (i + 1) * beat_interval) for i in range(60)]
        padded_downbeats = downbeat_video_frames + [int(last_downbeat + (i + 1) * beat_interval * 4) for i in range(16)]

        return {
            "tempo": float(tempo),
            "beat_frames": padded_beats[:60],
            "downbeat_frames": padded_downbeats[:16],
            "energy_peaks": energy_peaks[:20],
            "beat_interval": int(beat_interval),
        }

    except Exception as e:
        logger.warning(f"Failed to analyze beat tracking for {music_path} due to error: {e}. Falling back to default beats.")
        return default_data


def clean_word(w: str) -> str:
    return w.lower().strip(".,!?—\"'();:").replace("'", "").replace('"', '')


def find_chapter_boundary(chapter_text: str, captions: list[dict], search_from: int = 0) -> tuple[float | None, int]:
    """
    Find the start time of a chapter by matching its first 3-5 words
    as a phrase, not just the first word.
    More robust against common words appearing multiple times.
    """
    # Use first 4 words as the search phrase
    words = [clean_word(w) for w in chapter_text.split()[:4] if w.strip()]
    if not words:
        return None, -1

    n_words = len(words)
    # Build a sliding window of consecutive caption words
    for i in range(search_from, len(captions) - n_words + 1):
        window_words = [
            clean_word(captions[j]["text"])
            for j in range(i, i + n_words)
        ]
        # Compare clean versions on both sides exactly in order
        if words == window_words:
            return captions[i]["start"], i

    # Fallback: return None
    return None, -1


def derive_shots_from_captions(
    voiceover_script: str,
    captions: list[dict],   # [{"text": word, "start": secs, "end": secs}]
    shot_defs: list[dict],
    fps: int = 30,
) -> list[dict]:
    """
    Map voiceover chapters (paragraph breaks) to timed shots.
    Each chapter gets a start_frame and end_frame derived from
    the actual caption timestamps — not BPM arithmetic.
    """
    chapters = [c.strip() for c in voiceover_script.split("\n\n") if c.strip()]
    
    if len(chapters) != len(shot_defs):
        raise ValueError(
            f"Chapter count ({len(chapters)}) doesn't match shot count ({len(shot_defs)}). "
            f"Check voiceover script paragraph structure."
        )

    shots_with_timing = []
    search_idx = 0
    duration_secs = captions[-1]["end"] if captions else 0.0

    for i, (chapter_text, shot_def) in enumerate(zip(chapters, shot_defs)):
        # 1. Find start of current chapter
        start_secs, idx = find_chapter_boundary(chapter_text, captions, search_idx)
        if start_secs is not None:
            search_idx = idx
        else:
            # Fallback to proportional start time
            start_secs = i * (duration_secs / len(chapters))

        # 2. Find end of current chapter (start of next, or end of voiceover)
        if i < len(chapters) - 1:
            next_start_secs, _ = find_chapter_boundary(chapters[i + 1], captions, search_idx)
            if next_start_secs is not None:
                end_secs = next_start_secs
            else:
                end_secs = (i + 1) * (duration_secs / len(chapters))
        else:
            end_secs = duration_secs

        shots_with_timing.append({
            **shot_def,
            "start_frame": int(start_secs * fps),
            "end_frame":   int(end_secs * fps),
            "duration_frames": int((end_secs - start_secs) * fps),
        })

    return shots_with_timing
