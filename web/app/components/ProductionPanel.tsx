"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl, createDesignPackage, requestKey, type DesignPackage, type DesignPackageRequest } from "../lib/api";
import type { Design } from "../lib/types";
import PrintExports from "./PrintExports";
import { useCrewTask } from "../lib/WorkshopContext";

interface ProductionPanelProps {
  /** Null while no design is displayed. */
  request: DesignPackageRequest | null;
  /** The displayed design passed its simulation. Only such a design gets production data. */
  passed: boolean;
  onGenerated?: (value: DesignPackage) => void;
  onPrintGenerated?: (files: { name: string; url: string }[]) => void;
}

/** 製作データ: the files a passing design can support, what it cannot, and the print data. */
export default function ProductionPanel({ request, passed, onGenerated, onPrintGenerated }: ProductionPanelProps) {
  const design: Design | null = request?.design ?? null;
  const key = request ? requestKey(request) : "";
  const [made, setMade] = useState<DesignPackage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useCrewTask("production", { id: key, status: busy ? "working" : error ? "attention" : made ? "done" : "idle",
    label: busy ? "製作ファイルと数値の出典を点検中" : error ? "ファイル作成を止めて、エラーの確認を待っています" : "製作ファイルができました。内容を確認できます" });

  useEffect(() => {
    setMade(null);
    setError("");
    setBusy(false);
    return () => controller.current?.abort();
  }, [key]);

  async function generate(): Promise<void> {
    if (!request || busy) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    try {
      const next = await createDesignPackage(request, abort.signal);
      if (!abort.signal.aborted) { setMade(next); onGenerated?.(next); }
    } catch (e) {
      if (!abort.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }

  return <section className="wb-detail" aria-label="製作データ">
    <h2>製作データ</h2>
    <p className="wb-note">同じ案をもう一度シミュレーションして、製作票・設計レポート・部品表・側面図を作ります。</p>
    <button type="button" className="btn btn-primary" disabled={!passed || busy || made !== null} onClick={() => void generate()}>
      {busy ? "作成中…" : "この案の製作ファイルを作る"}
    </button>
    {!design ? <p className="wb-note">設計案が届くと作れます。</p>
      : !passed ? <p className="wb-note">シミュレーションに合格した案を選ぶと作れます。</p> : null}
    {error ? <p role="alert" className="wb-error">{error}</p> : null}
    {made ? <>
      <div className="wb-file-list">{made.files.map(file => <a key={file.kind} href={apiUrl(file.url)} download><span>{file.label}</span><small>{file.url.split(".").at(-1)?.toUpperCase()} ↓</small></a>)}</div>
      <h3>この案から作れないもの</h3>
      <ul className="wb-limitations">{made.unavailable.map(row => <li key={row.item}><b>{row.item}</b>: {row.reason}</li>)}</ul>
    </> : null}
    <PrintExports design={design} disabled={!passed} onGenerated={onPrintGenerated}/>
  </section>;
}
