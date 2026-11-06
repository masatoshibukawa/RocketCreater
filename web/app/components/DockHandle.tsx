"use client";

import type { KeyboardEvent, PointerEvent } from "react";

const KEY_STEP_PX = 16;

/** The edge of a dock: drag it, or use the arrow keys, to change the dock's width. */
export default function DockHandle({ side, label, width, onResize }: {
  side: "left" | "right"; label: string; width: number; onResize: (width: number) => void;
}) {
  const direction = side === "left" ? 1 : -1;
  function start(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const handle = event.currentTarget;
    const origin = event.clientX;
    handle.setPointerCapture(event.pointerId);
    handle.dataset.dragging = "true";
    const move = (next: globalThis.PointerEvent) => onResize(width + direction * (next.clientX - origin));
    const end = () => {
      delete handle.dataset.dragging;
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }
  function key(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    onResize(width + (event.key === "ArrowRight" ? KEY_STEP_PX : -KEY_STEP_PX) * direction);
  }
  return <div className={`dock-handle dock-handle-${side}`} role="separator" aria-orientation="vertical"
    aria-label={label} aria-valuenow={width} tabIndex={0} onPointerDown={start} onKeyDown={key}/>;
}
