import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
  spring,
} from "remotion";
import { Audio } from "@remotion/media";
import { ThreeCanvas } from "@remotion/three";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE, PILLAR_PALETTE, theme } from "../theme";
import { TYPE } from "../typography";
import { BeatData, EditorialStructure } from "../editorial";
import { useSpeedRamp, calculateSpeedRampFrame } from "../animations/speedRamp";
import { ZoomPunch } from "../animations/zoomPunch";
import { KineticWord } from "../animations/kineticWord";
import { RGBSplit } from "../effects/RGBSplit";
import { MotionBlur } from "../effects/MotionBlur";
import { CaptionWord } from "../components/CaptionsOverlay";
import { Shot, resolveShotList } from "../shot_list";
import { FilmGrain, Letterbox } from "../components/FilmGrain";

interface Stage {
  name?: string;
  description?: string;
  label?: string;
  sublabel?: string;
  id?: string;
  icon?: string;
  color?: string;
}

interface Props {
  title?: string;
  stages?: Stage[];
  audioFile?: string;
  beatData?: BeatData;
  editorialStructure?: EditorialStructure;
  shots?: Shot[];
  captions?: CaptionWord[];
  startOffset?: number;
}

const PipelineDollyRig: React.FC<{
  cameraX: number;
  frame: number;
  beatData: any;
}> = ({ cameraX, frame, beatData }) => {
  // Camera shake intensity triggered by beat energy peaks
  let shakeOffset = 0;
  if (beatData && beatData.energy_peaks && beatData.energy_peaks.length > 0) {
    const pastPeaks = beatData.energy_peaks.filter((p: number) => p <= frame);
    if (pastPeaks.length > 0) {
      const lastPeak = pastPeaks[pastPeaks.length - 1];
      const peakDistance = frame - lastPeak;
      if (peakDistance >= 0 && peakDistance < 15) {
        shakeOffset = (1 - (peakDistance / 15)) * 0.1;
      }
    }
  }

  useFrame(({ camera }) => {
    const shakeX = Math.sin(frame * 1.8) * shakeOffset;
    const shakeY = Math.cos(frame * 2.1) * shakeOffset;

    camera.position.set(cameraX + shakeX, 1.2 + shakeY, 5.0);
    camera.lookAt(cameraX, 0, 0);
  });

  return null;
};

const PipelineBlock: React.FC<{
  position: [number, number, number];
  color: string;
  revealFrame: number;
  frame: number;
}> = ({ position, color, revealFrame, frame }) => {
  const opacity = Math.min(1, Math.max(0, (frame - revealFrame) / 15));
  const zScale = opacity;

  // Float up/down and rotate continuously once revealed
  const floatY = opacity > 0 ? Math.sin(frame * 0.05 + position[0]) * 0.12 : 0;
  const rotY = opacity > 0 ? frame * 0.008 + position[0] : 0;

  return (
    <group position={[position[0], position[1] + floatY, position[2]]} rotation={[0, rotY, 0]}>
      {/* 3D block mesh */}
      <mesh>
        <boxGeometry args={[1.8, 0.9, 0.4 * zScale]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity * 0.25}
          roughness={0.3}
          metalness={0.7}
        />
      </mesh>
      {/* 3D Border mesh wireframe */}
      <mesh>
        <boxGeometry args={[1.84, 0.94, 0.42 * zScale]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity * 0.9}
          wireframe
        />
      </mesh>
    </group>
  );
};

