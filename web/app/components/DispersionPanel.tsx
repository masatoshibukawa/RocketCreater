"use client";

import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { fmt, fmtPercent } from "../lib/format";
import { isOrbital, type DispersionResult, type Ellipse95, type LandingPoint, type Quantiles, type Tier } from "../lib/types";

interface DispersionPanelProps {
  tier: Tier | null;
  dispersion: DispersionResult | null;
  /** Single-shot landing point of the selected attempt (bottle/amateur), shown when no
   * run_dispersion result exists yet. */
  landing: LandingPoint | null;
  /** The candidate currently selected; a caption says when the dispersion belongs to another. */
  selectedId: string | null;
}

const AXIS_STYLE = { fill: "#9aa3ad", fontSize: 11 };
const GRID_STROKE = "#343941";
const TOOLTIP_STYLE = {
  backgroundColor: "#1e2127",
  border: "1px solid #343941",
  borderRadius: 6,
  fontSize: 12,
};
const ELLIPSE_SEGMENTS = 64;
const MAX_FAILURE_ROWS = 4;

const toFixed0 = (v: unknown): string => fmt(Number(v), 0);
const toFixed1 = (v: unknown): string => fmt(Number(v), 1);

/** Polygon (closed, ELLIPSE_SEGMENTS + 1 points) tracing the 95 % ellipse. */
export function ellipsePolygon(e: Ellipse95, segments = ELLIPSE_SEGMENTS): LandingPoint[] {
  const theta = (e.angle_deg * Math.PI) / 180;
  const c = Math.cos(theta);
  const s = Math.sin(theta);
  const out: LandingPoint[] = [];
  for (let k = 0; k <= segments; k += 1) {
    const t = (2 * Math.PI * k) / segments;
    const u = e.semi_major_m * Math.cos(t);
    const v = e.semi_minor_m * Math.sin(t);
    out.push({ east_m: e.center_east_m + u * c - v * s, north_m: e.center_north_m + u * s + v * c });
  }
  return out;
}

/** Colour of the big success-rate number (inline so globals.css stays untouched). */
function rateColor(rate: number): string {
  if (!Number.isFinite(rate)) return "#9aa3ad";
  if (rate >= 0.9) return "#3fbf7f";
  if (rate >= 0.6) return "#f5a623";
  return "#ff6b6b";
}

/** Success rate as a large number plus the run's n / seed / matched candidate. */
function RateHeader({ dispersion, selectedId }: { dispersion: DispersionResult; selectedId: string | null }) {
  const rate = dispersion.success_rate;
  const other = dispersion.candidate_id !== null && dispersion.candidate_id !== selectedId;
  const failures = Object.entries(dispersion.failure_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_FAILURE_ROWS);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
      <span
        className="dispersion-rate"
        style={{ fontSize: 30, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: rateColor(rate) }}
        title="run_dispersion success_rate"
      >
        {Number.isFinite(rate) ? fmtPercent(rate) : "-"}
      </span>
      <span className="muted">
        成功率（多数回試行 n={dispersion.n}
        {dispersion.seed !== null ? `, seed ${dispersion.seed}` : ""}）
      </span>
      <span className="muted mono">{dispersion.source_id}</span>
      {other && (
        <span className="chip chip-muted" title="この結果は別の設計案に対するものです">
          対象: {dispersion.candidate_id}
        </span>
      )}
      {failures.length > 0 && (
        <span className="muted" style={{ flexBasis: "100%", fontSize: 12 }}>
          不合格の内訳: {failures.map(([reason, count]) => `${reason} ×${count}`).join(" / ")}
        </span>
      )}
    </div>
  );
}

