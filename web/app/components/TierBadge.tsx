"use client";

import type { Status } from "../lib/designState";
import { TIERS, TIER_LABEL, type ClassifyResult, type ReferenceInfo, type Tier } from "../lib/types";

interface TierBadgeProps {
  tier: Tier | null;
  classify: ClassifyResult | null;
  /** The reference vehicle the design was seeded from (find_reference_designs), if any. */
  reference: ReferenceInfo | null;
  attemptCount: number;
  maxAttempts: number;
  status: Status;
  /** Manual override of the right-panel view (null = follow the classified tier). */
  viewTier: Tier | null;
  onViewTierChange: (tier: Tier | null) => void;
}

export default function TierBadge({
  tier,
  classify,
  reference,
  attemptCount,
  maxAttempts,
  status,
  viewTier,
  onViewTierChange,
}: TierBadgeProps) {
  const mismatch =
    classify !== null && classify.required_tier !== null && classify.tier !== classify.required_tier;
  const fallback = classify?.fallback ?? null;

  return (
    <div className="panel">
      <div className="tier-row">
        <span className={`tier-badge ${tier ? `tier-${tier}` : "tier-none"}`}>
          {tier ? TIER_LABEL[tier] : "段階: 未判定"}
          {tier && <small>{tier}</small>}
        </span>
        <span className="attempt-counter">
          試行 {attemptCount}
          <span className="muted"> / {maxAttempts}</span>
        </span>
        {status === "streaming" && <span className="chip chip-muted">シミュレーション中</span>}
        {reference !== null && (
          <span className="chip chip-muted" title={reference.notes.join("\n")}>
            ベース実機: {reference.name}
          </span>
        )}
        <span className="spacer" style={{ flex: 1 }} />
        <span className="tier-select">
          表示
          <select
            value={viewTier ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              onViewTierChange(v === "" ? null : (v as Tier));
            }}
          >
            <option value="">判定に従う</option>
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {TIER_LABEL[t]}
              </option>
            ))}
          </select>
        </span>
      </div>
      {mismatch && classify && classify.required_tier && (
        <div className="warn-box">
          要求を満たすには {TIER_LABEL[classify.required_tier]} ({classify.required_tier})
          が必要ですが、予算などの制約で {tier ? TIER_LABEL[tier] : "-"} として扱います。
        </div>
      )}
      {fallback && (
        <div className="warn-box">
          代替要求 (fallback): <span className="mono">{JSON.stringify(fallback)}</span>
        </div>
      )}
      {classify && classify.warnings.length > 0 && (
        <div className="warn-box">{classify.warnings.join("\n")}</div>
      )}
      {classify && classify.reasons.length > 0 && (
        <ul className="reasons">
          {classify.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
