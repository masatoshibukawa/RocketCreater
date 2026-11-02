/**
 * Pure state machine for the design stream. `reduce` is free of React so it can be unit tested
 * by replaying recorded events (scripts/run_scenario.py output) without a browser.
 *
 * Event -> state mapping:
 *   thinking      -> chat message (role "thinking")
 *   text          -> chat message (role "agent"); a JSON blob (the model's final answer) is
 *                    collapsed to a system line because `final` carries the parsed version
 *   question      -> chat message (role "question") and `pendingQuestion` (the reply box)
 *   tool_call     -> chat system line; the input is kept by id so a result can be tied back
 *                    to the design it was run on
 *   tool_result   -> classify_requirement: tier badge; derive_requirements: the formula list
 *                    shown under 詳細; simulate_design: attempt log row;
 *                    find_reference_designs: the reference vehicle (TierBadge) and, when it
 *                    carries a seed with a sim, an attempt-0 row flagged `seededFrom`;
 *                    run_dispersion: stored per candidate (matched by design equality via
 *                    `findAttemptByDesign`) with success rate / scatter / orbit errors;
 *                    errors: chat error line
 *   candidate     -> candidate card (passed/failure_reasons looked up from the attempt log;
 *                    the loop emits one for a passing reference seed too, `seeded_from`)
 *   final         -> final summary, candidate cards merged with designs[], provenance warnings
 *   error         -> chat error line, status "error"
 */

import {
  isTier,
  TIER_LABEL,
  type AgentEvent,
  type AttemptRow,
  type Candidate,
  type ChatMessage,
  type ChatRole,
  type ClassifyResult,
  type DerivedQuantity,
  type DerivedRequirements,
  type Design,
  type DisplayedDesign,
  type DispersionResult,
  type Ellipse95,
  type FinalDesign,
  type FinalPayload,
  type FinalResult,
  type LandingPoint,
  type LandingScatter,
  type OrbitInsertionStats,
  type OrbitSample,
  type Quantiles,
  type ReferenceInfo,
  type SimResult,
  type Tier,
  type TracePoint,
} from "./types";
import { toolLabel } from "./format";

export type Status = "idle" | "streaming" | "done" | "error";

export interface DesignState {
  status: Status;
  request: string;
  events: AgentEvent[];
  messages: ChatMessage[];
  tier: Tier | null;
  classify: ClassifyResult | null;
  /** The reference vehicle the design was seeded from (find_reference_designs), if any. */
  reference: ReferenceInfo | null;
  /** The normalised Requirement from the classify_requirement tool_call input (sent along to
   * POST /artifacts/summary so the cost model knows the budget / goal). */
  requirement: Record<string, unknown> | null;
  /** derive_requirements tool_result: each target quantity with its formula string. */
  derived: DerivedRequirements | null;
  /** A clarifying `question` event waiting for the user's answer (null once answered / reset). */
  pendingQuestion: string | null;
  attempts: AttemptRow[];
  attemptCount: number;
  candidates: Candidate[];
  /** The most recent run_dispersion result (fallback when the selection has none). */
  dispersion: DispersionResult | null;
  /** run_dispersion results keyed by the matched candidate / attempt source_id (or by the
   * dispersion's own source_id when no attempt has the same design). */
  dispersions: Record<string, DispersionResult>;
  /** tool_call inputs by tool_use id (simulate_design / run_dispersion carry the design). */
  toolInputs: Record<string, Record<string, unknown>>;
  final: FinalPayload | null;
  errors: string[];
  seq: number;
}

export const initialState: DesignState = {
  status: "idle",
  request: "",
  events: [],
  messages: [],
  tier: null,
  classify: null,
  reference: null,
  requirement: null,
  derived: null,
  pendingQuestion: null,
  attempts: [],
  attemptCount: 0,
  candidates: [],
  dispersion: null,
  dispersions: {},
  toolInputs: {},
  final: null,
  errors: [],
  seq: 0,
};

export type Action =
  | { type: "start"; text: string }
  | { type: "event"; event: AgentEvent }
  | { type: "stream_end" }
  | { type: "fail"; message: string }
  | { type: "reset" };

