"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import AeroLoopPanel from "./components/AeroLoopPanel";
import FlightPlayer from "./components/FlightPlayer";
import BomPanel from "./components/BomPanel";
import ChatPanel from "./components/ChatPanel";
import CostPanel from "./components/CostPanel";
import DetailsPanel from "./components/DetailsPanel";
import DrawingPanel from "./components/DrawingPanel";
import FlightChart from "./components/FlightChart";
import ModelViewer from "./components/ModelViewer";
import ProductionPanel from "./components/ProductionPanel";
import ReferenceLibrary from "./components/ReferenceLibrary";
import ResultPanel from "./components/ResultPanel";
import StatusStrip from "./components/StatusStrip";
import WorkshopCrew from "./components/WorkshopCrew";
import WorkshopIcon from "./components/WorkshopIcon";
import DesignComparison from "./components/DesignComparison";
import VideoOutputs from "./components/VideoOutputs";
import { WorkshopProvider, useCrewTask, useWorkshop } from "./lib/WorkshopContext";
import { WORKSHOP_STAGES, stageLabel, type WorkshopStage, type AnalysisView, type OutputView } from "./lib/workshopNavigation";
import { designCrewTask } from "./lib/workshopActivity";
import { apiUrl, designKey, exportInfoFromEvents, exportsForDesign, requestKey, type DesignPackage, type DesignPackageRequest } from "./lib/api";
import { fmt } from "./lib/format";
import { certificationNotes, selectDisplayedDesign } from "./lib/designState";
import { carriesParachute } from "./lib/flightPlayback";
import { useDesignStream } from "./lib/useDesignStream";
import { useDesignSummary } from "./lib/useDesignSummary";
import type { AeroRequest } from "./lib/useAeroLoop";
import { isOrbital, TIER_LABEL, type DispersionResult, type DisplayedDesign, type LandingPoint, type TracePoint } from "./lib/types";

const NO_TRACE: TracePoint[] = [];
const NO_METRICS: Record<string, number> = {};

export default function Home() {
  return <WorkshopProvider><DesignScreen/></WorkshopProvider>;
}

