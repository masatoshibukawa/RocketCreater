"use client";

import type { WorkbenchProject } from "../lib/workbench";

const METHODS: Record<string, { label: string; purpose: string }> = {
  component: { label: "構成・重心・振動", purpose: "部品の組み合わせが、搭載寸法・重心と復元方向・振動減衰の計算条件を満たすか確かめます。" },
  flight: { label: "飛行と抗力", purpose: "現在の機体で、公称の高度・降下速度と抗力を変えた場合の結果を確かめます。" },
  screen: { label: "条件を変えた試行", purpose: "圧力と風の条件を変え、採用候補を絞り込むための試行です。" },
  confirm: { label: "採用案の独立確認", purpose: "採用候補を固定し、探索に使わなかった条件で計算上の通過率を確認します。" },
};
const CHECKS: Record<string, string> = {
  static_restoring_dry_and_wet: "乾燥・注水時の復元方向", mount_settles: "搭載部の振動減衰", payload_fits: "搭載室の寸法",
};

export default function AnalysisEvidence({ project, viewedIndex, unseen, onLatest }: {
  project: WorkbenchProject | null; viewedIndex: number | null; unseen: number; onLatest: () => void;
}) {
  const index = viewedIndex ?? (project?.history.length ?? 0) - 1;
  const row = project?.history[index];
  const [method, architecture, nozzle, pressure, fill] = row?.chosen.split("/") ?? [];
  const metadata = METHODS[method];
  const result = row?.result ?? {};
  const number = (key: string, suffix: string) => typeof result[key] === "number" ? `${(result[key] as number).toFixed(2)} ${suffix}` : "記録なし";
  const checks = result.checks && typeof result.checks === "object" ? result.checks as Record<string, boolean> : {};
  const passed = method === "component" ? result.eligible === true : method === "flight" ? result.success === true : typeof result.success_rate === "number" ? result.success_rate >= .8 : null;
  return <div className="wb-detail">
    <p className="wb-eyebrow">ANALYSIS / EVIDENCE</p><h2>条件と結果をつなぐ</h2>
    <div className="wb-view-state" role="status">
      <span>{viewedIndex === null ? "最新結果を表示" : `記録 ${index + 1} を固定表示`}</span>
      {viewedIndex !== null ? <button onClick={onLatest}>最新へ戻る{unseen > 0 ? ` · 新着${unseen}件` : ""}</button> : null}
    </div>
    {row ? <article className="wb-analysis-result">
      <h3>{String(index + 1).padStart(2, "0")} / {metadata?.label ?? method}</h3>
      <p className="wb-case-tag">{architecture} · 噴射口 {nozzle} mm · {pressure} kPa · 充填率 {fill}%</p>
      <h4>何を確かめたか</h4><p>{metadata?.purpose ?? row.reason}</p>
      <p className="wb-note">選択した理由: {row.reason}</p>
      <h4>得られた結果</h4>
      <p>{passed === null ? "結果の記録を確認してください。" : passed ? "この解析段階の計算条件を満たしました。" : "この解析段階で満たさない条件がありました。"}</p>
      {method === "component" ? <><dl className="wb-result-values"><div><dt>計算の乾燥質量</dt><dd>{number("dry_mass_g", "g")}</dd></div><div><dt>注水時の重心 / 先端から</dt><dd>{number("wet_cg_mm", "mm")}</dd></div><div><dt>推定圧力中心 / 先端から</dt><dd>{number("cp_mm", "mm")}</dd></div></dl><ul className="wb-checks">{Object.entries(checks).map(([key, value]) => <li key={key}><span className={value ? "wb-pass" : "wb-fail"}>{value ? "✓" : "×"}</span>{CHECKS[key] ?? key}</li>)}</ul></> : null}
      {method === "flight" ? <dl className="wb-result-values"><div><dt>公称高度</dt><dd>{number("apogee_m", "m")}</dd></div><div><dt>定常降下速度</dt><dd>{number("descent_speed_mps", "m/s")}</dd></div><div><dt>ガイド離脱速度</dt><dd>{number("rail_exit_speed_mps", "m/s")}</dd></div></dl> : null}
      {method === "screen" || method === "confirm" ? <p className="wb-case-tag">{String(result.passes)} / {String(result.n)}条件を通過 · {typeof result.success_rate === "number" ? `${(result.success_rate * 100).toFixed(1)}%` : "—"}<br/>計算で設定した条件群の通過率です。実飛行での回収確率はまだ分かりません。</p> : null}
      {Array.isArray(result.failures) && result.failures.length > 0 ? <p className="wb-note">未達の計算条件: {result.failures.map(String).join(" / ")}</p> : null}
      <h4>まだ確かでないこと</h4><p>仮定した寸法・材料・抗力の下での計算です。実物の寸法、取付保持、搭載部の減衰、回収装置の放出と着地は、測定・観察の記録が必要です。</p>
      <details className="wb-evidence"><summary>詳細な計算データを開く</summary><p>{row.chosen}</p><pre>{JSON.stringify(result, null, 2)}</pre></details>
    </article> : <p className="wb-note">工程を実行すると、計算条件・判定・結果がここに残ります。</p>}
  </div>;
}
