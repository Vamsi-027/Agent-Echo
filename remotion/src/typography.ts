import { loadFont as loadSyne } from "@remotion/google-fonts/Syne";
import { loadFont as loadSpaceGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";

// Load only the weights actually used — keeps render fast
export const fonts = {
  display: loadSyne("normal", { weights: ["700", "800"] }),
  body: loadSpaceGrotesk("normal", { weights: ["400", "500", "600"] }),
  mono: loadJetBrainsMono("normal", { weights: ["400", "700"] }),
};

export const TYPE = {
  display: {
    fontFamily: "Syne",
    fontSize: 72,
    fontWeight: 800 as const,
    letterSpacing: "-0.02em",
    lineHeight: 1.0,
  },
  title: {
    fontFamily: "Syne",
    fontSize: 48,
    fontWeight: 700 as const,
    letterSpacing: "-0.01em",
    lineHeight: 1.1,
  },
  heading: {
    fontFamily: "Space Grotesk",
    fontSize: 32,
    fontWeight: 600 as const,
    letterSpacing: "0em",
    lineHeight: 1.2,
  },
  label: {
    fontFamily: "Space Grotesk",
    fontSize: 20,
    fontWeight: 500 as const,
    letterSpacing: "0.04em",
    lineHeight: 1.3,
  },
  body: {
    fontFamily: "Space Grotesk",
    fontSize: 18,
    fontWeight: 400 as const,
    letterSpacing: "0em",
    lineHeight: 1.6,
  },
  caption: {
    fontFamily: "Space Grotesk",
    fontSize: 14,
    fontWeight: 400 as const,
    letterSpacing: "0.02em",
    lineHeight: 1.4,
  },
  code: {
    fontFamily: "JetBrains Mono",
    fontSize: 16,
    fontWeight: 400 as const,
    letterSpacing: "0em",
    lineHeight: 1.5,
  },
  codeLabel: {
    fontFamily: "JetBrains Mono",
    fontSize: 13,
    fontWeight: 700 as const,
    letterSpacing: "0.06em",
    lineHeight: 1.0,
  },
};
