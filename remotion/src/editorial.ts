export interface BeatData {
  tempo: number;
  beat_frames: number[];
  downbeat_frames: number[];
  energy_peaks: number[];
  beat_interval: number;
}

export interface EditorialStructure {
  hook: string;
  revelation_order: string[];
  takeaway: string;
  visual_metaphor?: string;
  cut_type: "hard_cut" | "smash_cut" | "fade_black" | "push_forward" | "push_back";
  act1_end: number;
  act2_end: number;
}

export const buildEditorialStructure = (durationInFrames: number, beatData: BeatData) => {
  const { downbeat_frames, beat_frames } = beatData;

  // Snap act boundaries to the nearest downbeat
  const ACT_1_END = snapToNearestDownbeat(Math.floor(durationInFrames * 0.15), downbeat_frames);
  const ACT_2_END = snapToNearestDownbeat(Math.floor(durationInFrames * 0.80), downbeat_frames);
  const ACT_3_START = ACT_2_END;

  return {
    act1: {
      from: 0,
      to: ACT_1_END,
      purpose: "hook",
    },
    act2: {
      from: ACT_1_END,
      to: ACT_2_END,
      purpose: "exposition",
      beatSlots: beat_frames.filter((f) => f > ACT_1_END && f < ACT_2_END),
    },
    act3: {
      from: ACT_3_START,
      to: durationInFrames,
      purpose: "resolution",
    },
  };
};

export const snapToNearestDownbeat = (targetFrame: number, downbeats: number[]): number => {
  if (!downbeats || downbeats.length === 0) {
    return targetFrame;
  }
  return downbeats.reduce(
    (nearest, f) => (Math.abs(f - targetFrame) < Math.abs(nearest - targetFrame) ? f : nearest),
    downbeats[0]
  );
};
