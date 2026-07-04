import React from "react";
import { useCurrentFrame } from "remotion";

export interface CaptionWord {
  text: string;
  startFrame: number;
  endFrame: number;
}

export interface CaptionsOverlayProps {
  captions: CaptionWord[];
  startOffset?: number;
}

export const CaptionsOverlay: React.FC<CaptionsOverlayProps> = ({ captions, startOffset }) => {
  const frame = useCurrentFrame() + (startOffset ?? 8);

  if (!captions || captions.length === 0) {
    return null;
  }

  // Find the active caption for the current frame
  const activeCaption = captions.find(
    (cap) => frame >= cap.startFrame && frame < cap.endFrame
  );

  if (!activeCaption) {
    return null;
  }

  return (
    <div style={{
      position: "absolute",
      bottom: "12%",
      left: 0,
      right: 0,
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      zIndex: 100,
      pointerEvents: "none",
    }}>
      <div style={{
        background: "rgba(10, 10, 10, 0.75)",
        backdropFilter: "blur(12px)",
        borderRadius: "24px",
        padding: "16px 32px",
        border: "1px solid rgba(255, 255, 255, 0.15)",
        boxShadow: "0 10px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(14, 165, 233, 0.2)",
        maxWidth: "85%",
        textAlign: "center",
        transform: "scale(1)",
        animation: "scaleIn 0.15s cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        <span style={{
          fontFamily: "Outfit, Inter, sans-serif",
          fontSize: "42px",
          fontWeight: 900,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#ffffff",
          textShadow: "0 2px 10px rgba(0, 0, 0, 0.5)",
          lineHeight: 1.2,
          display: "inline-block",
        }}>
          {activeCaption.text}
        </span>
      </div>
    </div>
  );
};