export function reduce(state: DesignState, action: Action): DesignState {
  switch (action.type) {
    case "reset":
      return initialState;
    case "start":
      return push({ ...initialState, status: "streaming", request: action.text }, "user", action.text);
    case "fail":
      return push(
        { ...state, status: "error", errors: [...state.errors, action.message] },
        "error",
        action.message,
      );
    case "stream_end":
      return { ...state, status: state.status === "error" ? "error" : "done" };
    case "event":
      return applyEvent(state, action.event);
    default:
      return state;
  }
}

// --------------------------------------------------------------------------- helpers

function push(state: DesignState, role: ChatRole, text: string): DesignState {
  if (text === "") return state;
  const key = `m${state.seq}`;
  return { ...state, seq: state.seq + 1, messages: [...state.messages, { key, role, text }] };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function asNumber(value: unknown, fallback = Number.NaN): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asNumberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(asString).filter((s) => s !== "") : [];
}

function asNumberMap(value: unknown): Record<string, number> {
  const rec = asRecord(value);
  const out: Record<string, number> = {};
  if (!rec) return out;
  for (const [k, v] of Object.entries(rec)) {
    if (typeof v === "number" && Number.isFinite(v)) out[k] = v;
  }
  return out;
}

function asStringMap(value: unknown): Record<string, string> {
  const rec = asRecord(value);
  const out: Record<string, string> = {};
  if (!rec) return out;
  for (const [k, v] of Object.entries(rec)) {
    if (typeof v === "string") out[k] = v;
  }
  return out;
}

function toTrace(value: unknown): TracePoint[] {
  if (!Array.isArray(value)) return [];
  const out: TracePoint[] = [];
  for (const item of value) {
    const rec = asRecord(item);
    if (!rec) continue;
    out.push({
      t_s: asNumber(rec.t_s, 0),
      altitude_m: asNumber(rec.altitude_m, 0),
      downrange_m: asNumber(rec.downrange_m, 0),
      east_m: asNumber(rec.east_m, 0),
      north_m: asNumber(rec.north_m, 0),
      speed_mps: asNumber(rec.speed_mps, 0),
      mass_kg: asNumberOrNull(rec.mass_kg),
    });
  }
  return out;
}

function toDesign(value: unknown): Design | null {
  const rec = asRecord(value);
  if (!rec || !isTier(rec.tier)) return null;
  // The backend validates designs with pydantic; the cast trusts that contract.
  return rec as unknown as Design;
}

function toSimResult(rec: Record<string, unknown>): SimResult {
  return {
    tier: isTier(rec.tier) ? rec.tier : null,
    success: rec.success === true,
    failure_reasons: asStringArray(rec.failure_reasons),
    metrics: asNumberMap(rec.metrics),
    cost_jpy: asNumber(rec.cost_jpy),
    trace: toTrace(rec.trace),
    warnings: asStringArray(rec.warnings),
    source_id: asString(rec.source_id),
  };
}

function toClassify(rec: Record<string, unknown>): ClassifyResult {
  return {
    tier: isTier(rec.tier) ? rec.tier : null,
    required_tier: isTier(rec.required_tier) ? rec.required_tier : null,
    fallback: asRecord(rec.fallback),
    warnings: asStringArray(rec.warnings),
    reasons: asStringArray(rec.reasons),
  };
}

function toQuantiles(value: unknown): Quantiles | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const p05 = asNumber(rec.p05);
  const p50 = asNumber(rec.p50);
  const p95 = asNumber(rec.p95);
  if (!Number.isFinite(p05) || !Number.isFinite(p50) || !Number.isFinite(p95)) return null;
  return { p05, p50, p95 };
}

function toLandingScatter(value: unknown): LandingScatter | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const points: LandingPoint[] = [];
  if (Array.isArray(rec.points)) {
    for (const item of rec.points) {
      const p = asRecord(item);
      if (p) points.push({ east_m: asNumber(p.east_m, 0), north_m: asNumber(p.north_m, 0) });
    }
  }
  const e = asRecord(rec.ellipse_95);
  const ellipse: Ellipse95 = {
    center_east_m: asNumber(e?.center_east_m, 0),
    center_north_m: asNumber(e?.center_north_m, 0),
    semi_major_m: asNumber(e?.semi_major_m, 0),
    semi_minor_m: asNumber(e?.semi_minor_m, 0),
    angle_deg: asNumber(e?.angle_deg, 0),
  };
  return { points, ellipse_95: ellipse };
}

