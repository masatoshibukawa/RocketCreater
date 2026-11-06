/** Display-unit conversion and Japanese labels. Backend values are SI (unit-suffixed keys). */

import { isOrbital, type Tier } from "./types";

export function fmt(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return "-";
  return value.toLocaleString("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtJpy(value: number): string {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1e8) return `${fmt(value / 1e8, 2)} 億円`;
  if (Math.abs(value) >= 1e4) return `${fmt(value / 1e4, 1)} 万円`;
  return `${fmt(value, 0)} 円`;
}

export function fmtPercent(fraction: number): string {
  return `${fmt(fraction * 100, 1)} %`;
}

export interface MetricSpec {
  key: string;
  label: string;
  format: (value: number) => string;
}

const km = (v: number): string => `${fmt(v / 1000, 1)} km`;
const metres = (v: number): string => `${fmt(v, 0)} m`;
const mps = (v: number): string => `${fmt(v, 1)} m/s`;
const kg = (v: number): string => `${fmt(v, 1)} kg`;
const kpa = (v: number): string => `${fmt(v / 1000, 1)} kPa`;
const cal = (v: number): string => `${fmt(v, 2)} cal`;

/** The handful of metrics shown in the attempt log and on candidate cards, per tier family. */
export function keyMetrics(tier: Tier | null): MetricSpec[] {
  if (isOrbital(tier)) {
    return [
      { key: "perigee_m", label: "近地点", format: km },
      { key: "apogee_m", label: "遠地点", format: km },
      { key: "payload_margin_kg", label: "積載余裕", format: kg },
      { key: "max_q_pa", label: "最大動圧", format: kpa },
    ];
  }
  if (tier === "bottle") {
    // physics/water.py has no stability margin: a parts build adds BOTTLE_MARGINS beside these
    return [
      { key: "apogee_m", label: "到達高度", format: metres },
      { key: "descent_speed_mps", label: "降下速度", format: mps },
      { key: "max_speed_mps", label: "最大速度", format: mps },
      { key: "landing_distance_m", label: "着地距離", format: metres },
    ];
  }
  return [
    { key: "apogee_m", label: "到達高度", format: metres },
    { key: "descent_speed_mps", label: "降下速度", format: mps },
    { key: "stability_margin_cal", label: "安定余裕", format: cal },
    { key: "max_speed_mps", label: "最大速度", format: mps },
  ];
}

/** Bottle static margins: metrics only when a parts build gives the real fins (agent/tools.py). */
export const BOTTLE_MARGINS: readonly MetricSpec[] = [
  { key: "stability_margin_cal", label: "静安定余裕（注水時）", format: cal },
  { key: "dry_stability_margin_cal", label: "静安定余裕（空のとき）", format: cal },
];

const METRIC_LABELS: Record<string, string> = {
  perigee_m: "近地点",
  apogee_m: "到達高度 / 遠地点",
  max_q_pa: "最大動圧",
  payload_margin_kg: "積載余裕",
  dv_ideal_mps: "理想増速量",
  dv_gravity_loss_mps: "重力損失",
  dv_drag_loss_mps: "抵抗損失",
  dv_pressure_loss_mps: "圧力損失",
  burnout_speed_mps: "燃焼終了速度",
  liftoff_mass_kg: "離床質量",
  total_liftoff_mass_kg: "離床質量",
  liftoff_twr_ratio: "離床推力重量比",
  landing_distance_m: "着地距離",
  rail_exit_speed_mps: "ランチャー離脱速度",
  stability_margin_cal: "静安定余裕",
  dry_stability_margin_cal: "空のときの静安定余裕",
  max_speed_mps: "最大速度",
  descent_speed_mps: "降下速度",
  flight_time_s: "飛行時間",
  landing_east_m: "着地点 (東)",
  landing_north_m: "着地点 (北)",
};

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key;
}

/** Japanese labels of the agent tools (rocketwright/agent/tools.py), shown next to the id. */
const TOOL_LABELS: Record<string, string> = {
  classify_requirement: "規模の判定",
  derive_requirements: "定量要求の算出",
  find_reference_designs: "実機データの検索",
  search_catalog: "カタログ検索",
  simulate_design: "シミュレーション",
  list_parts: "部品カタログ",
  design_from_parts: "部品から設計",
  auto_design: "自動設計",
  design_stage: "段階の候補",
  run_dispersion: "多数回試行",
  estimate_cost: "費用見積",
  render_drawing: "図面の描画",
  export_report: "レポート出力",
};

export function toolLabel(name: string): string {
  const label = TOOL_LABELS[name];
  return label === undefined ? name : `${label} (${name})`;
}

/** Japanese names of the design-chain stages (rocketwright/design_chain.py STAGES). */
const STAGE_LABELS: Record<string, string> = {
  motor: "モーター",
  mount: "モーターマウント",
  body_tube: "胴体チューブ",
  nose_cone: "ノーズコーン",
  body_length: "胴体の長さ",
  fins: "フィン",
  parachute: "パラシュート",
  deploy_delay: "開傘の遅延",
  bottle: "ボトル",
  nozzle: "ノズル",
  water_fill: "水の量",
  pressure: "空気圧",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

/** Generic formatter driven by the unit suffix of the metric key. */
export function formatMetric(key: string, value: number): string {
  if (!Number.isFinite(value)) return "-";
  if (key.endsWith("_mps2")) return `${fmt(value, 1)} m/s²`;
  if (key.endsWith("_mps")) return mps(value);
  if (key.endsWith("_m3")) return `${fmt(value * 1000, 2)} L`;
  if (key.endsWith("_m2")) return `${fmt(value, 3)} m²`;
  if (key.endsWith("_m")) return Math.abs(value) >= 10000 ? km(value) : metres(value);
  if (key.endsWith("_kg")) return kg(value);
  if (key.endsWith("_pa")) return kpa(value);
  if (key.endsWith("_s")) return `${fmt(value, 1)} s`;
  if (key.endsWith("_jpy")) return fmtJpy(value);
  if (key.endsWith("_cal")) return cal(value);
  if (key.endsWith("_count")) return fmt(value, 0);
  if (key.endsWith("_deg")) return `${fmt(value, 1)}°`;
  if (key.endsWith("_frac") || key.endsWith("_ratio")) return fmtPercent(value);
  if (key.endsWith("_n")) return `${fmt(value, 0)} N`;
  if (key.endsWith("_g")) return `${fmt(value, 2)} g`;
  return fmt(value, 2);
}
