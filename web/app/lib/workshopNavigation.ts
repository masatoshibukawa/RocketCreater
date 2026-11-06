export const WORKSHOP_STAGES = [
  { id: "design", label: "設計", title: "機体の構成" },
  { id: "analysis", label: "解析", title: "解析の工程" },
  { id: "exports", label: "出力", title: "成果物" },
] as const;
export type WorkshopStage = typeof WORKSHOP_STAGES[number]["id"];
export type AnalysisView = "aero" | "flight" | "chart";
export type OutputView = "drawing" | "production" | "video";
export const stageLabel = (stage: WorkshopStage) => WORKSHOP_STAGES.find(s => s.id === stage)?.label ?? "";