function DesignScreen() {
  const [stage, setStage] = useState<WorkshopStage>("brief");
  const [rightTab, setRightTab] = useState<"explain" | "history" | "consult">("consult");
  const [analysisView, setAnalysisView] = useState<AnalysisView>("aero");
  const [outputView, setOutputView] = useState<OutputView>("production");
  const [modelView, setModelView] = useState<"model" | "drawing">("model");
  const [frameRequest, setFrameRequest] = useState(0);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const settings = useRef<HTMLDialogElement>(null);
  const inspector = useRef<HTMLElement>(null);
  const { task, visible, setVisible, paused, setPaused, reduced } = useWorkshop();
  const [generated, setGenerated] = useState<{ key: string; package: DesignPackage } | null>(null);
  const [printed, setPrinted] = useState<{ key: string; files: { name: string; url: string }[] } | null>(null);
  const stream = useDesignStream();
  useCrewTask("design", designCrewTask(stream));
  const { start, answer, stop, reset } = stream;
  // Manual pick from 詳細 (attempt log / cards / reviews); null = follow the display rule.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Displayed design: the user's pick when it resolves, else the latest passing candidate,
  // else the latest attempt, else the reference seed (designState.selectDisplayedDesign).
  // Part-space attempts (auto_design / design_from_parts) carry the resolved design.
  const displayed = useMemo<DisplayedDesign | null>(() => {
    if (selectedId !== null) {
      const c = stream.candidates.find((x) => x.source_id === selectedId);
      if (c) return { design: c.design, sourceId: c.source_id, origin: "candidate" };
      const a = stream.attempts.find((x) => x.id === selectedId);
      if (a && a.design !== null) {
        return { design: a.design, sourceId: a.id, origin: a.seededFrom !== null ? "seed" : "attempt" };
      }
    }
    return selectDisplayedDesign(stream);
  }, [selectedId, stream]);

  const displayedId = displayed?.sourceId ?? null;
  const displayedAttempt = useMemo(
    () => (displayedId ? stream.attempts.find((a) => a.id === displayedId) : undefined),
    [displayedId, stream.attempts],
  );
  // auto_design and reference seeds leave the time series out of their event, so a design shown
  // from one of them flies on the trace of an attempt that simulated the very same design.
  const flight = useMemo(() => {
    if (displayedAttempt?.result?.trace.length || !displayed) return displayedAttempt?.result;
    const key = designKey(displayed.design);
    return stream.attempts.find(
      (a) => a.design !== null && a.result?.trace.length && designKey(a.design) === key,
    )?.result;
  }, [displayed, displayedAttempt, stream.attempts]);
  const trace: TracePoint[] = flight?.trace ?? NO_TRACE;
  // Certification / coupler warnings of the displayed build (amber note under the 3D view).
  const notes: string[] = useMemo(
    () => certificationNotes(displayedAttempt?.result?.warnings ?? []),
    [displayedAttempt],
  );
  const fallbackCost = displayedAttempt?.result?.cost_jpy ?? null;

  const landing: LandingPoint | null = useMemo(() => {
    const m = displayedAttempt?.result?.metrics;
    if (!m) return null;
    const east = m.landing_east_m;
    const north = m.landing_north_m;
    return typeof east === "number" && typeof north === "number" ? { east_m: east, north_m: north } : null;
  }, [displayedAttempt]);

  // run_dispersion result of the displayed design; otherwise the latest run.
  const dispersion: DispersionResult | null = useMemo(() => {
    const own = displayedId ? stream.dispersions[displayedId] : undefined;
    return own ?? stream.dispersion;
  }, [displayedId, stream.dispersions, stream.dispersion]);

  // Download maps from export_report / render_drawing results; the BOM CSV for the displayed
  // design when the agent exported it (else any exported BOM, else none).
  const exportInfos = useMemo(() => exportInfoFromEvents(stream.events), [stream.events]);
  const csvUrl: string | null = useMemo(() => {
    if (!displayed) return null;
    const own = exportsForDesign(exportInfos, displayed.design).find((e) => typeof e.download.bom === "string");
    if (own) return own.download.bom;
    const any = exportInfos.find((e) => typeof e.download.bom === "string");
    return any ? any.download.bom : null;
  }, [displayed, exportInfos]);

  // Every attempt that flew this very design, the one on screen first: a trace-only re-run has
  // neither the build nor the margins of the parts attempt, and an estimate_cost candidate no env.
  const sameDesign = useMemo(() => {
    if (!displayed) return [];
    const key = designKey(displayed.design);
    const same = stream.attempts.filter((a) => a.design !== null && designKey(a.design) === key);
    return [...same.filter((a) => a === displayedAttempt), ...same.filter((a) => a !== displayedAttempt)];
  }, [displayed, displayedAttempt, stream.attempts]);
  const build = sameDesign.find((a) => a.build !== null)?.build ?? null;

  // /artifacts/summary for the displayed design (debounced, cached by design JSON).
  const summaryState = useDesignSummary(displayed?.design ?? null, stream.requirement, build);
  const summary = summaryState.summary;

  const tier = stream.tier ?? displayed?.design.tier ?? null;

  // Everything the tools reported for this very design; the attempt on screen has the last word.
  const resultMetrics = useMemo(() => {
    if (!displayed) return NO_METRICS;
    const candidate = stream.candidates.find((c) => c.source_id === displayed.sourceId);
    const flown = [...sameDesign].reverse().map((a) => a.result?.metrics);
    return Object.assign({}, candidate?.metrics, ...flown) as Record<string, number>;
  }, [displayed, sameDesign, stream.candidates]);

  // A failing attempt or a reference seed gets no production data (CLAUDE.md section 1). A seed
  // flew in the reference's own conditions, which the tool inputs do not hold.
  const passed: boolean = useMemo(() => {
    const candidate = stream.candidates.find((c) => c.source_id === displayedId);
    if (candidate?.seededFrom || displayed?.origin === "seed") return false;
    return candidate?.passed ?? displayedAttempt?.result?.success ?? false;
  }, [displayed, displayedId, displayedAttempt, stream.candidates]);

  // Conditions of the run on screen, so that the API repeats what the agent simulated.
  const callEnv = [displayedId, ...sameDesign.map((a) => a.id)]
    .map((id) => (id ? stream.toolInputs[id]?.env : undefined))
    .find((value) => typeof value === "object" && value !== null);
  const env = (callEnv ?? null) as Record<string, unknown> | null;
  const rerun = useMemo(
    () => ({ requirement: stream.requirement, env, seed: dispersion?.seed ?? null, n: dispersion?.n ?? null }),
    [stream.requirement, env, dispersion],
  );
  const packageRequest: DesignPackageRequest | null = useMemo(
    () => (displayed ? { design: displayed.design, build, ...rerun } : null),
    [displayed, build, rerun],
  );
  const aeroRequest: AeroRequest | null = useMemo(() => {
    const target = stream.requirement?.target_altitude_m;
    if (!displayed || typeof target !== "number" || target <= 0) return null;
    return { design: displayed.design, target_altitude_m: target, ...rerun };
  }, [displayed, stream.requirement, rerun]);

  const handleStart = useCallback(
    (text: string, seed: number | null) => {
      setSelectedId(null);
      setStage("design");
      void start(text, seed);
    },
    [start],
  );
  const handleAnswer = useCallback(
    (text: string) => {
      setSelectedId(null);
      void answer(text);
    },
    [answer],
  );
  const handleReset = useCallback(() => {
    setSelectedId(null);
    reset();
  }, [reset]);

  const packageKey = packageRequest ? requestKey(packageRequest) : "";
  const currentPackage = generated?.key === packageKey ? generated.package : null;
  const handleGenerated = useCallback((value: DesignPackage) => setGenerated({ key: packageKey, package: value }), [packageKey]);
  const printKey = displayed ? designKey(displayed.design) : "";
  const printFiles = printed?.key === printKey ? printed.files : [];
  const handlePrintGenerated = useCallback((files: { name: string; url: string }[]) => setPrinted({ key: printKey, files }), [printKey]);
  const viewingReferenceFilm = stage === "exports" && outputView === "video";
  function closeTargets() { setLeftOpen(false); document.getElementById("target-toggle")?.focus(); }
  function toggleTargets() {
    if (leftOpen) { closeTargets(); return; }
    setLeftOpen(true);
    window.requestAnimationFrame(() => document.getElementById("workshop-targets")?.focus());
  }
  const chooseStage = (next: WorkshopStage) => {
    setStage(next); setLeftOpen(false); setExpanded(false);
    setRightTab(next === "brief" ? "consult" : "explain");
  };
  const hasModel = stage === "brief" || stage === "design" || stage === "assembly";
  const showCrew = (hasModel && modelView === "model" && displayed !== null) || stage === "analysis";
  const requirementRows = [
    ["目標の高度", typeof stream.requirement?.target_altitude_m === "number" ? `${fmt(stream.requirement.target_altitude_m, 0)} m` : "未入力"],
    ["積載物の質量", typeof stream.requirement?.payload_mass_kg === "number" ? `${fmt(stream.requirement.payload_mass_kg * 1000, 0)} g` : "未入力"],
    ["予算", typeof stream.requirement?.budget_jpy === "number" ? `${fmt(stream.requirement.budget_jpy, 0)} 円` : "未入力"],
    ["規模", tier ? TIER_LABEL[tier] : "要求から判定"],
  ];
  function saveDesign() {
    if (!displayed) return;
    const blob = new Blob([JSON.stringify({ design: displayed.design, requirement: stream.requirement, source_id: displayed.sourceId, metrics: resultMetrics }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "rocketwright-design.json"; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <main className={`workshop-app${expanded ? " is-expanded" : ""}`}>
    <header className="workshop-identity">
      <a className="workshop-brand" href="/" aria-label="RocketWright ホーム"><span className="rw-mark">RW</span><strong>RocketWright</strong></a>
      <span className="identity-divider"/>
      <span className="project-path">{tier ? TIER_LABEL[tier] : "新しいロケット"}<span>/</span><b>{displayedId ? `案 · ${displayedId}` : "条件の確認"}</b></span>
      <span className="session-state">セッション内の下書き</span>
      <div className="identity-actions"><button className="btn" type="button" disabled={!displayed} onClick={saveDesign}><WorkshopIcon name="download" size={16}/><span>設計を保存</span></button>
        <button className="icon-button" type="button" aria-label="表示と出力先の設定" onClick={() => settings.current?.showModal()}><WorkshopIcon name="settings"/></button></div>
    </header>
    <nav className="workshop-phases" aria-label="設計の工程">{WORKSHOP_STAGES.map((item, i) => <button key={item.id} type="button" aria-current={stage === item.id ? "step" : undefined}
      className={stage === item.id ? "phase-link is-active" : "phase-link"} onClick={() => chooseStage(item.id)}><WorkshopIcon name={item.id}/><span>{item.label}</span>{i < WORKSHOP_STAGES.length - 1 ? <span className="phase-chevron">›</span> : null}</button>)}</nav>
    <div className="workshop-body">
      <nav className="workshop-rail" aria-label="ワークスペース全体の移動">
        <button className="rail-button" type="button" aria-label="ミッションを開く" onClick={() => chooseStage("brief")}><WorkshopIcon name="home"/></button>
        <button className="rail-button" type="button" aria-label="設計例と資料を開く" aria-pressed={stage === "library"} onClick={() => chooseStage("library")}><WorkshopIcon name="library"/></button>
        <button className="rail-button" type="button" aria-label="計算の履歴を開く" onClick={() => { setRightTab("history"); setRightOpen(true); }}><WorkshopIcon name="history"/></button>
        <span className="rail-spacer"/>
        <button className="rail-button" type="button" aria-label="設定を開く" onClick={() => settings.current?.showModal()}><WorkshopIcon name="settings"/></button>
      </nav>
      <aside id="workshop-targets" tabIndex={-1} className={`workshop-left${leftOpen ? " is-open" : ""}`} aria-label="工程の対象" onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); closeTargets(); } }}>
        <div className="dock-heading"><h1>{WORKSHOP_STAGES.find(s => s.id === stage)?.title ?? "設計例と資料"}</h1><button className="mobile-close icon-button" type="button" aria-label="対象一覧を閉じる" onClick={closeTargets}><WorkshopIcon name="close" size={18}/></button></div>
        <div className="left-dock-scroll">
          <label className="case-selector">表示する案<select value={selectedId ?? ""} onChange={e => setSelectedId(e.target.value || null)}><option value="">最新の結果に追従</option>{stream.candidates.map((c, i) => <option key={c.source_id} value={c.source_id}>{c.seededFrom ? "参照の初期案" : `案 ${i + 1}`} · {c.source_id}</option>)}</select></label>
          {stage === "analysis" ? <div className="dock-list" role="group" aria-label="解析の表示">{([['aero','流体解析'],['flight','飛行と回収'],['chart','高度の推移']] as const).map(([id,label]) => <button key={id} type="button" className={analysisView === id ? "dock-row is-active" : "dock-row"} aria-pressed={analysisView === id} onClick={() => { setAnalysisView(id); setLeftOpen(false); }}><WorkshopIcon name={id === "aero" ? "analysis" : "play"} size={18}/>{label}</button>)}</div> : null}
          {stage === "exports" ? <div className="dock-list" role="group" aria-label="成果物の表示">{([['production','製作票・印刷データ'],['drawing','設計図 SVG'],['video','設計解説・打ち上げ CG']] as const).map(([id,label]) => <button key={id} type="button" className={outputView === id ? "dock-row is-active" : "dock-row"} aria-pressed={outputView === id} onClick={() => { setOutputView(id); setLeftOpen(false); }}><WorkshopIcon name={id === "video" ? "play" : "exports"} size={18}/><span>{label}<small>{id === "video" ? "保存済みの設計例" : id === "drawing" ? summary?.drawing ? "保存可能" : "未生成" : currentPackage || printFiles.length ? "保存可能" : "未生成"}</small></span></button>)}</div> : null}
          <section className="dock-section"><h2>条件の概要</h2><dl className="dock-properties">{requirementRows.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
            <button type="button" className="text-button" onClick={() => { chooseStage("brief"); setRightOpen(true); }}>条件について相談する <span>↗</span></button></section>
          {stage === "compare" ? <section className="dock-section"><h2>計算された候補</h2><div className="dock-list">{stream.candidates.filter(c => !c.seededFrom).map((c,i) => <button key={c.source_id} type="button" className={displayedId === c.source_id ? "dock-row is-active" : "dock-row"} onClick={() => setSelectedId(c.source_id)}><WorkshopIcon name="design" size={18}/><span>案 {i+1}<small>{c.passed ? "計算上の条件を満たす" : "要見直し"}</small></span></button>)}{stream.candidates.length === 0 ? <p className="dock-empty">候補はまだありません</p> : null}</div></section>
            : <section className="dock-section"><h2>{stage === "exports" ? "保存できるファイル" : "機体の構成"}</h2>{stage === "exports" && (currentPackage || printFiles.length > 0) ? <div className="dock-list">{currentPackage?.files.map(f => <a key={f.url} className="dock-row" href={apiUrl(f.url)} download><WorkshopIcon name="exports" size={18}/>{f.label}</a>)}{printFiles.map(f => <a key={f.url} className="dock-row" href={apiUrl(f.url)} download><WorkshopIcon name="design" size={18}/>{f.name}</a>)}</div>
              : stage === "exports" ? <p className="dock-empty">ファイルを生成すると、ここから保存できます。</p>
              : summary?.bom.length ? <ul className="component-tree">{summary.bom.map((part,i) => <li key={`${part.item_id}-${i}`}><WorkshopIcon name="design" size={16}/><span>{part.name}<small>{part.qty} 点</small></span></li>)}</ul> : <p className="dock-empty">設計案が届くと表示します</p>}</section>}
          <div className="dock-context"><WorkshopIcon name="info" size={16}/><p>{displayed ? `${displayed.origin === "seed" ? "参照の初期案" : passed ? "計算結果のある案" : "検討中の案"}を表示しています。` : "目的を一文で伝えるところから始められます。"}</p></div>
        </div>
      </aside>
      <section className={`workshop-center${showCrew ? " has-crew" : ""}`} aria-label={`${stageLabel(stage)}の表示`}>
        <div className="workshop-toolbar">
          <button id="target-toggle" className="btn mobile-target-toggle" type="button" aria-controls="workshop-targets" aria-expanded={leftOpen} onClick={toggleTargets}>対象一覧</button>
          {hasModel ? <div className="tool-tabs" role="group" aria-label="機体の表示"><button type="button" aria-pressed={modelView === "model"} onClick={() => setModelView("model")}><WorkshopIcon name="design" size={18}/>3D モデル</button><button type="button" aria-pressed={modelView === "drawing"} onClick={() => setModelView("drawing")}><WorkshopIcon name="exports" size={18}/>側面図</button></div> : <span className="toolbar-context"><WorkshopIcon name={stage}/>{stageLabel(stage)}</span>}
          <span className="toolbar-spacer"/>
          {hasModel && modelView === "model" ? <button className="icon-button" type="button" aria-label="機体全体を表示" disabled={!displayed} onClick={() => setFrameRequest(n => n+1)}><WorkshopIcon name="expand" size={18}/></button> : null}
          <button className="icon-button expand-workspace" type="button" aria-label={expanded ? "ドックを表示" : "中央の表示を拡大"} aria-pressed={expanded} onClick={() => setExpanded(!expanded)}><WorkshopIcon name="expand" size={18}/></button>
          <label className="crew-visibility">整備員を表示<input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/><span/></label>
          <button className="btn mobile-inspector-toggle" type="button" onClick={() => { setRightOpen(!rightOpen); inspector.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }); }}>解説・相談</button>
        </div>
        <div className="workshop-canvas">
          <div className="hero-view" hidden={!hasModel || modelView !== "model"}>
            <div className="hero-heading"><span>{stage === "assembly" ? "組立前に、部品の関係を確認する" : displayed ? "機体の形と構成を確かめる" : "条件を確認して、設計を始める"}</span><p>{displayed ? "計算で使った設計値から作る概念モデル" : "何を、どこまで飛ばしたいですか？"}</p></div>
            <ModelViewer design={displayed?.design ?? null} tier={tier} origin={displayed?.origin ?? null} statusLabel={displayed?.origin === "seed" ? "参照の初期案" : passed ? "条件を満たす案" : "検討中の案"} reference={stream.reference} dimensions={summary?.dimensions ?? null} notes={notes} frameRequest={frameRequest} active={hasModel && modelView === "model"}/>
            {!displayed ? <span className="scene-image-label">工房のイメージ · 設計データはまだありません</span> : null}
            {stage === "assembly" ? <div className="assembly-context"><b>組立の準備</b><span>形状の概略を確認できます。手・工具の干渉と実機の組立性は未評価です。</span></div> : null}
          </div>
          <div className="drawing-workspace" hidden={!((hasModel && modelView === "drawing") || (stage === "exports" && outputView === "drawing"))}><DrawingPanel svg={summaryState.svg} url={summary?.drawing?.url ?? null} loading={summaryState.loading}/></div>
          <div className="analysis-workspace" hidden={stage !== "analysis"}>
            <div className="analysis-screen" hidden={analysisView !== "aero" || isOrbital(tier)}><AeroLoopPanel request={isOrbital(tier) ? null : aeroRequest} hasDesign={displayed !== null}/></div>
            {analysisView === "aero" && isOrbital(tier) ? <div className="workspace-empty"><h2>この規模は構想設計の対象です</h2><p>飛行の結果と軌道を確認できます。</p><button className="btn" type="button" onClick={() => setAnalysisView("flight")}>飛行と回収を見る</button></div> : null}
            {analysisView === "flight" ? <div className="flight-workspace"><FlightPlayer key={displayedId ?? "none"} trace={trace} metrics={flight?.metrics ?? NO_METRICS} warnings={flight?.warnings ?? []} parachute={carriesParachute(displayed?.design)} emptyMessage="計算した飛行の時系列が届くと再生できます"/></div> : null}
            <div className="chart-workspace" hidden={analysisView !== "chart"}><FlightChart tier={tier} trace={trace} sourceId={displayedId}/></div>
          </div>
          {stage === "compare" ? <DesignComparison candidates={stream.candidates} selectedId={displayedId} onSelect={setSelectedId}/> : null}
          <div className="production-workspace" hidden={stage !== "exports" || outputView !== "production" || isOrbital(tier)}><ProductionPanel request={packageRequest} passed={passed && !isOrbital(tier)} onGenerated={handleGenerated} onPrintGenerated={handlePrintGenerated}/></div>
          {stage === "exports" && outputView === "production" && isOrbital(tier) ? <div className="workspace-empty"><h2>構想設計の結果を保存</h2><p>詳細な製作データはこの規模では作成しません。</p><button className="btn" type="button" onClick={saveDesign}>設計 JSON を保存</button></div> : null}
          {stage === "exports" && outputView === "video" ? <VideoOutputs/> : null}
          {stage === "library" ? <div className="reference-workspace"><ReferenceLibrary/></div> : null}
          <WorkshopCrew embedded hideScene={!showCrew}/>
        </div>
        <div className="workspace-caption"><span>{displayedId ? `表示対象: ${displayedId}` : "まだ設計案がありません"}</span>{selectedId ? <button type="button" className="text-button" onClick={() => setSelectedId(null)}>最新へ戻る ↻</button> : <span>最新の結果に追従</span>}</div>
      </section>
      <aside ref={inspector} className={`workshop-right${rightOpen ? " is-open" : ""}`} aria-label="解説と設計の相談">
        <div className="inspector-tabs" role="group" aria-label="右パネルの表示">{([['explain','解説'],['history','履歴'],['consult','相談']] as const).map(([id,label]) => <button key={id} type="button" aria-pressed={rightTab === id} onClick={() => setRightTab(id)}>{label}</button>)}<button className="mobile-close icon-button" type="button" aria-label="解説と相談を閉じる" onClick={() => setRightOpen(false)}><WorkshopIcon name="close" size={18}/></button></div>
        <div className="inspector-scroll" hidden={rightTab !== "explain"}>
          <div className="explanation-title"><span/>{viewingReferenceFilm ? "設計例の映像を確認する" : stage === "analysis" ? analysisView === "aero" ? "機体まわりの流れを確かめる" : "飛行と回収の結果を確かめる" : stage === "exports" ? "同じ設計から、成果物を作る" : stage === "assembly" ? "組立に必要な条件を確認する" : "機体の形と飛び方を、一緒に検討する"}</div>
          <section className="meaning-block"><h2><WorkshopIcon name="info"/>何を確かめる？</h2><p>{viewingReferenceFilm ? "保存済みの設計例で、部品構成と上昇予測の映像を確認できます。" : stage === "analysis" ? "空気の流れや飛行の変化を、計算結果の図から確認します。" : stage === "exports" ? "対象の案と条件をそろえ、図面・部品表・印刷用ファイルを作ります。" : stage === "assembly" ? "部品の向き、材料、必要な工具を整理します。" : "目的に合う構成と、無理なく回収できる条件を探します。"}</p></section>
          <section className="meaning-block"><h2><WorkshopIcon name="analysis"/>今わかること</h2><p>{viewingReferenceFilm ? "映像の対象は、中央に記載された設計例です。保存できるファイルには再生と保存の操作が表示されます。" : task.status === "working" || task.status === "waiting" || task.status === "attention" ? task.label : displayed ? "表示中の案の形状と、届いた計算結果を確認できます。" : "まずは目標、積載物、回収方法を教えてください。"}</p>{displayed && !viewingReferenceFilm ? <ResultPanel tier={tier} metrics={resultMetrics}/> : null}</section>
          <section className="meaning-block"><h2><WorkshopIcon name="history"/>まだ決められないこと</h2><p>{!displayed ? "設計案と計算結果はまだありません。" : stage === "assembly" ? "手・工具のアクセス、締結の条件、実機での組立確認は未評価です。" : stage === "exports" ? "スライス検査と、実際に印刷できたことは別に確認します。現在の設計の動画は未生成です。" : "計算の対象外の条件と、実物の強度・組立性は未確認です。"}</p></section>
          {stream.status === "error" ? <div className="inspector-error" role="alert">{stream.messages.filter(m => m.role === "error").at(-1)?.text ?? "処理に失敗しました。相談の記録を確認してください。"}</div> : null}
          {stage === "design" || stage === "brief" ? <><CostPanel summary={summary} fallbackCostJpy={fallbackCost} loading={summaryState.loading} error={summaryState.error}/><button className="btn inspector-primary" type="button" onClick={() => { chooseStage(displayed ? "analysis" : "brief"); if (!displayed) setRightTab("consult"); }}>{displayed ? "解析の画面へ" : "目的を相談する"}<WorkshopIcon name="arrow" size={18}/></button></> : null}
          {stage === "assembly" ? <BomPanel bom={summary?.bom ?? []} csvUrl={csvUrl} loading={summaryState.loading}/> : null}
          {stage === "exports" ? <p className="scope-note"><WorkshopIcon name="info" size={16}/>現在の案に対応するファイルだけを保存できます。</p> : null}
        </div>
        <div className="inspector-scroll" hidden={rightTab !== "history"}><DetailsPanel tier={tier} classify={stream.classify} derived={stream.derived} attempts={stream.attempts} candidates={stream.candidates} chain={stream.chain} events={stream.events} dispersion={dispersion} landing={landing} exports={exportInfos} selectedId={displayedId} onSelect={setSelectedId}/></div>
        <div className="consultation" hidden={rightTab !== "consult"}><div className="consultation-title"><WorkshopIcon name="chat" size={18}/><h2>設計の相談</h2></div><ChatPanel messages={stream.messages} status={stream.status} pendingQuestion={stream.pendingQuestion} onStart={handleStart} onAnswer={handleAnswer} onStop={stop} onReset={handleReset}/></div>
      </aside>
    </div>
    <footer className="workshop-footer"><StatusStrip status={stream.status} attemptCount={stream.attemptCount}/><span className="footer-divider"/><span className="footer-task">{task.label}</span><span className="toolbar-spacer"/><span className="footer-units">単位: m, g, 円</span><button className="btn" type="button" aria-pressed={paused} disabled={reduced} onClick={() => setPaused(!paused)}><WorkshopIcon name={paused ? "play" : "pause"} size={16}/>{reduced ? "動きを減らす設定" : paused ? "動きを再開" : "動きを止める"}</button>{stream.status === "streaming" ? <button type="button" className="btn stop-design" onClick={stop}>設計を中断</button> : null}</footer>
    <dialog ref={settings} className="workshop-settings" aria-labelledby="settings-title"><div className="dock-heading"><h2 id="settings-title">表示と出力先</h2><button className="icon-button" type="button" aria-label="設定を閉じる" onClick={() => settings.current?.close()}><WorkshopIcon name="close"/></button></div><div className="settings-content"><h3>工房の表示</h3><label><input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/>整備員を表示</label><label><input type="checkbox" checked={paused} disabled={reduced} onChange={e => setPaused(e.target.checked)}/>演出とカメラの動きを止める</label><p>{reduced ? "端末の設定に合わせ、動きを減らしています。" : "表示設定はこのブラウザーに保存します。"}</p><h3>3Dプリントの出力先</h3><p>UltiMaker S5 · Tough PLA Gray · AA 0.4</p><small>製作データで選択中の案を生成し、ファイルを保存できます。</small></div><form method="dialog"><button className="btn" type="submit">閉じる</button></form></dialog>
  </main>;
}
