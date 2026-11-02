"use client";

import { fmt, fmtJpy, fmtPercent } from "../lib/format";
import type { CostBreakdownItem, DesignSummary, MassSummary } from "../lib/types";

interface CostPanelProps {
  summary: DesignSummary | null;
  /** cost_jpy of the displayed attempt's SimResult: shown while the summary is loading. */
  fallbackCostJpy: number | null;
  loading: boolean;
  error: string | null;
}

/** Six segment colours for the stacked bar (globals.css --seg-1..6 keep them in one place). */
const SEGMENT_CLASSES = ["seg-1", "seg-2", "seg-3", "seg-4", "seg-5", "seg-6"];

function MassLine({ mass }: { mass: MassSummary }) {
  const parts: string[] = [];
  if (mass.liftoff_mass_kg !== null) parts.push(`離床 ${fmtKg(mass.liftoff_mass_kg)}`);
  if (mass.propellant_mass_kg !== null) parts.push(`推進剤 ${fmtKg(mass.propellant_mass_kg)}`);
  if (mass.dry_mass_kg !== null) parts.push(`乾燥 ${fmtKg(mass.dry_mass_kg)}`);
  if (mass.payload_mass_kg !== null) parts.push(`積載 ${fmtKg(mass.payload_mass_kg)}`);
  if (parts.length === 0) return null;
  return <div className="cost-mass muted">質量: {parts.join(" / ")}</div>;
}

function fmtKg(kg: number): string {
  if (kg >= 1000) return `${fmt(kg / 1000, 1)} t`;
  if (kg >= 10) return `${fmt(kg, 0)} kg`;
  if (kg >= 1) return `${fmt(kg, 2)} kg`;
  return `${fmt(kg * 1000, 0)} g`;
}

/** Big total, a stacked horizontal bar of the breakdown, and the itemised list with notes. */
export default function CostPanel({ summary, fallbackCostJpy, loading, error }: CostPanelProps) {
  const total =
    summary !== null && Number.isFinite(summary.cost_jpy)
      ? summary.cost_jpy
      : fallbackCostJpy !== null && Number.isFinite(fallbackCostJpy)
        ? fallbackCostJpy
        : null;
  const items: CostBreakdownItem[] = summary?.cost_breakdown ?? [];
  const sum = items.reduce((acc, it) => acc + Math.max(0, it.jpy), 0);
  const provisionalCount = items.filter((it) => it.provisional).length;

  return (
    <div className="panel cost-panel">
      <div className="panel-header">
        <h2 className="panel-title">費用</h2>
        <span className="muted">
          {loading ? "計算中…" : summary !== null ? "内訳は費用モデル（cost.py）の値" : ""}
        </span>
      </div>
      {total === null ? (
        <div className="empty">設計案が届くと概算費用を表示します</div>
      ) : (
        <>
          <div className="cost-total-row">
            <span className="cost-total">{fmtJpy(total)}</span>
            <span className="muted cost-total-sub">
              概算合計
              {provisionalCount > 0 && (
                <>
                  {" "}
                  <span className="chip chip-provisional" title="出典未確認の単価を含みます">
                    仮置き {provisionalCount} 件
                  </span>
                </>
              )}
            </span>
          </div>
          {items.length > 0 && sum > 0 && (
            <div className="cost-bar" role="img" aria-label="費用の内訳">
              {items.map((it, i) => {
                const frac = Math.max(0, it.jpy) / sum;
                if (frac <= 0) return null;
                return (
                  <div
                    key={`${it.label}-${i}`}
                    className={`cost-seg ${SEGMENT_CLASSES[i % SEGMENT_CLASSES.length]}`}
                    style={{ width: `${(frac * 100).toFixed(2)}%` }}
                    title={`${it.label}: ${fmtJpy(it.jpy)} (${fmtPercent(frac)})${it.note ? `\n${it.note}` : ""}`}
                  />
                );
              })}
            </div>
          )}
          {items.length > 0 ? (
            <ul className="cost-list">
              {items.map((it, i) => {
                const frac = sum > 0 ? Math.max(0, it.jpy) / sum : 0;
                return (
                  <li key={`${it.label}-${i}`} className="cost-item" title={it.note || undefined}>
                    <span className={`cost-swatch ${SEGMENT_CLASSES[i % SEGMENT_CLASSES.length]}`} />
                    <span className="cost-label">
                      {it.label}
                      {it.provisional && <span className="chip chip-provisional">仮置き</span>}
                    </span>
                    <span className="cost-value">{fmtJpy(it.jpy)}</span>
                    <span className="cost-frac muted">{fmtPercent(frac)}</span>
                    {it.note && <span className="cost-note muted">{it.note}</span>}
                  </li>
                );
              })}
            </ul>
          ) : (
            summary === null && !loading && (
              <div className="muted cost-fallback">
                シミュレーション結果の費用。内訳は /artifacts/summary の応答後に表示します。
              </div>
            )
          )}
          {summary?.mass && <MassLine mass={summary.mass} />}
        </>
      )}
      {error !== null && <div className="error-box">費用の内訳を取得できませんでした: {error}</div>}
    </div>
  );
}
