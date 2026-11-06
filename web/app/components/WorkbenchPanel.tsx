"use client";

import { useState } from "react";
import { apiUrl } from "../lib/api";
import { CHECK_LABELS, useWorkbench } from "../lib/workbench";
import RocketViewport from "./RocketViewport";
import ReferenceLibrary from "./ReferenceLibrary";
import PrintExports from "./PrintExports";
import AnalysisEvidence from "./AnalysisEvidence";
import SimulationPanel from "./SimulationPanel";

const METHOD: Record<string, string> = { component: "構成・重心・振動", flight: "飛行と抗力", screen: "条件を変えた試行", confirm: "採用案の独立確認" };
const VARIANT: Record<string, string> = { carton_plain: "紙製フィン / 基準", carton_damped: "紙製フィン / 緩衝材変更", carton_wide: "紙製フィン / 幅を拡大", pp_damped: "PP製フィン / 緩衝材変更", pp_wide: "PP製フィン / 幅を拡大" };

export default function WorkbenchPanel({ onOpenDesign }: { onOpenDesign: () => void }) {
  const { project, runtime, busy, error, elapsed, act } = useWorkbench();
  const [tab, setTab] = useState("assembly");
  const [choice, setChoice] = useState("");
  const [reason, setReason] = useState("");
  const [viewed, setViewed] = useState<{ projectId: string; index: number; seenCount: number } | null>(null);
  const pinned = viewed?.projectId === project?.id ? viewed : null;
  const working = Boolean(busy || project?.active);
  const selected = project?.options.find(o => o.id === choice) ?? project?.options.find(o => o.id === project.proposal?.id) ?? project?.options.find(o => o.id === project.recommendation);
  const last = pinned ? project?.history[pinned.index] : project?.history.at(-1);
  const files = project?.files ?? [];
  const metrics = pinned ? last?.chosen.startsWith("flight/") ? last.result : null : [...(project?.history ?? [])].reverse().find(row => row.chosen.startsWith("flight/"))?.result;
  const confirmation = last?.chosen.startsWith("confirm/") ? last.result : null;
  const plan = project?.video_plan;
  const caption = working ? busy === "aero-loop" || project?.active?.name === "aero_loop" ? "流体解析を実行中" : project?.active?.name.startsWith("component/") ? "構成・重心・振動を解析中" : project?.active?.name.startsWith("flight/") ? "飛行軌跡を計算中" : busy === "print-package" ? "部品を生成・検査・スライス中" : busy === "render-video" ? "設計説明と打ち上げCGを制作中" : "工程を実行中" : project?.confirmed ? "採用案の解析を確認しました" : "次の工程を選んでください";
  return <main className="wb-shell">
    <header className="wb-header"><div className="wb-wordmark"><span className="wb-logo" aria-hidden="true">↟</span>RocketWright<span className="wb-divider">/</span><span className="wb-project-name">ペットボトル / 製作設計</span></div><div className="wb-header-actions"><button onClick={onOpenDesign}>自由な要求から設計</button><button disabled={working} onClick={() => { setChoice(""); setReason(""); void act("create"); }}>新しい設計</button></div></header>
    <div className="wb-body">
      <aside className="wb-left">
        <div className="wb-dock-title">設計条件<span>MISSION</span></div>
        <dl className="wb-conditions"><div><dt>目標高度</dt><dd>20 <small>m</small></dd></div><div><dt>搭載質量</dt><dd>60 <small>g</small></dd></div><div><dt>ボトル容量</dt><dd>1.5 <small>L</small></dd></div><div><dt>材料予算</dt><dd>3,000 <small>円</small></dd></div><div><dt>解析の探索上限</dt><dd>{project?.workshop.pressure_ceiling_kpa ?? 400} <small>kPa</small></dd></div></dl>
        <p className="wb-note">卵の回収を想定した探索例。購入候補・寸法・発射台の条件を仮定し、工程ごとに確かめます。探索上限は計算用の範囲で、機材の許容値は未確認です。</p>
        <div className="wb-dock-title">機体の構成<span>ASSEMBLY</span></div>
        <ul className="wb-tree"><li>◈ 機体全体<ul><li>ノーズ・搭載室</li><li>回収装置</li><li>市販PETボトル</li><li>フィン・取付部</li></ul></li></ul>
        {project?.plan ? <><div className="wb-dock-title">確認結果<span>CHECKS</span></div><ul className="wb-checks">{Object.entries(project.plan.checks).map(([key, passed]) => <li key={key}><span className={passed ? "wb-pass" : "wb-fail"}>{passed ? "✓" : "×"}</span>{CHECK_LABELS[key] ?? key}</li>)}</ul><p className="wb-note">計算上の条件判定。実物の保持・寸法・回収は製作後に確認します。</p></> : null}
        <div className="wb-runtime"><span className={runtime?.comfyui.available ? "wb-online" : ""}/>ComfyUI {runtime?.comfyui.available ? runtime.comfyui.version : "未接続"}<br/><span className={runtime?.ollama.models.length ? "wb-online" : ""}/>Local LLM {runtime?.ollama.models.length ? "接続済み" : "未接続"}</div>
      </aside>
      <section className="wb-center" aria-label="設計と成果物">
        <p className="wb-mobile-mission">探索例: 高度20 m · 搭載60 g · 1.5 L · 材料予算3,000円</p>
        <nav className="wb-tabs" aria-label="設計の表示">{[["assembly", "機体"], ["analysis", "解析"], ["simulation", "シミュレーション"], ["files", "製作ファイル"], ["video", "動画"], ["library", "設計例と資料"]].map(([id, label]) => <button key={id} aria-pressed={tab === id} className={tab === id ? "is-active" : ""} onClick={() => setTab(id)}>{label}{id === "files" && files.length > 0 ? <span>{files.filter(f => f.kind === "production").length}</span> : null}</button>)}</nav>
        <div className="wb-main-content">
          {tab === "assembly" ? <RocketViewport project={project} working={working}/> : null}
          {tab === "library" ? <ReferenceLibrary/> : null}
          {tab === "analysis" ? <AnalysisEvidence project={project} viewedIndex={pinned?.index ?? null} unseen={pinned ? (project?.history.length ?? 0) - pinned.seenCount : 0} onLatest={() => setViewed(null)}/> : null}
          {tab === "simulation" ? <SimulationPanel project={project} busy={busy} working={working} elapsed={elapsed} error={error} onRunAero={() => void act("aero-loop")}/> : null}
          {tab === "files" ? <div className="wb-detail"><p className="wb-eyebrow">PRODUCTION / FROZEN DESIGN</p><h2>同じ設計から、製作へ</h2><p className="wb-note">組立配置図、原寸フィン型紙、組立手順PDF、部品表、購入計画、搭載部カラーとフィン位置決め治具のSTL。以下で、同じ設計から機種別の印刷データも生成できます。</p><button className="wb-primary" disabled={!project?.confirmed || working || files.some(f => f.kind === "production")} onClick={() => void act("exports")}>確認した案の製作ファイルを生成</button><PrintExports files={files} manifest={project?.print_package} disabled={working || !files.some(f => f.kind === "production")} onGenerate={() => void act("print-package")}/><button disabled={working || !files.some(f => f.kind === "production") || files.some(f => f.kind === "manual")} onClick={() => void act("assembly-pdf")}>組立手順PDFを生成</button><div className="wb-file-list">{files.filter(f => f.kind === "production" || f.kind === "manual").map(f => <a key={f.key} href={apiUrl(f.url)} download><span>{f.name}</span><small>{f.name.split(".").at(-1)?.toUpperCase()} ↗</small></a>)}</div></div> : null}
          {tab === "video" ? <div className="wb-detail"><p className="wb-eyebrow">FILM / DESIGN & FLIGHT</p><h2>設計を説明し、飛行を再生する</h2><p className="wb-note">寸法と飛行軌跡からBlender映像を作ります。Wan2.2の映像は演出用の別ショットとして保存します。音声なし。</p><div className="wb-video-actions"><button disabled={working || !files.length || Boolean(plan)} onClick={() => void act("video-plan", { local: false })}>標準のショット構成を確認</button><button disabled={working || !files.length || !runtime?.ollama.models.length || plan?.status === "rendered"} onClick={() => void act("video-plan", { local: true })}>ローカルLLMで演出を提案</button></div>{plan ? <div className="wb-shot-plan"><p><b>設計説明</b> {plan.design_caption}</p><p><b>打ち上げCG</b> {plan.launch_caption}</p><small>{plan.width} × {plan.height} / {plan.fps} fps / 各{plan.frames_per_clip / plan.fps}秒 · {plan.model}</small></div> : null}<button className="wb-primary" disabled={working || plan?.status !== "planned"} onClick={() => void act("render-video")}>この構成で2本の映像を制作</button>{files.filter(f => f.name.endsWith(".mp4")).map(f => <figure className="wb-video" key={f.key}><figcaption>{f.name === "design-explanation.mp4" ? "設計説明" : f.name === "launch-cg.mp4" ? "飛行軌跡のCG再生" : "AI映像 / 形状は要確認"}</figcaption><video controls preload="metadata" src={apiUrl(f.url)}/><a href={apiUrl(f.url)} download>MP4を保存 ↗</a></figure>)}<div className="wb-wan"><h3>Wan2.2で映像ショットを生成</h3><p className="wb-note">CGの参照フレームと確認したプロンプトを、このPCのComfyUIへ送ります。設計寸法と軌跡の忠実性は保証されません。</p><button disabled={working || !runtime?.comfyui.available || plan?.status !== "rendered" || plan.wan_status !== "not_submitted"} onClick={() => void act("wan")}>参照フレームから生成</button>{plan?.wan_status === "queued" || plan?.wan_status === "running" ? <button disabled={working} onClick={() => void act("wan-result")}>生成結果を確認</button> : null}<span className="wb-note">{plan?.wan_status}</span></div></div> : null}
        </div>
        <div className="wb-metric-strip"><div><small>{pinned ? "表示中の公称高度" : "最新の公称高度"}</small><strong>{typeof metrics?.apogee_m === "number" ? `${metrics.apogee_m.toFixed(2)} m` : "—"}</strong></div><div><small>定常降下速度</small><strong>{typeof metrics?.descent_speed_mps === "number" ? `${metrics.descent_speed_mps.toFixed(2)} m/s` : "—"}</strong></div><div><small>独立確認の通過数</small><strong>{confirmation ? `${String(confirmation.passes)} / ${String(confirmation.n)}` : "—"}</strong></div><div><small>工程</small><strong>{project?.history.length ?? 0} <span>解析記録</span></strong></div></div>
      </section>
      <aside className="wb-right">
        <div className="wb-dock-title">設計を進める<span>WORKFLOW</span></div>
        <div className="wb-progress" role="status" aria-live="polite"><span className={working ? "wb-working-dot" : "wb-idle-dot"}/><div><b>{caption}</b>{working ? <small>経過 {elapsed}秒 · 残り時間は計測中</small> : <small>工程ごとに結果を確認して進めます</small>}</div></div>
        {error || project?.error ? <p className="wb-error" role="alert">{error || project?.error}</p> : null}
        {!project ? <div className="wb-start"><p>まず構成、重心と振動を確認し、飛行解析へ進みます。</p><button className="wb-primary" disabled={working} onClick={() => void act("create")}>この条件で設計を開始</button></div> : null}
        {project?.options.length ? <div className="wb-next"><label htmlFor="analysis-choice">次に確かめること</label><select id="analysis-choice" value={selected?.id ?? ""} disabled={working} onChange={e => setChoice(e.target.value)}>{project.options.map(o => <option key={o.id} value={o.id}>{o.label} / {o.architecture} / {VARIANT[o.variant] ?? o.variant} / {o.pressure_kpa} kPa / {o.fill_pct}%</option>)}</select>{selected ? <div className="wb-selection"><b>{METHOD[selected.method]}</b><span>{selected.architecture} · {VARIANT[selected.variant] ?? selected.variant}</span><small>{selected.pressure_kpa} kPa · 充填率 {selected.fill_pct}% · 探索用の仮定</small></div> : null}{project.proposal ? <p className="wb-note">LLMの提案: {project.proposal.reason}</p> : null}<label htmlFor="analysis-reason">この工程を選ぶ理由</label><textarea id="analysis-reason" rows={2} placeholder="任意で補足できます" value={reason} onChange={e => setReason(e.target.value)} disabled={working}/><button className="wb-primary" disabled={working || !selected} onClick={() => { void act("steps", { id: selected?.id, reason: reason.trim() || (selected?.id === project.proposal?.id ? project.proposal?.reason : null) || "現在の構成に必要な次の解析を実行し、結果を確認する。" }); setChoice(""); setReason(""); }}>選んだ工程を実行</button><button disabled={working || !runtime?.ollama.models.length} onClick={() => void act("proposal")}>ローカルLLMに次の工程を相談</button></div> : null}
        {project?.confirmed ? <div className="wb-confirmed"><span>✓</span><h3>採用案の解析を確認しました</h3><p>現物の測定と製作に向けたファイルを作れます。</p><button className="wb-primary" onClick={() => setTab("files")}>製作ファイルへ進む</button></div> : null}
        <div className="wb-history"><h3>工程の記録</h3>{project?.history.length ? [...project.history].reverse().map((row, i) => <button key={row.chosen} aria-pressed={pinned?.index === project.history.length - i - 1} onClick={() => { setViewed({ projectId: project.id, index: project.history.length - i - 1, seenCount: project.history.length }); setTab("analysis"); }}><span>{String(project.history.length - i).padStart(2, "0")}</span><div><b>{METHOD[row.chosen.split("/")[0]]}</b><small>{row.chosen.split("/")[1]} · {VARIANT[row.chosen.split("/")[5]] ?? row.chosen.split("/")[5]}</small></div><span>↗</span></button>) : <p className="wb-note">実行した条件と結果を保存します。</p>}</div>
      </aside>
    </div>
    <footer className="wb-statusbar"><span><i className={working ? "wb-online" : ""}/>{working ? "処理中" : "待機中"}</span><span>{project ? `保存済み · revision ${project.revision}` : "新規プロジェクト"}</span><span>数値解析 / 実機の確認前</span></footer>
  </main>;
}
