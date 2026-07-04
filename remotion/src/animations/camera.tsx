import React from "react";
import { useFrame } from "@react-three/fiber";
import { spring } from "remotion";

export const CameraRig: React.FC<{
  frame: number;
  totalFrames: number;
  fps: number;
  beatData: any;
}> = ({ frame, totalFrames, fps, beatData }) => {
  const progress = frame / totalFrames;
  // Slow spatial orbit
  const angle = progress * Math.PI * 0.3;
  const radius = 8;
  const targetX = Math.sin(angle) * radius;
  const targetZ = Math.cos(angle) * radius;
  const targetY = 1.2;

  // Camera shake intensity triggered by beat energy peaks
  let shakeOffset = 0;
  if (beatData && beatData.energy_peaks && beatData.energy_peaks.length > 0) {
    const pastPeaks = beatData.energy_peaks.filter((p: number) => p <= frame);
    if (pastPeaks.length > 0) {
      const lastPeak = pastPeaks[pastPeaks.length - 1];
      const peakDistance = frame - lastPeak;
      // Active bounce decay duration
      if (peakDistance >= 0 && peakDistance < 15) {
        const bounce = spring({
          frame: peakDistance,
          fps,
          config: { damping: 8, stiffness: 200 },
        });
        shakeOffset = (1 - bounce) * 0.12;
      }
    }
  }

  useFrame(({ camera }) => {
    // Generate small orthogonal shake offsets
    const shakeX = Math.sin(frame * 1.8) * shakeOffset;
    const shakeY = Math.cos(frame * 2.1) * shakeOffset;

    camera.position.set(targetX + shakeX, targetY + shakeY, targetZ);
    camera.lookAt(0, 0, 0);
  });

  return null;
};
