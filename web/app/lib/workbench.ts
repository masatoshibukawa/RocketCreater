"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "./api";
import type { BottleDesign } from "./types";

export interface WorkbenchFile { name: string; key: string; kind: string; url: string; sha256: string }
export interface AnalysisOption {
  id: string; label: string; method: string; architecture: string;
  variant: string; pressure_kpa: number; fill_pct: number;
}
export interface WorkbenchProject {
  id: string; revision: number; confirmed: boolean; recommendation: string | null;
  workshop: { pressure_ceiling_kpa: number };
  active: { name: string; started_at: number } | null; error: string | null;
  options: AnalysisOption[]; files: WorkbenchFile[];
  proposal: { id: string; reason: string; model: string } | null;
  design: BottleDesign | null;
  plan: { dimensions_mm: Record<string, number>; dry_mass_g: number; cp_mm: number;
    wet_cg_mm: number; checks: Record<string, boolean>; pending_evidence?: string[];
    bill: { id: string; name: string; mass_g: number; allowance_jpy: number }[] } | null;
  history: { chosen: string; reason: string; result: Record<string, unknown> }[];
  last_elapsed_seconds?: number;
  video_plan?: { status: string; model: string; design_caption: string; launch_caption: string;
    wan_status: string; width: number; height: number; fps: number; frames_per_clip: number };
}
export interface RuntimeStatus {
  ollama: { available: boolean; models: string[] }; comfyui: { available: boolean; version?: string };
}
const STORAGE_KEY = "rocketwright.workbench.v1";

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(apiUrl(path), body === undefined ? { signal, cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  });
  const data = await response.json().catch(() => ({})) as T & { detail?: unknown };
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  return data;
}

export function useWorkbench() {
  const [project, setProject] = useState<WorkbenchProject | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const pending = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const saved = localStorage.getItem(STORAGE_KEY);
    void request<RuntimeStatus>("/workbench/runtime", undefined, controller.signal)
      .then(setRuntime).catch(() => undefined);
    if (saved && /^[a-f0-9]{32}$/.test(saved)) {
      void request<WorkbenchProject>(`/workbench/projects/${saved}`, undefined, controller.signal)
        .then(setProject).catch((e: unknown) => {
          if (!controller.signal.aborted) setError(`保存した工程を開けません: ${String(e)}`);
        });
    }
    return () => { mounted.current = false; controller.abort(); };
  }, []);

  useEffect(() => {
    if (!busy && !project?.active) { setElapsed(0); return; }
    const started = project?.active ? project.active.started_at * 1000 : Date.now();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [busy, project?.active?.started_at]);

  const projectId = project?.id;
  useEffect(() => {
    if (!projectId || (!busy && !project?.active)) return;
    const controller = new AbortController();
    let fetching = false;
    const timer = setInterval(() => {
      if (fetching) return;
      fetching = true;
      void request<WorkbenchProject>(`/workbench/projects/${projectId}`, undefined, controller.signal)
        .then(setProject).catch(() => undefined).finally(() => { fetching = false; });
    }, 1800);
    return () => { clearInterval(timer); controller.abort(); };
  }, [projectId, busy, Boolean(project?.active)]);

  const act = useCallback(async (operation: string, extra: Record<string, unknown> = {}) => {
    if (pending.current || project?.active) return;
    pending.current = true; setBusy(operation); setError("");
    try {
      const path = operation === "create" ? "/workbench/projects" : `/workbench/projects/${project?.id}/${operation}`;
      const next = await request<WorkbenchProject>(path, operation === "create" ? {} : { revision: project?.revision, ...extra });
      if (mounted.current) {
        setProject(next); localStorage.setItem(STORAGE_KEY, next.id);
      }
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
      if (projectId) {
        await request<WorkbenchProject>(`/workbench/projects/${projectId}`)
          .then(p => { if (mounted.current) setProject(p); }).catch(() => undefined);
      }
    } finally {
      pending.current = false;
      if (mounted.current) setBusy("");
    }
  }, [project, projectId]);

  return { project, runtime, busy, error, elapsed, act };
}