function toOrbitStats(value: unknown): OrbitInsertionStats | null {
  const rec = asRecord(value);
  if (!rec) return null;
  const zero: Quantiles = { p05: 0, p50: 0, p95: 0 };
  const samples: OrbitSample[] = [];
  if (Array.isArray(rec.samples)) {
    for (const item of rec.samples) {
      const p = asRecord(item);
      if (!p) continue;
      const perigee = asNumber(p.perigee_m);
      const apogee = asNumber(p.apogee_m);
      if (!Number.isFinite(perigee) || !Number.isFinite(apogee)) continue;
      samples.push({ perigee_m: perigee, apogee_m: apogee, payload_margin_kg: asNumber(p.payload_margin_kg, 0) });
    }
  }
  return {
    perigee_error_m: toQuantiles(rec.perigee_error_m) ?? zero,
    apogee_error_m: toQuantiles(rec.apogee_error_m) ?? zero,
    payload_margin_kg: toQuantiles(rec.payload_margin_kg) ?? zero,
    samples,
  };
}

function toDispersion(rec: Record<string, unknown>, design: Design | null): DispersionResult {
  const counts: Record<string, number> = {};
  const rawCounts = asRecord(rec.failure_counts);
  if (rawCounts) {
    for (const [k, v] of Object.entries(rawCounts)) counts[k] = asNumber(v, 0);
  }
  const quantiles: Record<string, Quantiles> = {};
  const rawQ = asRecord(rec.quantiles);
  if (rawQ) {
    for (const [k, v] of Object.entries(rawQ)) {
      const q = toQuantiles(v);
      if (q) quantiles[k] = q;
    }
  }
  const nominal = asRecord(rec.nominal);
  return {
    source_id: asString(rec.source_id),
    tier: isTier(rec.tier) ? rec.tier : null,
    n: asNumber(rec.n, 0),
    seed: asNumberOrNull(rec.seed),
    success_rate: asNumber(rec.success_rate, Number.NaN),
    quantiles,
    failure_counts: counts,
    landing: toLandingScatter(rec.landing),
    orbit_insertion: toOrbitStats(rec.orbit_insertion),
    warnings: asStringArray(rec.warnings),
    nominal_metrics: asNumberMap(nominal?.metrics),
    design,
    candidate_id: null,
    target_perigee_m: null,
    target_apogee_m: null,
  };
}

/** (target_perigee_m, target_apogee_m) of an orbit requirement in a tool_call input. */
function orbitTargets(input: Record<string, unknown> | undefined): [number | null, number | null] {
  const req = asRecord(input?.requirement);
  if (!req || req.goal_kind !== "orbit") return [null, null];
  return [asNumberOrNull(req.target_altitude_m), asNumberOrNull(req.target_apogee_m)];
}

/** JSON with keys sorted recursively, so two designs compare equal regardless of key order
 * (150 and 150.0 both serialise to "150" once parsed from JSON). */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const rec = asRecord(value);
  if (rec) {
    const keys = Object.keys(rec).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(rec[k])}`).join(",")}}`;
  }
  const text = JSON.stringify(value) as string | undefined;
  return text === undefined ? "null" : text;
}

/** source_id of the candidate (preferred) or attempt whose design equals `design`, else null.
 * Used to attach a run_dispersion result to the design card it was run on. */
export function findAttemptByDesign(
  state: Pick<DesignState, "candidates" | "attempts">,
  design: Design | null,
): string | null {
  if (!design) return null;
  const key = canonicalJson(design);
  const candidate = state.candidates.find((c) => canonicalJson(c.design) === key);
  if (candidate) return candidate.source_id;
  const attempt = state.attempts.find((a) => a.design !== null && canonicalJson(a.design) === key);
  return attempt ? attempt.id : null;
}

