"use client";

import { TIER_LABEL, type ClassifyResult, type Tier } from "../lib/types";

/** The tier chip (ペットボトル／アマチュア／企業級／重工級), shown over the 3D view. */
export default function TierBadge({ tier }: { tier: Tier | null }) {
  return (
    <span className={`tier-badge ${tier ? `tier-${tier}` : "tier-none"}`}>
      {tier ? TIER_LABEL[tier] : "段階: 未判定"}
      {tier && <small>{tier}</small>}
    </span>
  );
}

/** classify_requirement notes (mismatch with the required tier, fallback, warnings, reasons)
 * for the 詳細 area. Returns null when there is nothing to say. */
export function ClassifyNotes({ tier, classify }: { tier: Tier | null; classify: ClassifyResult | null }) {
  if (!classify) return null;
  const mismatch = classify.required_tier !== null && classify.tier !== classify.required_tier;
  const fallback = classify.fallback;
  if (!mismatch && !fallback && classify.warnings.length === 0 && classify.reasons.length === 0) return null;
  return (
    <div className="classify-notes">
      {mismatch && classify.required_tier && (
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
      {classify.warnings.length > 0 && <div className="warn-box">{classify.warnings.join("\n")}</div>}
      {classify.reasons.length > 0 && (
        <ul className="reasons">
          {classify.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
