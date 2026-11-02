"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS_STYLE, GRID_STROKE, SERIES, TOOLTIP_STYLE } from "../lib/chartTheme";
import { fmt } from "../lib/format";
import { isOrbital, type TracePoint, type Tier } from "../lib/types";

interface FlightChartProps {
  tier: Tier | null;
  /** Trace of the displayed attempt (simulate_design result). */
  trace: TracePoint[];
  /** source_id of the attempt the trace belongs to (caption). */
  sourceId: string | null;
  /** Compact (right column) or full-height (詳細) chart. */
  compact?: boolean;
}

interface AltitudeRow {
  t_s: number;
  altitude: number;
  downrange: number;
  speed_mps: number;
}

const toFixed1 = (v: unknown): string => fmt(Number(v), 1);
const toFixed0 = (v: unknown): string => fmt(Number(v), 0);

/**
 * 軌道／飛行: commercial / heavy show the ascent profile (altitude vs downrange, km);
 * bottle / amateur show altitude vs time (m, s). One chart; the dispersion lives in 詳細.
 */
export default function FlightChart({ tier, trace, sourceId, compact = true }: FlightChartProps) {
  const orbital = isOrbital(tier);
  const scale = orbital ? 1 / 1000 : 1;
  const rows: AltitudeRow[] = trace.map((p) => ({
    t_s: p.t_s,
    altitude: p.altitude_m * scale,
    downrange: p.downrange_m * scale,
    speed_mps: p.speed_mps,
  }));
  const title = orbital ? "軌道（上昇プロファイル）" : "飛行（高度の推移）";
  const caption = orbital ? "高度 [km] 対 水平距離 [km]" : "高度 [m] 対 時間 [s]";
  const chartClass = compact ? "chart chart-compact" : "chart";

  return (
    <div className="panel flight-panel">
      <div className="panel-header">
        <h2 className="panel-title">{title}</h2>
        <span className="muted chart-caption-inline">
          {caption}
          {sourceId ? ` · ${sourceId}` : ""}
        </span>
      </div>
      {rows.length === 0 ? (
        <div className="placeholder placeholder-short">シミュレーション結果が届くと飛行軌跡を表示します</div>
      ) : orbital ? (
        <div className={chartClass}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="downrange"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" km"
              />
              <YAxis dataKey="altitude" tick={AXIS_STYLE} tickFormatter={toFixed0} width={48} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(v) => `水平距離 ${toFixed1(v)} km`}
                formatter={(v): [string, string] => [`${toFixed1(v)} km`, "高度"]}
              />
              <Line type="monotone" dataKey="altitude" stroke={SERIES.ascent} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className={chartClass}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="t_s"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" s"
              />
              <YAxis dataKey="altitude" tick={AXIS_STYLE} tickFormatter={toFixed0} width={48} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(v) => `t = ${toFixed1(v)} s`}
                formatter={(v): [string, string] => [`${toFixed0(v)} m`, "高度"]}
              />
              <Line type="monotone" dataKey="altitude" stroke={SERIES.altitude} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
