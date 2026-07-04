import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

export interface RGBSplitProps {
  children: React.ReactNode;
  triggerFrames: number[]; // array of frames where the effect fires
  intensity?: number;
}

export const RGBSplit: React.FC<RGBSplitProps> = ({
  children,
  triggerFrames,
  intensity = 8,
}) => {
  const frame = useCurrentFrame();

  const nearestTrigger = triggerFrames.reduce((nearest, t) =>
    Math.abs(t - frame) < Math.abs(nearest - frame) ? t : nearest
  , triggerFrames[0] ?? -999);

  const elapsed = frame - nearestTrigger;
  const active = elapsed >= 0 && elapsed < 6;

  const split = active
    ? interpolate(elapsed, [0, 2, 6], [intensity, intensity * 0.5, 0])
    : 0;

  if (split === 0) return <>{children}</>;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Red channel — shifted left */}
      <div style={{
        position: "absolute",
        inset: 0,
        mixBlendMode: "screen",
        filter: "url(#red-channel)",
        transform: `translateX(${-split}px)`,
        opacity: 0.7,
        pointerEvents: "none",
      }}>
        {children}
      </div>
      {/* Blue channel — shifted right */}
      <div style={{
        position: "absolute",
        inset: 0,
        mixBlendMode: "screen",
        filter: "url(#blue-channel)",
        transform: `translateX(${split}px)`,
        opacity: 0.7,
        pointerEvents: "none",
      }}>
        {children}
      </div>
      {/* Normal composite */}
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        {children}
      </div>

      {/* SVG filter definitions */}
      <svg style={{ position: "absolute", width: 0, height: 0 }}>
        <defs>
          <filter id="red-channel">
            <feColorMatrix type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"/>
          </filter>
          <filter id="blue-channel">
            <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"/>
          </filter>
        </defs>
      </svg>
    </div>
  );
};
