/**
 * Backend URL helpers and the artifact endpoints (api/main.py):
 *   POST /artifacts/render            {design} -> {id, download: {svg}}
 *   POST /artifacts/summary           {design, requirement|null, width_px|null, build|null}
 *                                     -> DesignSummary
 *   POST /artifacts/package           DesignPackageRequest -> DesignPackage
 *   GET  /artifacts/{id}.{svg|md|csv|json}
 * Tool results of `export_report` / `render_drawing` carry the same `download` map, so the UI
 * only ever joins a path from the backend onto API_BASE.
 */

import {
  isTier,
  type AgentEvent,
  type BomItem,
  type CostBreakdownItem,
  type Design,
  type DesignSummary,
  type ExportInfo,
} from "./types";

export const API_BASE: string = process.env.NEXT_PUBLIC_API_BASE ?? "/backend";

/** Join a backend-relative path (e.g. "/artifacts/svg_1.svg") onto API_BASE. */
export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const base = API_BASE.replace(/\/+$/, "");
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** Stable key for a design (sorted keys) so equal designs compare equal across events. */
export function designKey(design: Design): string {
  return stableStringify(design);
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const rec = value as Record<string, unknown>;
    const keys = Object.keys(rec).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(rec[k])}`).join(",")}}`;
  }
  const s: string | undefined = JSON.stringify(value); // undefined for functions / symbols
  return typeof s === "string" ? s : "null";
}

/** Render the side view of a design: POST /artifacts/render, then GET the SVG text. */
export async function renderDrawing(design: Design, signal?: AbortSignal): Promise<string> {
  const res = await fetch(apiUrl("/artifacts/render"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ design }),
    signal,
  });
  if (!res.ok) throw new Error(`render failed: HTTP ${res.status}`);
  const body = (await res.json()) as { download?: { svg?: string } };
  const path = body.download?.svg;
  if (typeof path !== "string") throw new Error("render response has no download.svg");
  const svg = await fetch(apiUrl(path), { signal });
  if (!svg.ok) throw new Error(`svg fetch failed: HTTP ${svg.status}`);
  return svg.text();
}

/** GET a backend-relative text artifact (an SVG drawing). */
export async function fetchArtifactText(path: string, signal?: AbortSignal): Promise<string> {
  const res = await fetch(apiUrl(path), { signal });
  if (!res.ok) throw new Error(`artifact fetch failed: HTTP ${res.status}`);
  return res.text();
}

function numOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toCostBreakdown(value: unknown): CostBreakdownItem[] {
  if (!Array.isArray(value)) return [];
  const out: CostBreakdownItem[] = [];
  for (const item of value) {
    const rec = asRecord(item);
    if (!rec) continue;
    const jpy = numOrNull(rec.jpy);
    if (jpy === null) continue;
    out.push({
      label: typeof rec.label === "string" ? rec.label : "",
      jpy,
      note: typeof rec.note === "string" ? rec.note : "",
      provisional: rec.provisional === true,
    });
  }
  return out;
}

function toBom(value: unknown): BomItem[] {
  if (!Array.isArray(value)) return [];
  const out: BomItem[] = [];
  for (const item of value) {
    const rec = asRecord(item);
    if (!rec) continue;
    out.push({
      item_id: typeof rec.item_id === "string" ? rec.item_id : "",
      name: typeof rec.name === "string" ? rec.name : String(rec.item_id ?? ""),
      qty: numOrNull(rec.qty) ?? 1,
      mass_kg: numOrNull(rec.mass_kg),
      price_jpy: numOrNull(rec.price_jpy),
      source_or_provisional:
        typeof rec.source_or_provisional === "string" ? rec.source_or_provisional : "",
    });
  }
  return out;
}

/** Parse a POST /artifacts/summary body defensively (missing blocks become null / empty). */
export function toDesignSummary(raw: unknown): DesignSummary {
  const rec = asRecord(raw) ?? {};
  const drawing = asRecord(rec.drawing);
  const mass = asRecord(rec.mass);
  const dims = asRecord(rec.dimensions);
  return {
    tier: isTier(rec.tier) ? rec.tier : null,
    cost_jpy: numOrNull(rec.cost_jpy) ?? Number.NaN,
    cost_breakdown: toCostBreakdown(rec.cost_breakdown),
    bom: toBom(rec.bom),
    drawing:
      drawing && typeof drawing.url === "string"
        ? { id: typeof drawing.id === "string" ? drawing.id : "", url: drawing.url }
        : null,
    mass: mass
      ? {
          liftoff_mass_kg: numOrNull(mass.liftoff_mass_kg),
          dry_mass_kg: numOrNull(mass.dry_mass_kg),
          payload_mass_kg: numOrNull(mass.payload_mass_kg),
          propellant_mass_kg: numOrNull(mass.propellant_mass_kg),
        }
      : null,
    dimensions: dims
      ? { length_m: numOrNull(dims.length_m), diameter_m: numOrNull(dims.diameter_m) }
      : null,
  };
}

