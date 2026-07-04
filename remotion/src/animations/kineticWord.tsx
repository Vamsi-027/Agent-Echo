import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

export type KineticEntrance = "slam" | "slide_left" | "slide_right" | "rise" | "drop" | "scale_in";

export interface KineticWordProps {
  word: string;
  startFrame: number;
  entrance?: KineticEntrance;
  color?: string;
  size?: number;
  weight?: number;
  tracking?: string;
}

export const KineticWord: React.FC<KineticWordProps> = ({
  word,
  startFrame,
  entrance = "slam",
  color = "#ffffff",
  size = 120,
  weight = 800,
  tracking = "-0.03em",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const elapsed = frame - startFrame;

  const springConfigs = {
    slam:        { damping: 5,  stiffness: 500, mass: 1.2 },   // hard bounce
    slide_left:  { damping: 20, stiffness: 300, mass: 0.8 },   // smooth slide
    slide_right: { damping: 20, stiffness: 300, mass: 0.8 },
    rise:        { damping: 12, stiffness: 200, mass: 0.9 },   // float up
    drop:        { damping: 8,  stiffness: 400, mass: 1.5 },   // heavy drop
    scale_in:    { damping: 10, stiffness: 350, mass: 0.7 },   // pop in
  };

  const config = springConfigs[entrance] || springConfigs.slam;

  const progress = spring({
    frame: Math.max(0, elapsed),
    fps,
    config,
  });

  const transform = {
    slam:        `translateY(${(1 - progress) * -160}px) scaleY(${0.3 + progress * 0.7})`,
    slide_left:  `translateX(${(1 - progress) * -400}px)`,
    slide_right: `translateX(${(1 - progress) * 400}px)`,
    rise:        `translateY(${(1 - progress) * 80}px)`,
    drop:        `translateY(${(1 - progress) * -80}px)`,
    scale_in:    `scale(${0.2 + progress * 0.8})`,
  }[entrance] || `scale(${progress})`;

  return (
    <div style={{
      fontFamily: "Syne",
      fontSize: size,
      fontWeight: weight,
      letterSpacing: tracking,
      color,
      transform,
      opacity: elapsed < 0 ? 0 : 1,
      lineHeight: 1,
      textTransform: "uppercase",
      willChange: "transform",
    }}>
      {word}
    </div>
  );
};
