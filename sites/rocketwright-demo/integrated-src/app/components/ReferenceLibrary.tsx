"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api";
import { demoFetch } from "../lib/workbench";

interface Asset { id: string; label: string; status: string; url: string | null }
interface Library {
  title: string; description: string; limitations: string[]; assets: Asset[];
  geometry: { diameter_mm: number; bottle_height_mm: number; fin_count: number };
}
interface Reference {
  id: string; title: string; author: string; year: string; note: string; category: string;
  group: string; languages: string[]; source: string | null; checked_on: string;
}
interface References { total: number; records: Reference[]; counts: { water: number; model: number } }

export default function ReferenceLibrary() {
  const [library, setLibrary] = useState<Library | null>(null);
  const [references, setReferences] = useState<References | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    void demoFetch("/workbench/library", { signal: controller.signal, cache: "no-store" })
      .then(async r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() as Promise<Library>; })
      .then(setLibrary).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ q: query, category });
      void demoFetch(`/workbench/references?${params}`, { signal: controller.signal, cache: "no-store" })
        .then(async r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() as Promise<References>; })
        .then(setReferences).catch(e => { if (!controller.signal.aborted) setError(String(e)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, category]);

  const asset = (id: string) => library?.assets.find(a => a.id === id);
  return <div className="wb-detail wb-library">
    <p className="wb-eyebrow">REFERENCE / CAD · FILM · SOURCES</p>
    <h2>設計例と資料</h2>
    {error ? <p role="alert" className="wb-error">資料を取得できません: {error}</p> : null}
    {library ? <section aria-label="2Lの参照機体">
      <h3>{library.title}</h3><p className="wb-note">{library.description}</p>
      <p className="wb-case-tag">参照機体 · 外径{library.geometry.diameter_mm} mm · 容器高{library.geometry.bottle_height_mm} mm · {library.geometry.fin_count}枚翼</p>
      <ul className="wb-limitations">{library.limitations.map(text => <li key={text}>{text}</li>)}</ul>
      <div className="wb-file-list">{library.assets.filter(a => !a.id.includes("film") && !a.id.includes("poster")).map(a =>
        a.url ? <a key={a.id} href={apiUrl(a.url)} download><span>{a.label}</span><small>STL ↓</small></a>
          : <p key={a.id} className="wb-note">{a.label} · {a.status === "changed" ? "変更を検出・確認が必要" : "このPCにファイルがありません"}</p>)}</div>
      {[["design-film", "design-poster"], ["launch-film", "launch-poster"]].map(([filmId, posterId]) => {
        const film = asset(filmId), poster = asset(posterId);
        return <figure className="wb-video" key={filmId}>
          <figcaption>{film?.label} · 2 L 試作 v2</figcaption>
          {film?.url ? <><video controls preload="none" poster={poster?.url ? apiUrl(poster.url) : undefined} src={apiUrl(film.url)}/><a href={apiUrl(film.url)} download>1080p MP4を保存 ↓</a></>
            : <p className="wb-note">{film?.status === "changed" ? "保存された映像または形状が検証記録と異なります。" : "このPCに検証済みの映像ファイルがありません。"}</p>}
        </figure>;
      })}
      <p className="wb-note">形状・数値はCADと計算スクリプト、演出はローカルLLM、検証と出力順序は実行管理が担当します。背景素材: Poly Haven / CC0。音は合成音です。</p>
    </section> : <p role="status" className="wb-note">設計例を読み込み中…</p>}
    <section className="wb-reference-search" aria-label="文献の検索">
      <h3>根拠を探す</h3>
      <p className="wb-note">水ロケット {references?.counts.water ?? "…"}件 / モデルロケット {references?.counts.model ?? "…"}件。記録時点の文献目録です。別の推進方式の条件を、そのまま設計値に使わないでください。</p>
      <label htmlFor="reference-query">題名・著者・言語・資料ID</label>
      <input id="reference-query" type="search" maxLength={200} value={query} placeholder="例: D02、NASA、回収" onChange={e => setQuery(e.target.value)}/>
      <label htmlFor="reference-group">対象</label>
      <select id="reference-group" value={category} onChange={e => setCategory(e.target.value)}>
        <option value="all">すべて</option><option value="water">水ロケット</option><option value="model">モデルロケット</option>
      </select>
      <p className="wb-note" role="status">{loading ? "検索中…" : `${references?.total ?? 0}件`}</p>
      {!loading ? references?.records.map(row => <article className="wb-source" key={`${row.group}-${row.id}`}>
        <small>{row.id} · {row.group === "water" ? "水ロケット" : row.category} · {row.languages.join(" / ")} · {row.year}</small>
        <h4>{row.source ? <a href={row.source} target="_blank" rel="noreferrer">{row.title} ↗</a> : row.title}</h4>
        <p>{row.note}</p><small>{row.author} / 目録確認日 {row.checked_on}</small>
      </article>) : null}
    </section>
  </div>;
}