function toDerived(rec: Record<string, unknown>, id: string): DerivedRequirements {
  const quantities: DerivedQuantity[] = [];
  if (Array.isArray(rec.quantities)) {
    for (const item of rec.quantities) {
      const q = asRecord(item);
      if (!q) continue;
      const key = asString(q.key);
      if (key === "") continue;
      quantities.push({
        key,
        value: asNumber(q.value),
        formula: asString(q.formula),
        inputs: asNumberMap(q.inputs),
        assumptions: asStringArray(q.assumptions),
        provisional: q.provisional === true,
        annotation: asString(q.annotation),
      });
    }
  }
  return {
    source_id: asString(rec.source_id) || id,
    tier: isTier(rec.tier) ? rec.tier : null,
    goal_kind: asString(rec.goal_kind),
    quantities,
    summary: asString(rec.summary),
    warnings: asStringArray(rec.warnings),
    notes: asStringArray(rec.notes),
  };
}

/**
 * The design the centre / right panels show: the latest passing candidate, else the latest
 * attempt that carries a design, else the reference seed. Pure, so the rule is testable.
 */
export function selectDisplayedDesign(
  state: Pick<DesignState, "candidates" | "attempts" | "reference">,
): DisplayedDesign | null {
  for (let i = state.candidates.length - 1; i >= 0; i -= 1) {
    const c = state.candidates[i];
    if (c.passed) return { design: c.design, sourceId: c.source_id, origin: "candidate" };
  }
  for (let i = state.attempts.length - 1; i >= 0; i -= 1) {
    const a = state.attempts[i];
    if (a.design !== null) {
      return { design: a.design, sourceId: a.id, origin: a.seededFrom !== null ? "seed" : "attempt" };
    }
  }
  if (state.reference !== null && state.reference.design !== null) {
    return { design: state.reference.design, sourceId: "", origin: "seed" };
  }
  return null;
}

function toFinalDesign(rec: Record<string, unknown>): FinalDesign | null {
  const design = toDesign(rec.design);
  if (!design) return null;
  return {
    design,
    metrics: asNumberMap(rec.metrics),
    passed: rec.passed === true,
    cost_jpy: asNumber(rec.cost_jpy),
    success_rate: asNumberOrNull(rec.success_rate),
    sources: asStringMap(rec.sources),
    explanation: asString(rec.explanation),
  };
}

function toFinalResult(rec: Record<string, unknown>): FinalResult {
  const designs: FinalDesign[] = [];
  if (Array.isArray(rec.designs)) {
    for (const item of rec.designs) {
      const d = asRecord(item);
      const fd = d ? toFinalDesign(d) : null;
      if (fd) designs.push(fd);
    }
  }
  return {
    designs,
    summary: asString(rec.summary),
    open_questions: asStringArray(rec.open_questions),
    reference_id: asString(rec.reference_id) || null,
    derived_targets: asString(rec.derived_targets) || null,
  };
}

function upsertCandidate(list: Candidate[], candidate: Candidate): Candidate[] {
  const index = list.findIndex((c) => c.source_id === candidate.source_id);
  if (index === -1) return [...list, candidate];
  const copy = list.slice();
  copy[index] = { ...copy[index], ...candidate };
  return copy;
}

function looksLikeJson(text: string): boolean {
  const t = text.trim();
  return t.startsWith("{") && t.endsWith("}");
}

// --------------------------------------------------------------------------- event handlers

function applyEvent(state: DesignState, ev: AgentEvent): DesignState {
  const p = ev.payload;
  const next: DesignState = {
    ...state,
    events: [...state.events, ev],
    attemptCount: Math.max(state.attemptCount, ev.attempt),
  };
  switch (ev.type) {
    case "thinking":
      return push(next, "thinking", asString(p.summary));
    case "text": {
      const text = asString(p.text);
      if (looksLikeJson(text)) return push(next, "system", "最終回答 (JSON) を受信しました");
      return push(next, "agent", text);
    }
    case "question": {
      const text = asString(p.text);
      return push({ ...next, pendingQuestion: text || null }, "question", text);
    }
    case "tool_call": {
      const callId = asString(p.id);
      const input = asRecord(p.input);
      let withInput: DesignState =
        callId && input ? { ...next, toolInputs: { ...next.toolInputs, [callId]: input } } : next;
      if (asString(p.name) === "classify_requirement" && input) {
        const requirement = asRecord(input.requirement);
        if (requirement) withInput = { ...withInput, requirement };
      }
      return push(withInput, "system", `ツール呼び出し: ${toolLabel(asString(p.name))}`);
    }
    case "tool_result":
      return applyToolResult(next, ev);
    case "candidate":
      return applyCandidate(next, ev);
    case "final":
      return applyFinal(next, ev);
    case "error":
      return applyError(next, ev);
    default:
      return next;
  }
}

