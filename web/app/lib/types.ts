/**
 * TypeScript mirrors of the backend models (rocketwright/schema.py, rocketwright/agent/events.py).
 * All quantities are SI with unit suffixes; display conversion happens in format.ts.
 */

export type Tier = "bottle" | "amateur" | "commercial" | "heavy";

export const TIERS: readonly Tier[] = ["bottle", "amateur", "commercial", "heavy"];

export const TIER_LABEL: Record<Tier, string> = {
  bottle: "ペットボトル",
  amateur: "アマチュア",
  commercial: "企業級",
  heavy: "重工級",
};

export function isTier(value: unknown): value is Tier {
  return typeof value === "string" && (TIERS as readonly string[]).includes(value);
}

/** commercial / heavy show the ascent profile; bottle / amateur show the landing scatter. */
export function isOrbital(tier: Tier | null): boolean {
  return tier === "commercial" || tier === "heavy";
}

export type EventType =
  | "thinking"
  | "text"
  | "tool_call"
  | "tool_result"
  | "candidate"
  | "review"
  | "warning"
  | "final"
  | "error"
  | "question";

export const EVENT_TYPES: readonly EventType[] = [
  "thinking",
  "text",
  "tool_call",
  "tool_result",
  "candidate",
  "review",
  "warning",
  "final",
  "error",
  "question",
];

export function isEventType(value: unknown): value is EventType {
  return typeof value === "string" && (EVENT_TYPES as readonly string[]).includes(value);
}

/** One SSE message from POST /design (AgentEvent.model_dump_json()). */
export interface AgentEvent {
  type: EventType;
  attempt: number;
  payload: Record<string, unknown>;
  t_s: number;
}

// --------------------------------------------------------------------------- designs

export interface Stage {
  propellant_mass_kg: number;
  structural_fraction: number;
  engine_id: string;
  engine_count: number;
}

export interface Booster {
  booster_id: string;
  count: number;
}

export interface MultistageDesign {
  tier: "commercial" | "heavy";
  stages: Stage[];
  boosters: Booster[];
  fairing_mass_kg: number;
  payload_mass_kg: number;
  pitch_start_s: number;
  initial_pitch_deg: number;
}

export interface FinSet {
  count: number;
  root_chord_m: number;
  tip_chord_m: number;
  span_m: number;
  sweep_m: number;
  thickness_m: number;
}

export interface AmateurDesign {
  tier: "amateur";
  body_diameter_m: number;
  body_length_m: number;
  nose_shape: string;
  nose_length_m: number;
  fins: FinSet;
  motor_id: string;
  dry_mass_kg: number;
  payload_mass_kg: number;
  parachute_diameter_m: number;
  deploy_delay_s: number;
}

export interface BottleDesign {
  tier: "bottle";
  bottle_volume_m3: number;
  water_fill_frac: number;
  initial_gauge_pressure_pa: number;
  nozzle_diameter_m: number;
  dry_mass_kg: number;
  payload_mass_kg: number;
  has_fins: boolean;
  has_parachute: boolean;
  parachute_diameter_m: number | null;
}

export type Design = BottleDesign | AmateurDesign | MultistageDesign;

// --------------------------------------------------------------------------- results

export interface TracePoint {
  t_s: number;
  altitude_m: number;
  downrange_m: number;
  east_m: number;
  north_m: number;
  speed_mps: number;
  mass_kg: number | null;
}

export interface SimResult {
  tier: Tier | null;
  success: boolean;
  failure_reasons: string[];
  metrics: Record<string, number>;
  cost_jpy: number;
  trace: TracePoint[];
  warnings: string[];
  source_id: string;
}

export interface ClassifyResult {
  tier: Tier | null;
  required_tier: Tier | null;
  fallback: Record<string, unknown> | null;
  warnings: string[];
  reasons: string[];
}

export interface LandingPoint {
  east_m: number;
  north_m: number;
}

export interface Quantiles {
  p05: number;
  p50: number;
  p95: number;
}

/** 95 % containment ellipse of the landing scatter (schema.Ellipse95). */
export interface Ellipse95 {
  center_east_m: number;
  center_north_m: number;
  semi_major_m: number;
  semi_minor_m: number;
  /** Major axis from east, counter-clockwise. */
  angle_deg: number;
}

export interface LandingScatter {
  points: LandingPoint[];
  ellipse_95: Ellipse95;
}

export interface OrbitSample {
  perigee_m: number;
  apogee_m: number;
  payload_margin_kg: number;
}

export interface OrbitInsertionStats {
  perigee_error_m: Quantiles;
  apogee_error_m: Quantiles;
  payload_margin_kg: Quantiles;
  samples: OrbitSample[];
}

/** A run_dispersion tool result (schema.DispersionResult plus the tool's `nominal` echo and the
 * design it was run on, taken from the matching tool_call input). */
export interface DispersionResult {
  source_id: string;
  tier: Tier | null;
  n: number;
  seed: number | null;
  success_rate: number;
  quantiles: Record<string, Quantiles>;
  failure_counts: Record<string, number>;
  landing: LandingScatter | null;
  orbit_insertion: OrbitInsertionStats | null;
  warnings: string[];
  nominal_metrics: Record<string, number>;
  design: Design | null;
  /** source_id of the candidate / attempt whose design equals `design`, if any. */
  candidate_id: string | null;
  /** Orbit target from the tool_call's requirement (perigee = target_altitude_m), if any. */
  target_perigee_m: number | null;
  target_apogee_m: number | null;
}

