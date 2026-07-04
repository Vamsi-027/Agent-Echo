export const PALETTE = {
  // Surfaces
  void:      "#080C14",   // true background — slightly blue-black, not neutral
  depth:     "#0D1520",   // card backs, secondary surfaces
  surface:   "#141E2E",   // card faces
  elevated:  "#1A2640",   // active/hover surfaces

  // Brand spectrum — desaturated enough to feel engineered
  blue:      "#4F8EF7",   // primary action, technical insight
  cyan:      "#22D3EE",   // data flow, connections
  green:     "#10B981",   // success, published, approved
  amber:     "#F59E0B",   // in-progress, warning, publishing
  red:       "#EF4444",   // failure, error, rejected
  purple:    "#A78BFA",   // lesson learned pillar
  slate:     "#94A3B8",   // secondary text, disabled states

  // Text
  primary:   "#F8FAFC",   // headlines
  secondary: "#94A3B8",   // body text
  tertiary:  "#4E6580",   // captions, metadata
  mono:      "#7DD3FC",   // code, technical labels

  // Glow colors
  glowBlue:  "#4F8EF733",
  glowGreen: "#10B98133",
  glowAmber: "#F59E0B33",
};

export const PILLAR_PALETTE = {
  technical_insight:   { accent: PALETTE.blue,   glow: PALETTE.glowBlue  },
  project_milestone:   { accent: PALETTE.green,  glow: PALETTE.glowGreen },
  lesson_learned:      { accent: PALETTE.purple, glow: "#A78BFA33"        },
  industry_commentary: { accent: PALETTE.cyan,   glow: "#22D3EE33"        },
} as const;

export const postProcessing = {
  bloom: {
    intensity: 1.5,
    luminanceThreshold: 0.6,
    luminanceSmoothing: 0.3,
    radius: 0.8,
  },
  filmGrain: {
    opacity: 0.02,
  },
  letterbox: {
    barHeight: "5%",
  },
} as const;

// Keep legacy theme compatibility for un-refactored paths or general imports
export const theme = {
  colors: {
    bgDark: PALETTE.void,
    bgCard: PALETTE.depth,
    bgCardHover: PALETTE.surface,
    primary: PALETTE.blue,
    secondary: PALETTE.purple,
    accent: PALETTE.green,
    warning: PALETTE.amber,
    textPrimary: PALETTE.primary,
    textSecondary: PALETTE.secondary,
    border: PALETTE.elevated,
    highlight: PALETTE.cyan,
    gradientStart: PALETTE.blue,
    gradientEnd: PALETTE.purple,
  },
  fonts: {
    heading: "Space Grotesk, sans-serif",
    body: "Space Grotesk, sans-serif",
    mono: "JetBrains Mono, monospace",
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  },
  borderRadius: {
    sm: 6,
    md: 12,
    lg: 20,
  },
} as const;
