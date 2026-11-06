/** The tabs of the centre column, per tier. */

import { isOrbital, type Tier } from "./types";

export type CenterView = "model" | "simulation" | "aero" | "production" | "library";

export const CENTER_TABS: readonly { id: CenterView; label: string }[] = [
  { id: "model", label: "3D モデル" },
  { id: "simulation", label: "シミュレーション" },
  { id: "aero", label: "流体解析" },
  { id: "production", label: "製作データ" },
  { id: "library", label: "設計例と資料" },
];

/** Multistage designs stay at concept level (CLAUDE.md section 4): no flow, no production data. */
const CONCEPT_LEVEL_VIEWS: readonly CenterView[] = ["model", "simulation", "library"];

export function centerTabs(tier: Tier | null): readonly { id: CenterView; label: string }[] {
  return isOrbital(tier) ? CENTER_TABS.filter((t) => CONCEPT_LEVEL_VIEWS.includes(t.id)) : CENTER_TABS;
}
