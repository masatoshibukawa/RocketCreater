"use client";

import { useCallback, useMemo, useState } from "react";
import AeroLoopPanel from "./components/AeroLoopPanel";
import FlightPlayer from "./components/FlightPlayer";
import BomPanel from "./components/BomPanel";
import ChatPanel from "./components/ChatPanel";
import CostPanel from "./components/CostPanel";
import CrewBanner from "./components/CrewBanner";
import DetailsPanel from "./components/DetailsPanel";
import DrawingPanel from "./components/DrawingPanel";
import FlightChart from "./components/FlightChart";
import ModelViewer from "./components/ModelViewer";
import ProductionPanel from "./components/ProductionPanel";
import ReferenceLibrary from "./components/ReferenceLibrary";
import ResultPanel from "./components/ResultPanel";
import StatusStrip from "./components/StatusStrip";
import WorkshopCrew from "./components/WorkshopCrew";
import { WorkshopProvider, useCrewTask } from "./lib/WorkshopContext";
import { designCrewTask } from "./lib/workshopActivity";
import { designKey, exportInfoFromEvents, exportsForDesign, type DesignPackageRequest } from "./lib/api";
import { centerTabs, type CenterView } from "./lib/centerViews";
import { certificationNotes, selectDisplayedDesign } from "./lib/designState";
import { carriesParachute } from "./lib/flightPlayback";
import { useDesignStream } from "./lib/useDesignStream";
import { useDesignSummary } from "./lib/useDesignSummary";
import type { AeroRequest } from "./lib/useAeroLoop";
import { isOrbital, type DispersionResult, type DisplayedDesign, type LandingPoint, type TracePoint } from "./lib/types";

const NO_TRACE: TracePoint[] = [];
const NO_METRICS: Record<string, number> = {};

export default function Home() {
  return <WorkshopProvider><DesignScreen/></WorkshopProvider>;
}

function DesignScreen() {
  const [centerView, setCenterView] = useState<CenterView>("model");
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
  const tabs = centerTabs(tier);
  // A multistage run takes the flow and production tabs away while one of them is open.
  const view: CenterView = tabs.some((t) => t.id === centerView) ? centerView : "model";

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

  return (
    <main className="app">
      <StatusStrip status={stream.status} attemptCount={stream.attemptCount} />
      <div className="app-columns">
        <section className="column column-chat">
          <ChatPanel
            messages={stream.messages}
            status={stream.status}
            pendingQuestion={stream.pendingQuestion}
            onStart={handleStart}
            onAnswer={handleAnswer}
            onStop={stop}
            onReset={handleReset}
          />
        </section>
        <div className="column-rest">
          <section className="column column-center">
            <div className="center-tabs" role="group" aria-label="中央の表示">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`btn ${view === tab.id ? "is-active" : ""}`}
                  aria-pressed={view === tab.id}
                  onClick={() => setCenterView(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {stream.status === "streaming" && !isOrbital(tier) ? (
              <CrewBanner
                attemptCount={stream.attemptCount}
                latestApogeeM={stream.attempts.at(-1)?.result?.metrics.apogee_m}
              />
            ) : null}
            {view === "model" ? (
              <ModelViewer
                design={displayed?.design ?? null}
                tier={tier}
                origin={displayed?.origin ?? null}
                reference={stream.reference}
                dimensions={summary?.dimensions ?? null}
                notes={notes}
              />
            ) : null}
            {view === "simulation" ? (
              <div className="panel simulation-panel">
                <FlightPlayer
                  key={displayedId ?? "none"}
                  trace={trace}
                  metrics={flight?.metrics ?? NO_METRICS}
                  warnings={flight?.warnings ?? []}
                  parachute={carriesParachute(displayed?.design)}
                  emptyMessage={
                    displayed
                      ? "この案の飛行の時系列はまだありません。シミュレーションを実行した案を選ぶと再生できます。"
                      : "設計案が届くと、飛行を再生できます"
                  }
                />
              </div>
            ) : null}
            {/* Kept mounted: a running job and its result survive a switch of tab. */}
            <div className="panel simulation-panel" hidden={view !== "aero"}>
              <AeroLoopPanel request={aeroRequest} hasDesign={displayed !== null} />
            </div>
            <div className="panel simulation-panel" hidden={view !== "production"}>
              <ProductionPanel request={packageRequest} passed={passed} />
            </div>
            {view === "library" ? (
              <div className="panel simulation-panel">
                <ReferenceLibrary />
              </div>
            ) : null}
            <WorkshopCrew/>
            {view === "model" ? (
              <CostPanel
                summary={summary}
                fallbackCostJpy={fallbackCost}
                loading={summaryState.loading}
                error={summaryState.error}
              />
            ) : null}
          </section>
          <section className="column column-right">
            <ResultPanel tier={tier} metrics={resultMetrics} />
            <DrawingPanel svg={summaryState.svg} url={summary?.drawing?.url ?? null} loading={summaryState.loading} />
            <FlightChart tier={tier} trace={trace} sourceId={displayedId} />
            <BomPanel bom={summary?.bom ?? []} csvUrl={csvUrl} loading={summaryState.loading} />
            <DetailsPanel
              tier={tier}
              classify={stream.classify}
              derived={stream.derived}
              attempts={stream.attempts}
              candidates={stream.candidates}
              chain={stream.chain}
              events={stream.events}
              dispersion={dispersion}
              landing={landing}
              exports={exportInfos}
              selectedId={displayedId}
              onSelect={setSelectedId}
            />
          </section>
        </div>
      </div>
    </main>
  );
}