/** Landing scatter (bottle / amateur): every sample, the 95 % ellipse and the pad at the origin. */
function LandingScatterChart({ dispersion, landing }: { dispersion: DispersionResult | null; landing: LandingPoint | null }) {
  const scatter = dispersion?.landing ?? null;
  const points: LandingPoint[] = scatter && scatter.points.length > 0 ? scatter.points : landing ? [landing] : [];
  const ellipse = scatter && scatter.points.length > 1 ? ellipsePolygon(scatter.ellipse_95) : [];
  const pad: LandingPoint[] = [{ east_m: 0, north_m: 0 }];
  const caption =
    scatter && scatter.points.length > 0
      ? `着地点の散布 [m]（東 / 北）と 95 % 楕円（長半径 ${fmt(scatter.ellipse_95.semi_major_m, 0)} m, 短半径 ${fmt(
          scatter.ellipse_95.semi_minor_m,
          0,
        )} m）`
      : "着地点 [m]（東 / 北）";
  return (
    <div>
      <p className="chart-caption">{caption}</p>
      {points.length === 0 ? (
        <div className="placeholder">run_dispersion の結果（着地点の散布）はここに表示されます</div>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="east_m"
                type="number"
                name="東"
                domain={["auto", "auto"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" m"
              />
              <YAxis
                dataKey="north_m"
                type="number"
                name="北"
                domain={["auto", "auto"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" m"
                width={64}
              />
              <ZAxis zAxisId="dots" range={[28, 28]} />
              <ZAxis zAxisId="line" range={[0, 0]} />
              <ZAxis zAxisId="pad" range={[120, 120]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v): [string, string] => [`${toFixed0(v)} m`, ""]}
              />
              {ellipse.length > 0 && (
                <Scatter
                  name="95 % 楕円"
                  data={ellipse}
                  zAxisId="line"
                  fill="none"
                  line={{ stroke: "#f5a623", strokeWidth: 1.5, strokeDasharray: "5 3" }}
                  isAnimationActive={false}
                />
              )}
              <Scatter name="着地点" data={points} zAxisId="dots" fill="#3fbf7f" isAnimationActive={false} />
              <Scatter name="発射台" data={pad} zAxisId="pad" fill="#ff6b6b" shape="cross" isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
      {points.length === 1 && !scatter && (
        <p className="chart-caption">単発シミュレーションの着地点。run_dispersion を実行すると散布と 95 % 楕円を表示します。</p>
      )}
    </div>
  );
}

interface OrbitRow {
  perigee_km: number;
  apogee_km: number;
  margin_kg: number;
}

/** Insertion scatter (commercial / heavy): (perigee, apogee) of every sample, the nominal run
 * and the requirement's target. */
function OrbitScatterChart({ dispersion }: { dispersion: DispersionResult }) {
  const stats = dispersion.orbit_insertion;
  const rows: OrbitRow[] = (stats?.samples ?? []).map((s) => ({
    perigee_km: s.perigee_m / 1000,
    apogee_km: s.apogee_m / 1000,
    margin_kg: s.payload_margin_kg,
  }));
  const nominalPerigee = dispersion.nominal_metrics.perigee_m;
  const nominalApogee = dispersion.nominal_metrics.apogee_m;
  const nominal: OrbitRow[] =
    typeof nominalPerigee === "number" && typeof nominalApogee === "number"
      ? [{ perigee_km: nominalPerigee / 1000, apogee_km: nominalApogee / 1000, margin_kg: Number.NaN }]
      : [];
  const targetPerigee = dispersion.target_perigee_m;
  const target: OrbitRow[] =
    targetPerigee !== null
      ? [
          {
            perigee_km: targetPerigee / 1000,
            apogee_km: (dispersion.target_apogee_m ?? targetPerigee) / 1000,
            margin_kg: Number.NaN,
          },
        ]
      : [];
  return (
    <div>
      <p className="chart-caption">投入軌道の散布: 遠地点 [km] 対 近地点 [km]（◆ 公称, ✕ 目標）</p>
      {rows.length === 0 ? (
        <div className="placeholder">run_dispersion の結果（投入誤差）はここに表示されます</div>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
              <XAxis
                dataKey="perigee_km"
                type="number"
                name="近地点"
                domain={["auto", "auto"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" km"
              />
              <YAxis
                dataKey="apogee_km"
                type="number"
                name="遠地点"
                domain={["auto", "auto"]}
                tick={AXIS_STYLE}
                tickFormatter={toFixed0}
                unit=" km"
                width={64}
              />
              <ZAxis zAxisId="dots" range={[28, 28]} />
              <ZAxis zAxisId="marks" range={[120, 120]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v): [string, string] => [`${toFixed1(v)} km`, ""]}
              />
              <Scatter name="試行" data={rows} zAxisId="dots" fill="#a78bfa" isAnimationActive={false} />
              {nominal.length > 0 && (
                <Scatter name="公称" data={nominal} zAxisId="marks" fill="#5ab0ff" shape="diamond" isAnimationActive={false} />
              )}
              {target.length > 0 && (
                <Scatter name="目標" data={target} zAxisId="marks" fill="#ff6b6b" shape="cross" isAnimationActive={false} />
              )}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

interface QuantileRow {
  label: string;
  q: Quantiles;
  format: (v: number) => string;
}

const km1 = (v: number): string => `${fmt(v / 1000, 1)} km`;
const kg1 = (v: number): string => `${fmt(v, 1)} kg`;

/** p05 / p50 / p95 of the insertion errors (about the nominal run) and the payload margin. */
function OrbitQuantileTable({ dispersion }: { dispersion: DispersionResult }) {
  const stats = dispersion.orbit_insertion;
  if (!stats) return <div className="placeholder">投入誤差の分位点はここに表示されます</div>;
  const rows: QuantileRow[] = [
    { label: "近地点の誤差（公称比）", q: stats.perigee_error_m, format: km1 },
    { label: "遠地点の誤差（公称比）", q: stats.apogee_error_m, format: km1 },
    { label: "積載余裕", q: stats.payload_margin_kg, format: kg1 },
  ];
  const perigeeQ = dispersion.quantiles.perigee_m;
  if (perigeeQ) rows.push({ label: "近地点（絶対値）", q: perigeeQ, format: km1 });
  const nominalPerigee = dispersion.nominal_metrics.perigee_m;
  const nominalApogee = dispersion.nominal_metrics.apogee_m;
  return (
    <div>
      <p className="chart-caption">
        分位点（5 % / 50 % / 95 %）
        {typeof nominalPerigee === "number" && typeof nominalApogee === "number"
          ? ` — 公称 ${km1(nominalPerigee)} × ${km1(nominalApogee)}`
          : ""}
      </p>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>指標</th>
              <th className="num">p05</th>
              <th className="num">p50</th>
              <th className="num">p95</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{r.format(r.q.p05)}</td>
                <td className="num">{r.format(r.q.p50)}</td>
                <td className="num">{r.format(r.q.p95)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Virtual-launch panel: landing scatter + 95 % ellipse (bottle/amateur) or insertion scatter +
 * quantile table (commercial/heavy), headed by the success rate. */
export default function DispersionPanel({ tier, dispersion, landing, selectedId }: DispersionPanelProps) {
  const orbital = isOrbital(tier);
  if (orbital) {
    return (
      <div>
        {dispersion && <RateHeader dispersion={dispersion} selectedId={selectedId} />}
        <div className="charts charts-two">
          {dispersion ? (
            <>
              <OrbitScatterChart dispersion={dispersion} />
              <OrbitQuantileTable dispersion={dispersion} />
            </>
          ) : (
            <div className="placeholder">run_dispersion の結果（投入誤差の分布）はここに表示されます</div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div>
      {dispersion && <RateHeader dispersion={dispersion} selectedId={selectedId} />}
      <LandingScatterChart dispersion={dispersion} landing={landing} />
    </div>
  );
}
