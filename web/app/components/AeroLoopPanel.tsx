"use client";

import { useState } from "react";
import { apiUrl } from "../lib/api";
import { fmt } from "../lib/format";
import type { WorkbenchProject } from "../lib/workbench";

interface AeroLoopPanelProps {
  project: WorkbenchProject | null;
  running: boolean;
  working: boolean;
  elapsed: number;
  onRun: () => void;
}

const signedDegrees = (alpha: number): string => `${alpha > 0 ? "+" : ""}${fmt(alpha, 1)}°`;

/** Runs the flight/CFD loop on the confirmed design and shows its rounds and flow pictures. */
export default function AeroLoopPanel({ project, running, working, elapsed, onRun }: AeroLoopPanelProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const loop = project?.aero_loop ?? null;
  const images = project?.aero_images ?? [];
  const image = images.find((row) => row.name === picked) ?? images[0];
  return <section className="wb-aero" aria-label="流体解析">
    <h3>流体解析</h3>
    <p className="wb-note">確認済みの案について、飛行計算と流体計算を交互に回し、抗力係数と圧力の変化を確かめます。採用案そのものは変えません。</p>
    <button className="wb-primary" disabled={!project?.confirmed || working} onClick={onRun}>流体解析を実行</button>
    {!project?.confirmed ? <p className="wb-note">採用案の独立確認を通過すると実行できます。</p> : null}
    {running ? <p className="wb-case-tag" role="status">流体解析を実行中 · 経過 {elapsed}秒</p> : null}
    {loop ? <>
      <p className="wb-case-tag">{loop.converged ? "抗力係数が収束しました" : "抗力係数は収束していません"} · {loop.rounds.length}周 · 計算手段 {loop.rounds.at(-1)?.backend ?? "—"}</p>
      <div className="wb-table-scroll"><table className="wb-table">
        <thead><tr><th>周</th><th>流速 m/s</th><th>抗力係数</th><th>変化率</th><th>安定余裕 cal</th><th>圧力 kPa</th><th>高度 m</th><th>降下 m/s</th></tr></thead>
        <tbody>{loop.rounds.map(row => <tr key={row.round}>
          <td>{row.round}</td><td>{fmt(row.cfd_speed_mps, 1)}</td><td>{fmt(row.cd, 3)}</td><td>{fmt(row.cd_change_frac * 100, 1)}%</td>
          <td>{row.static_margin_cal === null ? "—" : fmt(row.static_margin_cal, 2)}</td><td>{fmt(row.pressure_kpa, 0)}</td><td>{fmt(row.apogee_m, 2)}</td><td>{fmt(row.descent_speed_mps, 2)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="wb-note">更新後の案の条件別試行: {loop.dispersion.passes} / {loop.dispersion.n}（{fmt(loop.dispersion.success_rate * 100, 1)}%）。元の案の圧力は{fmt(loop.baseline.pressure_kpa, 0)} kPa、抗力係数は{loop.baseline.cd === null ? "既定値" : fmt(loop.baseline.cd, 3)}です。</p>
      {loop.notes.length > 0 ? <ul className="wb-limitations">{loop.notes.map(text => <li key={text}>{text}</li>)}</ul> : null}
      {image ? <figure className="wb-flow">
        <div className="wb-flow-picker" role="group" aria-label="迎角">{images.map(row => <button key={row.name} aria-pressed={row.name === image.name} className={row.name === image.name ? "is-active" : ""} onClick={() => setPicked(row.name)}>{row.alpha_deg === null ? row.name : `迎角 ${signedDegrees(row.alpha_deg)}`}</button>)}</div>
        <img src={apiUrl(image.url)} alt={image.alpha_deg === null ? `流れの画像 ${image.name}` : `迎角 ${signedDegrees(image.alpha_deg)} の流れの画像`}/>
        <figcaption>{image.speed_mps === null ? image.name : `流速 ${fmt(image.speed_mps, 1)} m/s`}{image.alpha_deg === null ? "" : ` · 迎角 ${signedDegrees(image.alpha_deg)}`}</figcaption>
      </figure> : <p className="wb-note">この計算手段は流れの画像を残しません。</p>}
    </> : null}
  </section>;
}
