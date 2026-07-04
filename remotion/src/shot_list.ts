export interface Shot {
  id?: string;
  type: string;
  content: string;
  entrance: string;
  duration_beats?: number;
  start_frame?: number;
  end_frame?: number;
  rgb_split?: boolean;
  speed_before?: number;
  [key: string]: any;
}

export interface ResolvedShot extends Shot {
  from: number; // frame
  to: number;   // frame
  rgb_split: boolean;
  speed_before: number;
}

export function resolveShotList(
  shots: Shot[],
  beatFrames: number[],
  durationInFrames: number
): ResolvedShot[] {
  if (!shots || shots.length === 0) {
    return [];
  }

  // If shots have pre-calculated start_frame and end_frame (caption-driven timing)
  const hasTiming = shots.every(
    (shot) => typeof shot.start_frame === "number" && typeof shot.end_frame === "number"
  );

  if (hasTiming) {
    // These boundaries are derived directly from the voiceover's word-level
    // timestamps (see derive_shots_from_captions()) and validated for gapless
    // full-duration coverage. Do not re-snap them to the nearest beat — that
    // would desync the cut from the word the narrator is actually saying.
    return shots.map((shot, i) => {
      const fromFrame = shot.start_frame!;
      const toFrame = i < shots.length - 1 ? shot.end_frame! : durationInFrames;

      return {
        ...shot,
        from: fromFrame,
        to: toFrame,
        rgb_split: !!shot.rgb_split,
        speed_before: shot.speed_before ?? 1.0,
      };
    });
  }

  const totalShotBeats = shots.reduce((acc, s) => acc + (s.duration_beats ?? 4), 0);
  const totalAvailableBeats = beatFrames.length;

  let currentBeat = 0;
  const resolved: ResolvedShot[] = [];

  for (let i = 0; i < shots.length; i++) {
    const shot = shots[i];
    
    console.warn(
      `Shot ${i} (${shot.type}) missing start_frame/end_frame — ` +
      `falling back to BPM-based timing. Check derive_shots_from_captions().`
    );

    const shotBeats = shot.duration_beats ?? 4;
    
    // Scale beat positions to available audio beats
    const startBeatFraction = currentBeat;
    const endBeatFraction = currentBeat + shotBeats;
    
    const startBeatIndex = Math.round((startBeatFraction / totalShotBeats) * totalAvailableBeats);
    const endBeatIndex = Math.round((endBeatFraction / totalShotBeats) * totalAvailableBeats);

    // Map beat index to frames
    const fromFrame = startBeatIndex === 0 ? 0 : (beatFrames[startBeatIndex - 1] ?? 0);
    let toFrame = endBeatIndex === 0 ? 0 : (beatFrames[endBeatIndex - 1] ?? durationInFrames);
    
    // Last shot must go to the end of composition
    if (i === shots.length - 1) {
      toFrame = durationInFrames;
    }

    resolved.push({
      ...shot,
      from: fromFrame,
      to: toFrame,
      rgb_split: !!shot.rgb_split,
      speed_before: shot.speed_before ?? 1.0,
    });

    currentBeat += shotBeats;
  }

  return resolved;
}

