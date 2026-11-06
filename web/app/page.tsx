"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import AeroLoopPanel from "./components/AeroLoopPanel";
import FlightPlayer from "./components/FlightPlayer";
import BomPanel from "./components/BomPanel";
import ChatPanel from "./components/ChatPanel";
import LocalDesignChat from "./components/LocalDesignChat";
import DockHandle from "./components/DockHandle";
import CostPanel from "./components/CostPanel";
import DrawingPanel from "./components/DrawingPanel";
import FlightChart from "./components/FlightChart";
import ModelViewer from "./components/ModelViewer";
import ProductionPanel from "./components/ProductionPanel";
import ResultPanel from "./components/ResultPanel";
import StatusStrip from "./components/StatusStrip";
import WorkshopCrew from "./components/WorkshopCrew";
import WorkshopIcon from "./components/WorkshopIcon";
import DesignProduction from "./components/DesignProduction";
import { projectFileLabel, type DesignProject } from "./lib/designProjects";
import { WorkshopProvider, useCrewTask, useWorkshop } from "./lib/WorkshopContext";
import { WORKSHOP_STAGES, stageLabel, type WorkshopStage, type AnalysisView, type OutputView } from "./lib/workshopNavigation";
import { designCrewTask } from "./lib/workshopActivity";
import { apiUrl, designKey, exportInfoFromEvents, exportsForDesign, requestKey, type DesignPackage, type DesignPackageRequest } from "./lib/api";
import { fmt } from "./lib/format";
import { certificationNotes, selectDisplayedDesign } from "./lib/designState";
import { carriesParachute } from "./lib/flightPlayback";
import { caseLabels } from "./lib/caseLabels";
import { useDockWidths } from "./lib/useDockWidths";
import { useDesignStream } from "./lib/useDesignStream";
import { useDesignSummary } from "./lib/useDesignSummary";
import type { AeroRequest } from "./lib/useAeroLoop";
import { isOrbital, TIER_LABEL, type DispersionResult, type DisplayedDesign, type TracePoint } from "./lib/types";

const ANALYSIS_VIEWS = [["aero", "流体解析"], ["flight", "飛行と回収"], ["chart", "高度の推移"]] as const;
const OUTPUT_VIEWS = [["production", "製作票・印刷データ"], ["drawing", "設計図 SVG"], ["video", "設計解説・打ち上げ CG"]] as const;
const NO_TRACE: TracePoint[] = [];
const NO_METRICS: Record<string, number> = {};

export default function Home() {
  return <WorkshopProvider><DesignScreen/></WorkshopProvider>;
}

