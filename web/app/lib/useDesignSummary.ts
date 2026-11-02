"use client";

/**
 * Fetch POST /artifacts/summary (cost breakdown, BOM, drawing, mass, dimensions) for the
 * displayed design, plus the SVG text of its drawing. Debounced (the stream can switch the
 * displayed design several times a second) and cached by the design's canonical JSON for the
 * life of the page, so flipping between candidates never refetches.
 */

import { useEffect, useState } from "react";
import { fetchArtifactText, fetchDesignSummary } from "./api";
import { canonicalJson } from "./designState";
import type { Design, DesignSummary } from "./types";

export interface SummaryState {
  summary: DesignSummary | null;
  /** Inline SVG text of `summary.drawing.url`, once fetched. */
  svg: string | null;
  loading: boolean;
  error: string | null;
}

const DEBOUNCE_MS = 300;

interface CacheEntry {
  summary: DesignSummary;
  svg: string | null;
}

// Module-level cache: the same design JSON always yields the same summary (the backend is
// deterministic), so there is no reason to refetch within one page load.
const cache = new Map<string, CacheEntry>();

const EMPTY: SummaryState = { summary: null, svg: null, loading: false, error: null };

export function useDesignSummary(
  design: Design | null,
  requirement: Record<string, unknown> | null,
): SummaryState {
  const key = design === null ? "" : canonicalJson(design);
  const [state, setState] = useState<SummaryState>(EMPTY);

  useEffect(() => {
    if (key === "") {
      setState(EMPTY);
      return undefined;
    }
    const cached = cache.get(key);
    if (cached) {
      setState({ summary: cached.summary, svg: cached.svg, loading: false, error: null });
      return undefined;
    }
    const controller = new AbortController();
    // Keep the previous summary on screen while the new one loads (no flicker).
    setState((prev) => ({ ...prev, loading: true, error: null }));
    const timer = window.setTimeout(() => {
      const parsed = JSON.parse(key) as Design;
      fetchDesignSummary(parsed, requirement, controller.signal)
        .then(async (summary) => {
          let svg: string | null = null;
          if (summary.drawing !== null) {
            try {
              svg = await fetchArtifactText(summary.drawing.url, controller.signal);
            } catch {
              svg = null; // the drawing is optional; the download link still works
            }
          }
          if (controller.signal.aborted) return;
          cache.set(key, { summary, svg });
          setState({ summary, svg, loading: false, error: null });
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          const message = err instanceof Error ? err.message : String(err);
          setState((prev) => ({ ...prev, loading: false, error: message }));
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
    // `requirement` is deliberately not a dependency: the cache key is the design, and the
    // requirement only changes when a new run starts (which also changes the design).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}
