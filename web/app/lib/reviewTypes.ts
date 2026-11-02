/**
 * Reviewer verdicts (rocketwright/agent/review.py) and the `review` / `warning` events emitted
 * by rocketwright/agent/loop.py. Kept separate from types.ts so the review panel can evolve
 * without touching the core event types.
 *
 * `review` payload (loop.py):
 *   { source_id, verdicts: ReviewVerdict[], max_severity, blocked, feedback | null,
 *     dropped: { [aspect]: string[] } }
 * `warning` payload of kind "review_gate" (loop.py):
 *   { kind: "review_gate", detail, rejected_ids: string[] }
 */

import type { AgentEvent } from "./types";

export type ReviewAspect = "stability" | "recovery" | "cost" | "safety";
export type ReviewSeverity = "ok" | "minor" | "major" | "blocker";

export const REVIEW_ASPECTS: readonly ReviewAspect[] = ["stability", "recovery", "cost", "safety"];
export const REVIEW_SEVERITIES: readonly ReviewSeverity[] = ["ok", "minor", "major", "blocker"];

export const ASPECT_LABEL: Record<ReviewAspect, string> = {
  stability: "安定性",
  recovery: "回収",
  cost: "費用",
  safety: "安全",
};

export const SEVERITY_LABEL: Record<ReviewSeverity, string> = {
  ok: "OK",
  minor: "軽微",
  major: "要修正",
  blocker: "不可",
};

export interface ReviewVerdict {
  aspect: ReviewAspect;
  severity: ReviewSeverity;
  findings: string[];
  suggested_changes: string[];
}

/** One reviewed candidate, folded from a `review` event. */
export interface ReviewEntry {
  source_id: string;
  attempt: number;
  t_s: number;
  verdicts: ReviewVerdict[];
  max_severity: ReviewSeverity;
  blocked: boolean;
  feedback: string | null;
  /** aspect -> reviewer texts removed in code because they cited unsourced numbers. */
  dropped: Record<string, string[]>;
}

/** A `warning` event of kind `review_gate` (designs moved out of the final passing list). */
export interface ReviewGateWarning {
  detail: string;
  rejected_ids: string[];
}

export function isReviewAspect(value: unknown): value is ReviewAspect {
  return typeof value === "string" && (REVIEW_ASPECTS as readonly string[]).includes(value);
}

export function isReviewSeverity(value: unknown): value is ReviewSeverity {
  return typeof value === "string" && (REVIEW_SEVERITIES as readonly string[]).includes(value);
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (let i = 0; i < value.length; i += 1) {
    const v: unknown = value[i];
    if (typeof v === "string") out.push(v);
  }
  return out;
}

function toVerdict(raw: unknown): ReviewVerdict | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const rec = raw as Record<string, unknown>;
  if (!isReviewAspect(rec.aspect)) return null;
  const severity: ReviewSeverity = isReviewSeverity(rec.severity) ? rec.severity : "minor";
  return {
    aspect: rec.aspect,
    severity,
    findings: stringList(rec.findings),
    suggested_changes: stringList(rec.suggested_changes),
  };
}

function toDropped(raw: unknown): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return out;
  const rec = raw as Record<string, unknown>;
  const keys = Object.keys(rec);
  for (let i = 0; i < keys.length; i += 1) {
    const texts = stringList(rec[keys[i]]);
    if (texts.length > 0) out[keys[i]] = texts;
  }
  return out;
}

const SEVERITY_RANK: Record<ReviewSeverity, number> = { ok: 0, minor: 1, major: 2, blocker: 3 };

export function maxSeverity(verdicts: ReviewVerdict[]): ReviewSeverity {
  let best: ReviewSeverity = "ok";
  for (let i = 0; i < verdicts.length; i += 1) {
    if (SEVERITY_RANK[verdicts[i].severity] > SEVERITY_RANK[best]) best = verdicts[i].severity;
  }
  return best;
}

/** Fold one `review` event into a ReviewEntry; null when the payload is not usable. */
export function reviewEntryFromEvent(ev: AgentEvent): ReviewEntry | null {
  if (ev.type !== "review") return null;
  const p = ev.payload;
  if (typeof p.source_id !== "string") return null;
  const verdicts: ReviewVerdict[] = [];
  if (Array.isArray(p.verdicts)) {
    for (let i = 0; i < p.verdicts.length; i += 1) {
      const v = toVerdict(p.verdicts[i]);
      if (v) verdicts.push(v);
    }
  }
  const max_severity: ReviewSeverity = isReviewSeverity(p.max_severity)
    ? p.max_severity
    : maxSeverity(verdicts);
  return {
    source_id: p.source_id,
    attempt: ev.attempt,
    t_s: ev.t_s,
    verdicts,
    max_severity,
    blocked: p.blocked === true || max_severity === "blocker",
    feedback: typeof p.feedback === "string" && p.feedback.length > 0 ? p.feedback : null,
    dropped: toDropped(p.dropped),
  };
}

/**
 * All reviewed candidates in stream order. A candidate reviewed more than once
 * (`max_rounds_per_candidate` > 1) keeps its latest verdicts.
 */
export function reviewsFromEvents(events: AgentEvent[]): ReviewEntry[] {
  const byId: Record<string, number> = {};
  const out: ReviewEntry[] = [];
  for (let i = 0; i < events.length; i += 1) {
    const entry = reviewEntryFromEvent(events[i]);
    if (!entry) continue;
    const idx = byId[entry.source_id];
    if (idx === undefined) {
      byId[entry.source_id] = out.length;
      out.push(entry);
    } else {
      out[idx] = entry;
    }
  }
  return out;
}

/** `warning` events of kind `review_gate`, in stream order. */
export function reviewGateWarningsFromEvents(events: AgentEvent[]): ReviewGateWarning[] {
  const out: ReviewGateWarning[] = [];
  for (let i = 0; i < events.length; i += 1) {
    const ev = events[i];
    if (ev.type !== "warning") continue;
    const p = ev.payload;
    if (p.kind !== "review_gate") continue;
    out.push({
      detail: typeof p.detail === "string" ? p.detail : "",
      rejected_ids: stringList(p.rejected_ids),
    });
  }
  return out;
}