/**
 * POST /artifacts/summary for one design. `requirement` is the normalised Requirement from the
 * classify_requirement tool_call (or null before classification). With a parts `build` the cost
 * and BOM are the bill's rather than cost.py's estimate.
 */
export async function fetchDesignSummary(
  design: Design,
  requirement: Record<string, unknown> | null,
  signal?: AbortSignal,
  widthPx: number | null = null,
  build: Record<string, unknown> | null = null,
): Promise<DesignSummary> {
  const res = await fetch(apiUrl("/artifacts/summary"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ design, requirement, width_px: widthPx, build }),
    signal,
  });
  if (!res.ok) throw new Error(`summary failed: HTTP ${res.status}`);
  return toDesignSummary(await res.json());
}

export interface DesignPackageRequest {
  design: Design;
  /** The parts build the design resolved from, so the bill and margins stay the build's. */
  build: Record<string, unknown> | null;
  requirement: Record<string, unknown> | null;
  env: Record<string, unknown> | null;
  /** Seed and size of the agent's dispersion, so the report repeats that very run. */
  seed: number | null;
  n: number | null;
}

export interface DesignPackage {
  passed: boolean;
  failure_reasons: string[];
  files: { kind: string; label: string; url: string }[];
  unavailable: { item: string; reason: string }[];
}

/** POST /artifacts/package: the production files of one design. */
export async function createDesignPackage(
  request: DesignPackageRequest,
  signal?: AbortSignal,
): Promise<DesignPackage> {
  const res = await fetch(apiUrl("/artifacts/package"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  const data = (await res.json().catch(() => ({}))) as DesignPackage & { detail?: unknown };
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
  return data;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toDownload(value: unknown): Record<string, string> {
  const rec = asRecord(value);
  const out: Record<string, string> = {};
  if (!rec) return out;
  for (const [k, v] of Object.entries(rec)) {
    if (typeof v === "string" && v !== "") out[k] = v;
  }
  return out;
}

function toDesign(value: unknown): Design | null {
  const rec = asRecord(value);
  return rec && typeof rec.tier === "string" ? (rec as unknown as Design) : null;
}

/**
 * Collect every `download` map the stream produced: tool_result events of `export_report` /
 * `render_drawing` (the design comes from the matching tool_call) and `final.result.designs[*]`
 * entries that carry a `download` key.
 */
export function exportInfoFromEvents(events: readonly AgentEvent[]): ExportInfo[] {
  const callDesigns = new Map<string, Design | null>();
  const out: ExportInfo[] = [];
  for (const ev of events) {
    const p = ev.payload;
    if (ev.type === "tool_call") {
      if (p.name === "export_report" || p.name === "render_drawing") {
        const input = asRecord(p.input);
        callDesigns.set(String(p.id ?? ""), input ? toDesign(input.design) : null);
      }
      continue;
    }
    if (ev.type === "tool_result") {
      if (p.name !== "export_report" && p.name !== "render_drawing") continue;
      const result = asRecord(p.result);
      if (!result || typeof result.error === "string" || p.is_error === true) continue;
      const download = toDownload(result.download);
      if (Object.keys(download).length === 0) continue;
      const id = String(p.id ?? "");
      out.push({
        id: typeof result.id === "string" ? result.id : id,
        source_id: id,
        design: callDesigns.get(id) ?? null,
        download,
      });
      continue;
    }
    if (ev.type === "final") {
      const result = asRecord(p.result);
      const designs = result && Array.isArray(result.designs) ? result.designs : [];
      designs.forEach((item, i) => {
        const rec = asRecord(item);
        if (!rec) return;
        const download = toDownload(rec.download);
        if (Object.keys(download).length === 0) return;
        out.push({ id: `final-${i}`, source_id: `final-${i}`, design: toDesign(rec.design), download });
      });
    }
  }
  return out;
}

/** Downloads that belong to a card: same design, or (fallback) nothing. */
export function exportsForDesign(exports: readonly ExportInfo[], design: Design): ExportInfo[] {
  const key = designKey(design);
  return exports.filter((e) => e.design !== null && designKey(e.design) === key);
}
