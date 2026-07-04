import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { postProcessing } from "../theme";

export const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        opacity: postProcessing.filmGrain.opacity,
        mixBlendMode: "overlay",
        // Shifts the noise pattern on random coordinates to simulate physical grain movement
        transform: `translate(${(frame * 7) % 8}px, ${(frame * 13) % 8}px)`,
      }}
    />
  );
};

export const Letterbox: React.FC = () => {
  const barHeight = postProcessing.letterbox.barHeight;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Top Black Bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: barHeight,
          backgroundColor: "#000000",
          zIndex: 100,
        }}
      />
      {/* Bottom Black Bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: barHeight,
          backgroundColor: "#000000",
          zIndex: 100,
        }}
      />
    </AbsoluteFill>
  );
};
