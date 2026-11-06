import type { CSSProperties } from "react";

const PATHS: Record<string, string> = {
  brief: "M8 4H5v17h14V4h-3M9 2h6v5H9zM8 11h8M8 15h8",
  design: "m12 2 9 5v10l-9 5-9-5V7zm-9 5 9 5 9-5M12 12v10",
  analysis: "M3 7h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 17h6",
  compare: "M12 3v18M3 7h18M6 7l-4 8h8zm12 0-4 8h8M7 21h10",
  assembly: "m14 6 4 4M3 21l9-9M15 3a6 6 0 0 0-5 8L2 19l3 3 8-8a6 6 0 0 0 8-8l-4 4-3-3 4-4z",
  exports: "M4 2h11l5 5v15H4zM14 2v6h6M8 12h8M8 16h8",
  library: "M3 3h6v18H3zM10 3h5v18h-5zm7 1 4-1 4 17-4 1z",
  home: "m2 11 10-9 10 9M5 9v12h5v-7h4v7h5V9",
  settings: "m10 2-.7 3-2 .8-2.6-1.5-2 3.4L5 10v2L2.7 14l2 3.4 2.6-1.5 2 .8.7 3h4l.7-3 2-.8 2.6 1.5 2-3.4-2.3-2v-2l2.3-2.3-2-3.4-2.6 1.5-2-.8L14 2zM15.5 11a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0",
  history: "M3 10a9 9 0 1 1 1 7M3 4v6h6M12 6v6l4 2",
  chat: "M3 3h18v14H9l-6 4zM7 7h10M7 11h7",
  play: "m8 4 12 8-12 8z", pause: "M8 4v16M16 4v16",
  download: "M12 2v13m-5-5 5 5 5-5M3 16v6h18v-6",
  expand: "M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6",
  check: "m4 12 5 5L20 6", info: "M12 11v7M12 6v1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  arrow: "M4 12h16m-6-6 6 6-6 6", close: "m5 5 14 14M5 19 19 5",
};

export default function WorkshopIcon({ name, size = 20, style }: { name: string; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={PATHS[name] ?? PATHS.design}/></svg>;
}
