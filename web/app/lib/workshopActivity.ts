/** Presentation state only: no operation can be started or marked complete here. */
import type { DesignState } from "./designState";

export type CrewTaskStatus = "idle" | "working" | "waiting" | "done" | "attention" | "stopped";
export type CrewPhase = "waiting" | "inspecting" | "tidying" | "attention";
export interface CrewTask { id: string; status: CrewTaskStatus; label: string }
export interface CrewState {
  key: string; taskStatus: CrewTaskStatus; phase: CrewPhase; cleanupUntil: number; label: string;
}
export const IDLE_TASK: CrewTask = { id: "idle", status: "idle", label: "次の工程を待っています" };
export const INITIAL_CREW: CrewState = { key: "", taskStatus: "idle", phase: "waiting", cleanupUntil: 0, label: IDLE_TASK.label };
export const CLEANUP_MS = 6000;

const INSPECTION: Record<string, string> = {
  simulate_design: "飛行計算の結果を点検中", design_from_parts: "部品の構成と飛行を点検中",
  auto_design: "構成案を点検中", run_dispersion: "条件を変えた試行を点検中",
  estimate_cost: "材料と費用を点検中", render_drawing: "図面を点検中",
  export_report: "出力ファイルを点検中", design_stage: "設計条件を点検中",
};

export function designCrewTask(state: Pick<DesignState, "refused" | "status" | "pendingQuestion" | "events" | "candidates" | "final">): CrewTask {
  if (state.status === "error") return { id: "design", status: "attention", label: "処理を止めて、エラーの確認を待っています" };
  if (state.pendingQuestion) return { id: "design", status: "waiting", label: "資料を持って、追加の回答を待っています" };
  if (state.status === "streaming") {
    const finished = new Set(state.events.filter(e => e.type === "tool_result").map(e => e.payload.id));
    const call = [...state.events].reverse().find(e => e.type === "tool_call" && !finished.has(e.payload.id));
    if (call) {
      const name = String(call.payload.name);
      return { id: "design", status: "working", label: INSPECTION[name] ?? "要求と資料を点検中" };
    }
    const latest = [...state.events].reverse().find(e => e.type === "tool_result");
    const result = latest?.payload.result;
    if (latest?.type === "tool_result" && (latest.payload.is_error === true
      || (result && typeof result === "object" && "error" in result && result.error))) {
      return { id: "design", status: "attention", label: "点検を止めて、処理の見直しを待っています" };
    }
    return { id: "design", status: "waiting", label: "資料を確認し、次の処理を待っています" };
  }
  if (state.status === "done") {
    if (state.refused) return { id: "design", status: "done", label: "ペットボトルロケットの範囲を超える要求でした" };
    if (!state.final) return { id: "design", status: "stopped", label: "処理は中断されました。受け取った結果を確認できます" };
    const passed = state.candidates.some(c => c.passed === true && !c.seededFrom);
    return passed
      ? { id: "design", status: "done", label: "計算が終了しました。結果を確認できます" }
      : { id: "design", status: "attention", label: "条件を満たす案は未確認です。結果の見直しを待っています" };
  }
  return IDLE_TASK;
}

export function chooseCrewTask(tasks: { source: string; task: CrewTask; order: number }[]): CrewTask {
  const priority: Record<CrewTaskStatus, number> = { working: 5, waiting: 4, attention: 3, stopped: 3, done: 2, idle: 0 };
  const chosen = [...tasks].sort((a, b) => priority[b.task.status] - priority[a.task.status] || b.order - a.order)[0];
  return chosen && chosen.task.status !== "idle" ? { ...chosen.task, id: `${chosen.source}:${chosen.task.id}` } : IDLE_TASK;
}

/** Only a live task's observed successful end starts cleanup; restored results do not. */
export function transitionCrew(previous: CrewState, task: CrewTask, now: number): CrewState {
  const same = previous.key === task.id;
  const justFinished = same && task.status === "done" && ["working", "waiting"].includes(previous.taskStatus);
  const until = justFinished ? now + CLEANUP_MS : same && task.status === "done" ? previous.cleanupUntil : 0;
  const phase: CrewPhase = task.status === "working" ? "inspecting"
    : task.status === "attention" || task.status === "stopped" ? "attention"
    : until > now ? "tidying" : "waiting";
  return { key: task.id, taskStatus: task.status, phase, cleanupUntil: until,
    label: phase === "tidying" ? "処理が終了し、道具を片付けています" : task.label };
}
