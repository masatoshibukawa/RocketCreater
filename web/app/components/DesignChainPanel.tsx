"use client";

import { fmtJpy, stageLabel } from "../lib/format";
import type { ChainAutoStep, ChainCandidate, ChainFunnel, ChainStageStep, ChainStep } from "../lib/types";

interface DesignChainPanelProps {
  chain: ChainStep[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** "24 列挙 → 13 検証 → 1 合格" (numbers straight from the tool result). */
function FunnelText({ funnel }: { funnel: ChainFunnel }) {
  return (
    <span className="chain-funnel" title={rejectedText(funnel)}>
      {funnel.enumerated} 列挙
      {funnel.compatible !== null ? ` → ${funnel.compatible} 適合` : ""} → {funnel.simulated} 検証 →{" "}
      {funnel.passed} 合格
    </span>
  );
}

function rejectedText(funnel: ChainFunnel): string {
  const rows = Object.entries(funnel.rejected);
  if (rows.length === 0) return "";
  return `除外の理由:\n${rows.map(([reason, n]) => `${reason}: ${n}`).join("\n")}`;
}

function PassChip({ passed }: { passed: boolean }) {
  return passed ? <span className="chip chip-ok">合格</span> : <span className="chip chip-bad">不合格</span>;
}

function CandidateLine({ c }: { c: ChainCandidate }) {
  return (
    <li className="chain-candidate">
      <PassChip passed={c.passed} /> <span className="mono">{c.option}</span>
      {c.cost_jpy !== null && <span className="muted"> · {fmtJpy(c.cost_jpy)}</span>}
      <div className="chain-why">{c.why}</div>
    </li>
  );
}

/** auto_design: the baseline through the fixed stage order, one row per stage. */
function AutoStepView({ step, selected, onSelect }: { step: ChainAutoStep; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <li className={`chain-step${selected ? " chain-step-selected" : ""}`}>
      <div className="chain-step-header row-clickable" onClick={() => onSelect(step.source_id)} title="クリックでこの案を表示">
        <span className="chip chip-accent">自動設計（基準案）</span>
        <PassChip passed={step.passed} />
        <span className="muted mono">{step.source_id}</span>
      </div>
      <div className="table-scroll">
        <table className="table chain-table">
          <thead>
            <tr>
              <th>段階</th>
              <th>採用</th>
              <th>候補の絞り込み</th>
              <th>次点（上位 3）</th>
            </tr>
          </thead>
          <tbody>
            {step.trace.map((t) => (
              <tr key={t.stage}>
                <td>
                  {stageLabel(t.stage)}
                  <div className="muted mono">{t.stage}</div>
                </td>
                <td>
                  <span className="mono">{t.label || t.chosen}</span>
                  {t.fixed && <span className="chip chip-muted">指定</span>}
                  <div className="chain-why">{t.why}</div>
                </td>
                <td>
                  <FunnelText funnel={t.funnel} />
                </td>
                <td>
                  {t.alternatives.length === 0 ? (
                    <span className="muted">-</span>
                  ) : (
                    <ul className="chain-alts">
                      {t.alternatives.slice(0, 3).map((a) => (
                        <li key={a.option} title={a.why}>
                          <PassChip passed={a.passed} /> <span className="mono">{a.option}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {step.feasibility !== null && <div className="warn-box">予算内の合格案なし: {step.feasibility}</div>}
      {step.warnings.length > 0 && <div className="warn-box">{step.warnings.join("\n")}</div>}
    </li>
  );
}

/** design_stage: one stage re-ranked for the upstream decisions (exploration, not an attempt). */
function StageStepView({ step }: { step: ChainStageStep }) {
  return (
    <li className="chain-step">
      <div className="chain-step-header">
        <span className="chip chip-muted">段階の候補</span>
        <strong>{stageLabel(step.stage)}</strong>
        <span className="muted mono">{step.stage}</span>
        <FunnelText funnel={step.funnel} />
      </div>
      {step.chosen.length > 0 && (
        <div className="muted chain-upstream">
          上流で確定: <span className="mono">{step.chosen.join(", ")}</span>
        </div>
      )}
      {step.candidates.length === 0 ? (
        <div className="empty">候補なし</div>
      ) : (
        <ul className="chain-candidates">
          {step.candidates.map((c) => (
            <CandidateLine key={c.option} c={c} />
          ))}
        </ul>
      )}
      {step.invalidated.length > 0 && (
        <div className="muted chain-upstream">
          下流をやり直し: <span className="mono">{step.invalidated.join(", ")}</span>
        </div>
      )}
    </li>
  );
}

/**
 * 設計の決定順: the staged design chain in time order. The auto_design baseline (stage → chosen
 * part → why → funnel counts → top-3 alternatives) and every design_stage result (the stage,
 * its candidates with pass chips and the code's `why`, the downstream stages it invalidated).
 * Every number is the tool's; nothing is computed here.
 */
export default function DesignChainPanel({ chain, selectedId, onSelect }: DesignChainPanelProps) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">設計の決定順</h2>
        <span className="muted">{chain.length} 件</span>
      </div>
      {chain.length === 0 ? (
        <div className="empty">自動設計（auto_design）と段階の候補（design_stage）の結果が、決めた順に並びます</div>
      ) : (
        <ol className="chain-list">
          {chain.map((step) =>
            step.kind === "auto" ? (
              <AutoStepView
                key={step.source_id}
                step={step}
                selected={step.source_id === selectedId}
                onSelect={onSelect}
              />
            ) : (
              <StageStepView key={step.source_id} step={step} />
            ),
          )}
        </ol>
      )}
    </div>
  );
}