/** One row of the attempt log: a simulate_design tool_result (or its error). */
export interface AttemptRow {
  id: string;
  attempt: number;
  t_s: number;
  result: SimResult | null;
  error: string | null;
  /** The simulated design (tool_call input, or the tuned design the result reports). */
  design: Design | null;
  /** Reference id when this row is the seed of a find_reference_designs result (attempt 0,
   * free: not a simulate_design call), else null. */
  seededFrom: string | null;
}

/** The reference vehicle a find_reference_designs result seeded the design from. */
export interface ReferenceInfo {
  id: string;
  name: string;
  /** The tool's notes: one line per scaling step. */
  notes: string[];
  /** The seed design scaled from the reference (shown in 3D until the first attempt exists). */
  design: Design | null;
}

/** A design candidate, merged from `candidate` events and `final.result.designs`. */
export interface Candidate {
  source_id: string;
  design: Design;
  metrics: Record<string, number>;
  cost_jpy: number;
  passed: boolean;
  success_rate: number | null;
  explanation: string;
  failure_reasons: string[];
  inFinal: boolean;
  /** Reference id for the free seed candidate (candidate event `seeded_from`), else null. */
  seededFrom: string | null;
}

export interface FinalDesign {
  design: Design;
  metrics: Record<string, number>;
  passed: boolean;
  cost_jpy: number;
  success_rate: number | null;
  sources: Record<string, string>;
  explanation: string;
}

export interface FinalResult {
  designs: FinalDesign[];
  summary: string;
  open_questions: string[];
  /** Id of the reference vehicle the design was seeded from (catalog/references), or null. */
  reference_id: string | null;
  /** source_id of the derive_requirements call the targets came from, or null. */
  derived_targets: string | null;
}

export interface FinalPayload {
  result: FinalResult | null;
  provenance_violations: string[];
  attempts: number | null;
  stop_reason: string;
  raw_text: string;
  parse_error: string;
}

/**
 * Download paths produced by the `export_report` / `render_drawing` tools (or a final design
 * that carries a `download` map). Keys: "svg" | "report" | "bom" | "json"; values are
 * backend-relative paths such as "/artifacts/rep_1.md" (join with api.ts `apiUrl`).
 */
export interface ExportInfo {
  id: string;
  source_id: string;
  design: Design | null;
  download: Record<string, string>;
}

export type ChatRole = "user" | "agent" | "thinking" | "question" | "error" | "system";

export interface ChatMessage {
  key: string;
  role: ChatRole;
  text: string;
}

// --------------------------------------------------------------------------- derived requirements

/** One quantity of a derive_requirements tool_result (`quantities[]`). */
export interface DerivedQuantity {
  key: string;
  value: number;
  /** Human-readable formula with the numbers substituted, e.g. "v_circ = sqrt(mu / (R + h)) = ...". */
  formula: string;
  inputs: Record<string, number>;
  assumptions: string[];
  provisional: boolean;
  annotation: string;
}

/** The derive_requirements tool_result (rocketwright/agent/tools.py). */
export interface DerivedRequirements {
  source_id: string;
  tier: Tier | null;
  goal_kind: string;
  quantities: DerivedQuantity[];
  summary: string;
  warnings: string[];
  notes: string[];
}

// --------------------------------------------------------------------------- design summary (POST /artifacts/summary)

export interface CostBreakdownItem {
  label: string;
  jpy: number;
  note: string;
  provisional: boolean;
}

export interface BomItem {
  item_id: string;
  name: string;
  qty: number;
  mass_kg: number | null;
  price_jpy: number | null;
  /** Source URL, or the word "provisional" (or a text starting with it) when unsourced. */
  source_or_provisional: string;
}

export interface MassSummary {
  liftoff_mass_kg: number | null;
  dry_mass_kg: number | null;
  payload_mass_kg: number | null;
  propellant_mass_kg: number | null;
}

export interface DimensionSummary {
  length_m: number | null;
  diameter_m: number | null;
}

/**
 * Response of `POST /artifacts/summary {design, requirement|null, width_px|null}`:
 * cost, cost breakdown, BOM, side-view drawing path, masses and overall dimensions for one
 * design. Every number comes from the backend (cost.py / drawing.py); the UI only formats.
 */
export interface DesignSummary {
  tier: Tier | null;
  cost_jpy: number;
  cost_breakdown: CostBreakdownItem[];
  bom: BomItem[];
  drawing: { id: string; url: string } | null;
  mass: MassSummary | null;
  dimensions: DimensionSummary | null;
}

/** Which design the centre / right panels show and where it came from. */
export type DisplayOrigin = "candidate" | "attempt" | "seed";

export interface DisplayedDesign {
  design: Design;
  /** source_id of the candidate / attempt (tool_use id), used to look up trace and dispersion. */
  sourceId: string;
  origin: DisplayOrigin;
}
