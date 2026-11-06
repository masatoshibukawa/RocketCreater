"use client";

import { keyMetrics, fmt } from "../lib/format";
import type { Candidate } from "../lib/types";
import ModelViewer from "./ModelViewer";

export default function DesignComparison({ candidates, selectedId, onSelect }: {
  candidates: Candidate[]; selectedId: string | null; onSelect: (id: string) => void;
}) {
  const own = candidates.filter(c => !c.seededFrom);
  return <section className="comparison-workspace" aria-label="設計案の比較">
    <div className="workspace-heading"><span>候補を見比べる</span><small>同じ要求から得た案 · {own.length}件</small></div>
    {own.length === 0 ? <div className="workspace-empty"><h2>比較する案はまだありません</h2><p>条件を伝えて設計を実行すると、計算結果が届いた案をここで見比べられます。</p></div>
      : <div className="comparison-cards">{own.map((c, i) => <article key={c.source_id} className={selectedId === c.source_id ? "comparison-card is-selected" : "comparison-card"}>
        <header><h2>案 {i + 1}</h2><span className={`result-tag ${c.passed ? "is-pass" : "is-pending"}`}>{c.passed ? "計算上の条件を満たす" : "見直しが必要"}</span></header>
        <ModelViewer design={c.design} tier={c.design.tier} origin="candidate" statusLabel={c.passed ? "条件を満たす案" : "見直しが必要"} reference={null} dimensions={null} notes={[]}/>
        <dl>{keyMetrics(c.design.tier).filter(m => Number.isFinite(c.metrics[m.key])).map(m => <div key={m.key}><dt>{m.label}</dt><dd>{m.format(c.metrics[m.key])}</dd></div>)}
          {c.design.tier === "bottle" ? <div><dt>初期ゲージ圧</dt><dd>{fmt(c.design.initial_gauge_pressure_pa / 1000, 0)} kPa</dd></div> : null}
          <div><dt>概算費用</dt><dd>{fmt(c.cost_jpy, 0)} 円</dd></div></dl>
        <p>{c.explanation || "説明は詳細の計算記録から確認できます。"}</p>
        <button type="button" className="btn" aria-pressed={selectedId === c.source_id} onClick={() => onSelect(c.source_id)}>この案を表示</button>
        <small>出典 {c.source_id}</small>
      </article>)}</div>}
  </section>;
}
