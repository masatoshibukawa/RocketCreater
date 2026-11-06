"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl, type DesignPackageRequest } from "../lib/api";
import { newSpec, projectRequest, projectFileLabel, type DesignProject, type ProductionSpec, type ProductionGeometry } from "../lib/designProjects";
import { useCrewTask } from "../lib/WorkshopContext";
import ModelViewer from "./ModelViewer";
import VideoOutputs from "./VideoOutputs";
import ProjectEquipmentEditor from "./ProjectEquipmentEditor";
import ProjectObservations from "./ProjectObservations";

const STORAGE = "rocketwright-production-project-v1";
const DIMENSIONS: [keyof Omit<ProductionGeometry, "dimensions_measured">, string][] = [
  ["body_diameter_mm", "ボトル胴径 mm"], ["body_height_mm", "ボトル高さ mm"],
  ["nose_length_mm", "ノーズ長さ mm"], ["nose_wall_mm", "ノーズ肉厚 mm"],
  ["fin_root_mm", "フィン翼根 mm"], ["fin_tip_mm", "フィン翼端 mm"],
  ["fin_span_mm", "フィン張出し mm"], ["fin_sweep_mm", "フィン後退 mm"],
  ["fin_thickness_mm", "フィン厚さ mm"], ["fin_count", "フィン枚数"],
  ["fin_tail_inset_mm", "フィン後端の高さ mm"],
  ["radial_clearance_mm", "径方向の嵌合余裕 mm"], ["fin_slot_width_mm", "固定材スロット幅 mm"],
];
const OPERATION: Record<string, string> = { analyse: "CADと飛行を再解析中", slicing: "S5用データを検査中", render_design_and_launch: "同じ採用版の動画を制作中" };

