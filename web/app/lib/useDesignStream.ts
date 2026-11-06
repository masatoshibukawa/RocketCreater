"use client";

/**
 * React hook that POSTs a request to the backend and folds the SSE stream into DesignState.
 * The stream is read with `fetch` + ReadableStream because EventSource cannot POST.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, reduce, type DesignState } from "./designState";
import { parseSseChunk } from "./sse";
import { API_BASE } from "./api";
import { isEventType, type AgentEvent } from "./types";

export { API_BASE };

export interface DesignStream extends DesignState {
  /** Send a request. `seed` is forwarded when given (deterministic demo runs). */
  start: (text: string, seed?: number | null) => Promise<void>;
  /**
   * Answer a clarifying `question` event. POST /design has no conversation memory (it takes a
   * single `text`), so the answer is appended to the request so far
   * ("<request>\n\n追加情報: <answer>") and the loop is restarted with the same seed.
   */
  answer: (text: string) => Promise<void>;
  /** Abort the in-flight request, keeping what was received so far. */
  stop: () => void;
  /** Abort and clear all state. */
  reset: () => void;
}

/** Chat line for a refused POST /design. 423 is the switched-off paid API, not a fault. */
export function designRefusalMessage(status: number, detail: string): string {
  if (status === 423) {
    return "Claude の設計は今オフです（課金 API の実行が無効です）。要求は送信されていません。条件を決めた計算は「製作ワークベンチ」で実行できます。";
  }
  return `バックエンドが HTTP ${status} を返しました ${detail.slice(0, 200)}`;
}

/** Validate one decoded SSE `data` payload against AgentEvent. `fallbackType` is the SSE event name. */
export function toAgentEvent(raw: unknown, fallbackType: string): AgentEvent | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const rec = raw as Record<string, unknown>;
  const type = isEventType(rec.type) ? rec.type : isEventType(fallbackType) ? fallbackType : null;
  if (type === null) return null;
  const payload =
    typeof rec.payload === "object" && rec.payload !== null && !Array.isArray(rec.payload)
      ? (rec.payload as Record<string, unknown>)
      : {};
  const attempt = typeof rec.attempt === "number" ? rec.attempt : 0;
  const t_s = typeof rec.t_s === "number" ? rec.t_s : 0;
  return { type, attempt, payload, t_s };
}

export function useDesignStream(): DesignStream {
  const [state, dispatch] = useReducer(reduce, initialState);
  const abortRef = useRef<AbortController | null>(null);
  // The request text and seed of the current run, so an answer can restart with them.
  const requestRef = useRef<string>("");
  const seedRef = useRef<number | null>(null);

  const stop = useCallback(() => {
    const active = abortRef.current;
    if (active === null) return;
    abortRef.current = null;
    active.abort();
    // The aborted fetch rejects asynchronously; settle the status here so that a `start`
    // issued right after `stop` cannot be overwritten by the old request's teardown.
    dispatch({ type: "stream_end" });
  }, []);

  const reset = useCallback(() => {
    stop();
    dispatch({ type: "reset" });
  }, [stop]);

  // Abort any in-flight request when the component unmounts.
  useEffect(() => stop, [stop]);

  const start = useCallback(
    async (text: string, seed?: number | null) => {
      const trimmed = text.trim();
      if (trimmed === "") return;
      stop();
      const controller = new AbortController();
      abortRef.current = controller;
      requestRef.current = trimmed;
      seedRef.current = typeof seed === "number" && Number.isFinite(seed) ? seed : null;
      dispatch({ type: "start", text: trimmed });

      const handleMessage = (eventName: string, data: string): void => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(data);
        } catch {
          dispatch({ type: "fail", message: `SSE データを JSON として読めません: ${data.slice(0, 120)}` });
          return;
        }
        const event = toAgentEvent(parsed, eventName);
        if (event) dispatch({ type: "event", event });
      };

      try {
        const body: Record<string, unknown> = { text: trimmed };
        if (typeof seed === "number" && Number.isFinite(seed)) body.seed = seed;
        const res = await fetch(`${API_BASE}/design`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        if (!res.ok) {
          const detail = await res.text().catch(() => "");
          dispatch({ type: "fail", message: designRefusalMessage(res.status, detail) });
          return;
        }
        if (!res.body) {
          dispatch({ type: "fail", message: "レスポンスにストリーム本文がありません" });
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { events, rest } = parseSseChunk(buffer);
          buffer = rest;
          for (const m of events) handleMessage(m.event, m.data);
        }
        // Flush the decoder and any final block that lacked a trailing blank line.
        buffer += decoder.decode();
        const tail = parseSseChunk(`${buffer}\n\n`);
        for (const m of tail.events) handleMessage(m.event, m.data);
        dispatch({ type: "stream_end" });
      } catch (err) {
        // `stop` already settled the status for an aborted request.
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        dispatch({ type: "fail", message: `接続エラー: ${message} (${API_BASE})` });
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [stop],
  );

  const answer = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (trimmed === "") return;
      const base = requestRef.current;
      const combined = base === "" ? trimmed : `${base}\n\n追加情報: ${trimmed}`;
      await start(combined, seedRef.current);
    },
    [start],
  );

  return { ...state, start, answer, stop, reset };
}
