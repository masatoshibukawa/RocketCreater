"use client";

import { fmt, fmtJpy, fmtPercent, formatMetric, keyMetrics, metricLabel } from "../lib/format";
import type { Candidate, Design, Tier } from "../lib/types";

interface CandidateCardsProps {
  candidates: Candidate[];
  tier: Tier | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Design variables, rendered per design family (discriminated on design.tier). */
function DesignVars({ design }: { design: Design }) {
  if (design.tier === "commercial" || design.tier === "heavy") {
    return (
      <>
        <div className="card-section">段構成</div>
        <table className="table">
          <thead>
            <tr>
              <th>段</th>
              <th>エンジン</th>
              <th className="num">基数</th>
              <th className="num">推進剤</th>
              <th className="num">構造比</th>
            </tr>
          </thead>
          <tbody>
            {design.stages.map((s, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td className="mono">{s.engine_id}</td>
                <td className="num">{s.engine_count}</td>
                <td className="num">{fmt(s.propellant_mass_kg, 0)} kg</td>
                <td className="num">{fmtPercent(s.structural_fraction)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="kv" style={{ marginTop: 6 }}>
          {design.boosters.length > 0 && (
            <>
              <dt>ブースタ</dt>
              <dd>{design.boosters.map((b) => `${b.booster_id} x${b.count}`).join(", ")}</dd>
            </>
          )}
          <dt>フェアリング</dt>
          <dd>{fmt(design.fairing_mass_kg, 0)} kg</dd>
          <dt>積載質量</dt>
          <dd>{fmt(design.payload_mass_kg, 1)} kg</dd>
          <dt>ピッチ開始 / 角度</dt>
          <dd>
            {fmt(design.pitch_start_s, 1)} s / {fmt(design.initial_pitch_deg, 1)}°
          </dd>
        </dl>
      </>
    );
  }
  if (design.tier === "amateur") {
    const f = design.fins;
    return (
      <dl className="kv">
        <dt>機体 直径 / 全長</dt>
        <dd>
          {fmt(design.body_diameter_m * 1000, 0)} mm / {fmt(design.body_length_m, 2)} m
        </dd>
        <dt>ノーズ</dt>
        <dd>
          {design.nose_shape} {fmt(design.nose_length_m * 1000, 0)} mm
        </dd>
        <dt>フィン</dt>
        <dd>
          {f.count} 枚, 翼根 {fmt(f.root_chord_m * 1000, 0)} / 翼端 {fmt(f.tip_chord_m * 1000, 0)} / スパン{" "}
          {fmt(f.span_m * 1000, 0)} mm
        </dd>
        <dt>モーター</dt>
        <dd>{design.motor_id}</dd>
        <dt>乾燥質量 / 積載</dt>
        <dd>
          {fmt(design.dry_mass_kg, 2)} / {fmt(design.payload_mass_kg, 2)} kg
        </dd>
        <dt>パラシュート</dt>
        <dd>
          φ{fmt(design.parachute_diameter_m, 2)} m, 遅延 {fmt(design.deploy_delay_s, 1)} s
        </dd>
      </dl>
    );
  }
  return (
    <dl className="kv">
      <dt>ボトル容量</dt>
      <dd>{fmt(design.bottle_volume_m3 * 1000, 2)} L</dd>
      <dt>水の充填率</dt>
      <dd>{fmtPercent(design.water_fill_frac)}</dd>
      <dt>初期ゲージ圧</dt>
      <dd>{fmt(design.initial_gauge_pressure_pa / 1000, 0)} kPa</dd>
      <dt>ノズル径</dt>
      <dd>{fmt(design.nozzle_diameter_m * 1000, 1)} mm</dd>
      <dt>乾燥質量 / 積載</dt>
      <dd>
        {fmt(design.dry_mass_kg, 3)} / {fmt(design.payload_mass_kg, 3)} kg
      </dd>
      <dt>羽根 / パラシュート</dt>
      <dd>
        {design.has_fins ? "あり" : "なし"} /{" "}
        {design.has_parachute
          ? `あり${design.parachute_diameter_m !== null ? ` φ${fmt(design.parachute_diameter_m, 2)} m` : ""}`
          : "なし"}
      </dd>
    </dl>
  );
}

export default function CandidateCards({ candidates, tier, selectedId, onSelect }: CandidateCardsProps) {
  const specs = keyMetrics(tier);
  const keySet = new Set(specs.map((s) => s.key));
  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">設計案</h2>
        <span className="muted">{candidates.length} 件</span>
      </div>
      {candidates.length === 0 ? (
        <div className="empty">合格した設計案がここにカードで並びます</div>
      ) : (
        <div className="cards">
          {candidates.map((c, i) => {
            const selected = c.source_id === selectedId;
            const others = Object.entries(c.metrics).filter(([k]) => !keySet.has(k));
            return (
              <div
                key={c.source_id}
                className={`card${selected ? " card-selected" : ""}`}
                onClick={() => onSelect(c.source_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onSelect(c.source_id);
                }}
              >
                <div className="card-header">
                  <span className="card-title">
                    案 {i + 1} <small className="muted mono">{c.source_id}</small>
                  </span>
                  <span>
                    {c.inFinal && <span className="chip chip-muted">最終</span>}{" "}
                    <span className={`chip ${c.passed ? "chip-ok" : "chip-bad"}`}>
                      {c.passed ? "合格" : "不合格"}
                    </span>
                  </span>
                </div>
                <DesignVars design={c.design} />
                <div className="card-section">主要指標</div>
                <dl className="kv">
                  {specs.map((s) => {
                    const v = c.metrics[s.key];
                    return v === undefined ? null : (
                      <Metric key={s.key} label={s.label} value={s.format(v)} />
                    );
                  })}
                  <dt>費用</dt>
                  <dd>{fmtJpy(c.cost_jpy)}</dd>
                  {c.success_rate !== null && (
                    <>
                      <dt>成功率</dt>
                      <dd>{fmtPercent(c.success_rate)}</dd>
                    </>
                  )}
                </dl>
                {others.length > 0 && (
                  <details>
                    <summary className="card-section">その他の指標 ({others.length})</summary>
                    <dl className="kv">
                      {others.map(([k, v]) => (
                        <Metric key={k} label={metricLabel(k)} value={formatMetric(k, v)} />
                      ))}
                    </dl>
                  </details>
                )}
                {c.failure_reasons.length > 0 && (
                  <div className="fail-reasons" style={{ marginTop: 6 }}>
                    {c.failure_reasons.join(" / ")}
                  </div>
                )}
                {c.explanation && <div className="card-explanation">{c.explanation}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
