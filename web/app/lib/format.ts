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
  return [
    { key: "apogee_m", label: "到達高度", format: metres },
    { key: "descent_speed_mps", label: "降下速度", format: mps },
    { key: "stability_margin_cal", label: "安定余裕", format: cal },
    { key: "max_speed_mps", label: "最大速度", format: mps },
  ];
}

const METRIC_LABELS: Record<string, string> = {
  perigee_m: "近地点",
  apogee_m: "到達高度 / 遠地点",
  max_q_pa: "最大動圧",
  payload_margin_kg: "積載余裕",
  delta_v_ideal_mps: "理想増速量",
  gravity_loss_mps: "重力損失",
  drag_loss_mps: "抵抗損失",
  burnout_speed_mps: "燃焼終了速度",
  liftoff_mass_kg: "離床質量",
  stage_count_count: "段数",
  rail_exit_speed_mps: "ランチャー離脱速度",
  stability_margin_cal: "静安定余裕",
  max_speed_mps: "最大速度",
  descent_speed_mps: "降下速度",
  flight_time_s: "飛行時間",
  landing_east_m: "着地点 (東)",
  landing_north_m: "着地点 (北)",
};

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key;
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
