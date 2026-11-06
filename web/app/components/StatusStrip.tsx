"use client";

import type { Status } from "../lib/designState";

interface StatusStripProps {
  status: Status;
  attemptCount: number;
}

/** App name and a one-line status (待機中 / 設計中 (試行 n) / 完了 / エラー). */
export default function StatusStrip({ status, attemptCount }: StatusStripProps) {
  let label: string;
  if (status === "streaming") label = `設計中（試行 ${attemptCount}）`;
  else if (status === "done") label = "完了";
  else if (status === "error") label = "エラー";
  else label = "待機中";
  return (
    <div className={`status-strip status-${status}`}>
      <span className="status-line">
        <span className="status-dot" />
        {label}
      </span>
    </div>
  );
}
