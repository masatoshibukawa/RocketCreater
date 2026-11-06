"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";

const STORAGE = "rocketwright.docks.v1";
const DOCK_MIN_PX = 240;
const DOCK_MAX_FRACTION = 0.42;
const DEFAULT_WIDTHS = { left: 320, right: 340 };

function clampWidth(width: number): number {
  const limit = Math.max(DOCK_MIN_PX, window.innerWidth * DOCK_MAX_FRACTION);
  return Math.round(Math.min(Math.max(width, DOCK_MIN_PX), limit));
}

/** Widths of the two docks, kept in this browser. */
export function useDockWidths() {
  const [widths, setWidths] = useState(DEFAULT_WIDTHS);
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(STORAGE) ?? "null");
      if (saved && typeof saved === "object" && "left" in saved && "right" in saved
        && typeof saved.left === "number" && typeof saved.right === "number") {
        setWidths({ left: clampWidth(saved.left), right: clampWidth(saved.right) });
      }
    } catch { /* Storage can be disabled; the docks then start at their defaults. */ }
  }, []);
  const save = useCallback((next: typeof DEFAULT_WIDTHS) => {
    setWidths(next);
    try { localStorage.setItem(STORAGE, JSON.stringify(next)); } catch { /* Optional preference. */ }
  }, []);
  const setLeft = useCallback((left: number) => save({ ...widths, left: clampWidth(left) }), [save, widths]);
  const setRight = useCallback((right: number) => save({ ...widths, right: clampWidth(right) }), [save, widths]);
  const style = useMemo(
    () => ({ "--dock-left": `${widths.left}px`, "--dock-right": `${widths.right}px` }) as CSSProperties,
    [widths],
  );
  return { ...widths, setLeft, setRight, style };
}
