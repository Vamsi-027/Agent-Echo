import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
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

interface StateNode {
  name: string;
  label: string;
}

interface Transition {
  from: string;
  to: string;
  label: string;
}

interface Props {
  title: string;
  states: StateNode[];
  transitions: Transition[];
  audioFile?: string;
  beatData: BeatData;
  editorialStructure: EditorialStructure;
  shots: Shot[];
  captions: CaptionWord[];
  startOffset?: number;
}

const StateCard: React.FC<{
  position: [number, number, number];
  color: string;
  revealFrame: number;
  frame: number;
}> = ({ position, color, revealFrame, frame }) => {
  const opacity = Math.min(1, Math.max(0, (frame - revealFrame) / 15));
  const yOffset = (1 - opacity) * -1.5;

  return (
    <group position={[position[0], position[1] + yOffset, position[2]]}>
      {/* 3D Card back mesh */}
      <mesh>
        <boxGeometry args={[2.0, 0.7, 0.05]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity * 0.25}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
      {/* 3D Border mesh wireframe */}
      <mesh>
        <boxGeometry args={[2.04, 0.74, 0.06]} />
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

const ConnectionTube: React.FC<{
  fromPos: [number, number, number];
  toPos: [number, number, number];
  color: string;
  revealFrame: number;
  frame: number;
}> = ({ fromPos, toPos, color, revealFrame, frame }) => {
  const opacity = Math.min(1, Math.max(0, (frame - revealFrame) / 15));
  if (opacity <= 0) return null;

  const p1 = new THREE.Vector3(...fromPos);
  const p2 = new THREE.Vector3(...toPos);
  const distance = p1.distanceTo(p2);
  const position = p1.clone().add(p2).multiplyScalar(0.5);

  const direction = new THREE.Vector3().subVectors(p2, p1).normalize();
  const up = new THREE.Vector3(0, 1, 0);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(up, direction);

  return (
    <mesh
      position={[position.x, position.y, position.z]}
      quaternion={[quaternion.x, quaternion.y, quaternion.z, quaternion.w]}
    >
      <cylinderGeometry args={[0.025, 0.025, distance - 0.4, 8]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={opacity * 0.7}
        roughness={0.1}
        metalness={0.9}
        emissive={color}
        emissiveIntensity={0.6}
      />
    </mesh>
  );
};

// Orbiting Camera Rig matching speed ramped frame
const CameraRig: React.FC<{
  frame: number;
  totalFrames: number;
  fps: number;
  beatData: BeatData;
}> = ({ frame, totalFrames, fps, beatData }) => {
  const radius = 5.5;
  const progress = frame / totalFrames;
  
  // Slow orbit angle
  const angle = progress * Math.PI * 0.5 - Math.PI * 0.25;
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

export const StateMachineAnimation: React.FC<Props> = ({
  title,
  states,
  transitions,
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

  // Check if speed is high to trigger motion blur (cheaper than SVG/canvas filters)
  const isSpeedHigh = ramps.some(r => frame >= r.frame && frame < r.frame + 4 && r.speed > 1.5);
  const blurAmount = isSpeedHigh ? 6 : 0;

  // RGB Split triggers
  const rgbSplitTriggers = resolvedShots.filter(s => s.rgb_split).map(s => s.from);

  // Zoom punch triggers
  const zoomPunchShot = resolvedShots.find(s => s.entrance === "zoom_punch" && frame >= s.from && frame < s.to);
  const zoomPunchFrame = zoomPunchShot ? zoomPunchShot.from : -999;

  // X Spacing algorithm
  const spacingX = 2.4;
  const nodePositions = states.map((_, i) => {
    const x = (i - (states.length - 1) / 2) * spacingX;
    return [x, 0, 0] as [number, number, number];
  });

  // Map 3D mesh reveals to the start frame of 3D shots
  const threeShots = resolvedShots.filter(s => s.type !== "hook_word" && s.type !== "takeaway_word");
  const revealFrames = states.map((_, i) => {
    return threeShots[i]?.from ?? (durationInFrames / 2);
  });

  const transitionRevealFrames = transitions.map((t, i) => {
    const fromIdx = states.findIndex((s) => s.name === t.from);
    const toIdx = states.findIndex((s) => s.name === t.to);
    const maxIdx = Math.max(fromIdx, toIdx, 0);
    return (revealFrames[maxIdx] ?? (durationInFrames / 2)) + 8;
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
                    <pointLight position={[5, 5, 5]} intensity={1.5} color={pillarAccent} />
                    <pointLight position={[-5, -3, -5]} intensity={0.6} color={PALETTE.purple} />

                    <CameraRig frame={effectiveFrame} totalFrames={durationInFrames} fps={fps} beatData={beatData} />

                    {/* Render 3D Cards */}
                    {states.map((state, i) => (
                      <StateCard
                        key={state.name}
                        position={nodePositions[i]}
                        color={i === (Math.floor(effectiveFrame / 30)) % states.length ? PALETTE.green : pillarAccent}
                        revealFrame={revealFrames[i]}
                        frame={effectiveFrame}
                      />
                    ))}

                    {/* Render 3D Connections */}
                    {transitions.map((t, i) => {
                      const fromIdx = states.findIndex((s) => s.name === t.from);
                      const toIdx = states.findIndex((s) => s.name === t.to);
                      if (fromIdx === -1 || toIdx === -1) return null;
                      return (
                        <ConnectionTube
                          key={`${t.from}-${t.to}`}
                          fromPos={nodePositions[fromIdx]}
                          toPos={nodePositions[toIdx]}
                          color={PALETTE.cyan}
                          revealFrame={transitionRevealFrames[i]}
                          frame={effectiveFrame}
                        />
                      );
                    })}

                    <EffectComposer>
                      <Bloom intensity={1.2} luminanceThreshold={0.5} luminanceSmoothing={0.2} radius={0.8} />
                    </EffectComposer>
                  </ThreeCanvas>

                  {/* 2D Overlay */}
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

                    {/* 2D Text Node Labels */}
                    {states.map((state, i) => {
                      const revealFrame = revealFrames[i];
                      if (effectiveFrame < revealFrame) return null;
                      const leftPercent = 50 + (nodePositions[i][0] / 8) * 100;
                      return (
                        <div
                          key={`label-${state.name}`}
                          style={{
                            position: "absolute",
                            left: `${leftPercent}%`,
                            top: "54%",
                            transform: "translate(-50%, -50%)",
                            ...TYPE.label,
                            color: PALETTE.primary,
                            fontSize: 16,
                            fontWeight: 600,
                          }}
                        >
                          {state.label}
                        </div>
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