function applyToolResult(state: DesignState, ev: AgentEvent): DesignState {
  const p = ev.payload;
  const name = asString(p.name);
  const id = asString(p.id);
  const result = asRecord(p.result);
  // tools.py never raises: a failed tool returns {"error": ...} and the loop sets is_error.
  let errorText: string | null = null;
  if (result && typeof result.error === "string") errorText = result.error;
  else if (p.is_error === true) errorText = asString(p.result) || "unknown tool error";

  if (errorText !== null) {
    let next = state;
    if (name === "simulate_design") {
      next = {
        ...next,
        attempts: [
          ...next.attempts,
          {
            id,
            attempt: ev.attempt,
            t_s: ev.t_s,
            result: null,
            error: errorText,
            design: null,
            seededFrom: null,
          },
        ],
      };
    }
    return push(next, "error", `ツール ${toolLabel(name)} がエラーを返しました: ${errorText}`);
  }
  if (!result) return state;

  switch (name) {
    case "classify_requirement": {
      const classify = toClassify(result);
      const tier = classify.tier ?? state.tier;
      let next: DesignState = { ...state, classify, tier };
      if (classify.tier) next = push(next, "system", `段階を判定: ${TIER_LABEL[classify.tier]} (${classify.tier})`);
      for (const w of classify.warnings) next = push(next, "error", `分類の警告: ${w}`);
      return next;
    }
    case "derive_requirements":
      return { ...state, derived: toDerived(result, id) };
    case "simulate_design": {
      const sim = toSimResult(result);
      // with tune_pitch the simulated design is the tuned one the result reports
      const design = toDesign(result.tuned_design) ?? toDesign(state.toolInputs[id]?.design);
      const row: AttemptRow = {
        id,
        attempt: ev.attempt,
        t_s: ev.t_s,
        result: sim,
        error: null,
        design,
        seededFrom: null,
      };
      let next: DesignState = { ...state, attempts: [...state.attempts, row] };
      if (!state.tier && sim.tier) next = { ...next, tier: sim.tier };
      return next;
    }
    case "find_reference_designs": {
      const seed = asRecord(result.seed);
      const referenceId = asString(seed?.reference_id);
      if (!seed || referenceId === "") {
        const note = asString(result.note);
        return note ? push(state, "system", `実機データ: ${note}`) : state;
      }
      let name = referenceId;
      if (Array.isArray(result.references)) {
        for (const item of result.references) {
          const rec = asRecord(item);
          if (rec && asString(rec.id) === referenceId && asString(rec.name) !== "") {
            name = asString(rec.name);
          }
        }
      }
      const sim = asRecord(seed.sim);
      const design = toDesign(seed.design);
      const reference: ReferenceInfo = { id: referenceId, name, notes: asStringArray(seed.notes), design };
      let next: DesignState = { ...state, reference };
      if (sim && design) {
        // the seed's own simulation: attempt 0 (free, not a simulate_design call)
        const row: AttemptRow = {
          id,
          attempt: ev.attempt,
          t_s: ev.t_s,
          result: toSimResult(sim),
          error: null,
          design,
          seededFrom: referenceId,
        };
        next = { ...next, attempts: [...next.attempts, row] };
      }
      return push(next, "system", `ベース実機: ${name} (${referenceId})`);
    }
    case "run_dispersion": {
      const input = state.toolInputs[id];
      const design = toDesign(input?.design);
      const candidateId = findAttemptByDesign(state, design);
      const [targetPerigee, targetApogee] = orbitTargets(input);
      const dispersion: DispersionResult = {
        ...toDispersion(result, design),
        candidate_id: candidateId,
        target_perigee_m: targetPerigee,
        target_apogee_m: targetApogee,
      };
      const key = candidateId ?? (dispersion.source_id || id);
      let next: DesignState = {
        ...state,
        dispersion,
        dispersions: { ...state.dispersions, [key]: dispersion },
      };
      if (Number.isFinite(dispersion.success_rate)) {
        next = push(
          next,
          "system",
          `多数回試行 n=${dispersion.n}${candidateId ? ` (${candidateId})` : ""}: 成功率 ${(
            dispersion.success_rate * 100
          ).toFixed(1)} %`,
        );
      }
      return next;
    }
    default:
      return state;
  }
}

