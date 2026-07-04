import React from "react";

export interface MotionBlurProps {
  children: React.ReactNode;
  blurAmount: number; // Blur radius in pixels
  direction?: "horizontal" | "vertical" | "both";
}

export const MotionBlur: React.FC<MotionBlurProps> = ({
  children,
  blurAmount,
  direction = "both",
}) => {
  if (blurAmount <= 0.2) {
    return <>{children}</>;
  }

  // To prevent the edges from looking transparent/bleeding during blur,
  // we scale the container slightly based on the blur amount.
  const scale = 1 + (blurAmount * 0.015);
  
  // Simple CSS blur filter
  const filter = `blur(${blurAmount}px)`;

  return (
    <div style={{
      filter,
      transform: `scale(${scale})`,
      width: "100%",
      height: "100%",
      willChange: "filter, transform",
    }}>
      {children}
    </div>
  );
};
