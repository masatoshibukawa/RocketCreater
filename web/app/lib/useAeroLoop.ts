"use client";

/**
 * The flow analysis of the displayed design. POST /aero/loop only starts a job, so nothing waits
 * on a long request; each unfinished job is polled until it ends. Jobs are kept per design, so
 * going back to a design shows its result, and the API shares a job between equal requests.
 */

import { useCallback, useEffect, useState } from "react";
import { apiUrl, designKey } from "./api";
import type { Design } from "./types";

export interface AeroLoopRound {
  round: number; cfd_speed_mps: number; cd: number; cd_change_frac: number;
  static_margin_cal: number | null; pressure_kpa?: number; apogee_m: number;
  descent_speed_mps: number; backend: string;
}
export interface AeroLoopResult {
  tier: string; rounds: AeroLoopRound[]; converged: boolean; notes: string[];
  baseline: { pressure_kpa: number | null; cd: number | null };
  dispersion: { n: number; passes: number; success_rate: number } | null;
}
export interface AeroImage { name: string; url: string; speed_mps: number | null; alpha_deg: number | null }
export interface AeroJob {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  elapsed_s: number | null;
  result: AeroLoopResult | null;
  error: string | null;
  images: AeroImage[];
}
export interface AeroRequest {
  design: Design;
  target_altitude_m: number;
  requirement: Record<string, unknown> | null;
  env: Record<string, unknown> | null;
  seed: number | null;
  n: number | null;
}

const POLL_MS = 2000;
const FORGOTTEN = "API が再起動したため解析の記録が消えました。もう一度実行してください。";
const isActive = (job: AeroJob): boolean => job.status === "queued" || job.status === "running";

async function readJob(response: Response): Promise<AeroJob> {
  const data = (await response.json().catch(() => ({}))) as AeroJob & { detail?: unknown };
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  return data;
}

export function useAeroLoop(request: AeroRequest | null) {
  const key = request ? `${designKey(request.design)}@${request.target_altitude_m}` : "";
  const [jobs, setJobs] = useState<Record<string, AeroJob>>({});
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const job = jobs[key] ?? null;
  useEffect(() => setError(""), [key]);

  const run = useCallback(async () => {
    if (!request) return;
    setStarting(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/aero/loop"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const started = await readJob(response);
      setJobs((all) => ({ ...all, [key]: started }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }, [request, key]);

  // [design key, job id] of each unfinished job, as text so that an update of a job's elapsed
  // time does not restart the timer.
  const active = JSON.stringify(Object.entries(jobs).filter(([, j]) => isActive(j)).map(([k, j]) => [k, j.id]));
  useEffect(() => {
    const pairs = JSON.parse(active) as [string, string][];
    if (pairs.length === 0) return undefined;
    const controller = new AbortController();
    const refresh = async (designId: string, jobId: string): Promise<void> => {
      const response = await fetch(apiUrl(`/aero/loop/${jobId}`), { signal: controller.signal, cache: "no-store" });
      if (response.status === 404) {
        setJobs((all) => ({ ...all, [designId]: { ...all[designId], status: "failed", error: FORGOTTEN } }));
        return;
      }
      const next = await readJob(response);
      setJobs((all) => ({ ...all, [designId]: next }));
    };
    const timer = setInterval(() => {
      // A network slip is simply retried on the next tick.
      for (const [designId, jobId] of pairs) refresh(designId, jobId).catch(() => undefined);
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [active]);

  return { job, starting, error, run };
}
