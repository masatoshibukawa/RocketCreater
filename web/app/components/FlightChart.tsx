"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt } from "../lib/format";
import { isOrbital, type DispersionResult, type LandingPoint, type TracePoint, type Tier } from "../lib/types";
import DispersionPanel from "./DispersionPanel";

interface FlightChartProps {
  tier: Tier | null;
  trace: TracePoint[];
  /** Single-shot landing point from the selected attempt's metrics (bottle/amateur), if any. */
  landing: LandingPoint | null;
  /** run_dispersion result for the selected candidate (or the latest one as a fallback). */
  dispersion: DispersionResult | null;
  selectedId: string | null;
}

interface AltitudeRow {
  t_s: number;
  altitude: number;
  downrange: number;
  speed_mps: number;
}

const AXIS_STYLE = { fill: "#9aa3ad", fontSize: 11 };
const GRID_STROKE = "#343941";
const TOOLTIP_STYLE = {
  backgroundColor: "#1e2127",
  border: "1px solid #343941",
  borderRadius: 6,
  fontSize: 12,
};

const toFixed1 = (v: unknown): string => fmt(Number(v), 1);
const toFixed0 = (v: unknown): string => fmt(Number(v), 0);

/** Flight graph for the selected candidate. Orbital tiers add the ascent profile and, below it,
 * the insertion-error dispersion; suborbital tiers show the landing scatter with its 95 %
 * ellipse (DispersionPanel) next to the altitude plot. */
export default function FlightChart({ tier, trace, landing, dispersion, selectedId }: FlightChartProps) {
  const orbital = isOrbital(tier);
  const unit = orbital ? "km" : "m";
  const scale = orbital ? 1 / 1000 : 1;
  const rows: AltitudeRow[] = trace.map((p) => ({
    t_s: p.t_s,
    altitude: p.altitude_m * scale,
    downrange: p.downrange_m * scale,
    speed_mps: p.speed_mps,
  }));
  const yFormat = orbital ? toFixed1 : toFixed0;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">{orbital ? "飛行解析（上昇軌道）" : "飛行解析（仮想打ち上げ）"}</h2>
        <span className="muted mono">{selectedId ?? "案を選択してください"}</span>
      </div>
      <div className="charts charts-two">
        <div>
          <p className="chart-caption">高度 [{unit}] 対 時間 [s]</p>
          {rows.length === 0 ? (
            <div className="placeholder">試行ログか設計案を選ぶと飛行軌跡を表示します</div>
          ) : (
            <div className="chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t_s"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tick={AXIS_STYLE}
                    tickFormatter={toFixed0}
                    unit=" s"
                  />
                  <YAxis dataKey="altitude" tick={AXIS_STYLE} tickFormatter={yFormat} width={56} />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    labelFormatter={(v) => `t = ${toFixed1(v)} s`}
                    formatter={(v): [string, string] => [`${yFormat(v)} ${unit}`, "高度"]}
                  />
                  <Line
                    type="monotone"
                    dataKey="altitude"
                    stroke="#5ab0ff"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        {orbital ? (
          <AscentProfile rows={rows} />
        ) : (
          <DispersionPanel tier={tier} dispersion={dispersion} landing={landing} selectedId={selectedId} />
        )}
      </div>
      {orbital && (
        <div style={{ marginTop: 12 }}>
          <DispersionPanel tier={tier} dispersion={dispersion} landing={landing} selectedId={selectedId} />
        </div>
      )}
    </div>
  );
}

/** Downrange vs altitude (km) for commercial / heavy. */
function AscentProfile({ rows }: { rows: AltitudeRow[] }) {
  return (
    <div>
      <p className="chart-caption">上昇プロファイル: 高度 [km] 対 水平距離 [km]</p>
      {rows.length === 0 ? (
        <div className="placeholder">上昇軌道はここに表示されます</div>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="downrange"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" km"
              />
              <YAxis dataKey="altitude" tick={AXIS_STYLE} tickFormatter={toFixed0} width={56} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={(v) => `水平距離 ${toFixed1(v)} km`}
                formatter={(v): [string, string] => [`${toFixed1(v)} km`, "高度"]}
              />
              <Line
                type="monotone"
                dataKey="altitude"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
