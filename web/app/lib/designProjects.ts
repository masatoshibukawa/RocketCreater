import { apiUrl, type DesignPackageRequest } from "./api";
import type { BottleDesign, TracePoint } from "./types";

export interface ProductionGeometry {
  body_diameter_mm: number; body_height_mm: number; nose_length_mm: number;
  fin_root_mm: number; fin_tip_mm: number; fin_span_mm: number; fin_sweep_mm: number;
  fin_count: number; fin_thickness_mm: number; nose_wall_mm: number;
  fin_tail_inset_mm: number; dimensions_measured: boolean;
  radial_clearance_mm?: number; fin_slot_width_mm?: number;
}
export interface ProjectEquipment {
  printer_profile: "s5-gray-aa04"; printer_label: string; print_core: "AA 0.4"; build_plate: "glass";
  material_lot: string; print_orientation: "host_validated_profile"; operator: string; glove: string;
  hand_width_mm: number | null; glove_allowance_mm: number | null; strap_width_mm: number | null;
  strap_thickness_mm: number | null; tool_radius_mm: number | null; required_force_n: number | null;
  allowable_force_n: number | null; tools: string[]; workbench_clear_width_mm: number | null;
  procurement: { part: string; quantity: number; unit_price_jpy: number | null;
    basis: "unknown" | "estimate" | "quote" | "paid"; source: string; checked_on: string }[];
}
export function defaultEquipment(): ProjectEquipment { return {
  printer_profile:"s5-gray-aa04", printer_label:"実験室1 / UltiMaker-006707", print_core:"AA 0.4", build_plate:"glass",
  material_lot:"", print_orientation:"host_validated_profile", operator:"未指定", glove:"未指定",
  hand_width_mm:null, glove_allowance_mm:null, strap_width_mm:null, strap_thickness_mm:null,
  tool_radius_mm:null, required_force_n:null, allowable_force_n:null, tools:["ノギス","はかり","適合する固定材"],
  workbench_clear_width_mm:null, procurement:[] }; }
export interface ProductionSpec {
  name: string; design: BottleDesign; geometry: ProductionGeometry;
  requirement: Record<string, unknown> | null; env: Record<string, unknown>;
  other_dry_mass_g: number; measured_printed_mass_g: number | null; material: string;
  equipment?: ProjectEquipment;
  altitude_rule?: "band_10pct" | "minimum";
}
export interface ProjectFile { name: string; key: string; kind: string; url: string; version: number; sha256: string }
export function projectFileLabel(name: string): string {
  return ({ "assembly.pdf": "組立手順 PDF", "design-sheet.pdf": "製作・計算確認票 PDF",
    "calculation-report.md": "計算レポート", "bom.csv": "部品表 CSV", "flight.csv": "飛行データ CSV",
    "side-view.svg": "側面図 SVG", "design.json": "設計 JSON", "print-package.zip": "S5印刷データ一式",
    "design-package.zip": "採用版の一括 ZIP", "analysis-envelope-m.stl": "解析用包絡（m単位・印刷用ではありません）",
  } as Record<string, string>)[name] ?? name;
}
export interface DesignProject {
  id: string; name: string; revision: number; version: number; spec: ProductionSpec;
  adopted: boolean; active: { id?:string; name: string; phase?:string; started_at: number;
    progress?:{phase:string;completed:number;total:number|null;reused?:number;eta_s:[number,number]|null;elapsed_s:number} } | null; error: string | null;
  analysis: { design: BottleDesign; result: { success: boolean; metrics: Record<string, number>;
    trace: TracePoint[]; warnings: string[]; failure_reasons: string[] }; printed_mass_used_g: number;
    printed_solid_mass_g: number; mass_basis: string; limitations: string[];
    requirements?: { scope: string; all_requirements_passed: boolean; checks: { id: string; label: string; status: string; reason: string }[] } } | null;
  files: ProjectFile[]; versions: { version: number; adopted: boolean; spec: ProductionSpec }[];
  history: { operation: string; version: number; at: number }[];
  video_plan: { status: string; reason: string } | null;
  photographic_video_plan: { status: string; reason: string } | null;
  observations?: {step:string; status:string; operator:string; observed_on:string; note:string;
    measured_values:Record<string,number>; version:number}[];
  adaptive?: {status:string;remaining_s:number;decisions:{action:string|null;reason:string}[]}|null;
}
export async function projectRequest<T>(path = "", body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(apiUrl(`/design-projects${path}`), {
    ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), signal,
  });
  const data = await response.json();
  if (!response.ok) {
    const labels: Record<string, string> = { body_diameter_mm: "ボトル胴径", body_height_mm: "ボトル高さ", nose_length_mm: "ノーズ長さ", fin_root_mm: "フィン翼根", fin_tip_mm: "フィン翼端", fin_span_mm: "フィン張出し", fin_sweep_mm: "フィン後退", fin_count: "フィン枚数", other_dry_mass_g: "他の部材の質量", geometry: "部品寸法", spec: "入力条件" };
    const issues = Array.isArray(data.detail) ? data.detail.map((item: { loc?: string[]; msg?: string }) => `${labels[item.loc?.at(-1) ?? ""] ?? "入力値"}: ${item.msg ?? "値を確認してください"}`).join(" / ") : null;
    throw new Error(typeof data.detail === "string" ? data.detail : issues ?? "入力内容と設計版を確認してください。");
  }
  return data as T;
}
export function newSpec(source: DesignPackageRequest | null): ProductionSpec {
  const design: BottleDesign = source?.design.tier === "bottle" ? source.design : {
    tier: "bottle", bottle_volume_m3: .002, water_fill_frac: .3, initial_gauge_pressure_pa: 350000,
    nozzle_diameter_m: .009, dry_mass_kg: .1, payload_mass_kg: .06, has_fins: true,
    has_parachute: true, parachute_diameter_m: .7,
  };
  const d = Math.cbrt(4 * design.bottle_volume_m3 / (Math.PI * 3.5)) * 1000;
  return { name: "ペトロケの試作", design, geometry: design.geometry ?? {
    body_diameter_mm: d, body_height_mm: d*3.5, nose_length_mm: d*.8,
    fin_root_mm: d, fin_tip_mm: d*.35, fin_span_mm: d*.8, fin_sweep_mm: d*.35,
    fin_count: 4, fin_thickness_mm: 2.4, nose_wall_mm: 1.6, fin_tail_inset_mm: d*3.5*.25,
    dimensions_measured: false,
  }, requirement: source?.requirement ?? null, env: source?.env ?? {},
  other_dry_mass_g: design.dry_mass_kg*1000, measured_printed_mass_g: null,
  material: "UltiMaker Tough PLA Gray", equipment: defaultEquipment() };
}
