"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { drawFlight } from "../lib/flightCanvas";
import {
  buildTimeline,
  PHASE_COLOR,
  phaseAt,
  phaseLabel,
  phaseSpans,
  playbackSpeeds,
  sampleIndexAt,
  thrustOf,
} from "../lib/flightPlayback";
import { fmt } from "../lib/format";
import type { TracePoint } from "../lib/types";

interface FlightPlayerProps {
  /** Time series from the simulation (API result, never made up here). */
  trace: TracePoint[];
  metrics: Record<string, number>;
  warnings: string[];
  parachute: boolean;
  /** Shown instead of the player when the trace cannot be played. */
  emptyMessage: string;
}

const MAX_FRAME_S = 0.1; // a throttled tab must not jump ahead
const SUMMARY: readonly { key: string; label: string; unit: string; digits: number }[] = [
  { key: "apogee_m", label: "頂点の高度", unit: "m", digits: 2 },
  { key: "max_speed_mps", label: "最大速度", unit: "m/s", digits: 2 },
  { key: "peak_thrust_n", label: "最大推力", unit: "N", digits: 1 },
  { key: "descent_speed_mps", label: "降下速度", unit: "m/s", digits: 2 },
  { key: "flight_time_s", label: "飛行時間", unit: "s", digits: 2 },
  { key: "landing_distance_m", label: "着地点までの距離", unit: "m", digits: 2 },
];

/** Plays a simulated flight on a canvas, with the sample values kept in step with it. */
export default function FlightPlayer({ trace, metrics, warnings, parachute, emptyMessage }: FlightPlayerProps) {
  const timeline = useMemo(() => buildTimeline(trace), [trace]);
  const [timeS, setTimeS] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const timeRef = useRef(0);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const seek = (next: number): void => {
    timeRef.current = next;
    setTimeS(next);
  };

  useEffect(() => {
    setPlaying(false);
    if (!timeline) return;
    seek(timeline.startS);
    setSpeed(playbackSpeeds(timeline).initial);
  }, [timeline]);

  useEffect(() => {
    if (!playing || !timeline) return;
    let frame = 0;
    let previous = performance.now();
    const tick = (now: number): void => {
      const elapsed = Math.min((now - previous) / 1000, MAX_FRAME_S);
      previous = now;
      const next = Math.min(timeRef.current + elapsed * speed, timeline.endS);
      seek(next);
      if (next >= timeline.endS) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, timeline]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(stage);
    return () => observer.disconnect();
  }, [timeline]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !timeline || size.width === 0 || size.height === 0) return;
    const ratio = window.devicePixelRatio || 1;
    const width = Math.round(size.width * ratio);
    const height = Math.round(size.height * ratio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    drawFlight(ctx, size.width, size.height, timeline, timeS, parachute);
  }, [timeline, timeS, size, parachute]);

  if (!timeline) return <div className="placeholder">{emptyMessage}</div>;

  const sample = timeline.points[sampleIndexAt(timeline, timeS)];
  const thrust = thrustOf(sample);
  const phase = phaseAt(timeline, timeS);
  const finished = timeS >= timeline.endS;
  const { speeds } = playbackSpeeds(timeline);
  const longRange = timeline.points[timeline.apogeeIndex].altitude_m >= 10_000;
  const speedText = sample.speed_mps >= 1000 ? `${fmt(sample.speed_mps / 1000, 2)} km/s` : `${fmt(sample.speed_mps, 2)} m/s`;
  const altitude = longRange ? `${fmt(sample.altitude_m / 1000, 2)} km` : `${fmt(sample.altitude_m, 2)} m`;
  const lastAltitude = timeline.points[timeline.points.length - 1].altitude_m;
  const summary = SUMMARY.filter((row) => typeof metrics[row.key] === "number");

  return (
    <div className="flight-player">
      <dl className="flight-readouts" aria-label="再生中の時系列の値">
        <div><dt>時刻</dt><dd data-readout="time">{fmt(sample.t_s, 2)} s</dd></div>
        <div><dt>高度</dt><dd data-readout="altitude">{altitude}</dd></div>
        <div><dt>速度</dt><dd data-readout="speed">{speedText}</dd></div>
        <div><dt>推力</dt><dd data-readout="thrust">{thrust === null ? "記録なし" : `${fmt(thrust, 1)} N`}</dd></div>
      </dl>
      <div className="flight-stage" ref={stageRef}>
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={`飛行のアニメーション。現在は${phaseLabel(phase, parachute)}、高度 ${altitude}`}
        />
      </div>
      <input
        className="flight-seek"
        type="range"
        aria-label="再生位置"
        min={timeline.startS}
        max={timeline.endS}
        step="any"
        value={timeS}
        onChange={(e) => {
          setPlaying(false);
          seek(Number(e.target.value));
        }}
      />
      <div className="flight-controls">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            if (!playing && finished) seek(timeline.startS);
            setPlaying(!playing);
          }}
        >
          {playing ? "一時停止" : "再生"}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setPlaying(false);
            seek(timeline.startS);
          }}
        >
          最初に戻す
        </button>
        <div className="flight-speeds" role="group" aria-label="再生速度">
          {speeds.map((value) => (
            <button
              key={value}
              type="button"
              className={`btn ${value === speed ? "is-active" : ""}`}
              aria-pressed={value === speed}
              onClick={() => setSpeed(value)}
            >
              {value}×
            </button>
          ))}
        </div>
      </div>
      <ul className="flight-phases" aria-label="飛行の段階">
        {phaseSpans(timeline).map((span) => (
          <li key={span.phase} className={span.phase === phase ? "is-current" : ""}>
            <i style={{ background: PHASE_COLOR[span.phase] }} />
            {phaseLabel(span.phase, parachute)} {fmt(span.fromS, 2)}〜{fmt(span.toS, 2)} s
          </li>
        ))}
      </ul>
      {!timeline.reachesGround ? (
        <p className="warn-box">
          この時系列は高度 {fmt(lastAltitude / (longRange ? 1000 : 1), 1)} {longRange ? "km" : "m"}
          （{fmt(timeline.endS, 1)} s）で終わります。その先と着地の値はシミュレーション結果にないため、描いていません。
        </p>
      ) : null}
      {summary.length > 0 ? (
        <dl className="flight-summary">
          {summary.map((row) => (
            <div key={row.key}>
              <dt>{row.label}</dt>
              <dd>{fmt(metrics[row.key], row.digits)} {row.unit}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {warnings.length > 0 ? (
        <ul className="flight-warnings">
          {warnings.map((text) => <li key={text}>{text}</li>)}
        </ul>
      ) : null}
      <p className="flight-note">
        数値は時系列の標本の値です。機体の図の大きさは目盛りと別で、向きは軌跡に沿わせた表示です。
      </p>
    </div>
  );
}
