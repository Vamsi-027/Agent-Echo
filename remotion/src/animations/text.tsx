import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { TYPE } from "../typography";

export const WordReveal: React.FC<{
  text: string;
  startFrame: number;
  stagger?: number;
  style?: React.CSSProperties;
}> = ({ text, startFrame, stagger = 3, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");

  return (
    <span
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.25em",
        ...style,
      }}
    >
      {words.map((word, i) => {
        const wordFrame = startFrame + i * stagger;
        const progress = spring({
          frame: frame - wordFrame,
          fps,
          config: { damping: 12, stiffness: 180, mass: 0.8 },
        });

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: Math.min(1, Math.max(0, progress)),
              transform: `translateY(${(1 - progress) * 24}px)`,
              filter: `blur(${Math.max(0, (1 - progress) * 4)}px)`,
            }}
          >
            {word}
          </span>
        );
      })}
    </span>
  );
};

export const TypewriterReveal: React.FC<{
  text: string;
  startFrame: number;
  charsPerFrame?: number;
  style?: React.CSSProperties;
}> = ({ text, startFrame, charsPerFrame = 2, style }) => {
  const frame = useCurrentFrame();
  const chars = Math.min(text.length, Math.max(0, (frame - startFrame) * charsPerFrame));

  return (
    <span style={{ ...TYPE.code, ...style }}>
      {text.slice(0, chars)}
      {chars < text.length && (
        <span style={{ opacity: Math.floor((frame - startFrame) / 8) % 2 }}>█</span>
      )}
    </span>
  );
};

export const CountUp: React.FC<{
  value: string;
  unit: string;
  startFrame: number;
  duration?: number;
  style?: React.CSSProperties;
}> = ({ value, unit, startFrame, duration = 30, style }) => {
  const frame = useCurrentFrame();
  const progress = Math.min(1, Math.max(0, (frame - startFrame) / duration));
  // Ease out cubic — fast start, slow landing
  const eased = 1 - Math.pow(1 - progress, 3);
  const numericValue = parseFloat(value.replace(/[^0-9.]/g, "")) || 0;
  const displayed = Math.floor(numericValue * eased);

  return (
    <span style={style}>
      <span style={{ ...TYPE.display, fontSize: TYPE.display.fontSize - 12 }}>
        {displayed.toLocaleString()}
      </span>
      <span style={{ ...TYPE.label, opacity: 0.6, marginLeft: 6 }}>
        {unit}
      </span>
    </span>
  );
};
