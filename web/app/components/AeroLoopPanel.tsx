"use client";

import { useState } from "react";
import { apiUrl } from "../lib/api";
import { fmt } from "../lib/format";
import { useAeroLoop, type AeroRequest } from "../lib/useAeroLoop";
import { useCrewTask, useWorkshop } from "../lib/WorkshopContext";

interface AeroLoopPanelProps {
  /** Null until there is a design and a target altitude to fly it to. */
  request: AeroRequest | null;
  hasDesign: boolean;
}

const signedDegrees = (alpha: number): string => `${alpha > 0 ? "+" : ""}${fmt(alpha, 1)}°`;

/** Runs the flight/CFD loop on the displayed design and shows its rounds and flow pictures. */
export default function AeroLoopPanel({ request, hasDesign }: AeroLoopPanelProps) {
  const { visible } = useWorkshop();
  const { job, starting, error, connectionLost, run } = useAeroLoop(request);
  const [picked, setPicked] = useState<string | null>(null);
  const working = starting || job?.status === "queued" || job?.status === "running";
  const loop = job?.result ?? null;
  const images = job?.images ?? [];
  const image = images.find((row) => row.name === picked) ?? images[0];
  const hasPressure = loop?.baseline.pressure_kpa !== null;
  useCrewTask("aero", { id: job?.id ?? "starting",
    status: connectionLost || error || job?.status === "failed" ? "attention"
      : starting || job?.status === "queued" ? "waiting"
      : job?.status === "running" ? "working"
      : job?.status === "done" ? loop?.converged ? "done" : "attention" : "idle",
    label: connectionLost ? "接続が途切れたため、解析の状態確認を待っています"
      : error || job?.status === "failed" ? "流体解析を止めて、エラーの確認を待っています"
      : starting || job?.status === "queued" ? "資料を持って、流体解析の順番を待っています"
      : job?.status === "running" ? "流れと飛行の計算を点検中"
      : loop?.converged ? "流体解析が終了しました。結果を確認できます" : "収束は未確認です。結果の見直しを待っています" });
  return <section className="wb-detail wb-aero" aria-label="流体解析">
    <h2>流体解析</h2>
    <p className="wb-note">表示中の案について、飛行計算と流体計算を交互に回し、抗力係数の変化を確かめます。ボトルは圧力を設計値以下の範囲で選び直します。元の案そのものは変えません。</p>
    <button type="button" className="btn btn-primary" disabled={!request || working} onClick={() => void run()}>
      {working ? "流体解析を実行中…" : "流体解析を実行"}
    </button>
    {!hasDesign ? <p className="wb-note">設計案が届くと実行できます。</p>
      : !request ? <p className="wb-note">要求の目標高度が分からないため、実行できません。</p> : null}
    {job?.status === "queued" ? <p className="wb-case-tag" role="status">順番を待っています</p> : null}
    {connectionLost ? <p className="wb-note" role="status">接続が途切れました。解析の現在の状態は未確認です。自動で再接続を試みています。</p> : null}
    {error ? <p role="alert" className="wb-error">{error}</p> : null}
    {job?.error && !error ? <p role="alert" className="wb-error">{job.error}</p> : null}
    <div className="backscreen">
      {image ? <figure className="wb-flow">
        <div className="wb-flow-picker" role="group" aria-label="迎角">{images.map(row => <button type="button" key={row.name} aria-pressed={row.name === image.name} className={`btn ${row.name === image.name ? "is-active" : ""}`} onClick={() => setPicked(row.name)}>{row.alpha_deg === null ? row.name : `迎角 ${signedDegrees(row.alpha_deg)}`}</button>)}</div>
        <img src={apiUrl(image.url)} alt={image.alpha_deg === null ? `流れの画像 ${image.name}` : `迎角 ${signedDegrees(image.alpha_deg)} の流れの画像`}/>
        <figcaption>{image.speed_mps === null ? image.name : `流速 ${fmt(image.speed_mps, 1)} m/s`}{image.alpha_deg === null ? "" : ` · 迎角 ${signedDegrees(image.alpha_deg)}`}</figcaption>
      </figure> : <p className="backscreen-idle" role="status">
        {connectionLost ? "接続待ち · 解析の現在の状態は未確認です"
          : job?.status === "running" ? `流体解析を実行中 · 経過 ${fmt(job.elapsed_s ?? 0, 0)} 秒`
          : loop ? "この実行には流れの画像がありません。" : "計算した流れの画像がここに映ります"}
      </p>}
      {visible ? <img className="backscreen-crew" src="/workshop/crew.webp" alt=""/> : null}
    </div>
    {loop ? <>
      <p className="wb-case-tag">{loop.converged ? "抗力係数が収束しました" : "抗力係数は収束していません"} · {loop.rounds.length}周 · 計算手段 {loop.rounds.at(-1)?.backend ?? "—"}</p>
      <div className="wb-table-scroll"><table className="wb-table">
        <thead><tr><th>周</th><th>流速 m/s</th><th>抗力係数</th><th>変化率</th><th>安定余裕 cal</th>{hasPressure ? <th>圧力 kPa</th> : null}<th>高度 m</th><th>降下 m/s</th></tr></thead>
        <tbody>{loop.rounds.map(row => <tr key={row.round}>
          <td>{row.round}</td><td>{fmt(row.cfd_speed_mps, 1)}</td><td>{fmt(row.cd, 3)}</td><td>{fmt(row.cd_change_frac * 100, 1)}%</td>
          <td>{row.static_margin_cal === null ? "—" : fmt(row.static_margin_cal, 2)}</td>{hasPressure ? <td>{fmt(row.pressure_kpa ?? Number.NaN, 0)}</td> : null}<td>{fmt(row.apogee_m, 2)}</td><td>{fmt(row.descent_speed_mps, 2)}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="wb-note">機体の形は容量から決めた代表形状で、部品のフィンの寸法は入っていません。この表の安定余裕は、右の欄の値と一致しないことがあります。</p>
      {loop.dispersion ? <p className="wb-note">更新後の案の条件別試行: {loop.dispersion.passes} / {loop.dispersion.n}（{fmt(loop.dispersion.success_rate * 100, 1)}%）。</p> : null}
      <p className="wb-note">元の案の{loop.baseline.pressure_kpa === null ? "" : `圧力は${fmt(loop.baseline.pressure_kpa, 0)} kPa、`}抗力係数は{loop.baseline.cd === null ? "既定値" : fmt(loop.baseline.cd, 3)}です。</p>
      {loop.notes.length > 0 ? <ul className="wb-limitations">{loop.notes.map(text => <li key={text}>{text}</li>)}</ul> : null}
    </> : null}
  </section>;
}
