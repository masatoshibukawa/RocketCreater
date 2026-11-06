"use client";

import type { Status } from "../lib/designState";

interface StatusStripProps {
  status: Status;
  attemptCount: number;
  onOpenWorkbench: () => void;
}

/** App name, a one-line status (待機中 / 設計中 (試行 n) / 完了 / エラー) and the way to the workbench. */
export default function StatusStrip({ status, attemptCount, onOpenWorkbench }: StatusStripProps) {
  let label: string;
  if (status === "streaming") label = `設計中（試行 ${attemptCount}）`;
  else if (status === "done") label = "完了";
  else if (status === "error") label = "エラー";
  else label = "待機中";
  return (
    <header className={`status-strip status-${status}`}>
      <span className="status-brand">RocketWright</span>
      <span className="status-sub">自然文の要求から、シミュレーションで検証した設計案を返します</span>
      <span className="status-line">
        <span className="status-dot" />
        {label}
      </span>
      <button type="button" className="btn" onClick={onOpenWorkbench}>
        製作ワークベンチへ
      </button>
    </header>
  );
}
