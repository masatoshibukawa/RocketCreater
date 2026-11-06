import type { BottleDesign } from "./types";
export interface WorkbenchFile { name: string; key: string; kind: string; url: string; sha256: string }
export interface AnalysisOption {
  id: string; label: string; method: string; architecture: string;
  variant: string; pressure_kpa: number; fill_pct: number;
}
export interface WorkbenchProject {
  print_package?: { status: string; brim_width_mm: number; brim_gap_mm: number;
    parts: { part: string; model_layers: number; estimated_mass_g: number;
      estimated_time_seconds: number; all_print_paths_inside_s5: boolean }[] };
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
