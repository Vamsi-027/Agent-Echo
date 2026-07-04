import React from "react";
import { Composition, getInputProps } from "remotion";
import { StateMachineAnimation } from "./compositions/StateMachineAnimation";
import { PipelineFlowAnimation } from "./compositions/PipelineFlowAnimation";
import { ArchitectureRevealAnimation } from "./compositions/ArchitectureRevealAnimation";
import { MetricsSummaryAnimation } from "./compositions/MetricsSummaryAnimation";
import { BeatData, EditorialStructure } from "./editorial";
import { Shot } from "./shot_list";
import { CaptionWord } from "./components/CaptionsOverlay";

export const Root: React.FC = () => {
  const inputProps = getInputProps() as any;
  const duration = inputProps.durationInFrames || 180;
  const audioFile = inputProps.audioFile || undefined;
  const startOffset = typeof inputProps.startOffset === "number" ? inputProps.startOffset : 8;

  // Set default fallback values for development & local studio preview
  const defaultBeatData: BeatData = inputProps.beatData || {
    tempo: 120,
    beat_frames: Array.from({ length: 60 }, (_, i) => (i + 1) * 15),
    downbeat_frames: Array.from({ length: 16 }, (_, i) => (i + 1) * 60),
    energy_peaks: [30, 75, 120],
    beat_interval: 15,
  };

  const defaultEditorial: EditorialStructure = inputProps.editorialStructure || {
    hook: "Engineering video narration hook",
    revelation_order: ["Step One", "Step Two", "Step Three"],
    takeaway: "Always build reliable technical abstractions.",
    visual_metaphor: "",
    cut_type: "hard_cut",
    act1_end: 45,
    act2_end: 135,
  };

  const defaultShots: Shot[] = inputProps.shots || [
    { type: "hook_word", content: "Optimize", entrance: "slam", duration_beats: 4 },
    { type: "context_3d", content: "Latency Spike", entrance: "zoom_punch", duration_beats: 4 },
    { type: "tension", content: "High Connections", entrance: "slide_left", duration_beats: 4 },
    { type: "reveal", content: "Connection Pool", entrance: "rise", duration_beats: 4 },
    { type: "takeaway_word", content: "Success", entrance: "scale_in", duration_beats: 4 },
  ];

  const defaultCaptions: CaptionWord[] = inputProps.captions || [];

  return (
    <>
      <Composition
        id="StateMachineAnimation"
        component={StateMachineAnimation}
        durationInFrames={duration}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          title: "State Machine",
          audioFile,
          durationInFrames: duration,
          beatData: defaultBeatData,
          editorialStructure: defaultEditorial,
          shots: defaultShots,
          captions: defaultCaptions,
          startOffset,
          states: [
            { name: "idle", label: "Idle" },
            { name: "loading", label: "Loading" },
            { name: "ready", label: "Ready" },
          ],
          transitions: [
            { from: "idle", to: "loading", label: "start" },
            { from: "loading", to: "ready", label: "done" },
          ],
        }}
      />
      <Composition
        id="PipelineFlowAnimation"
        component={PipelineFlowAnimation}
        durationInFrames={duration}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          title: "Pipeline Flow",
          audioFile,
          durationInFrames: duration,
          beatData: defaultBeatData,
          editorialStructure: defaultEditorial,
          shots: defaultShots,
          captions: defaultCaptions,
          startOffset,
          stages: [
            { name: "Ingest", description: "Collect data from sources" },
            { name: "Process", description: "Transform and validate" },
            { name: "Publish", description: "Distribute to channels" },
          ],
        }}
      />
      <Composition
        id="ArchitectureRevealAnimation"
        component={ArchitectureRevealAnimation}
        durationInFrames={duration}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          title: "System Architecture",
          audioFile,
          durationInFrames: duration,
          beatData: defaultBeatData,
          editorialStructure: defaultEditorial,
          shots: defaultShots,
          captions: defaultCaptions,
          startOffset,
          components: [
            { name: "API Gateway", x: 0.5, y: 0.2 },
            { name: "Auth Service", x: 0.25, y: 0.5 },
            { name: "Core Engine", x: 0.75, y: 0.5 },
            { name: "Database", x: 0.5, y: 0.8 },
          ],
          connections: [
            { from: 0, to: 1 },
            { from: 0, to: 2 },
            { from: 1, to: 3 },
            { from: 2, to: 3 },
          ],
        }}
      />
      <Composition
        id="MetricsSummaryAnimation"
        component={MetricsSummaryAnimation}
        durationInFrames={duration}
        fps={30}
        width={1080}
        height={1080}
        defaultProps={{
          title: "Performance Metrics",
          audioFile,
          durationInFrames: duration,
          beatData: defaultBeatData,
          editorialStructure: defaultEditorial,
          shots: defaultShots,
          captions: defaultCaptions,
          startOffset,
          metrics: [
            { label: "Latency", before: 450, after: 120, unit: "ms" },
            { label: "Throughput", before: 100, after: 850, unit: "req/s" },
            { label: "Error Rate", before: 4.2, after: 0.3, unit: "%" },
          ],
        }}
      />
    </>
  );
};
