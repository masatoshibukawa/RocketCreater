"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl, designKey } from "../lib/api";
import type { Design } from "../lib/types";

type File = { name: string; url: string; kind?: string };
type Manifest = { status: string; brim_width_mm: number; brim_gap_mm: number;
  parts: { part: string; model_layers: number; estimated_mass_g: number;
    estimated_time_seconds: number; all_print_paths_inside_s5: boolean;
    quantity_for_assembly?: number }[] };
type Bundle = { manifest: Manifest; files: File[] };

export default function PrintExports({ design, files, manifest, onGenerate, disabled = false }: {
  design?: Design | null; files?: File[]; manifest?: Manifest;
  onGenerate?: () => void; disabled?: boolean;
}) {
  const [ready, setReady] = useState<boolean | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = design ? designKey(design) : "workbench";
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch(apiUrl("/manufacturing/runtime"), { signal: abort.signal })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("印刷環境を確認できません")))
      .then(r => setReady(Boolean(r.available)))
      .catch(() => { if (!abort.signal.aborted) setReady(false); });
    return () => abort.abort();
  }, []);
  useEffect(() => {
    controller.current?.abort(); setBundle(null); setError(""); setBusy(false);
    return () => controller.current?.abort();
  }, [key]);
  async function generate() {
    if (onGenerate) { onGenerate(); return; }
    if (!design || design.tier !== "bottle" || busy) return;
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError("");
    try {
      const response = await fetch(apiUrl("/manufacturing/packages"), {
        method: "POST", signal: abort.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design, printer: "s5-gray-aa04" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "印刷データを生成できませんでした");
      if (!abort.signal.aborted) setBundle(data);
    } catch (e) {
      if (!abort.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally { if (!abort.signal.aborted) setBusy(false); }
  }
  if (!onGenerate && design?.tier !== "bottle") return null;
  const report = manifest ?? bundle?.manifest;
  const outputs = files ? files.filter(f => f.kind === "manufacturing") : bundle?.files ?? [];
  return <section className="wb-print-exports" aria-label="設計ごとの3Dプリント出力">
    <h3>3Dプリンター用データ</h3>
    <p>UltiMaker S5 · Tough PLA Gray · AA 0.4</p>
    <p className="wb-note">この設計からフィン・ノーズ・試着リングを生成し、形状検査と機種別スライスを行います。除去用ブリム20 mm以上・隙間0 mm。フィンの終盤の転倒を受けた次の試作条件です。</p>
    <button className="wb-primary" disabled={disabled || busy || ready !== true || Boolean(report)} onClick={() => void generate()}>
      {busy ? "形状生成・検査・スライス中…" : "この設計の印刷データを生成"}
    </button>
    {ready === false ? <p className="wb-note">このPCのBlender、CuraEngine 5.12.0、Cura材料定義を設定してください。</p> : null}
    {error ? <p role="alert" className="wb-error">{error}</p> : null}
    {report ? <>
      <p role="status">スライス検査済み · 実機での再試作は未確認</p>
      <p className="wb-note">各印刷ファイルは部品1個分です。</p>
      <ul>{report.parts.map(p => <li key={p.part}>{p.part} · 必要{p.quantity_for_assembly ?? 1}個 · 1個あたり{p.model_layers}層・約{Math.ceil(p.estimated_time_seconds / 60)}分・{p.estimated_mass_g.toFixed(1)} g · 土台を含めベッド内</li>)}</ul>
      <p className="wb-note">PLA製部品へ変更した後は、質量を測定して飛行解析を更新してください。耐圧部品は出力しません。</p>
    </> : null}
    <div className="wb-file-list">{outputs.map(f => <a href={apiUrl(f.url)} download key={f.url}>{f.name} ↗</a>)}</div>
  </section>;
}
