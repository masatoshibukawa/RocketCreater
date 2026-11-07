"use client";

import { fmt } from "../lib/format";
import type { AeroLive } from "../lib/useAeroLoop";
import FlowVideo from "./FlowVideo";

const WIDTH = 320;
const HEIGHT = 150;
const PAD = 6;
const SERIES_COLORS = ["#6fb6ff", "#f2b632", "#5fd38d", "#ff8a7a", "#c6a7ff", "#7ee0e0"];

function path(points: [number, number][], xMax: number, yMin: number, yMax: number): string {
  const span = yMax - yMin || 1;
  return points.map(([x, y], i) => {
    const px = PAD + (x / xMax) * (WIDTH - 2 * PAD);
    const py = HEIGHT - PAD - ((y - yMin) / span) * (HEIGHT - 2 * PAD);
    return `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`;
  }).join(" ");
}

/** Residuals on a log axis: the lines falling is the solver converging. */
function ResidualChart({ residuals, xMax }: { residuals: AeroLive["residuals"]; xMax: number }) {
  const logged = Object.entries(residuals).map(([name, points]) => ({
    name, points: points.filter(([, y]) => y > 0).map(([x, y]): [number, number] => [x, Math.log10(y)]),
  }));
  const values = logged.flatMap((s) => s.points.map(([, y]) => y));
  if (values.length === 0) return null;
  const yMin = Math.floor(Math.min(...values));
  const yMax = Math.ceil(Math.max(...values));
  return <section className="aero-live-chart">
    <h3>残差（下がるほど計算が落ち着く）</h3>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="残差の推移" preserveAspectRatio="none">
      {logged.map((s, i) => <path key={s.name} d={path(s.points, xMax, yMin, yMax)} fill="none" stroke={SERIES_COLORS[i % SERIES_COLORS.length]} strokeWidth="1.6" vectorEffect="non-scaling-stroke"/>)}
    </svg>
    <div className="aero-live-legend">{logged.map((s, i) => <span key={s.name}><i style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }}/>{s.name}</span>)}<span>10^{yMin} 〜 10^{yMax}</span></div>
  </section>;
}

function ForceChart({ points, xMax }: { points: [number, number][]; xMax: number }) {
  if (points.length === 0) return null;
  // The first iterations swing widely; the scale follows the part that tells the result.
  const settled = points.slice(Math.floor(points.length / 4)).map(([, y]) => y);
  const yMin = Math.min(...settled);
  const yMax = Math.max(...settled);
  const shown = points.filter(([, y]) => y >= yMin - (yMax - yMin) && y <= yMax + (yMax - yMin));
  return <section className="aero-live-chart">
    <h3>機体にかかる軸方向の力</h3>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="軸方向の力の推移" preserveAspectRatio="none">
      <path d={path(shown, xMax, yMin - (yMax - yMin), yMax + (yMax - yMin))} fill="none" stroke="#f2b632" strokeWidth="1.6" vectorEffect="non-scaling-stroke"/>
    </svg>
    <div className="aero-live-legend"><span>今の値 {fmt(points[points.length - 1][1], 2)} N</span></div>
  </section>;
}

/** The solver at work, from the files it writes: no number here is estimated. */
export default function AeroLiveView({ live }: { live: AeroLive }) {
  const total = live.iterations_total ?? 0;
  const xMax = Math.max(total, live.iteration ?? 1, 1);
  const stage = live.stage === "solve"
    ? `計算 ${live.case_index ?? "?"} / ${live.case_total ?? "?"} ケース目`
    : live.stage === "mesh" ? "格子を作成中" : "準備中";
  return <div className="aero-live" role="status">
    <div className="aero-live-head">
      <span>{stage}{live.speed_mps === null ? "" : ` · 流速 ${fmt(live.speed_mps, 0)} m/s · 迎角 ${fmt(live.alpha_deg ?? 0, 0)}°`}</span>
      {live.cells === null ? null : <small>格子 {live.cells.toLocaleString("ja-JP")} セル</small>}
    </div>
    {live.iteration !== null && total > 0 ? <>
      <div className="aero-live-bar"><span style={{ width: `${Math.min(100, (live.iteration / total) * 100)}%` }}/></div>
      <p className="aero-live-note">反復 {live.iteration} / 上限 {total}（収束すると早く終わります）</p>
    </> : null}
    <div className={live.frames.length > 0 ? "aero-live-main" : undefined}>
      <FlowVideo frames={live.frames.map((frame) => ({ ...frame, url: `/aero/loop/live/${frame.name}` }))} loop={false}/>
      <div className="aero-live-charts">
        <ResidualChart residuals={live.residuals} xMax={xMax}/>
        <ForceChart points={live.axial_force_n} xMax={xMax}/>
      </div>
    </div>
    {live.finished.length > 0 ? <p className="aero-live-note">終わったケース：{live.finished.map((c) => `迎角 ${fmt(c.alpha_deg, 0)}° の抗力係数 ${fmt(c.cd, 3)}`).join("、")}</p> : null}
  </div>;
}
