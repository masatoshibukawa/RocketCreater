export const WORKSHOP_STAGES = [
  { id: "brief", label: "条件", title: "ミッション" },
  { id: "design", label: "設計", title: "機体の構成" },
  { id: "analysis", label: "解析", title: "解析の工程" },
  { id: "compare", label: "比較", title: "設計案の候補" },
  { id: "assembly", label: "組立", title: "組立の準備" },
  { id: "exports", label: "出力", title: "成果物" },
] as const;
export type WorkshopStage = typeof WORKSHOP_STAGES[number]["id"] | "library";
export type AnalysisView = "aero" | "flight" | "chart";
export type OutputView = "drawing" | "production" | "video";
export const stageLabel = (stage: WorkshopStage) => WORKSHOP_STAGES.find(s => s.id === stage)?.label ?? "設計例と資料";
