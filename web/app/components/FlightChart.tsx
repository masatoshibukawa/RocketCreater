"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmt, fmtPercent } from "../lib/format";
import { isOrbital, type DispersionSummary, type LandingPoint, type TracePoint, type Tier } from "../lib/types";

interface FlightChartProps {
  tier: Tier | null;
  trace: TracePoint[];
  /** Single-shot landing point from the selected attempt's metrics (bottle/amateur), if any. */
  landing: LandingPoint | null;
  dispersion: DispersionSummary | null;
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

/** Flight graph for the selected candidate. Orbital tiers add the ascent profile; suborbital
 * tiers show the landing scatter panel (placeholder until run_dispersion results arrive). */
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
          <LandingScatter landing={landing} dispersion={dispersion} />
        )}
      </div>
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

/** Landing-point scatter for bottle / amateur. Uses run_dispersion points when available,
 * otherwise the single landing point of the selected attempt, otherwise a placeholder. */
function LandingScatter({
  landing,
  dispersion,
}: {
  landing: LandingPoint | null;
  dispersion: DispersionSummary | null;
}) {
  const points: LandingPoint[] =
    dispersion && dispersion.landing_points.length > 0
      ? dispersion.landing_points
      : landing
        ? [landing]
        : [];
  const caption =
    dispersion && dispersion.landing_points.length > 0
      ? `着地点の散布 (n=${dispersion.n}, 成功率 ${
          Number.isFinite(dispersion.success_rate) ? fmtPercent(dispersion.success_rate) : "-"
        })`
      : "着地点 [m]（東 / 北）";
  return (
    <div>
      <p className="chart-caption">{caption}</p>
      {points.length === 0 ? (
        <div className="placeholder">多数回試行の結果はフェーズ3で表示</div>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="east_m"
                type="number"
                name="東"
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" m"
              />
              <YAxis
                dataKey="north_m"
                type="number"
                name="北"
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" m"
                width={64}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} />
              <Scatter data={points} fill="#3fbf7f" isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
      {points.length === 1 && (
        <p className="chart-caption">単発シミュレーションの着地点。散布はフェーズ3の多数回試行で表示。</p>
      )}
    </div>
  );
}