export default function DesignProduction({ source, mode, onProjectChange, active, projectId }: {
  source: DesignPackageRequest | null; mode: "files" | "assembly" | "video" | "edit";
  onProjectChange: (project: DesignProject | null) => void; active: boolean; projectId: string | null;
}) {
  const [project, setProject] = useState<DesignProject | null>(null);
  useEffect(() => { if (projectId === null) setProject(null); }, [projectId]);
  const [draft, setDraft] = useState<ProductionSpec | null>(null);
  const [projects, setProjects] = useState<{ id: string; name: string; version: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [style, setStyle] = useState<"photographic" | "engineering">("photographic");
  const [local, setLocal] = useState(true);
  const accept = useCallback((value: DesignProject) => {
    setProject(value); onProjectChange(value);
    try { localStorage.setItem(STORAGE, value.id); } catch { /* Storage may be unavailable. */ }
  }, [onProjectChange]);
  const refreshList = useCallback(async () => {
    const data = await projectRequest<{ projects: typeof projects }>(); setProjects(data.projects);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    void projectRequest<{ projects: typeof projects }>("", undefined, abort.signal).then(data => setProjects(data.projects)).catch(() => {});
    let id: string | null = null;
    try { id = localStorage.getItem(STORAGE); } catch { /* Optional convenience only. */ }
    if (id && /^[a-f0-9]{32}$/.test(id)) void projectRequest<DesignProject>(`/${id}`, undefined, abort.signal).then(accept).catch(() => {});
    return () => abort.abort();
  }, [accept]);
  useEffect(() => {
    if (!project?.active) return;
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const next = await projectRequest<DesignProject>(`/${project.id}`, undefined, abort.signal); if (!abort.signal.aborted) { accept(next); setError(null); } }
      catch { if (!abort.signal.aborted) setError("接続状態を確認しています。新しいジョブは開始せず、再接続を試みます。"); }
      if (!abort.signal.aborted) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 1500);
    return () => { abort.abort(); clearTimeout(timer); };
  }, [project?.id, project?.active?.started_at, accept]);
  const working = busy || !!project?.active;
  useCrewTask("design-production", { id: project ? `${project.id}:v${project.version}` : "new",
    status: working ? "working" : error || project?.error ? "attention" : project?.adopted ? "done" : "idle",
    label: project?.active ? OPERATION[project.active.name] ?? "採用版の資料を作成中" : "保存した設計と次の工程を確認できます" });

  async function action(operation: string, extra: Record<string, unknown> = {}) {
    if (!project || (working && operation !== "cancel")) return;
    setBusy(true); setError(null);
    try { accept(await projectRequest<DesignProject>(`/${project.id}/${operation}`, { revision: project.revision, ...extra })); await refreshList(); }
    catch (e) { setError(String(e instanceof Error ? e.message : e));
      const latest = await projectRequest<DesignProject>(`/${project.id}`).catch(() => null); if (latest) accept(latest);
    } finally { setBusy(false); }
  }
  async function save() {
    if (!draft || working) return;
    setBusy(true); setError(null);
    try {
      const next = await projectRequest<DesignProject>(project ? `/${project.id}/edit` : "", project ? { revision: project.revision, spec: draft } : { spec: draft });
      accept(next); setDraft(null); await refreshList();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  async function open(id: string) {
    if (!id || busy) return;
    setError(null); setDraft(null);
    try { accept(await projectRequest<DesignProject>(`/${id}`)); } catch (e) { setError(String(e)); }
  }
  async function importFile(file?: File) {
    if (!file) return;
    try {
      if (file.size > 100000) throw new Error("設計JSONは100KB以下にしてください。");
      const data = JSON.parse(await file.text());
      // Imported results/paths are never trusted; the server validates only a new input spec.
      const spec = data.spec ?? (data.design ? newSpec({ ...source, design: data.design, requirement: data.requirement ?? null } as DesignPackageRequest) : null);
      if (!spec) throw new Error("設計データが見つかりません。");
      setBusy(true); accept(await projectRequest<DesignProject>("", { spec })); setDraft(null); await refreshList();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  const videos = project?.files.filter(f => f.kind === (style === "photographic" ? "photographic_video" : "video") && f.name.endsWith(".mp4")) ?? [];
  const plan = style === "photographic" ? project?.photographic_video_plan : project?.video_plan;
  const result = project?.analysis?.result;
  const mainFile = (f: { kind: string; name: string }) => f.kind === "manual" || f.kind === "package" || ["design.json", "bom.csv", "print-package.zip"].includes(f.name);
  const num = (label: string, value: number | null, change: (value: number) => void) => <label>{label}<input type="number" step="any" required value={value ?? ""} onChange={e => change(Number(e.target.value))}/></label>;
  return <section className="wb-detail production-project" aria-label="設計の保存と制作">
    <h2>{project ? `${project.name} / v${project.version}` : "同じ設計から、製作と映像へ"}</h2>
    <p className="wb-note">寸法・材料・質量を保存し、再解析した版を採用してから出力します。このPCで制作します。プリンターへの送信は別操作です。</p>
    <div className="project-actions">
      <label>保存した案件<select aria-label="保存した案件" value={project?.id ?? ""} disabled={busy} onChange={e => void open(e.target.value)}><option value="">案件を選択</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name} / v{p.version}</option>)}</select></label>
      <button className="btn" disabled={busy} onClick={() => { const next = project ? structuredClone(project.spec) : newSpec(source); setProject(null); onProjectChange(null); setDraft(next); }}>表示中の案から新しい案件</button>
      <label className="btn">設計JSONを開く<input aria-label="設計JSONを開く" type="file" accept=".json,application/json" disabled={working} onChange={e => void importFile(e.target.files?.[0])}/></label>
      {project ? <button className="btn" disabled={working} onClick={() => setDraft(structuredClone(project.spec))}>寸法・質量を編集</button> : null}
    </div>
    {!project && !draft ? <button className="btn btn-primary" onClick={() => setDraft(newSpec(source))}>寸法を確認して保存</button> : null}
    {draft ? <form onSubmit={e => { e.preventDefault(); void save(); }}>
      <p className="wb-case-tag">保存すると新しい版になり、解析・採用・出力をやり直します。初期の寸法は容量からの仮定です。</p>
      <div className="project-fields"><label>案件名<input required maxLength={100} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/></label>
        {DIMENSIONS.map(([key, label]) => <span key={key}>{num(label, draft.geometry[key] ?? (key === "radial_clearance_mm" ? .4 : 3.6), value => setDraft({ ...draft, geometry: { ...draft.geometry, [key]: value } }))}</span>)}
        {num("印刷部品以外の乾燥質量 g（要確認）", draft.other_dry_mass_g, value => setDraft({ ...draft, other_dry_mass_g: value }))}
        <label>機体に使う印刷部品の実測合計 g（任意）<input type="number" min="0.01" step="any" value={draft.measured_printed_mass_g ?? ""} onChange={e => setDraft({ ...draft, measured_printed_mass_g: e.target.value ? Number(e.target.value) : null })}/></label>
        {num("ボトル容量 L", draft.design.bottle_volume_m3*1000, value => setDraft({ ...draft, design: { ...draft.design, bottle_volume_m3: value/1000 } }))}
        {num("ノズル径 mm", draft.design.nozzle_diameter_m*1000, value => setDraft({ ...draft, design: { ...draft.design, nozzle_diameter_m: value/1000 } }))}
        {draft.design.has_parachute ? num("回収傘の直径 m", draft.design.parachute_diameter_m, value => setDraft({ ...draft, design: { ...draft.design, parachute_diameter_m: value } })) : null}
        {num("初期圧力差 kPa（計算条件）", draft.design.initial_gauge_pressure_pa/1000, value => setDraft({ ...draft, design: { ...draft.design, initial_gauge_pressure_pa: value*1000 } }))}
        {num("水の充填率 %", draft.design.water_fill_frac*100, value => setDraft({ ...draft, design: { ...draft.design, water_fill_frac: value/100 } }))}
        {num("搭載質量 g", draft.design.payload_mass_kg*1000, value => setDraft({ ...draft, design: { ...draft.design, payload_mass_kg: value/1000 }, requirement: draft.requirement ? { ...draft.requirement, payload_mass_kg: value/1000 } : null }))}
        <label>目標高度 m（任意）<input type="number" min="1" step="any" value={Number(draft.requirement?.target_altitude_m) || ""} onChange={e => setDraft({ ...draft, requirement: e.target.value ? { goal_kind: "altitude", payload_mass_kg: draft.design.payload_mass_kg, budget_jpy: 3000, recovery_required: true, ...draft.requirement, target_altitude_m: Number(e.target.value) } : null })}/></label>
      </div>
      <ProjectEquipmentEditor spec={draft} onChange={setDraft}/>
      <p className="wb-note">材料：{draft.material}。実測質量がないときは、同じCADの一様固体の質量で計算します。充填率による実際の部品質量や取付強度は未確認です。</p>
      {project ? <p className="wb-note">変更する寸法：{DIMENSIONS.filter(([key]) => draft.geometry[key] !== project.spec.geometry[key]).map(([, label]) => label).join("、") || "なし"}。質量・計算条件も保存した入力で再解析します。変更後はCAD・印刷・手順書・動画を新しい版から生成します。</p> : null}
      <label><input type="checkbox" checked={draft.geometry.dimensions_measured} onChange={e => setDraft({ ...draft, geometry: { ...draft.geometry, dimensions_measured: e.target.checked } })}/>ボトルと部品の寸法を実測して入力した</label>
      <div className="project-actions"><button className="btn btn-primary" disabled={working} type="submit">{project ? "変更を新しい版に保存" : "案件を保存"}</button><button className="btn" type="button" onClick={() => setDraft(null)}>編集を閉じる</button></div>
    </form> : null}
    {error || project?.error ? <p role="alert" className="wb-error">{error ?? project?.error}</p> : null}
    {project ? <>
      <p className="wb-case-tag" role="status">{project.active ? OPERATION[project.active.name] ?? "制作中" : project.adopted ? "試作版として採用済み" : project.analysis ? result?.success ? "数値スクリーニング済み · 採用待ち" : "計算条件が未達 · 編集して再解析" : "編集を保存済み · 再解析が必要"}</p>
      {project.active ? <div role="status"><p>{project.active.phase?.startsWith("waiting_") ? "機材の空きを待っています" : "保存したジョブを実行中"} · {project.active.id?.slice(0,8)}</p>
        {project.active.progress?.total ? <><progress value={project.active.progress.completed} max={project.active.progress.total}/><p>描画 {project.active.progress.completed}/{project.active.progress.total} フレーム · 再利用 {project.active.progress.reused??0}</p></> : null}
        <p>{project.active.progress?.eta_s ? `描画の残り目安 ${Math.ceil(project.active.progress.eta_s[0]/60)}〜${Math.ceil(project.active.progress.eta_s[1]/60)}分（直近の実測時間から算出）` : "残り時間は未計測です"}</p>
        <button className="btn" disabled={busy} onClick={()=>void action("cancel")}>区切りで中断・再開用に保存</button></div> : null}
      {project.analysis?.requirements ? <details open><summary>要求ごとの確認</summary>{project.analysis.requirements.checks.map(check => <p key={check.id}>{check.label}：{({pass:"計算・入力確認済み",fail:"未達",not_evaluated:"未評価",not_required:"要求なし"} as Record<string,string>)[check.status]} · {check.reason}</p>)}</details> : null}
      <div className="project-actions"><button className="btn" disabled={working || project.adopted || !!draft} onClick={() => void action("analyse")}>CADと飛行を再解析</button><button className="btn btn-primary" disabled={working || !result?.success || project.adopted || !!draft} onClick={() => void action("adopt")}>この版を採用</button></div>
      {result ? <div className="wb-note"><b>計算高度 {result.metrics.apogee_m?.toFixed(2)} m / 乾燥質量 {(project.analysis!.design.dry_mass_kg*1000).toFixed(2)} g</b><p>印刷部品 {project.analysis!.printed_mass_used_g.toFixed(2)} g（{project.analysis!.mass_basis === "measured" ? "実測入力" : "CADの一様固体推定"}）。{project.spec.requirement ? "保存した目標高度で判定" : "目標高度は未指定"}。</p>{result.failure_reasons.map(t => <p key={t}>{t}</p>)}<details><summary>解析の前提と限界</summary>{project.analysis!.limitations.map(t => <p key={t}>{t}</p>)}</details></div> : null}
      {project.analysis && mode !== "video" ? <div className="project-model"><ModelViewer design={project.analysis.design} tier="bottle" origin="attempt" reference={null} dimensions={null} notes={[]} active={active} statusLabel={`採用候補 v${project.version} の寸法付き包絡`}/></div> : null}
      {mode === "assembly" || mode === "files" ? <div className="project-actions"><button className="btn" disabled={working || !project.adopted || !!draft} onClick={() => void action("manual")}>この版の組立PDFを生成</button><button className="btn" disabled={working || !project.adopted || !!draft} onClick={() => void action("print")}>この版のS5印刷データを生成</button></div> : null}
      {mode === "assembly" || mode === "files" ? <ProjectObservations key={`${project.id}:${project.version}`} project={project} disabled={working || !!draft} save={action}/> : null}
      {mode === "video" ? <>
        <div className="project-actions"><label>仕上げ<select value={style} disabled={working} onChange={e => setStyle(e.target.value as typeof style)}><option value="photographic">写真調 1080p / 16秒・12秒</option><option value="engineering">簡易CG / 各4秒</option></select></label><label><input type="checkbox" checked={local} disabled={working} onChange={e => setLocal(e.target.checked)}/>Gemmaで演出を提案</label></div>
        <div className="project-actions"><button className="btn" disabled={working || !project.adopted || !!draft || videos.length > 0} onClick={() => void action("video-plan", { style, local })}>この版の演出案を作る</button><button className="btn btn-primary" disabled={working || !project.adopted || plan?.status !== "planned" || !!draft || videos.length > 0} onClick={() => void action("render-video", { style })}>設計説明・飛行動画を制作</button></div>
        {plan ? <p className="wb-note">演出案（計算データを可視化）：{plan.reason}</p> : null}
        {videos.map(f => <figure key={f.url}><figcaption>{f.name} / v{f.version}・計算結果のCG・無音</figcaption><video controls preload="metadata" src={apiUrl(f.url)}/><a className="btn" href={apiUrl(f.url)} download>MP4を保存</a></figure>)}
        <details><summary>保存済みの参考映像を見る</summary><VideoOutputs/></details>
      </> : null}
      {mode === "files" ? <button className="btn btn-primary" disabled={working || !project.adopted || !!draft} onClick={() => void action("archive")}>この版の一括ZIPを作る</button> : null}
      <div className="wb-file-list">{project.files.filter(mainFile).map(f => <a key={f.url} href={apiUrl(f.url)} download>{projectFileLabel(f.name)}<small>v{f.version}</small></a>)}</div>
      <details><summary>CAD・印刷・検査の詳細ファイル</summary><div className="wb-file-list">{project.files.filter(f => !mainFile(f) && !f.name.endsWith(".mp4")).map(f => <a key={f.url} href={apiUrl(f.url)} download>{projectFileLabel(f.name)}<small>v{f.version} · {f.kind}</small></a>)}</div></details>
      {project.versions.length ? <details><summary>保存した版と差戻し</summary>{project.versions.map(v => <p key={v.version}>v{v.version} · {v.adopted ? "採用済み" : "検討案"} · 胴径{v.spec.geometry.body_diameter_mm.toFixed(1)} mm · 翼根{v.spec.geometry.fin_root_mm.toFixed(1)} mm <button className="btn" disabled={working || !!draft} onClick={() => void action("restore", { version: v.version })}>この入力を新しい版に戻す</button></p>)}</details> : null}
    </> : null}
  </section>;
}
