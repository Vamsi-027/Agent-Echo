import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";

export interface ZoomPunchProps {
  children: React.ReactNode;
  punchFrame: number;     // frame the punch hits
  targetX?: number;       // 0-1, normalized target point
  targetY?: number;
  peakScale?: number;
  duration?: number;
}

export const ZoomPunch: React.FC<ZoomPunchProps> = ({
  children,
  punchFrame,
  targetX = 0.5,
  targetY = 0.5,
  peakScale = 1.35,
  duration = 12,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - punchFrame,
    fps,
    config: { damping: 6, stiffness: 400, mass: 0.6 },
    // Intentionally springy — the overshoot IS the effect
  });

  const scale = frame < punchFrame
    ? 1
    : interpolate(
        progress,
        [0, 0.4, 1],
        [1, peakScale, 1],     // punch in, spring back
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
      );

  const xOffset = (targetX - 0.5) * (scale - 1) * 1080;
  const yOffset = (targetY - 0.5) * (scale - 1) * 1080;

  return (
    <div style={{
      transform: `scale(${scale}) translate(${-xOffset}px, ${-yOffset}px)`,
      transformOrigin: `${targetX * 100}% ${targetY * 100}%`,
      width: "100%",
      height: "100%",
    }}>
      {children}
    </div>
  );
};
