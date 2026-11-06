"use client";

import { useState } from "react";
import { apiUrl } from "../lib/api";
import type { RuntimeStatus, WorkbenchProject } from "../lib/workbench";

export default function WorkbenchFilms({ project, runtime, working, act }: {
  project: WorkbenchProject | null; runtime: RuntimeStatus | null; working: boolean;
  act: (operation: string, extra?: Record<string, unknown>) => Promise<void>;
}) {
  const [style, setStyle] = useState<"engineering" | "photographic">("photographic");
  const photographic = style === "photographic";
  const plan = photographic ? project?.photographic_video_plan : project?.video_plan;
  const files = project?.files ?? [];
  const kind = photographic ? "photographic_video" : "video";
  const outputs = files.filter(f => f.name.endsWith(".mp4") &&
    (f.kind === kind || (!photographic && f.kind === "ai_video")));
  const available = !photographic || runtime?.photographic?.available === true;
  const production = files.some(f => f.kind === "production");
  return <div className="wb-detail">
    <p className="wb-eyebrow">FILM / DESIGN & FLIGHT</p>
    <h2>設計を説明し、飛行を再生する</h2>
    <label htmlFor="film-style">映像の仕上げ</label>
    <select id="film-style" value={style} disabled={working} onChange={e => {
      if (e.target.value === "engineering" || e.target.value === "photographic") setStyle(e.target.value);
    }}>
      <option value="photographic">写真調 / 1080p・設計16秒・飛行12秒</option>
      <option value="engineering">簡易CG / 各4秒・短時間で確認</option>
    </select>
    <p className="wb-note">{photographic
      ? "写真由来の照明・地面、透明なPET、地上カメラを使い、この設計の寸法と計算軌跡から制作します。実物の撮影映像ではありません。描画には時間がかかります。音声なし。"
      : "寸法と飛行軌跡から簡易CGを作ります。音声なし。"}</p>
    {photographic && !available ? <p role="status" className="wb-note">保存済みの写真素材を確認できません。素材を設定すると写真調で制作できます。</p> : null}
    <div className="wb-video-actions">
      <button disabled={working || !production || !available || Boolean(plan)} onClick={() => void act("video-plan", { local: false, style })}>標準のショット構成を確認</button>
      <button disabled={working || !production || !available || !runtime?.ollama.models.length || plan?.status === "rendered"} onClick={() => void act("video-plan", { local: true, style })}>ローカルLLMで演出を提案</button>
    </div>
    {plan ? <div className="wb-shot-plan">
      <p><b>設計説明</b> {plan.design_caption}</p><p><b>打ち上げCG</b> {plan.launch_caption}</p>
      <small>{plan.width} × {plan.height} / {plan.fps} fps / 設計{(plan.design_frames ?? plan.frames_per_clip) / plan.fps}秒・飛行{(plan.launch_frames ?? plan.frames_per_clip) / plan.fps}秒 · {plan.model}</small>
    </div> : null}
    <button className="wb-primary" disabled={working || !available || plan?.status !== "planned"} onClick={() => void act("render-video", { style })}>この構成で2本の映像を制作</button>
    {outputs.map(f => <figure className="wb-video" key={f.key}>
      <figcaption>{f.name === "design-explanation.mp4" ? "設計説明" : f.name === "launch-cg.mp4" ? "飛行軌跡のCG再生" : "AI映像 / 形状は要確認"}{photographic ? " / 写真調" : ""}</figcaption>
      <video aria-label={f.name === "design-explanation.mp4" ? "設計説明映像" : "飛行軌跡映像"} controls preload="metadata" src={apiUrl(f.url)}/>
      <a href={apiUrl(f.url)} download>MP4を保存 ↗</a>
    </figure>)}
    {photographic ? <p className="wb-note">写真素材: Poly Haven（CC0）。検査記録・素材の出典も保存できます。</p> : <div className="wb-wan">
      <h3>Wan2.2で映像ショットを生成</h3>
      <p className="wb-note">参照フレームと確認したプロンプトを、このPCのComfyUIへ送ります。設計寸法と軌跡の忠実性は保証されません。</p>
      <button disabled={working || !runtime?.comfyui.available || plan?.status !== "rendered" || plan.wan_status !== "not_submitted"} onClick={() => void act("wan")}>参照フレームから生成</button>
      {plan?.wan_status === "queued" || plan?.wan_status === "running" ? <button disabled={working} onClick={() => void act("wan-result")}>生成結果を確認</button> : null}
      <span className="wb-note">{plan?.wan_status}</span>
    </div>}
    <div className="wb-file-list">{files.filter(f => f.kind === kind && ["verification.json", "appearance-sources.json", "scene-source.json", "rendered-trajectory.csv"].includes(f.name)).map(f => <a key={f.key} href={apiUrl(f.url)} download>{f.name} ↗</a>)}</div>
  </div>;
}
