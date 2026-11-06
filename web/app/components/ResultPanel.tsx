"use client";

import { BOTTLE_MARGINS, keyMetrics } from "../lib/format";
import type { Tier } from "../lib/types";

interface ResultPanelProps {
  tier: Tier | null;
  /** Tool-result metrics of the displayed design. */
  metrics: Record<string, number>;
}

/** 飛行の結果: the displayed design's key metrics; on a bottle also its static margins. */
export default function ResultPanel({ tier, metrics }: ResultPanelProps) {
  const specs = tier === "bottle" ? [...keyMetrics(tier), ...BOTTLE_MARGINS] : keyMetrics(tier);
  const rows = specs.filter((spec) => typeof metrics[spec.key] === "number");
  const noMargins = tier === "bottle" && rows.length > 0 && !BOTTLE_MARGINS.some((spec) => spec.key in metrics);
  return (
    <div className="panel result-panel">
      <h2 className="panel-title">飛行の結果</h2>
      {rows.length === 0 ? (
        <div className="empty">設計案が届くと結果を表示します</div>
      ) : (
        <dl className="flight-summary">
          {rows.map((spec) => (
            <div key={spec.key}>
              <dt>{spec.label}</dt>
              <dd>{spec.format(metrics[spec.key])}</dd>
            </div>
          ))}
        </dl>
      )}
      {noMargins ? <p className="muted result-note">静安定余裕は、部品のフィンを選んだ案で算出します。</p> : null}
    </div>
  );
}
