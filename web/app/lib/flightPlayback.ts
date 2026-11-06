/**
 * Playback of a simulated flight. Pure functions over the API's `trace`, so nothing here makes up
 * a value: phases are read off the samples, and what the trace lacks stays null.
 */

import type { Design, TracePoint } from "./types";

export type FlightPhase = "thrust" | "coast" | "ascent" | "descent";

export const PHASE_COLOR: Record<FlightPhase, string> = {
  thrust: "#b93a08",
  coast: "#1a4db0",
  ascent: "#1a4db0",
  descent: "#0f6e4d",
};

/** Altitude under which the last sample counts as landed. */
const GROUND_FRACTION = 0.01;
const LONG_FLIGHT_S = 120;

export interface FlightTimeline {
  points: TracePoint[];
  /** Signed horizontal position of each sample, along the pad-to-last-sample line. */
  horizontal: number[];
  startS: number;
  endS: number;
  apogeeIndex: number;
  /** Time of the last sample with thrust; null when the trace has no thrust samples. */
  thrustEndS: number | null;
  reachesGround: boolean;
  hasDescent: boolean;
}

export function thrustOf(point: TracePoint): number | null {
  const thrust = point.extra.thrust_n;
  return typeof thrust === "number" ? thrust : null;
}

function horizontalPositions(points: TracePoint[]): number[] {
  const last = points[points.length - 1];
  const reach = Math.hypot(last.east_m, last.north_m);
  const widest = Math.max(...points.map((p) => Math.hypot(p.east_m, p.north_m)));
  if (widest === 0) return points.map((p) => p.downrange_m); // multistage: along-track only
  if (reach === 0) return points.map((p) => p.east_m);
  const east = last.east_m / reach;
  const north = last.north_m / reach;
  return points.map((p) => p.east_m * east + p.north_m * north);
}

/** The timeline of a trace, or null when it has too few samples to play. */
export function buildTimeline(trace: TracePoint[]): FlightTimeline | null {
  if (trace.length < 2) return null;
  const points = [...trace].sort((a, b) => a.t_s - b.t_s);
  let apogeeIndex = 0;
  let thrustEndS: number | null = null;
  points.forEach((p, i) => {
    if (p.altitude_m > points[apogeeIndex].altitude_m) apogeeIndex = i;
    if ((thrustOf(p) ?? 0) > 0) thrustEndS = p.t_s;
  });
  const apogee = points[apogeeIndex].altitude_m;
  const last = points[points.length - 1];
  return {
    points,
    horizontal: horizontalPositions(points),
    startS: points[0].t_s,
    endS: last.t_s,
    apogeeIndex,
    thrustEndS,
    reachesGround: last.altitude_m <= apogee * GROUND_FRACTION,
    hasDescent: apogeeIndex < points.length - 1,
  };
}

/** Index of the last sample at or before `timeS`. */
export function sampleIndexAt(timeline: FlightTimeline, timeS: number): number {
  const { points } = timeline;
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (points[middle].t_s <= timeS) low = middle;
    else high = middle - 1;
  }
  return low;
}

export function phaseAt(timeline: FlightTimeline, timeS: number): FlightPhase {
  const { thrustEndS, points, apogeeIndex } = timeline;
  if (thrustEndS !== null && timeS <= thrustEndS) return "thrust";
  if (timeS > points[apogeeIndex].t_s) return "descent";
  return thrustEndS === null ? "ascent" : "coast";
}

export function phaseLabel(phase: FlightPhase, parachute: boolean): string {
  if (phase === "thrust") return "推力";
  if (phase === "coast") return "慣性で上昇";
  if (phase === "ascent") return "上昇";
  return parachute ? "パラシュート降下" : "降下";
}

export interface PhaseSpan {
  phase: FlightPhase;
  fromS: number;
  toS: number;
}

export function phaseSpans(timeline: FlightTimeline): PhaseSpan[] {
  const { startS, endS, thrustEndS, points, apogeeIndex, hasDescent } = timeline;
  const apogeeS = points[apogeeIndex].t_s;
  const rising = thrustEndS === null ? startS : thrustEndS;
  const spans: PhaseSpan[] = [];
  if (thrustEndS !== null) spans.push({ phase: "thrust", fromS: startS, toS: thrustEndS });
  if (apogeeS > rising) {
    spans.push({ phase: thrustEndS === null ? "ascent" : "coast", fromS: rising, toS: apogeeS });
  }
  if (hasDescent) spans.push({ phase: "descent", fromS: apogeeS, toS: endS });
  return spans;
}

/** Playback rates: slow enough to see a water rocket's thrust, fast enough for an orbital ascent. */
export function playbackSpeeds(timeline: FlightTimeline): { speeds: number[]; initial: number } {
  return timeline.endS - timeline.startS > LONG_FLIGHT_S
    ? { speeds: [1, 10, 30, 60, 120], initial: 30 }
    : { speeds: [0.1, 0.25, 0.5, 1, 2], initial: 1 };
}

export function carriesParachute(design: Design | null | undefined): boolean {
  if (!design) return false;
  if (design.tier === "bottle") return design.has_parachute;
  return design.tier === "amateur" && design.parachute_diameter_m > 0;
}

/** A step of 1, 2 or 5 x 10^n that divides `span` into about `ticks` parts. */
export function niceStep(span: number, ticks: number): number {
  const raw = span / ticks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const leading = raw / magnitude;
  return (leading <= 1 ? 1 : leading <= 2 ? 2 : leading <= 5 ? 5 : 10) * magnitude;
}
