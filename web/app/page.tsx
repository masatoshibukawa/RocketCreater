"use client";

import { useCallback, useMemo, useState } from "react";
import AttemptLog from "./components/AttemptLog";
import CandidateCards from "./components/CandidateCards";
import ChatPanel from "./components/ChatPanel";
import FlightChart from "./components/FlightChart";
import TierBadge from "./components/TierBadge";
import { useDesignStream } from "./lib/useDesignStream";
import type { LandingPoint, Tier, TracePoint } from "./lib/types";

/** Mirrors config/models.yaml `max_attempts` (display only; the backend enforces the budget). */
const MAX_ATTEMPTS = 40;

export default function Home() {
  const stream = useDesignStream();
  const { start, stop, reset } = stream;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewTier, setViewTier] = useState<Tier | null>(null);

  // The right panel follows the classified tier unless the user overrides the view.
  const tier: Tier | null = viewTier ?? stream.tier;

  // Selection falls back to the newest candidate, then the newest attempt.
  const effectiveId: string | null = useMemo(() => {
    if (selectedId !== null) return selectedId;
    const lastCandidate = stream.candidates[stream.candidates.length - 1];
    if (lastCandidate) return lastCandidate.source_id;
    const lastAttempt = stream.attempts[stream.attempts.length - 1];
    return lastAttempt ? lastAttempt.id : null;
  }, [selectedId, stream.candidates, stream.attempts]);

  const selectedAttempt = useMemo(
    () => (effectiveId === null ? undefined : stream.attempts.find((a) => a.id === effectiveId)),
    [effectiveId, stream.attempts],
  );
  const trace: TracePoint[] = selectedAttempt?.result?.trace ?? [];
  const landing: LandingPoint | null = useMemo(() => {
    const m = selectedAttempt?.result?.metrics;
    if (!m) return null;
    const east = m.landing_east_m;
    const north = m.landing_north_m;
    return typeof east === "number" && typeof north === "number" ? { east_m: east, north_m: north } : null;
  }, [selectedAttempt]);

  const handleStart = useCallback(
    (text: string, seed: number | null) => {
      setSelectedId(null);
      setViewTier(null);
      void start(text, seed);
    },
    [start],
  );
  const handleReset = useCallback(() => {
    setSelectedId(null);
    setViewTier(null);
    reset();
  }, [reset]);

  return (
    <main className="app">
      <section className="column column-left">
        <ChatPanel
          messages={stream.messages}
          status={stream.status}
          onStart={handleStart}
          onStop={stop}
          onReset={handleReset}
        />
      </section>
      <section className="column column-right">
        <TierBadge
          tier={stream.tier}
          classify={stream.classify}
          attemptCount={stream.attemptCount}
          maxAttempts={MAX_ATTEMPTS}
          status={stream.status}
          viewTier={viewTier}
          onViewTierChange={setViewTier}
        />
        <AttemptLog attempts={stream.attempts} tier={tier} selectedId={effectiveId} onSelect={setSelectedId} />
        <CandidateCards
          candidates={stream.candidates}
          tier={tier}
          selectedId={effectiveId}
          onSelect={setSelectedId}
        />
        <FlightChart
          tier={tier}
          trace={trace}
          landing={landing}
          dispersion={stream.dispersion}
          selectedId={effectiveId}
        />
      </section>
    </main>
  );
}
