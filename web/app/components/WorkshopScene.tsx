"use client";

import type { CSSProperties } from "react";
import { useWorkshop } from "../lib/WorkshopContext";
import { WORKSHOP_SCENES } from "../lib/workshopLayers";
import type { CrewPhase } from "../lib/workshopActivity";

export type WorkshopSceneName = keyof typeof WORKSHOP_SCENES;

/** The drafted workshop picture with its heads and hands moving. Presentation only: the tempo
 * follows the running job, and nothing here starts a job or says that a check is complete. */
export default function WorkshopScene({ scene, phase }: { scene: WorkshopSceneName; phase?: CrewPhase }) {
  const { task, motionEnabled } = useWorkshop();
  const { base, width, height, parts } = WORKSHOP_SCENES[scene];
  const stopped = task.status === "attention" || task.status === "stopped";
  const tempo = !motionEnabled || stopped ? "still" : task.status === "working" ? "busy" : "calm";
  const currentPhase = phase ?? (stopped ? "attention" : task.status === "working" ? "inspecting" : "waiting");
  return <div className={`workshop-scene workshop-scene-${scene}`} data-tempo={tempo} data-phase={currentPhase}
    style={{ aspectRatio: `${width} / ${height}` }} aria-hidden="true">
    <img src={base} alt=""/>
    {parts.map((part, i) => <img key={part.src} src={part.src} alt="" className={`ws-part ws-${part.move}`} style={{
      left: `${part.left}%`, top: `${part.top}%`, width: `${part.width}%`,
      transformOrigin: `${part.originX}% ${part.originY}%`, animationDelay: `${-0.9 * i}s`,
    } as CSSProperties}/>)}
    {scene === "diorama" ? <><span className="ws-lamp"/><span className="ws-scan"/></> : null}
    {scene === "crew" ? <><span className="ws-tool-tray"/><span className="ws-returned-tool"/></> : null}
  </div>;
}
