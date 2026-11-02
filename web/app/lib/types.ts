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
  | "final"
  | "error"
  | "question";

export const EVENT_TYPES: readonly EventType[] = [
  "thinking",
  "text",
  "tool_call",
  "tool_result",
  "candidate",
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

export interface DispersionSummary {
  source_id: string;
  tier: Tier | null;
  n: number;
  success_rate: number;
  landing_points: LandingPoint[];
  failure_counts: Record<string, number>;
}

/** One row of the attempt log: a simulate_design tool_result (or its error). */
export interface AttemptRow {
  id: string;
  attempt: number;
  t_s: number;
  result: SimResult | null;
  error: string | null;
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
}

export interface FinalPayload {
  result: FinalResult | null;
  provenance_violations: string[];
  attempts: number | null;
  stop_reason: string;
  raw_text: string;
  parse_error: string;
}

export type ChatRole = "user" | "agent" | "thinking" | "question" | "error" | "system";

export interface ChatMessage {
  key: string;
  role: ChatRole;
  text: string;
}
