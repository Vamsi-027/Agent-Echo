import { useCurrentFrame } from "remotion";

export interface SpeedRampPoint {
  frame: number;
  speed: number; // 1.0 = normal, 0.3 = slow, 2.5 = fast
}

export function calculateSpeedRampFrame(currentFrame: number, ramps: SpeedRampPoint[]): number {
  if (!ramps || ramps.length === 0) return currentFrame;
  
  // Ensure the ramps are sorted chronologically
  const sortedRamps = [...ramps].sort((a, b) => a.frame - b.frame);
  
  let realTime = 0;
  let lastFrame = 0;
  let lastSpeed = 1.0;

  for (const ramp of sortedRamps) {
    if (currentFrame <= ramp.frame) break;
    realTime += (ramp.frame - lastFrame) * lastSpeed;
    lastFrame = ramp.frame;
    lastSpeed = ramp.speed;
  }
  realTime += (currentFrame - lastFrame) * lastSpeed;

  return realTime;
}

export const useSpeedRamp = (ramps: SpeedRampPoint[]) => {
  const frame = useCurrentFrame();
  return calculateSpeedRampFrame(frame, ramps);
};