function applyCandidate(state: DesignState, ev: AgentEvent): DesignState {
  const p = ev.payload;
  const design = toDesign(p.design);
  if (!design) return state;
  const sourceId = asString(p.source_id);
  const attempt = state.attempts.find((a) => a.id === sourceId);
  const sim = attempt?.result ?? null;
  const candidate: Candidate = {
    source_id: sourceId,
    design,
    metrics: asNumberMap(p.metrics),
    cost_jpy: asNumber(p.cost_jpy),
    passed: sim ? sim.success : true,
    success_rate: asNumberOrNull(p.success_rate),
    explanation: "",
    failure_reasons: sim ? sim.failure_reasons : [],
    inFinal: false,
    seededFrom: asString(p.seeded_from) || null,
  };
  return { ...state, candidates: upsertCandidate(state.candidates, candidate) };
}

function applyFinal(state: DesignState, ev: AgentEvent): DesignState {
  const p = ev.payload;
  const resultRec = asRecord(p.result);
  const final: FinalPayload = {
    result: resultRec ? toFinalResult(resultRec) : null,
    provenance_violations: asStringArray(p.provenance_violations),
    attempts: asNumberOrNull(p.attempts),
    stop_reason: asString(p.stop_reason),
    raw_text: asString(p.raw_text),
    parse_error: asString(p.parse_error),
  };
  let next: DesignState = { ...state, final };

  if (final.result) {
    let candidates = state.candidates;
    final.result.designs.forEach((fd, i) => {
      const sourceValues = Object.values(fd.sources);
      const sourceId = fd.sources.cost_jpy ?? sourceValues[0] ?? `final-${i}`;
      const attempt = state.attempts.find((a) => a.id === sourceId);
      candidates = upsertCandidate(candidates, {
        source_id: sourceId,
        design: fd.design,
        metrics: fd.metrics,
        cost_jpy: fd.cost_jpy,
        passed: fd.passed,
        success_rate: fd.success_rate,
        explanation: fd.explanation,
        failure_reasons: attempt?.result?.failure_reasons ?? [],
        inFinal: true,
        seededFrom: attempt?.seededFrom ?? null,
      });
    });
    next = { ...next, candidates };
    const passedCount = final.result.designs.filter((d) => d.passed).length;
    next = push(
      next,
      "agent",
      `${final.result.summary}\n（最終案 ${final.result.designs.length} 件、うち合格 ${passedCount} 件）`,
    );
    for (const q of final.result.open_questions) next = push(next, "question", q);
  } else {
    next = push(
      next,
      "error",
      `最終回答を JSON として解釈できませんでした (${final.parse_error || "parse_error"})`,
    );
    if (final.raw_text) next = push(next, "agent", final.raw_text);
  }
  if (final.provenance_violations.length > 0) {
    const text = `出典のない数値が説明文に含まれています: ${final.provenance_violations.join(", ")}`;
    next = push({ ...next, errors: [...next.errors, text] }, "error", text);
  }
  return next;
}

function applyError(state: DesignState, ev: AgentEvent): DesignState {
  const p = ev.payload;
  const kind = asString(p.kind) || "error";
  const detail = asString(p.reason) || asString(p.detail) || asString(p.error) || asString(p.text);
  const suggestion = asString(p.suggestion);
  const text = `[${kind}] ${detail || JSON.stringify(p)}${suggestion ? `\n提案: ${suggestion}` : ""}`;
  return push({ ...state, status: "error", errors: [...state.errors, text] }, "error", text);
}