const PipelineTrack: React.FC<{
  fromX: number;
  toX: number;
  color: string;
  revealFrame: number;
  frame: number;
  beatData: any;
}> = ({ fromX, toX, color, revealFrame, frame, beatData }) => {
  const opacity = Math.min(1, Math.max(0, (frame - revealFrame) / 15));
  if (opacity <= 0) return null;

  // Pulse glow on downbeats
  let emissiveIntensity = 0.5;
  if (beatData && beatData.beat_frames) {
    const isNearBeat = beatData.beat_frames.some((bf: number) => Math.abs(frame - bf) < 4);
    if (isNearBeat) {
      emissiveIntensity = 1.3;
    }
  }

  return (
    <mesh position={[(fromX + toX) / 2, -0.6, 0]}>
      <boxGeometry args={[toX - fromX - 0.4, 0.05, 0.05]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={opacity * 0.5}
        emissive={color}
        emissiveIntensity={emissiveIntensity}
      />
    </mesh>
  );
};

export const PipelineFlowAnimation: React.FC<Props> = ({
  title = "Pipeline Flow",
  stages = [],
  audioFile,
  beatData = { tempo: 120, beat_frames: [], downbeat_frames: [], energy_peaks: [], beat_interval: 15 },
  editorialStructure = { hook: "", revelation_order: [], takeaway: "", visual_metaphor: "", cut_type: "hard_cut", act1_end: 0, act2_end: 0 },
  shots = [],
  captions = [],
  startOffset = 8,
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

  // Space stages horizontally in 3D space
  const spacingX = 2.6;
  const nodePositions = stages.map((_, i) => {
    const x = (i - (stages.length - 1) / 2) * spacingX;
    return [x, 0, 0] as [number, number, number];
  });

  // Map 3D reveals to the start frame of 3D shots
  const threeShots = resolvedShots.filter(s => s.type !== "hook_word" && s.type !== "takeaway_word");
  const revealFrames = stages.map((_, i) => {
    return threeShots[i]?.from ?? (durationInFrames / 2);
  });

  const trackRevealFrames = stages.slice(0, -1).map((_, i) => {
    return (revealFrames[i] ?? (durationInFrames / 2)) + 8;
  });

  // Camera Dolly Rig glide based on active shot index
  const currentThreeShotIdx = threeShots.findIndex(s => frame >= s.from && frame < s.to);
  const activeIdx = Math.max(0, currentThreeShotIdx);
  const prevIdx = Math.max(0, activeIdx - 1);
  const activeShotObj = threeShots[activeIdx];
  const startFrameOfShot = activeShotObj ? activeShotObj.from : 0;

  // Spring transition progress when shot index changes
  const elapsedInShot = frame - startFrameOfShot;
  const transitionProgress = spring({
    frame: Math.max(0, elapsedInShot),
    fps,
    config: { damping: 18, stiffness: 80, mass: 1.0 },
  });

  const prevX = nodePositions[Math.min(prevIdx, nodePositions.length - 1)][0];
  const targetX = nodePositions[Math.min(activeIdx, nodePositions.length - 1)][0];
  const currentCamX = prevX + (targetX - prevX) * transitionProgress;

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
                  {/* Glowing audio waveform visualizer */}
                  {activeShot.type === "takeaway_word" && (
                    <div
                      style={{
                        position: "absolute",
                        left: "10%",
                        right: "10%",
                        bottom: "12%",
                        height: 120,
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "flex-end",
                        gap: 6,
                        pointerEvents: "none",
                      }}
                    >
                      {Array.from({ length: 28 }).map((_, bIdx) => {
                        const waveSeed = bIdx * 0.3 + (frame - activeShot.from) * 0.18;
                        const baseHeight = Math.sin(waveSeed) * Math.cos(waveSeed * 0.6);
                        const finalHeight = 10 + Math.abs(baseHeight) * 90;

                        return (
                          <div
                            key={bIdx}
                            style={{
                              width: 8,
                              height: `${finalHeight}px`,
                              backgroundColor: PALETTE.cyan,
                              borderRadius: 4,
                              boxShadow: `0 0 10px ${PALETTE.cyan}66`,
                              opacity: 0.85,
                            }}
                          />
                        );
                      })}
                    </div>
                  )}
                </AbsoluteFill>
              ) : (
                /* Else it's a 3D shot */
                <AbsoluteFill>
                  <ThreeCanvas width={width} height={height}>
                    <ambientLight intensity={0.4} />
                    <pointLight position={[0, 4, 3]} intensity={1.5} color={pillarAccent} />
                    <pointLight position={[5, -2, -3]} intensity={0.5} color={PALETTE.cyan} />

                    <PipelineDollyRig
                      cameraX={currentCamX}
                      frame={effectiveFrame}
                      beatData={beatData}
                    />

                    {/* Render 3D Blocks */}
                    {stages.map((stage, i) => (
                      <PipelineBlock
                        key={stage.label || stage.name || i}
                        position={nodePositions[i]}
                        color={i === (Math.floor(effectiveFrame / 30)) % stages.length ? PALETTE.green : pillarAccent}
                        revealFrame={revealFrames[i]}
                        frame={effectiveFrame}
                      />
                    ))}

                    {/* Render Connecting Tracks */}
                    {stages.slice(0, -1).map((_, i) => (
                      <PipelineTrack
                        key={`track-${i}`}
                        fromX={nodePositions[i][0]}
                        toX={nodePositions[i + 1][0]}
                        color={PALETTE.cyan}
                        revealFrame={trackRevealFrames[i]}
                        frame={effectiveFrame}
                        beatData={beatData}
                      />
                    ))}

                    <EffectComposer>
                      <Bloom intensity={1.2} luminanceThreshold={0.5} luminanceSmoothing={0.2} radius={0.8} />
                    </EffectComposer>
                  </ThreeCanvas>

                  {/* 2D Text overlay synced to camera location */}
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

                    {/* Spatially tracked labels */}
                    {stages.map((stage, i) => {
                      const revealFrame = revealFrames[i];
                      if (effectiveFrame < revealFrame) return null;

                      const relativeX = nodePositions[i][0] - currentCamX;
                      const leftPercent = 50 + (relativeX / 5) * 100;

                      if (leftPercent < -10 || leftPercent > 110) return null;

                      // Hide spatial labels during full-screen custom overlays to prevent clutter
                      const isDetailOverlay = activeShot && (
                        activeShot.chapter_index === 3 ||
                        activeShot.chapter_index === 7 ||
                        activeShot.chapter_index === 8 ||
                        activeShot.chapter_index === 9 ||
                        activeShot.chapter_index === 10
                      );
                      if (isDetailOverlay) return null;

                      return (
                        <div
                          key={`label-${stage.label || stage.name || i}`}
                          style={{
                            position: "absolute",
                            left: `${leftPercent}%`,
                            top: "54%",
                            transform: "translate(-50%, -50%)",
                            textAlign: "center",
                            width: 180,
                          }}
                        >
                          <div style={{ ...TYPE.heading, fontSize: 20, color: PALETTE.primary, fontWeight: 700, marginBottom: 4 }}>
                            {stage.label || stage.name}
                          </div>
                        </div>
                      );
                    })}

                    {/* [SCENE 0 - Shot 1] Hook Glitch Grid */}
                    {activeShot && activeShot.chapter_index === 0 && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                          padding: 60,
                          fontFamily: theme.fonts.mono,
                          color: PALETTE.red,
                          fontSize: 16,
                          pointerEvents: "none",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <div>LOC: [0x7FFA2B]</div>
                          <div>SYS: ACTIVE</div>
                        </div>
                        <div
                          style={{
                            alignSelf: "center",
                            textAlign: "center",
                            fontSize: 22,
                            color: PALETTE.primary,
                            textShadow: `0 0 10px ${PALETTE.red}`,
                            opacity: Math.max(0, Math.min(1, (frame - activeShot.from) / 10)),
                          }}
                        >
                          {frame - activeShot.from > 25 ? "WARNING: AUTONOMOUS LOGIC DETECTED" : "STATUS: DECRYPTING SIGNAL..."}
                          <span style={{ opacity: Math.floor(frame / 6) % 2 === 0 ? 1 : 0 }}>_</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <div>CORE: ECHO_V2</div>
                          <div>SIG: ENCRYPTED</div>
                        </div>
                      </div>
                    )}

                    {/* [SCENE 1 - Shot 2] Tech HUD Scanner */}
                    {activeShot && activeShot.chapter_index === 1 && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          display: "flex",
                          justifyContent: "center",
                          alignItems: "center",
                          pointerEvents: "none",
                        }}
                      >
                        <div
                          style={{
                            width: 320,
                            height: 320,
                            border: `2px dashed ${PALETTE.cyan}`,
                            borderRadius: "50%",
                            opacity: 0.45,
                            transform: `rotate(${(frame - activeShot.from) * 1.5}deg)`,
                          }}
                        />
                        <div
                          style={{
                            position: "absolute",
                            width: 140,
                            height: 140,
                            border: `1px solid ${PALETTE.blue}`,
                            borderRadius: "50%",
                            opacity: 0.65,
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                            transform: `scale(${1 + Math.sin((frame - activeShot.from) * 0.08) * 0.05})`,
                          }}
                        >
                          <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: PALETTE.blue }} />
                          <div style={{ position: "absolute", width: 40, height: 1, backgroundColor: PALETTE.blue }} />
                          <div style={{ position: "absolute", width: 1, height: 40, backgroundColor: PALETTE.blue }} />
                        </div>
                        <div
                          style={{
                            position: "absolute",
                            top: 140,
                            left: 100,
                            fontFamily: theme.fonts.mono,
                            fontSize: 13,
                            color: PALETTE.mono,
                            lineHeight: 1.5,
                            backgroundColor: "rgba(13, 21, 32, 0.75)",
                            padding: "8px 12px",
                            borderLeft: `2px solid ${PALETTE.blue}`,
                            borderRadius: 4,
                          }}
                        >
                          <div>SYS_LOC: STAGE_01</div>
                          <div>SCAN_RATE: 60Hz</div>
                        </div>
                        <div
                          style={{
                            position: "absolute",
                            bottom: 140,
                            right: 100,
                            fontFamily: theme.fonts.mono,
                            fontSize: 13,
                            color: PALETTE.mono,
                            lineHeight: 1.5,
                            backgroundColor: "rgba(13, 21, 32, 0.75)",
                            padding: "8px 12px",
                            borderRight: `2px solid ${PALETTE.blue}`,
                            textAlign: "right",
                            borderRadius: 4,
                          }}
                        >
                          <div>TARGET: 3D_BLOCK</div>
                          <div>LATENCY: MINIMAL</div>
                        </div>
                      </div>
                    )}

                    {/* [SCENE 2 - Shot 3] Surveillance Viewfinder */}
                    {activeShot && activeShot.chapter_index === 2 && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 60,
                          border: `1px solid rgba(248, 250, 252, 0.2)`,
                          pointerEvents: "none",
                        }}
                      >
                        <div
                          style={{
                            position: "absolute",
                            top: 20,
                            right: 20,
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            fontFamily: theme.fonts.mono,
                            color: PALETTE.primary,
                            fontSize: 14,
                            fontWeight: 700,
                          }}
                        >
                          <div
                            style={{
                              width: 12,
                              height: 12,
                              borderRadius: "50%",
                              backgroundColor: PALETTE.red,
                              opacity: Math.floor(frame / 15) % 2 === 0 ? 1 : 0.2,
                            }}
                          />
                          REC
                        </div>
                        <div style={{ position: "absolute", top: -2, left: -2, width: 24, height: 24, borderTop: `4px solid ${PALETTE.primary}`, borderLeft: `4px solid ${PALETTE.primary}` }} />
                        <div style={{ position: "absolute", top: -2, right: -2, width: 24, height: 24, borderTop: `4px solid ${PALETTE.primary}`, borderRight: `4px solid ${PALETTE.primary}` }} />
                        <div style={{ position: "absolute", bottom: -2, left: -2, width: 24, height: 24, borderBottom: `4px solid ${PALETTE.primary}`, borderLeft: `4px solid ${PALETTE.primary}` }} />
                        <div style={{ position: "absolute", bottom: -2, right: -2, width: 24, height: 24, borderBottom: `4px solid ${PALETTE.primary}`, borderRight: `4px solid ${PALETTE.primary}` }} />

                        <div
                          style={{
                            position: "absolute",
                            bottom: 20,
                            left: 20,
                            fontFamily: theme.fonts.mono,
                            color: PALETTE.mono,
                            fontSize: 13,
                            lineHeight: 1.6,
                          }}
                        >
                          <div>ISO 800</div>
                          <div>1/60s f/2.8</div>
                          <div>CAM_02_MONITOR</div>
                        </div>
                        <div
                          style={{
                            position: "absolute",
                            bottom: 20,
                            right: 20,
                            fontFamily: theme.fonts.mono,
                            color: PALETTE.mono,
                            fontSize: 13,
                            textAlign: "right",
                          }}
                        >
                          <div>TIME: {((frame - activeShot.from) / 30).toFixed(2)}s</div>
                          <div>STATE: ACTIVE_SCAN</div>
                        </div>
                      </div>
                    )}

                    {/* [SCENE 3 - Shot 4] Activity Logs Feed */}
                    {activeShot && activeShot.chapter_index === 3 && (
                      <div
                        style={{
                          position: "absolute",
                          left: "8%",
                          right: "8%",
                          top: "22%",
                          bottom: "35%",
                          display: "flex",
                          flexDirection: "column",
                          gap: 12,
                          pointerEvents: "none",
                        }}
                      >
                        {[
                          { time: "02:04:12", type: "COMMIT", text: "feat: agent-voice-engine", color: PALETTE.green },
                          { time: "02:04:15", type: "NOTION", text: "Sync page 'launch-milestone'", color: PALETTE.purple },
                          { time: "02:04:18", type: "BROWSER", text: "Active tab: elevenlabs.io", color: PALETTE.cyan },
                          { time: "02:04:22", type: "LANGGRAPH", text: "Decide pipeline state: render_required", color: PALETTE.amber }
                        ].map((log, idx) => {
                          const showDelay = idx * 15;
                          const elapsed = frame - activeShot.from - showDelay;
                          if (elapsed < 0) return null;

                          const popProgress = spring({
                            frame: Math.max(0, elapsed),
                            fps,
                            config: { damping: 14, stiffness: 150 },
                          });

                          return (
                            <div
                              key={idx}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 12,
                                backgroundColor: "rgba(13, 21, 32, 0.9)",
                                border: `1px solid ${PALETTE.elevated}`,
                                borderRadius: 8,
                                padding: "12px 18px",
                                fontFamily: theme.fonts.mono,
                                fontSize: 14,
                                transform: `scale(${popProgress}) translateX(${(1 - popProgress) * -20}px)`,
                                opacity: popProgress,
                                backdropFilter: "blur(4px)",
                              }}
                            >
                              <span style={{ color: PALETTE.secondary }}>[{log.time}]</span>
                              <span
                                style={{
                                  color: log.color,
                                  fontWeight: 700,
                                  backgroundColor: `${log.color}22`,
                                  padding: "2px 6px",
                                  borderRadius: 4,
                                  fontSize: 12,
                                }}
                              >
                                {log.type}
                              </span>
                              <span style={{ color: PALETTE.primary }}>{log.text}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* [SCENE 4 - Shot 5] Falling Dull Text Columns */}
                    {activeShot && activeShot.chapter_index === 4 && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          opacity: 0.35,
                          pointerEvents: "none",
                          overflow: "hidden",
                          display: "flex",
                          justifyContent: "space-around",
                          fontFamily: theme.fonts.mono,
                          fontSize: 14,
                          color: PALETTE.secondary,
                        }}
                      >
                        {[0, 1, 2, 3, 4, 5].map((colIdx) => {
                          const yOffset = (((frame - activeShot.from) * (1.8 + colIdx * 0.2)) % 600) - 100;
                          const wordsList = ["text", "draft", "paragraph", "wall of words", "boring", "flat", "forgotten", "ordinary"];
                          const word = wordsList[colIdx % wordsList.length];
                          return (
                            <div
                              key={colIdx}
                              style={{
                                transform: `translateY(${yOffset}px)`,
                                writingMode: "vertical-rl",
                                textOrientation: "upright",
                                opacity: Math.max(0, 1 - (yOffset / 500)),
                                display: "flex",
                                gap: 15,
                              }}
                            >
                              <div>{word.toUpperCase()}</div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* [SCENE 5 - Shot 6] Neon Impact Flash */}
                    {activeShot && activeShot.chapter_index === 5 && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          backgroundColor: PALETTE.green,
                          opacity: Math.max(0, 0.45 - (frame - activeShot.from) / 12),
                          pointerEvents: "none",
                          zIndex: 5,
                        }}
                      />
                    )}

                    {/* [ANIMATION OVERLAY 1] Render sequential stages flow chart if active shot is reveal (Scene 7 - Shot 8) */}
                    {activeShot && activeShot.type === "reveal" && (
                      <div
                        style={{
                          position: "absolute",
                          top: "22%",
                          left: "5%",
                          right: "5%",
                          display: "flex",
                          flexDirection: "column",
                          gap: 20,
                        }}
                      >
                        {/* Connecting Laser Beam Line */}
                        <div
                          style={{
                            position: "absolute",
                            top: 35,
                            left: "5%",
                            right: "5%",
                            height: 2,
                            backgroundColor: "rgba(148, 163, 184, 0.2)",
                            zIndex: 1,
                          }}
                        >
                          <div
                            style={{
                              height: "100%",
                              width: `${Math.min(100, ((frame - activeShot.from) / (activeShot.to - activeShot.from)) * 100)}%`,
                              backgroundColor: PALETTE.green,
                              boxShadow: `0 0 10px ${PALETTE.green}`,
                            }}
                          />
                        </div>

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", position: "relative" }}>
                          {stages.map((stage, sIdx) => {
                            const delay = sIdx * 5;
                            const popProgress = spring({
                              frame: Math.max(0, frame - activeShot.from - delay),
                              fps,
                              config: { damping: 12, stiffness: 180 },
                            });

                            const durationOfShot = activeShot.to - activeShot.from;
                            const timePerStage = durationOfShot / stages.length;
                            const isNodeActive = sIdx === Math.floor((frame - activeShot.from) / timePerStage);
                            const isActive = frame >= activeShot.from + delay;

                            return (
                              <div
                                key={sIdx}
                                style={{
                                  display: "flex",
                                  flexDirection: "column",
                                  alignItems: "center",
                                  transform: `scale(${popProgress * (isNodeActive ? 1.15 : 1.0)})`,
                                  opacity: popProgress,
                                  zIndex: 10,
                                  transition: "transform 0.2s",
                                }}
                              >
                                <div
                                  style={{
                                    width: 70,
                                    height: 70,
                                    borderRadius: "50%",
                                    backgroundColor: isNodeActive ? PALETTE.green : (isActive ? "rgba(16, 185, 129, 0.2)" : "rgba(15, 23, 42, 0.8)"),
                                    border: `2px solid ${isNodeActive ? PALETTE.primary : (isActive ? PALETTE.green : PALETTE.secondary)}`,
                                    display: "flex",
                                    justifyContent: "center",
                                    alignItems: "center",
                                    fontSize: 28,
                                    boxShadow: isNodeActive ? `0 0 30px ${PALETTE.green}` : "none",
                                    transition: "background-color 0.2s, border-color 0.2s, box-shadow 0.2s",
                                    backdropFilter: "blur(6px)",
                                  }}
                                >
                                  {stage.icon || "⚙️"}
                                </div>
                                <div style={{ fontSize: 13, fontWeight: 700, color: isNodeActive ? PALETTE.primary : (isActive ? PALETTE.green : PALETTE.secondary), marginTop: 8 }}>
                                  {stage.label || stage.name}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* [ANIMATION OVERLAY 2] Render metrics overlay if active shot is statistic (Scene 6 - Shot 7 & Scene 10 - Shot 11) */}
                    {activeShot && activeShot.type === "statistic" && activeShot.metrics && (
                      <div
                        style={{
                          position: "absolute",
                          top: "22%",
                          left: "5%",
                          right: "5%",
                          display: "flex",
                          justifyContent: "center",
                          gap: "24px",
                          alignItems: "center",
                          flexWrap: "wrap",
                        }}
                      >
                        {activeShot.metrics.map((metric: any, mIdx: number) => {
                          const delay = mIdx * 6;
                          const progress = spring({
                            frame: Math.max(0, frame - activeShot.from - delay),
                            fps,
                            config: { damping: 12, stiffness: 180 },
                          });

                          // Highlight active card sequentially in Shot 7 ("Poll. Image. Video.")
                          let isCardActive = false;
                          if (activeShot.chapter_index === 6) {
                            const timeInShot = frame - activeShot.from;
                            if (mIdx === 0 && timeInShot >= 0 && timeInShot < 65) isCardActive = true;
                            if (mIdx === 1 && timeInShot >= 65 && timeInShot < 135) isCardActive = true;
                            if (mIdx === 2 && timeInShot >= 135) isCardActive = true;
                          }

                          return (
                            <div
                              key={mIdx}
                              style={{
                                backgroundColor: isCardActive ? "rgba(34, 211, 238, 0.15)" : "rgba(15, 23, 42, 0.85)",
                                border: `2px solid ${isCardActive ? PALETTE.cyan : (activeShot.chapter_index === 6 ? "rgba(148, 163, 184, 0.3)" : PALETTE.cyan)}`,
                                borderRadius: 16,
                                padding: "20px 24px",
                                minWidth: 220,
                                textAlign: "center",
                                transform: `scale(${progress * (isCardActive ? 1.08 : 1.0)}) translateY(${(1 - progress) * 40}px)`,
                                opacity: progress,
                                boxShadow: isCardActive ? `0 12px 35px ${PALETTE.cyan}44` : "0 12px 30px rgba(0,0,0,0.5)",
                                backdropFilter: "blur(8px)",
                                transition: "background-color 0.3s, border-color 0.3s, transform 0.3s, box-shadow 0.3s",
                              }}
                            >
                              <div style={{ fontSize: 44, fontWeight: 800, color: PALETTE.primary }}>
                                {metric.value}
                              </div>
                              <div style={{ fontSize: 15, fontWeight: 700, color: isCardActive ? PALETTE.primary : PALETTE.cyan, marginTop: 4, textTransform: "uppercase" }}>
                                {metric.label}
                              </div>
                              <div style={{ fontSize: 12, color: PALETTE.secondary, marginTop: 4 }}>
                                {metric.unit}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* [SCENE 8 - Shot 9] Architecture Node Connection Map */}
                    {activeShot && activeShot.chapter_index === 8 && (
                      <div
                        style={{
                          position: "absolute",
                          left: "5%",
                          right: "5%",
                          top: "22%",
                          bottom: "35%",
                          backgroundColor: "rgba(13, 21, 32, 0.9)",
                          border: `2px dashed rgba(167, 139, 250, 0.4)`,
                          borderRadius: 16,
                          padding: 24,
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          backdropFilter: "blur(6px)",
                          pointerEvents: "none",
                          boxShadow: "0 15px 35px rgba(0,0,0,0.6)",
                          overflow: "hidden",
                        }}
                      >
                        {/* Connecting line */}
                        <div
                          style={{
                            position: "absolute",
                            left: "10%",
                            right: "10%",
                            top: "42%",
                            height: 4,
                            backgroundColor: "rgba(167, 139, 250, 0.2)",
                            zIndex: 1,
                          }}
                        >
                          {/* Pulsing travel packet */}
                          <div
                            style={{
                              position: "absolute",
                              left: `${((frame - activeShot.from) * 1.5) % 100}%`,
                              width: 16,
                              height: 16,
                              borderRadius: "50%",
                              backgroundColor: PALETTE.purple,
                              top: -6,
                              boxShadow: `0 0 10px ${PALETTE.purple}`,
                            }}
                          />
                        </div>

                        {[
                          { name: "GitHub", color: PALETTE.slate, label: "commits" },
                          { name: "Claude", color: PALETTE.blue, label: "planning" },
                          { name: "LangGraph", color: PALETTE.purple, label: "orchestrator" },
                          { name: "Remotion", color: PALETTE.green, label: "rendering" },
                          { name: "LinkedIn", color: PALETTE.cyan, label: "publishing" },
                        ].map((node, nIdx) => {
                          const delay = nIdx * 8;
                          const progress = spring({
                            frame: Math.max(0, frame - activeShot.from - delay),
                            fps,
                            config: { damping: 12, stiffness: 180 },
                          });

                          return (
                            <div
                              key={nIdx}
                              style={{
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                zIndex: 10,
                                transform: `scale(${progress})`,
                                opacity: progress,
                              }}
                            >
                              <div
                                style={{
                                  width: 80,
                                  height: 80,
                                  borderRadius: "50%",
                                  backgroundColor: PALETTE.depth,
                                  border: `3px solid ${node.color}`,
                                  display: "flex",
                                  justifyContent: "center",
                                  alignItems: "center",
                                  fontWeight: "bold",
                                  fontSize: 12,
                                  color: PALETTE.primary,
                                  boxShadow: `0 0 15px ${node.color}33`,
                                }}
                              >
                                {node.name}
                              </div>
                              <div style={{ fontSize: 10, color: PALETTE.secondary, marginTop: 6, fontFamily: theme.fonts.mono }}>
                                {node.label}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* [ANIMATION OVERLAY 3] Render terminal code block if active shot is code_moment (Scene 9 - Shot 10) */}
                    {activeShot && activeShot.type === "code_moment" && (
                      <div
                        style={{
                          position: "absolute",
                          top: "22%",
                          left: "12%",
                          right: "12%",
                          backgroundColor: "rgba(10, 10, 12, 0.95)",
                          border: `2px solid ${PALETTE.purple}`,
                          borderRadius: 12,
                          padding: 24,
                          boxShadow: "0 20px 50px rgba(0,0,0,0.8)",
                          backdropFilter: "blur(12px)",
                          transform: `scale(${spring({
                            frame: Math.max(0, frame - activeShot.from),
                            fps,
                            config: { damping: 15, stiffness: 150 },
                          })})`,
                        }}
                      >
                        <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
                          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: "#EF4444" }} />
                          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: "#F59E0B" }} />
                          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: "#10B981" }} />
                        </div>
                        <div style={{ fontFamily: theme.fonts.mono, fontSize: 18, color: PALETTE.primary, lineHeight: 1.6, textAlign: "left" }}>
                          {activeShot.content.split("\n").map((line: string, lIdx: number) => {
                            const lineProgress = spring({
                              frame: Math.max(0, frame - activeShot.from - (lIdx * 10)),
                              fps,
                              config: { damping: 15, stiffness: 200 },
                            });
                            return (
                              <div
                                key={lIdx}
                                style={{
                                  opacity: lineProgress,
                                  transform: `translateX(${(1 - lineProgress) * -15}px)`,
                                  paddingLeft: line.startsWith("→") ? 20 : 0,
                                  color: line.includes("published") ? PALETTE.green : (line.includes("publishing") ? PALETTE.amber : PALETTE.primary)
                                }}
                              >
                                {line}
                              </div>
                            );
                          })}
                        </div>
                        {/* Simulated Progress Bar */}
                        <div style={{ marginTop: 24, fontFamily: theme.fonts.mono, fontSize: 13, color: PALETTE.secondary }}>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                            <span>DEPLOYING PIPELINE</span>
                            <span>{Math.min(100, Math.floor(((frame - activeShot.from) / (activeShot.to - activeShot.from)) * 100))}%</span>
                          </div>
                          <div style={{ width: "100%", height: 8, backgroundColor: "rgba(255,255,255,0.05)", borderRadius: 4, overflow: "hidden" }}>
                            <div
                              style={{
                                width: `${Math.min(100, ((frame - activeShot.from) / (activeShot.to - activeShot.from)) * 100)}%`,
                                height: "100%",
                                backgroundColor: PALETTE.purple,
                                boxShadow: `0 0 8px ${PALETTE.purple}`,
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    )}

                    {/* [SCENE 10 - Shot 11] Approve Target Scanner */}
                    {activeShot && activeShot.chapter_index === 10 && (
                      <div
                        style={{
                          position: "absolute",
                          left: "5%",
                          right: "5%",
                          top: "22%",
                          bottom: "35%",
                          display: "flex",
                          justifyContent: "center",
                          alignItems: "center",
                          pointerEvents: "none",
                        }}
                      >
                        <div
                          style={{
                            position: "relative",
                            width: 140,
                            height: 140,
                            borderRadius: "50%",
                            border: `3px solid ${PALETTE.green}`,
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                            backgroundColor: "rgba(16, 185, 129, 0.08)",
                            boxShadow: `0 0 25px rgba(16, 185, 129, 0.2)`,
                            transform: `scale(${spring({
                              frame: Math.max(0, frame - activeShot.from),
                              fps,
                              config: { damping: 10, stiffness: 120 },
                            })})`,
                          }}
                        >
                          {[1, 2].map((rIdx) => {
                            const scale = 1 + (((frame - activeShot.from) * 0.02 + rIdx * 0.5) % 1) * 0.8;
                            const op = 0.6 - (((frame - activeShot.from) * 0.02 + rIdx * 0.5) % 1);
                            return (
                              <div
                                key={rIdx}
                                style={{
                                  position: "absolute",
                                  width: 140,
                                  height: 140,
                                  borderRadius: "50%",
                                  border: `2px solid ${PALETTE.green}`,
                                  transform: `scale(${scale})`,
                                  opacity: Math.max(0, op),
                                }}
                              />
                            );
                          })}
                          <div
                            style={{
                              fontFamily: theme.fonts.heading,
                              fontSize: 16,
                              fontWeight: 800,
                              color: PALETTE.primary,
                              textAlign: "center",
                              lineHeight: 1.2,
                            }}
                          >
                            TAP TO
                            <br />
                            <span style={{ color: PALETTE.green }}>APPROVE</span>
                          </div>
                        </div>
                      </div>
                    )}


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

      <FilmGrain />
      <Letterbox />
    </AbsoluteFill>
  );
};
