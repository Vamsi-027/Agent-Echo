import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
  interpolate,
  spring,
} from "remotion";
import { Audio } from "@remotion/media";
import { ThreeCanvas } from "@remotion/three";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";

import { PALETTE, PILLAR_PALETTE, theme } from "../theme";
import { TYPE } from "../typography";
import { BeatData, EditorialStructure } from "../editorial";
import { useSpeedRamp, calculateSpeedRampFrame } from "../animations/speedRamp";
import { ZoomPunch } from "../animations/zoomPunch";
import { KineticWord } from "../animations/kineticWord";
import { RGBSplit } from "../effects/RGBSplit";
import { MotionBlur } from "../effects/MotionBlur";
import { CaptionsOverlay, CaptionWord } from "../components/CaptionsOverlay";
import { Shot, resolveShotList } from "../shot_list";
import { FilmGrain, Letterbox } from "../components/FilmGrain";

interface Metric {
  label: string;
  before: number;
  after: number;
  unit: string;
}

interface Props {
  title: string;
  metrics: Metric[];
  audioFile?: string;
  beatData: BeatData;
  editorialStructure: EditorialStructure;
  shots: Shot[];
  captions: CaptionWord[];
  startOffset?: number;
}

const ReflectiveGround: React.FC = () => {
  return (
    <group position={[0, -1.5, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial
          color={PALETTE.depth}
          roughness={0.15}
          metalness={0.9}
        />
      </mesh>
      <gridHelper args={[20, 20, PALETTE.elevated, PALETTE.surface]} position={[0, 0.01, 0]} />
    </group>
  );
};

// Orbiting Camera rig with speed ramped frame
const CameraRig: React.FC<{
  frame: number;
  totalFrames: number;
  fps: number;
  beatData: BeatData;
}> = ({ frame, totalFrames, fps, beatData }) => {
  const radius = 5.5;
  const progress = frame / totalFrames;
  
  const angle = progress * Math.PI * 0.4 - Math.PI * 0.2;
  const x = radius * Math.sin(angle);
  const z = radius * Math.cos(angle);
  
  // Beat pulse camera zoom
  const activeBeat = beatData.beat_frames.find(bf => Math.abs(frame - bf) < 3);
  const zoomPulse = activeBeat ? 0.96 : 1.0;
  
  return (
    <perspectiveCamera
      makeDefault
      position={[x * zoomPulse, 1.2, z * zoomPulse]}
      fov={45}
      onUpdate={(self) => {
        self.lookAt(0, 0, 0);
      }}
    />
  );
};

export const MetricsSummaryAnimation: React.FC<Props> = ({
  title,
  metrics,
  audioFile,
  beatData,
  editorialStructure,
  shots,
  captions,
  startOffset,
}) => {
  const frame = useCurrentFrame() + (startOffset ?? 8);
  const { fps, durationInFrames, width, height } = useVideoConfig();

  const pillarAccent = PILLAR_PALETTE.technical_insight.accent;

  // Resolve shots to frame ranges
  const resolvedShots = resolveShotList(shots, beatData.beat_frames, durationInFrames);
  const activeShot = resolvedShots.find(s => frame >= s.from && frame < s.to) || resolvedShots[0];

  // Build speed ramp points dynamically based on shot configurations
  const ramps = resolvedShots.flatMap(s => {
    if (s.speed_before && s.speed_before !== 1.0) {
      return [
        { frame: Math.max(0, s.from - 8), speed: s.speed_before },
        { frame: s.from, speed: 1.0 }
      ];
    }
    return [];
  });
  const effectiveFrame = calculateSpeedRampFrame(frame, ramps);

  // Check if speed is high to trigger motion blur
  const isSpeedHigh = ramps.some(r => frame >= r.frame && frame < r.frame + 4 && r.speed > 1.5);
  const blurAmount = isSpeedHigh ? 6 : 0;

  // RGB Split triggers
  const rgbSplitTriggers = resolvedShots.filter(s => s.rgb_split).map(s => s.from);

  // Zoom punch triggers
  const zoomPunchShot = resolvedShots.find(s => s.entrance === "zoom_punch" && frame >= s.from && frame < s.to);
  const zoomPunchFrame = zoomPunchShot ? zoomPunchShot.from : -999;

  // Space metric cards horizontally on the 2D overlay
  const cardWidth = 260;
  const gap = 40;
  const totalWidth = metrics.length * cardWidth + (metrics.length - 1) * gap;
  const startX = (1080 - totalWidth) / 2;
  const y = 440;

  // Map card reveals to the start frame of 3D shots
  const threeShots = resolvedShots.filter(s => s.type !== "hook_word" && s.type !== "takeaway_word");
  const revealFrames = metrics.map((_, i) => {
    return threeShots[i]?.from ?? (durationInFrames / 2);
  });

  return (
    <AbsoluteFill style={{ backgroundColor: PALETTE.void }}>
      {audioFile && <Audio src={staticFile(audioFile)} />}

      {/* Transition sound effects */}
      {resolvedShots.map((shot, idx) => {
        const sfxFrom = Math.max(0, shot.from - (startOffset ?? 8));
        if (shot.entrance === "slam" || shot.entrance === "zoom_punch") {
          return (
            <Audio
              key={`sfx-${idx}`}
              src={staticFile("sfx/pop.wav")}
              from={sfxFrom}
              volume={0.5}
            />
          );
        }
        if (shot.entrance === "slide_left" || shot.entrance === "slide_right") {
          return (
            <Audio
              key={`sfx-${idx}`}
              src={staticFile("sfx/whoosh.wav")}
              from={sfxFrom}
              volume={0.4}
            />
          );
        }
        return null;
      })}

      <RGBSplit triggerFrames={rgbSplitTriggers} intensity={8}>
        <ZoomPunch punchFrame={zoomPunchFrame} peakScale={1.35}>
          <MotionBlur blurAmount={blurAmount}>
            <AbsoluteFill>
              {/* If it's a typography-only shot */}
              {activeShot && (activeShot.type === "hook_word" || activeShot.type === "takeaway_word") ? (
                <AbsoluteFill style={{ display: "flex", justifyContent: "center", alignItems: "center", padding: 60 }}>
                  <KineticWord
                    word={activeShot.content}
                    startFrame={activeShot.from}
                    entrance={activeShot.entrance as any}
                    color={PALETTE.primary}
                  />
                </AbsoluteFill>
              ) : (
                /* Else it's a 3D shot */
                <AbsoluteFill>
                  <ThreeCanvas width={width} height={height}>
                    <ambientLight intensity={0.4} />
                    <pointLight position={[5, 6, 5]} intensity={1.5} color={pillarAccent} />
                    <pointLight position={[-5, -2, -5]} intensity={0.5} color={PALETTE.cyan} />

                    <CameraRig frame={effectiveFrame} totalFrames={durationInFrames} fps={fps} beatData={beatData} />
                    <ReflectiveGround />

                    <EffectComposer>
                      <Bloom intensity={1.0} luminanceThreshold={0.5} luminanceSmoothing={0.2} radius={0.8} />
                    </EffectComposer>
                  </ThreeCanvas>

                  {/* 2D Metrics Cards Overlay */}
                  <AbsoluteFill style={{ pointerEvents: "none" }}>
                    <div
                      style={{
                        position: "absolute",
                        top: 80,
                        width: "100%",
                        textAlign: "center",
                        ...TYPE.codeLabel,
                        color: PALETTE.mono,
                      }}
                    >
                      {title.toUpperCase()}
                    </div>

                    {/* Render Cards */}
                    {metrics.map((m, i) => {
                      const delay = revealFrames[i];
                      const cardSpring = spring({
                        frame: effectiveFrame - delay,
                        fps,
                        config: { damping: 14, stiffness: 100 },
                      });

                      if (effectiveFrame < delay) return null;

                      const countDelay = delay + 10;
                      const countProgressVal = interpolate(
                        effectiveFrame,
                        [countDelay, countDelay + 30],
                        [0, 1],
                        { extrapolateRight: "clamp" }
                      );

                      const currentVal = Math.round(m.before + (m.after - m.before) * countProgressVal);

                      // Check improvement direction
                      const improved =
                        m.label.toLowerCase().includes("error") ||
                        m.label.toLowerCase().includes("latency")
                          ? m.after < m.before
                          : m.after > m.before;
                      const deltaColor = improved ? PALETTE.green : PALETTE.amber;

                      const delta = m.after - m.before;
                      const deltaPercent = m.before !== 0 ? Math.round((delta / m.before) * 100) : 0;
                      const deltaSign = delta > 0 ? "+" : "";

                      const cardX = startX + i * (cardWidth + gap);

                      return (
                        <React.Fragment key={m.label}>
                          {/* Pop sound effect */}
                          {audioFile && (
                            <Audio
                              key={`sfx-pop-${i}`}
                              src={staticFile("sfx/pop.wav")}
                              from={Math.max(0, delay - (startOffset ?? 8))}
                              volume={0.4}
                            />
                          )}

                          {/* Tick sound effects for metric change highlights */}
                          {audioFile && (
                            <React.Fragment key={`sfx-ticks-${i}`}>
                              <Audio
                                src={staticFile("sfx/tick.wav")}
                                from={Math.max(0, countDelay + 5 - (startOffset ?? 8))}
                                volume={0.35}
                              />
                              <Audio
                                src={staticFile("sfx/tick.wav")}
                                from={Math.max(0, countDelay + 25 - (startOffset ?? 8))}
                                volume={0.35}
                              />
                            </React.Fragment>
                          )}

                          {/* Card container */}
                          <div
                            style={{
                              position: "absolute",
                              left: cardX,
                              top: y,
                              width: cardWidth,
                              height: 200,
                              borderRadius: 16,
                              backgroundColor: `${PALETTE.surface}CC`,
                              border: `2px solid ${PALETTE.elevated}`,
                              transform: `scale(${cardSpring})`,
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              justifyContent: "center",
                              padding: 16,
                              boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                              backdropFilter: "blur(10px)",
                            }}
                          >
                            <div
                              style={{
                                ...TYPE.caption,
                                color: PALETTE.secondary,
                                fontWeight: 600,
                                letterSpacing: "0.08em",
                                marginBottom: 12,
                                textAlign: "center",
                                textTransform: "uppercase",
                              }}
                            >
                              {m.label}
                            </div>

                            {/* Animated Value */}
                            <div
                              style={{
                                color: PALETTE.primary,
                                fontSize: 38,
                                fontWeight: 800,
                                fontFamily: "JetBrains Mono",
                                lineHeight: 1,
                              }}
                            >
                              {currentVal}
                              <span style={{ fontSize: 18, color: PALETTE.secondary, marginLeft: 4 }}>
                                {m.unit}
                              </span>
                            </div>

                            {/* Delta badge */}
                            <div
                              style={{
                                marginTop: 16,
                                color: deltaColor,
                                ...TYPE.code,
                                fontSize: 12,
                                fontWeight: 600,
                                opacity: interpolate(effectiveFrame, [countDelay + 25, countDelay + 35], [0, 1], {
                                  extrapolateRight: "clamp",
                                }),
                              }}
                            >
                              {deltaSign}
                              {deltaPercent}% from {m.before}
                              {m.unit}
                            </div>
                          </div>
                        </React.Fragment>
                      );
                    })}

                    {/* Bottom overlay text showing active shot content */}
                    {activeShot && activeShot.content && (
                      <div
                        style={{
                          position: "absolute",
                          bottom: "22%",
                          width: "100%",
                          textAlign: "center",
                          padding: "0 60px",
                        }}
                      >
                        <div style={{
                          fontFamily: theme.fonts.mono,
                          color: PALETTE.secondary,
                          fontSize: 20,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                        }}>
                          {activeShot.content}
                        </div>
                      </div>
                    )}
                  </AbsoluteFill>
                </AbsoluteFill>
              )}
            </AbsoluteFill>
          </MotionBlur>
        </ZoomPunch>
      </RGBSplit>

      <CaptionsOverlay captions={captions} startOffset={startOffset} />
      <FilmGrain />
      <Letterbox />
    </AbsoluteFill>
  );
};
