"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api";

interface Asset { id: string; label: string; status: string; url: string | null }
interface Library { title: string; assets: Asset[] }

/** Existing validated films stay explicitly attributed to their reference design. */
export default function VideoOutputs() {
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    void fetch(apiUrl("/workbench/library"), { signal: abort.signal }).then(async r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json() as Promise<Library>;
    }).then(setLibrary).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    return () => abort.abort();
  }, []);
  const asset = (id: string) => library?.assets.find(a => a.id === id);
  return <section className="film-workspace" aria-label="動画と出力">
    <div className="workspace-heading"><span>設計解説と打ち上げ CG</span><small>保存済みの設計例</small></div>
    <p className="film-context">{library?.title ?? "映像を読み込んでいます"} · 表示中の設計案の映像とは別の、検証済みの設計例です。</p>
    {error ? <p role="alert" className="wb-error">映像を取得できません: {error}</p> : null}
    {[["design-film", "design-poster", "設計の解説"], ["launch-film", "launch-poster", "打ち上げ CG"]].map(([id, posterId, title]) => {
      const film = asset(id), poster = asset(posterId);
      return <figure key={id} className="output-film"><figcaption><h2>{title}</h2><span>{film?.url ? "保存可能" : "未取得"}</span></figcaption>
        {film?.url ? <><video controls preload="metadata" poster={poster?.url ? apiUrl(poster.url) : undefined} src={apiUrl(film.url)}/><a className="btn" href={apiUrl(film.url)} download>MP4 を保存</a></>
          : <div className="film-placeholder">{film?.status === "changed" ? "ファイルの変更が検出されたため、検証が必要です。" : "このPCに検証済みの映像がありません。"}</div>}
      </figure>;
    })}
    <p className="wb-note">現在の設計の図面・部品表・印刷データは「製作データ」から作成できます。</p>
  </section>;
}
