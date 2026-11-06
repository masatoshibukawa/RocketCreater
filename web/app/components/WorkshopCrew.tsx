"use client";

import { useEffect, useState } from "react";
import { useWorkshop } from "../lib/WorkshopContext";
import WorkshopScene from "./WorkshopScene";
import { INITIAL_CREW, transitionCrew, type CrewPhase } from "../lib/workshopActivity";

const PHASE_LABEL: Record<CrewPhase, string> = {
  waiting: "待機", inspecting: "点検", tidying: "片付け", attention: "確認待ち",
};

/** A separate presentation stage; its controls never change design or job state. */
export default function WorkshopCrew({ embedded = false, hideScene = false }: { embedded?: boolean; hideScene?: boolean }) {
  const { task, visible, paused, reduced, setVisible, setPaused } = useWorkshop();
  const [crew, setCrew] = useState(INITIAL_CREW);
  useEffect(() => {
    setCrew(previous => transitionCrew(previous, task, Date.now()));
  }, [task]);
  useEffect(() => {
    if (crew.phase !== "tidying") return;
    const timer = window.setTimeout(() => {
      setCrew(previous => transitionCrew(previous, task, Date.now()));
    }, Math.max(0, crew.cleanupUntil - Date.now()));
    return () => window.clearTimeout(timer);
  }, [crew.phase, crew.cleanupUntil, task]);

  return <section className={`crew-panel${embedded ? " crew-embedded" : ""}`} aria-label="整備チーム" data-phase={crew.phase} hidden={embedded && hideScene}>
    {!embedded ? <div className="crew-toolbar">
      <div className="crew-heading"><strong>整備チーム</strong><span className={`crew-phase crew-phase-${crew.phase}`}>{PHASE_LABEL[crew.phase]}</span></div>
      <div className="crew-controls">
        <label><input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/>表示</label>
        <button type="button" className="btn" aria-pressed={paused} onClick={() => setPaused(!paused)} disabled={reduced}>
          {paused ? "動きを再開" : "動きを止める"}
        </button>
      </div>
    </div> : null}
    {visible && !hideScene ? <WorkshopScene scene="crew"/> : null}
    <div className="crew-description">
      <p role="status" aria-live="polite">{crew.label}</p>
      {!embedded ? <small>{reduced ? "端末の設定に合わせて静止表示 · " : paused ? "演出は静止中 · " : ""}工程の案内役です。実機の点検完了を示すものではありません。</small> : null}
    </div>
  </section>;
}
