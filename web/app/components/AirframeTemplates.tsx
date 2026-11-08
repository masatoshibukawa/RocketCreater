"use client";

import { useEffect, useState } from "react";
import { projectRequest, type DesignProject } from "../lib/designProjects";

type Template = { id: string; label: string; litres: number };

export default function AirframeTemplates({ disabled, onCreated }: {
  disabled: boolean; onCreated: (project: DesignProject) => void;
}) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState("pet-15l");
  const [payload, setPayload] = useState(60);
  const [recovery, setRecovery] = useState(true);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<{ templates: Template[] }>("/airframe-templates", undefined, controller.signal)
      .then(data => setTemplates(data.templates))
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  const working = busy || disabled;
  async function choose() {
    setBusy(true); setError(null);
    try {
      const choice = await projectRequest<{ template_id: string; reason: string }>(
        "/airframe-templates/recommend", { text });
      setSelected(choice.template_id); setReason(choice.reason);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError(null);
    try {
      onCreated(await projectRequest<DesignProject>("/from-airframe-template", {
        template_id: selected, payload_g: payload, recovery,
      }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <details className="wb-note"><summary>機体テンプレートから始める</summary>
    <p>参照CADから作った出発案です。作成後に寸法を編集し、CADと飛行を解析します。</p>
    <div className="project-actions">
      <label>機体テンプレート<select value={selected} disabled={working || !templates.length}
        onChange={e => { setSelected(e.target.value); setReason(""); }}>
        {templates.map(template => <option key={template.id} value={template.id}>{template.label}</option>)}
      </select></label>
      <label>搭載質量 g<input type="number" min={0} max={2000} step="any" value={payload}
        disabled={working} onChange={e => setPayload(Number(e.target.value))}/></label>
      <label><input type="checkbox" checked={recovery} disabled={working}
        onChange={e => setRecovery(e.target.checked)}/>パラシュート回収</label>
      <button className="btn" disabled={working || !templates.length || !Number.isFinite(payload) || payload < 0 || payload > 2000}
        onClick={() => void create()}>このテンプレートで案件を作る</button>
    </div>
    <label>テンプレート選びの相談<input value={text} maxLength={4000} disabled={working}
      placeholder="例：1.5 Lで、搭載物を回収したい" onChange={e => setText(e.target.value)}/></label>
    <button className="btn" disabled={working || !text.trim()} onClick={() => void choose()}>Gemmaにテンプレートを選んでもらう</button>
    {reason ? <p>{reason}（出発案・未解析）</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    <p>ボトル外形は参照モデルで、手元の実測値ではありません。ボトルは印刷対象外です。</p>
  </details>;
}
