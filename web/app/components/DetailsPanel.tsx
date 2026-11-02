"use client";

import { formatMetric, metricLabel } from "../lib/format";
import type {
  AgentEvent,
  AttemptRow,
  Candidate,
  ClassifyResult,
  DerivedRequirements,
  DispersionResult,
  ExportInfo,
  LandingPoint,
  Tier,
} from "../lib/types";
import AttemptLog from "./AttemptLog";
import CandidateCards from "./CandidateCards";
import DispersionPanel from "./DispersionPanel";
import ReviewPanel from "./ReviewPanel";
import { ClassifyNotes } from "./TierBadge";

interface DetailsPanelProps {
  tier: Tier | null;
  classify: ClassifyResult | null;
  derived: DerivedRequirements | null;
  attempts: AttemptRow[];
  candidates: Candidate[];
  events: AgentEvent[];
  dispersion: DispersionResult | null;
  landing: LandingPoint | null;
  exports: ExportInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** derive_requirements: each target quantity with the formula string the tool reported. */
function DerivedList({ derived }: { derived: DerivedRequirements | null }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">定量要求の算出（公式）</h2>
        {derived && <span className="muted mono">{derived.source_id}</span>}
      </div>
      {!derived || derived.quantities.length === 0 ? (
        <div className="empty">derive_requirements の結果（各量の公式）がここに並びます</div>
      ) : (
        <>
          {derived.summary && <p className="derived-summary">{derived.summary}</p>}
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>量</th>
                  <th className="num">値</th>
                  <th>公式</th>
                </tr>
              </thead>
              <tbody>
                {derived.quantities.map((q) => (
                  <tr key={q.key} title={q.assumptions.join("\n") || undefined}>
                    <td>
                      {metricLabel(q.key)}
                      <div className="muted mono">{q.key}</div>
                      {q.provisional && <span className="chip chip-provisional">仮置き</span>}
                    </td>
                    <td className="num">{formatMetric(q.key, q.value)}</td>
                    <td className="mono formula">
                      {q.formula}
                      {q.annotation && <div className="muted">{q.annotation}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {derived.notes.length > 0 && <div className="muted derived-notes">{derived.notes.join(" / ")}</div>}
          {derived.warnings.length > 0 && <div className="warn-box">{derived.warnings.join("\n")}</div>}
        </>
      )}
    </div>
  );
}

/**
 * 詳細（エンジニア向け）: collapsed by default. Attempt log, candidate cards, reviewer verdicts,
 * the Monte-Carlo dispersion (success rate, landing scatter / insertion errors) and the
 * derived-requirement formulas. Nothing here navigates away from the page.
 */
export default function DetailsPanel({
  tier,
  classify,
  derived,
  attempts,
  candidates,
  events,
  dispersion,
  landing,
  exports,
  selectedId,
  onSelect,
}: DetailsPanelProps) {
  return (
    <details className="details-panel">
      <summary className="details-summary">
        詳細（エンジニア向け）
        <span className="muted details-hint">
          試行ログ {attempts.length} 件 · 設計案 {candidates.length} 件 · 多数回試行
          {dispersion ? ` n=${dispersion.n}` : " -"}
        </span>
      </summary>
      <div className="details-body">
        <ClassifyNotes tier={tier} classify={classify} />
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">仮想打ち上げ（多数回試行）</h2>
          </div>
          <DispersionPanel tier={tier} dispersion={dispersion} landing={landing} selectedId={selectedId} />
        </div>
        <AttemptLog attempts={attempts} tier={tier} selectedId={selectedId} onSelect={onSelect} />
        <CandidateCards candidates={candidates} tier={tier} selectedId={selectedId} onSelect={onSelect} exports={exports} />
        <ReviewPanel events={events} selectedId={selectedId} onSelect={onSelect} />
        <DerivedList derived={derived} />
      </div>
    </details>
  );
}
