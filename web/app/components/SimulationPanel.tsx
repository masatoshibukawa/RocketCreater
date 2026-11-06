"use client";

import { useEffect, useState } from "react";
import { carriesParachute } from "../lib/flightPlayback";
import { loadTrajectory, type Trajectory, type WorkbenchProject } from "../lib/workbench";
import AeroLoopPanel from "./AeroLoopPanel";
import FlightPlayer from "./FlightPlayer";

interface SimulationPanelProps {
  project: WorkbenchProject | null;
  busy: string;
  working: boolean;
  elapsed: number;
  error: string;
  onRunAero: () => void;
}

/** ワークベンチの「シミュレーション」: the current design's flight, then the flow analysis. */
export default function SimulationPanel({ project, busy, working, elapsed, error, onRunAero }: SimulationPanelProps) {
  const [trajectory, setTrajectory] = useState<Trajectory | null>(null);
  const [failure, setFailure] = useState("");
  const projectId = project?.id;
  const steps = project?.history.length ?? 0;

  useEffect(() => {
    setTrajectory(null);
    setFailure("");
    if (!projectId || steps === 0) return;
    const controller = new AbortController();
    void loadTrajectory(projectId, controller.signal).then(setTrajectory).catch((e: unknown) => {
      if (!controller.signal.aborted) setFailure(e instanceof Error ? e.message : String(e));
    });
    return () => controller.abort();
  }, [projectId, steps]);

  const aeroRunning = busy === "aero-loop" || project?.active?.name === "aero_loop";
  return <div className="wb-detail wb-simulation">
    <p className="wb-eyebrow">SIMULATION / FLIGHT & FLOW</p>
    <h2>飛行を再生する</h2>
    {failure ? <p className="wb-error" role="alert">飛行の時系列を取得できません: {failure}</p> : null}
    {steps === 0 ? <p className="wb-note">工程を実行すると、現在の案の飛行を計算して再生できます。</p>
      : trajectory ? <FlightPlayer key={trajectory.source_action} trace={trajectory.trace} metrics={trajectory.metrics} warnings={trajectory.warnings} parachute={carriesParachute(trajectory.design)} emptyMessage="この案は飛び上がらないため、再生できる時系列がありません。"/>
      : !failure ? <p className="wb-note" role="status">飛行を計算中…</p> : null}
    <AeroLoopPanel project={project} running={aeroRunning} working={working} elapsed={elapsed} onRun={onRunAero}/>
    {aeroRunning || !error ? null : <p className="wb-error" role="alert">{error}</p>}
  </div>;
}
