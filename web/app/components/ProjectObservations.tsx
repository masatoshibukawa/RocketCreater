"use client";
import { useState } from "react";
import type { DesignProject } from "../lib/designProjects";

export default function ProjectObservations({project, disabled, save}: {
  project: DesignProject; disabled: boolean;
  save:(operation:string, extra:Record<string,unknown>)=>Promise<void>;
}) {
  const [step,setStep]=useState("parts"), [status,setStatus]=useState("unconfirmed");
  const [operator,setOperator]=useState(""), [date,setDate]=useState("");
  const [note,setNote]=useState(""), [measure,setMeasure]=useState("");
  const [error,setError]=useState<string|null>(null);
  return <details><summary>この版の組立・観察記録</summary>
    <p className="wb-note">最初はすべて未確認です。観察の保存は飛行の合格や測定値の自動反映にはなりません。変更後の手順PDFとZIPは作り直します。</p>
    {(project.observations??[]).map((row,i)=><p key={i}>v{row.version} / {row.step} / {row.status} / {row.operator} / {row.observed_on}：{row.note}</p>)}
    <div className="project-fields">
      <label>工程<select value={step} onChange={e=>setStep(e.target.value)}>{[["parts","部品と版"],["finish","仕上げ"],["fin_mount","フィン取付"],["nose_fit","ノーズ嵌合"],["recovery","搭載・回収"],["measure","測定"]].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
      <label>確認状態<select value={status} onChange={e=>setStatus(e.target.value)}>{[["unconfirmed","未確認"],["needs_change","要修正"],["observed","観察済み"]].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
      <label>担当<input value={operator} onChange={e=>setOperator(e.target.value)}/></label>
      <label>観察日<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
      <label>内容・保持・視認・分解<textarea value={note} onChange={e=>setNote(e.target.value)}/></label>
      <label>測定値 JSON（単位をキーに含める）<textarea placeholder={'{"printed_mass_g": 98.2}'} value={measure} onChange={e=>setMeasure(e.target.value)}/></label>
    </div>
    {error?<p role="alert">{error}</p>:null}
    <button type="button" className="btn" disabled={disabled||!project.adopted} onClick={()=>{
      try { const measured_values=measure?JSON.parse(measure):{}; setError(null);
        void save("observe",{observation:{step,status,operator,observed_on:date,note,measured_values,evidence:[]}});
      } catch {setError("測定値をJSON形式で入力してください。");}
    }}>この版に観察を保存</button>
  </details>;
}