function DesignScreen() {
  const [stage, setStage] = useState<WorkshopStage>("design");
  const [analysisView, setAnalysisView] = useState<AnalysisView>("aero");
  const [outputView, setOutputView] = useState<OutputView>("production");
  const [modelView, setModelView] = useState<"model" | "drawing">("model");
  const [frameRequest, setFrameRequest] = useState(0);
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const settings = useRef<HTMLDialogElement>(null);
  const inspector = useRef<HTMLElement>(null);
  const docks = useDockWidths();
  const { task, visible, setVisible, paused, setPaused, reduced } = useWorkshop();
  const [generated, setGenerated] = useState<{ key: string; package: DesignPackage } | null>(null);
  const [printed, setPrinted] = useState<{ key: string; files: { name: string; url: string }[] } | null>(null);
  const stream = useDesignStream();
  const [productionProject, setProductionProject] = useState<DesignProject | null>(null);
  const activeRequirement = productionProject ? productionProject.spec.requirement : stream.requirement;
  useCrewTask("design", designCrewTask(stream));
  const { start, answer, stop, reset } = stream;
  // Manual pick from 詳細 (attempt log / cards / reviews); null = follow the display rule.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Displayed design: the user's pick when it resolves, else the latest passing candidate,
  // else the latest attempt, else the reference seed (designState.selectDisplayedDesign).
  // Part-space attempts (auto_design / design_from_parts) carry the resolved design.
  const displayed = useMemo<DisplayedDesign | null>(() => {
    if (productionProject) return { design: productionProject.analysis?.design ?? { ...productionProject.spec.design, geometry: productionProject.spec.geometry }, sourceId: `${productionProject.id}:v${productionProject.version}`, origin: "attempt" };
    if (selectedId !== null) {
      const c = stream.candidates.find((x) => x.source_id === selectedId);
      if (c) return { design: c.design, sourceId: c.source_id, origin: "candidate" };
      const a = stream.attempts.find((x) => x.id === selectedId);
      if (a && a.design !== null) {
        return { design: a.design, sourceId: a.id, origin: a.seededFrom !== null ? "seed" : "attempt" };
      }
    }
    return selectDisplayedDesign(stream);
  }, [selectedId, stream, productionProject]);

  const displayedId = displayed?.sourceId ?? null;
  const labels = useMemo(() => caseLabels(stream.candidates, stream.attempts), [stream.candidates, stream.attempts]);
  const displayedLabel = productionProject ? `${productionProject.name} / v${productionProject.version}` : displayedId ? labels.get(displayedId) ?? "検討中の案" : null;
  const displayedAttempt = useMemo(
    () => (displayedId ? stream.attempts.find((a) => a.id === displayedId) : undefined),
    [displayedId, stream.attempts],
  );
  // auto_design and reference seeds leave the time series out of their event, so a design shown
  // from one of them flies on the trace of an attempt that simulated the very same design.
  const flight = useMemo(() => {
    if (productionProject) return productionProject.analysis?.result;
    if (displayedAttempt?.result?.trace.length || !displayed) return displayedAttempt?.result;
    const key = designKey(displayed.design);
    return stream.attempts.find(
      (a) => a.design !== null && a.result?.trace.length && designKey(a.design) === key,
    )?.result;
  }, [displayed, displayedAttempt, stream.attempts, productionProject]);
  const trace: TracePoint[] = flight?.trace ?? NO_TRACE;
  // Certification / coupler warnings of the displayed build (amber note under the 3D view).
  const notes: string[] = useMemo(
    () => certificationNotes(displayedAttempt?.result?.warnings ?? []),
    [displayedAttempt],
  );
  const fallbackCost = displayedAttempt?.result?.cost_jpy ?? null;

  // run_dispersion result of this design only; never show a different case.
  const dispersion: DispersionResult | null = useMemo(() => {
    if (productionProject || !displayed) return null;
    const key = designKey(displayed.design);
    const own = displayedId ? stream.dispersions[displayedId] : undefined;
    const same = Object.values(stream.dispersions).filter(d => d.design && designKey(d.design) === key);
    return own ?? same.at(-1) ?? null;
  }, [displayed, displayedId, stream.dispersions, productionProject]);

  // Download maps from export_report / render_drawing results; the BOM CSV for the displayed
  // design when the agent exported it, else none.
  const exportInfos = useMemo(() => exportInfoFromEvents(stream.events), [stream.events]);
  const csvUrl: string | null = useMemo(() => {
    if (productionProject) return productionProject.files.find(f => f.key === "production/bom.csv")?.url ?? null;
    if (!displayed) return null;
    const own = exportsForDesign(exportInfos, displayed.design).find((e) => typeof e.download.bom === "string");
    if (own) return own.download.bom;
    return null;
  }, [displayed, exportInfos, productionProject]);

  // Every attempt that flew this very design, the one on screen first: a trace-only re-run has
  // neither the build nor the margins of the parts attempt, and an estimate_cost candidate no env.
  const sameDesign = useMemo(() => {
    if (!displayed) return [];
    const key = designKey(displayed.design);
    const same = stream.attempts.filter((a) => a.design !== null && designKey(a.design) === key);
    return [...same.filter((a) => a === displayedAttempt), ...same.filter((a) => a !== displayedAttempt)];
  }, [displayed, displayedAttempt, stream.attempts]);
  const build = productionProject ? null : displayedAttempt?.build ?? sameDesign.find((a) => a.build !== null)?.build ?? null;

  // /artifacts/summary for the displayed design (debounced, cached by design JSON).
  const summaryState = useDesignSummary(displayed?.design ?? null, activeRequirement, build);
  const summary = summaryState.summary;

  const projectBom = productionProject ? [
    { item_id: "fin", name: `${productionProject.spec.material} フィン`, qty: productionProject.spec.design.has_fins ? productionProject.spec.geometry.fin_count : 0, mass_kg: null, price_jpy: null, source_or_provisional: "provisional 採用寸法のCAD / 実測・価格未確認" },
    { item_id: "nose", name: `${productionProject.spec.material} ノーズ`, qty: 1, mass_kg: null, price_jpy: null, source_or_provisional: "provisional 採用寸法のCAD / 実測・価格未確認" },
    { item_id: "other", name: "ボトル・回収等の入力した他の部材", qty: 1, mass_kg: productionProject.spec.other_dry_mass_g / 1000, price_jpy: null, source_or_provisional: "provisional 入力質量 / 詳細部材と価格は要確認" },
  ] : null;

  const tier = productionProject ? "bottle" : stream.tier ?? displayed?.design.tier ?? null;

  // Everything the tools reported for this very design; the attempt on screen has the last word.
  const resultMetrics = useMemo(() => {
    if (productionProject) return productionProject.analysis?.result.metrics ?? NO_METRICS;
    if (!displayed) return NO_METRICS;
    const candidate = stream.candidates.find((c) => c.source_id === displayed.sourceId);
    const flown = [...sameDesign].reverse().map((a) => a.result?.metrics);
    return Object.assign({}, candidate?.metrics, ...flown) as Record<string, number>;
  }, [displayed, sameDesign, stream.candidates, productionProject]);

  // A failing attempt or a reference seed gets no production data (CLAUDE.md section 1). A seed
  // flew in the reference's own conditions, which the tool inputs do not hold.
  const passed: boolean = useMemo(() => {
    if (productionProject) return productionProject.adopted && !!productionProject.analysis?.result.success;
    const candidate = stream.candidates.find((c) => c.source_id === displayedId);
    if (candidate?.seededFrom || displayed?.origin === "seed") return false;
    return candidate?.passed ?? displayedAttempt?.result?.success ?? false;
  }, [displayed, displayedId, displayedAttempt, stream.candidates, productionProject]);

  // Conditions of the run on screen, so that the API repeats what the agent simulated.
  const callEnv = [displayedId, ...sameDesign.map((a) => a.id)]
    .map((id) => (id ? stream.toolInputs[id]?.env : undefined))
    .find((value) => typeof value === "object" && value !== null);
  const env = (productionProject ? productionProject.spec.env : callEnv ?? null) as Record<string, unknown> | null;
  const rerun = useMemo(
    () => ({ requirement: activeRequirement, env, seed: dispersion?.seed ?? null, n: dispersion?.n ?? null }),
    [activeRequirement, env, dispersion],
  );
  const packageRequest: DesignPackageRequest | null = useMemo(
    () => (displayed ? { design: displayed.design, build, ...rerun } : null),
    [displayed, build, rerun],
  );
  const aeroRequest: AeroRequest | null = useMemo(() => {
    const target = activeRequirement?.target_altitude_m;
    if (!displayed || typeof target !== "number" || target <= 0) return null;
    return { design: displayed.design, target_altitude_m: target, ...rerun };
  }, [displayed, activeRequirement, rerun]);

  const handleStart = useCallback(
    (text: string, seed: number | null) => {
      setProductionProject(null);
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
  const viewingReferenceFilm = stage === "exports" && outputView === "video" && !productionProject;
  function closeTargets() { setLeftOpen(false); document.getElementById("target-toggle")?.focus(); }
  function toggleTargets() {
    if (leftOpen) { closeTargets(); return; }
    setLeftOpen(true);
    window.requestAnimationFrame(() => document.getElementById("workshop-targets")?.focus());
  }
  const chooseStage = (next: WorkshopStage) => {
    setStage(next); setLeftOpen(false); setExpanded(false);
  };
  const hasModel = stage === "design";
  const showCrew = (hasModel && modelView === "model" && displayed !== null) || stage === "analysis" || stage === "exports";
  const requirementRows = [
    ["目標の高度", typeof activeRequirement?.target_altitude_m === "number" ? `${fmt(activeRequirement.target_altitude_m, 0)} m` : productionProject ? "未指定" : "未入力"],
    ["積載物の質量", productionProject ? `${fmt(productionProject.spec.design.payload_mass_kg * 1000, 0)} g` : typeof activeRequirement?.payload_mass_kg === "number" ? `${fmt(activeRequirement.payload_mass_kg * 1000, 0)} g` : "未入力"],
    ["予算", typeof activeRequirement?.budget_jpy === "number" ? `${fmt(activeRequirement.budget_jpy, 0)} 円` : "未入力"],
    ["規模", tier ? TIER_LABEL[tier] : "要求から判定"],
  ];
  function saveDesign() {
    if (!displayed) return;
    const blob = new Blob([JSON.stringify(productionProject ? { schema_version: 1, spec: productionProject.spec } : { design: displayed.design, requirement: activeRequirement, source_id: displayed.sourceId, metrics: resultMetrics }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = "rocketwright-design.json"; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <main className={`workshop-app${expanded ? " is-expanded" : ""}`}>
    <header className="workshop-identity">
      <a className="workshop-brand" href="/" aria-label="RocketWright ホーム" onClick={e => { e.preventDefault(); chooseStage("design"); }}><span className="rw-mark">RW</span><strong>RocketWright</strong></a>
      <span className="identity-divider"/>
      <span className="project-path">{tier ? TIER_LABEL[tier] : "新しいロケット"}<span>/</span><b>{displayedLabel ?? "条件の確認"}</b></span>
      <span className="session-state">{productionProject ? `保存済み / v${productionProject.version}` : "セッション内の下書き"}</span>
      <div className="identity-actions"><button className="btn" type="button" disabled={!displayed} onClick={saveDesign}><WorkshopIcon name="download" size={16}/><span>設計を保存</span></button>
        <button className="icon-button" type="button" aria-label="表示と出力先の設定" onClick={() => settings.current?.showModal()}><WorkshopIcon name="settings"/></button></div>
    </header>
    <nav className="workshop-phases" aria-label="設計の工程">{WORKSHOP_STAGES.map((item, i) => <button key={item.id} type="button" aria-current={stage === item.id ? "step" : undefined}
      className={stage === item.id ? "phase-link is-active" : "phase-link"} onClick={() => chooseStage(item.id)}><WorkshopIcon name={item.id}/><span>{item.label}</span>{i < WORKSHOP_STAGES.length - 1 ? <span className="phase-chevron">›</span> : null}</button>)}</nav>
    <div className={`workshop-body${stage === "design" ? "" : " without-results"}`} style={docks.style}>
      <aside id="workshop-targets" tabIndex={-1} className={`workshop-left${leftOpen ? " is-open" : ""}`} aria-label="設計の相談" onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); closeTargets(); } }}>
        <div className="dock-heading"><h1>設計の相談</h1><button className="mobile-close icon-button" type="button" aria-label="相談を閉じる" onClick={closeTargets}><WorkshopIcon name="close" size={18}/></button></div>
        <div className="consultation"><LocalDesignChat project={productionProject} onProject={setProductionProject}/><details><summary>既存の構想設計フロー（課金接続は無効）</summary><ChatPanel messages={stream.messages} status={stream.status} pendingQuestion={stream.pendingQuestion} onStart={handleStart} onAnswer={handleAnswer} onStop={stop} onReset={handleReset}/></details></div>
        <DockHandle side="left" label="相談の幅を変える" width={docks.left} onResize={docks.setLeft}/>
      </aside>
      <section className={`workshop-center${showCrew ? " has-crew" : ""}`} aria-label={`${stageLabel(stage)}の表示`}>
        <div className="workshop-toolbar">
          <button id="target-toggle" className="btn mobile-target-toggle" type="button" aria-controls="workshop-targets" aria-expanded={leftOpen} onClick={toggleTargets}>相談</button>
          {hasModel ? <div className="tool-tabs" role="group" aria-label="機体の表示"><button type="button" aria-pressed={modelView === "model"} onClick={() => setModelView("model")}><WorkshopIcon name="design" size={18}/>3D モデル</button><button type="button" aria-pressed={modelView === "drawing"} onClick={() => setModelView("drawing")}><WorkshopIcon name="exports" size={18}/>側面図</button></div> : stage === "analysis" ? <div className="tool-tabs" role="group" aria-label="解析の表示">{ANALYSIS_VIEWS.map(([id, label]) => <button key={id} type="button" aria-pressed={analysisView === id} onClick={() => setAnalysisView(id)}><WorkshopIcon name={id === "aero" ? "analysis" : "play"} size={18}/>{label}</button>)}</div>
            : stage === "exports" ? <div className="tool-tabs" role="group" aria-label="成果物の表示">{OUTPUT_VIEWS.map(([id, label]) => <button key={id} type="button" aria-pressed={outputView === id} onClick={() => setOutputView(id)}><WorkshopIcon name={id === "video" ? "play" : "exports"} size={18}/>{label}</button>)}</div>
            : <span className="toolbar-context"><WorkshopIcon name={stage}/>{stageLabel(stage)}</span>}
          <span className="toolbar-spacer"/>
          {hasModel && modelView === "model" ? <button className="icon-button" type="button" aria-label="機体全体を表示" disabled={!displayed} onClick={() => setFrameRequest(n => n+1)}><WorkshopIcon name="expand" size={18}/></button> : null}
          <button className="icon-button expand-workspace" type="button" aria-label={expanded ? "ドックを表示" : "中央の表示を拡大"} aria-pressed={expanded} onClick={() => setExpanded(!expanded)}><WorkshopIcon name="expand" size={18}/></button>
          <label className="crew-visibility">整備員を表示<input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/><span/></label>
          <button className="btn mobile-inspector-toggle" type="button" onClick={() => { setRightOpen(!rightOpen); inspector.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }); }}>結果</button>
        </div>
        <div className="workshop-canvas">
          <div className="hero-view" hidden={!hasModel || modelView !== "model"}>
            <div className="hero-heading"><span>{displayed ? "機体の形と構成を確かめる" : "条件を確認して、設計を始める"}</span><p>{displayed ? "計算で使った設計値から作る概念モデル" : "何を、どこまで飛ばしたいですか？"}</p></div>
            <ModelViewer design={displayed?.design ?? null} tier={tier} origin={displayed?.origin ?? null} statusLabel={displayed?.origin === "seed" ? "参照の初期案" : passed ? "条件を満たす案" : "検討中の案"} reference={stream.reference} dimensions={summary?.dimensions ?? null} notes={notes} frameRequest={frameRequest} active={hasModel && modelView === "model"}/>
            {!displayed ? <span className="scene-image-label">工房のイメージ · 設計データはまだありません</span> : null}
          </div>
          <div className="drawing-workspace" hidden={!((hasModel && modelView === "drawing") || (stage === "exports" && outputView === "drawing"))}><DrawingPanel svg={summaryState.svg} url={summary?.drawing?.url ?? null} loading={summaryState.loading}/></div>
          <div className="analysis-workspace" hidden={stage !== "analysis"}>
            <div className="analysis-screen" hidden={analysisView !== "aero" || isOrbital(tier)}><AeroLoopPanel request={isOrbital(tier) ? null : aeroRequest} hasDesign={displayed !== null}/></div>
            {analysisView === "aero" && isOrbital(tier) ? <div className="workspace-empty"><h2>この規模は構想設計の対象です</h2><p>飛行の結果と軌道を確認できます。</p><button className="btn" type="button" onClick={() => setAnalysisView("flight")}>飛行と回収を見る</button></div> : null}
            {analysisView === "flight" ? <div className="flight-workspace"><FlightPlayer key={displayedId ?? "none"} trace={trace} metrics={flight?.metrics ?? NO_METRICS} warnings={flight?.warnings ?? []} parachute={carriesParachute(displayed?.design)} emptyMessage="計算した飛行の時系列が届くと再生できます"/></div> : null}
            <div className="chart-workspace" hidden={analysisView !== "chart"}><FlightChart tier={tier} trace={trace} sourceId={displayedLabel}/></div>
          </div>
          {stage === "exports" && outputView === "production" && isOrbital(tier) ? <div className="workspace-empty"><h2>構想設計の結果を保存</h2><p>詳細な製作データはこの規模では作成しません。</p><button className="btn" type="button" onClick={saveDesign}>設計 JSON を保存</button></div> : null}
          <div className="production-stack" hidden={stage !== "exports" || outputView === "drawing" || isOrbital(tier)}>
          <div className="production-workspace" hidden={stage !== "exports" || outputView !== "production" || isOrbital(tier)}><ProductionPanel request={packageRequest} passed={passed && !isOrbital(tier)} onGenerated={handleGenerated} onPrintGenerated={handlePrintGenerated}/></div>
          <div className="production-workspace" hidden={stage !== "exports" || isOrbital(tier)}><DesignProduction source={packageRequest} mode={outputView === "video" ? "video" : "files"} onProjectChange={setProductionProject} projectId={productionProject?.id ?? null} active={stage === "exports"}/></div>
          </div>
          <WorkshopCrew embedded hideScene={!showCrew}/>
        </div>
        <div className="workspace-caption"><span>{displayedLabel ? `表示対象: ${displayedLabel}` : "まだ設計案がありません"}</span>{selectedId ? <button type="button" className="text-button" onClick={() => { setProductionProject(null); setSelectedId(null); }}>最新へ戻る ↻</button> : <span>最新の結果に追従</span>}</div>
      </section>
      {stage === "design" ? <aside ref={inspector} className={`workshop-right${rightOpen ? " is-open" : ""}`} aria-label="結果と履歴">
        <div className="dock-heading"><h1>結果</h1><button className="mobile-close icon-button" type="button" aria-label="結果を閉じる" onClick={() => setRightOpen(false)}><WorkshopIcon name="close" size={18}/></button></div>
        <div className="inspector-scroll">
          <label className="case-selector">表示する案<select value={productionProject?.id ?? selectedId ?? ""} onChange={e => { if (e.target.value !== productionProject?.id) { setProductionProject(null); setSelectedId(e.target.value || null); } }}><option value="">最新の結果に追従</option>{productionProject ? <option value={productionProject.id}>{productionProject.name} / v{productionProject.version}</option> : null}{stream.candidates.map(c => <option key={c.source_id} value={c.source_id}>{labels.get(c.source_id)}</option>)}</select></label>
          {stream.status === "error" ? <div className="inspector-error" role="alert">{stream.messages.filter(m => m.role === "error").at(-1)?.text ?? "処理に失敗しました。相談の記録を確認してください。"}</div> : null}
          {displayed && !viewingReferenceFilm ? <ResultPanel tier={tier} metrics={resultMetrics}/> : <p className="dock-empty">{viewingReferenceFilm ? "映像の対象は、中央に記載された設計例です。" : "設計案が届くと、ここに結果を表示します。"}</p>}
          {dispersion ? <p className="scope-note">条件を変えた {dispersion.n} 回の試行で、成功率 {fmt(dispersion.success_rate * 100, 0)} %</p> : null}
          {productionProject ? <p className="scope-note">採用版の部品価格と固定材の費用は未見積りです。</p> : <CostPanel summary={summary} fallbackCostJpy={fallbackCost} loading={summaryState.loading} error={summaryState.error}/>}
          <section className="dock-section"><h2>条件の概要</h2><dl className="dock-properties">{requirementRows.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>
          <BomPanel bom={projectBom ?? summary?.bom ?? []} csvUrl={csvUrl} loading={summaryState.loading}/>
          <section className="meaning-block"><h2><WorkshopIcon name="history"/>まだ確かめていないこと</h2><p>{!displayed ? "設計案と計算結果はまだありません。" : "計算の対象外の条件と、実物の強度・組立性は未確認です。結果はすべてシミュレーションです。"}</p></section>
        </div>
        <DockHandle side="right" label="結果の幅を変える" width={docks.right} onResize={docks.setRight}/>
      </aside> : null}
    </div>
    <footer className="workshop-footer">{productionProject ? <span role="status">{productionProject.active ? "処理中" : productionProject.adopted ? "採用版を保存済み" : "設計版を確認中"}</span> : <StatusStrip status={stream.status} attemptCount={stream.attemptCount}/>}<span className="footer-divider"/><span className="footer-task">{task.label}</span><span className="toolbar-spacer"/><span className="footer-units">単位: m, g, 円</span><button className="btn" type="button" aria-pressed={paused} disabled={reduced} onClick={() => setPaused(!paused)}><WorkshopIcon name={paused ? "play" : "pause"} size={16}/>{reduced ? "動きを減らす設定" : paused ? "動きを再開" : "動きを止める"}</button>{stream.status === "streaming" ? <button type="button" className="btn stop-design" onClick={stop}>設計を中断</button> : null}</footer>
    <dialog ref={settings} className="workshop-settings" aria-labelledby="settings-title"><div className="dock-heading"><h2 id="settings-title">表示と出力先</h2><button className="icon-button" type="button" aria-label="設定を閉じる" onClick={() => settings.current?.close()}><WorkshopIcon name="close"/></button></div><div className="settings-content"><h3>工房の表示</h3><label><input type="checkbox" checked={visible} onChange={e => setVisible(e.target.checked)}/>整備員を表示</label><label><input type="checkbox" checked={paused} disabled={reduced} onChange={e => setPaused(e.target.checked)}/>演出とカメラの動きを止める</label><p>{reduced ? "端末の設定に合わせ、動きを減らしています。" : "表示設定はこのブラウザーに保存します。"}</p><h3>3Dプリントの出力先</h3><p>UltiMaker S5 · Tough PLA Gray · AA 0.4</p><small>製作データで選択中の案を生成し、ファイルを保存できます。</small></div><form method="dialog"><button className="btn" type="submit">閉じる</button></form></dialog>
  </main>;
}
