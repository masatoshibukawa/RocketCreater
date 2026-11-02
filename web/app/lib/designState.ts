/**
 * Pure state machine for the design stream. `reduce` is free of React so it can be unit tested
 * by replaying recorded events (scripts/run_scenario.py output) without a browser.
 *
 * Event -> state mapping:
 *   thinking      -> chat message (role "thinking")
 *   text          -> chat message (role "agent"); a JSON blob (the model's final answer) is
 *                    collapsed to a system line because `final` carries the parsed version
 *   question      -> chat message (role "question")
 *   tool_call     -> chat system line
 *   tool_result   -> classify_requirement: tier badge; simulate_design: attempt log row;
 *                    run_dispersion: landing scatter / success rate; errors: chat error line
 *   candidate     -> candidate card (passed/failure_reasons looked up from the attempt log)
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
  type Design,
  type DispersionSummary,
  type FinalDesign,
  type FinalPayload,
  type FinalResult,
  type LandingPoint,
  type SimResult,
  type Tier,
  type TracePoint,
} from "./types";

export type Status = "idle" | "streaming" | "done" | "error";

export interface DesignState {
  status: Status;
  request: string;
  events: AgentEvent[];
  messages: ChatMessage[];
  tier: Tier | null;
  classify: ClassifyResult | null;
  attempts: AttemptRow[];
  attemptCount: number;
  candidates: Candidate[];
  dispersion: DispersionSummary | null;
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
  attempts: [],
  attemptCount: 0,
  candidates: [],
  dispersion: null,
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

function toDispersion(rec: Record<string, unknown>): DispersionSummary {
  const landing = asRecord(rec.landing);
  const points: LandingPoint[] = [];
  if (landing && Array.isArray(landing.points)) {
    for (const item of landing.points) {
      const p = asRecord(item);
      if (p) points.push({ east_m: asNumber(p.east_m, 0), north_m: asNumber(p.north_m, 0) });
    }
  }
  const counts: Record<string, number> = {};
  const rawCounts = asRecord(rec.failure_counts);
  if (rawCounts) {
    for (const [k, v] of Object.entries(rawCounts)) counts[k] = asNumber(v, 0);
  }
  return {
    source_id: asString(rec.source_id),
    tier: isTier(rec.tier) ? rec.tier : null,
    n: asNumber(rec.n, 0),
    success_rate: asNumber(rec.success_rate, Number.NaN),
    landing_points: points,
    failure_counts: counts,
  };
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
    case "question":
      return push(next, "question", asString(p.text));
    case "tool_call":
      return push(next, "system", `ツール呼び出し: ${asString(p.name)}`);
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
        attempts: [...next.attempts, { id, attempt: ev.attempt, t_s: ev.t_s, result: null, error: errorText }],
      };
    }
    return push(next, "error", `ツール ${name} がエラーを返しました: ${errorText}`);
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
    case "simulate_design": {
      const sim = toSimResult(result);
      const row: AttemptRow = { id, attempt: ev.attempt, t_s: ev.t_s, result: sim, error: null };
      let next: DesignState = { ...state, attempts: [...state.attempts, row] };
      if (!state.tier && sim.tier) next = { ...next, tier: sim.tier };
      return next;
    }
    case "run_dispersion": {
      const dispersion = toDispersion(result);
      let next: DesignState = { ...state, dispersion };
      if (Number.isFinite(dispersion.success_rate)) {
        next = push(
          next,
          "system",
          `多数回試行 n=${dispersion.n}: 成功率 ${(dispersion.success_rate * 100).toFixed(1)} %`,
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
