"use client";

import { fmtJpy, keyMetrics } from "../lib/format";
import type { AttemptRow, Tier } from "../lib/types";

interface AttemptLogProps {
  attempts: AttemptRow[];
  tier: Tier | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** One row per simulate_design tool_result (plus the free attempt-0 row of a reference seed,
 * flagged 実機ベース): pass/fail chip, key metrics, failure reasons. */
export default function AttemptLog({ attempts, tier, selectedId, onSelect }: AttemptLogProps) {
  const specs = keyMetrics(tier);
  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">試行ログ</h2>
        <span className="muted">{attempts.length} 件</span>
      </div>
      {attempts.length === 0 ? (
        <div className="empty">simulate_design の結果がここに並びます</div>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>合否</th>
                {specs.map((s) => (
                  <th key={s.key} className="num">
                    {s.label}
                  </th>
                ))}
                <th className="num">費用</th>
                <th>失敗理由 / 警告</th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((row) => {
                const sim = row.result;
                const selected = row.id === selectedId;
                return (
                  <tr
                    key={row.id || `attempt-${row.attempt}`}
                    className={`row-clickable${selected ? " row-selected" : ""}`}
                    onClick={() => onSelect(row.id)}
                    title={row.id}
                  >
                    <td className="num">{row.attempt}</td>
                    <td>
                      {sim === null ? (
                        <span className="chip chip-bad">エラー</span>
                      ) : sim.success ? (
                        <span className="chip chip-ok">合格</span>
                      ) : (
                        <span className="chip chip-bad">不合格</span>
                      )}
                      {row.seededFrom !== null && (
                        <span className="chip chip-muted" title={`実機 ${row.seededFrom} から縮尺`}>
                          実機ベース
                        </span>
                      )}
                    </td>
                    {specs.map((s) => {
                      const v = sim?.metrics[s.key];
                      return (
                        <td key={s.key} className="num">
                          {v === undefined ? "-" : s.format(v)}
                        </td>
                      );
                    })}
                    <td className="num">{sim ? fmtJpy(sim.cost_jpy) : "-"}</td>
                    <td>
                      {row.error !== null && <span className="fail-reasons">{row.error}</span>}
                      {sim && sim.failure_reasons.length > 0 && (
                        <span className="fail-reasons">{sim.failure_reasons.join(" / ")}</span>
                      )}
                      {sim && sim.failure_reasons.length === 0 && sim.warnings.length > 0 && (
                        <span className="muted">{sim.warnings.join(" / ")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
