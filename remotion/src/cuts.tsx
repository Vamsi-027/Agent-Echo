import React from "react";
import { Sequence, useCurrentFrame, interpolate } from "remotion";

export const HardCut: React.FC<{
  from: number;
  duration?: number;
  children: React.ReactNode;
}> = ({ from, duration, children }) => (
  <Sequence from={from} durationInFrames={duration}>
    {children}
  </Sequence>
);

export const SmashCut: React.FC<{
  from: number;
  duration?: number;
  children: React.ReactNode;
}> = ({ from, duration, children }) => {
  const frame = useCurrentFrame();
  const scale =
    frame >= from - 4 && frame < from
      ? interpolate(frame, [from - 4, from], [1, 1.08])
      : 1;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `scale(${scale})`,
        transformOrigin: "center",
      }}
    >
      <Sequence from={from} durationInFrames={duration}>
        {children}
      </Sequence>
    </div>
  );
};

export const FadeThroughBlack: React.FC<{
  from: number;
  durationFrames?: number;
  children: React.ReactNode;
}> = ({ from, durationFrames = 10, children }) => {
  const frame = useCurrentFrame();
  const midPoint = from + Math.floor(durationFrames / 2);
  const opacity =
    frame < midPoint
      ? interpolate(frame, [from, midPoint], [1, 0])
      : interpolate(frame, [midPoint, from + durationFrames], [0, 1]);

  return (
    <div style={{ width: "100%", height: "100%", opacity }}>
      <Sequence from={from}>
        {children}
      </Sequence>
    </div>
  );
};

export const PushCut: React.FC<{
  from: number;
  direction?: "forward" | "backward";
  durationFrames?: number;
  children: React.ReactNode;
}> = ({ from, direction = "forward", durationFrames = 8, children }) => {
  const frame = useCurrentFrame();
  const progress = Math.min(1, Math.max(0, (frame - from) / durationFrames));
  const eased = 1 - Math.pow(1 - progress, 2); // easeOutQuad
  const xOffset = direction === "forward" ? (1 - eased) * -1080 : (1 - eased) * 1080;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `translateX(${xOffset}px)`,
      }}
    >
      <Sequence from={from}>
        {children}
      </Sequence>
    </div>
  );
};
