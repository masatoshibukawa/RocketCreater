"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api";
import { fmt } from "../lib/format";
import type { AeroFrame } from "../lib/useAeroLoop";

const FRAMES_PER_SECOND = 8;

/** The flow as OpenFOAM solved it, frame by frame. While a run is on it plays up to the newest
 * frame and holds there; `loop` replays a finished run. */
export default function FlowVideo({ frames, loop }: { frames: AeroFrame[]; loop: boolean }) {
  const [position, setPosition] = useState(0);
  const count = frames.length;

  useEffect(() => {
    if (count < 2) return;
    const timer = setInterval(() => {
      setPosition((at) => (at + 1 < count ? at + 1 : loop ? 0 : at));
    }, 1000 / FRAMES_PER_SECOND);
    return () => clearInterval(timer);
  }, [count, loop]);

  // Fetched ahead, so a frame is in the cache when its turn comes.
  useEffect(() => {
    for (const frame of frames.slice(position + 1, position + 1 + FRAMES_PER_SECOND)) {
      new Image().src = apiUrl(frame.url);
    }
  }, [frames, position]);

  const frame = frames[Math.min(position, count - 1)];
  if (!frame) return null;
  return <figure className="flow-video">
    <img src={apiUrl(frame.url)} alt={`流速 ${fmt(frame.speed_mps, 0)} m/s、迎角 ${fmt(frame.alpha_deg, 0)}°の流れ（反復 ${frame.iteration}）`}/>
    <figcaption>
      <span>OpenFOAM の計算中の流れ · 流速 {fmt(frame.speed_mps, 0)} m/s · 迎角 {fmt(frame.alpha_deg, 0)}° · 反復 {frame.iteration}</span>
      <span className="flow-video-scale">遅い<i/>速い</span>
    </figcaption>
  </figure>;
}
