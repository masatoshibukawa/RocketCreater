"use client";

import { useCallback, useMemo, useState } from "react";
import BomPanel from "./components/BomPanel";
import ChatPanel from "./components/ChatPanel";
import CostPanel from "./components/CostPanel";
import DetailsPanel from "./components/DetailsPanel";
import DrawingPanel from "./components/DrawingPanel";
import FlightChart from "./components/FlightChart";
import ModelViewer from "./components/ModelViewer";
import PrintExports from "./components/PrintExports";
import StatusStrip from "./components/StatusStrip";
import WorkbenchPanel from "./components/WorkbenchPanel";
import { exportInfoFromEvents, exportsForDesign } from "./lib/api";
import { certificationNotes, selectDisplayedDesign } from "./lib/designState";
import { useDesignStream } from "./lib/useDesignStream";
import { useDesignSummary } from "./lib/useDesignSummary";
import type { DispersionResult, DisplayedDesign, LandingPoint, TracePoint } from "./lib/types";

export default function Home() {
  const [workspace, setWorkspace] = useState(true);
  const stream = useDesignStream();
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
  const trace: TracePoint[] = displayedAttempt?.result?.trace ?? [];
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

  // /artifacts/summary for the displayed design (debounced, cached by design JSON).
  const summaryState = useDesignSummary(displayed?.design ?? null, stream.requirement);
  const summary = summaryState.summary;

  const tier = stream.tier ?? displayed?.design.tier ?? null;

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

  if (workspace) return <WorkbenchPanel onOpenDesign={() => setWorkspace(false)} />;

  return (
    <main className="app">
      <StatusStrip status={stream.status} attemptCount={stream.attemptCount} />
      <div className="app-columns">
        <section className="column column-chat">
          <button onClick={() => setWorkspace(true)}>製作ワークベンチに戻る</button>
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
            <ModelViewer
              design={displayed?.design ?? null}
              tier={tier}
              origin={displayed?.origin ?? null}
              reference={stream.reference}
              dimensions={summary?.dimensions ?? null}
              notes={notes}
            />
            <PrintExports design={displayed?.design}/>
            <CostPanel
              summary={summary}
              fallbackCostJpy={fallbackCost}
              loading={summaryState.loading}
              error={summaryState.error}
            />
          </section>
          <section className="column column-right">
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
