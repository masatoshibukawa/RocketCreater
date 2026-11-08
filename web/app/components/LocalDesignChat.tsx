"use client";
import {useState} from "react";
import {projectRequest,type DesignProject,type ProductionSpec} from "../lib/designProjects";
import {useCrewTask} from "../lib/WorkshopContext";

interface Proposal {id:string;model:string;text:string;questions:string[];intent:{reason:string};
  candidates:{id:string;label:string;spec:ProductionSpec;assumptions:string[]}[]}

export default function LocalDesignChat({project,onProject}:{project:DesignProject|null;onProject:(p:DesignProject)=>void}) {
  const [text,setText]=useState(""),[proposal,setProposal]=useState<Proposal|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [history,setHistory]=useState<string[]>([]);
  useCrewTask("local-intake",{id:proposal?.id??"intake",status:busy?"working":error?"attention":"idle",
    label:busy?"Claude が要求と候補を整理しています":"保存した設計の条件を相談できます"});
  async function propose(){
    setBusy(true);setError(null);
    const request=proposal?.questions.length?`${proposal.text}\n補足：${text}`:text;
    setHistory(v=>[...v,request]);
    try {setProposal(await projectRequest<Proposal>("/intent",{text:request,project_id:project?.id??null}));setText("");}
    catch(e){setError(e instanceof Error?e.message:String(e));} finally{setBusy(false);}
  }
  async function accept(candidate_id:string){
    if(!proposal)return;setBusy(true);setError(null);
    try {let p=await projectRequest<DesignProject>("/intent/accept",{ticket_id:proposal.id,candidate_id});
      onProject(p);p=await projectRequest<DesignProject>(`/${p.id}/analyse`,{revision:p.revision});onProject(p);setProposal(null);}
    catch(e){setError(e instanceof Error?e.message:String(e));} finally{setBusy(false);}
  }
  return <div className="chat-panel local-design-chat">
    <p>Claude がペットボトルロケットの要求と候補を整理します。</p>
    <p className="wb-note">{project?`${project.name} / v${project.version} への変更を相談できます。`:"目標高度、搭載質量、容量、回収方法を入力してください。"}</p>
    {history.map((line,i)=><p key={i} className="chat-message">{line}</p>)}
    {proposal?<><p>{proposal.intent.reason}</p>{proposal.questions.map(q=><p key={q}>{q}</p>)}
      {proposal.candidates.map(c=><article key={c.id}><h3>{c.label}</h3><p>容量 {(c.spec.design.bottle_volume_m3*1000).toFixed(2)} L / 搭載 {(c.spec.design.payload_mass_kg*1000).toFixed(0)} g / 目標 {String(c.spec.requirement?.target_altitude_m)} m / {c.spec.altitude_rule==="minimum"?"最低高度":"±10%の目標帯"}</p>
        <p>フィン {c.spec.geometry.fin_count}枚・張出し {c.spec.geometry.fin_span_mm.toFixed(1)} mm</p>
        <details><summary>仮定と未確認</summary>{c.assumptions.map(a=><p key={a}>{a}</p>)}</details>
        <button className="btn" disabled={busy||!!project?.active} onClick={()=>void accept(c.id)}>この候補を保存してCAD・飛行を計算</button></article>)}
    </>:null}
    <form onSubmit={e=>{e.preventDefault();void propose();}}><label>設計の依頼<textarea value={text} maxLength={3000} disabled={busy} placeholder="2 L、60 gを20 m程度へ。パラシュートで回収したい。" onChange={e=>setText(e.target.value)}/></label>
      <button className="btn btn-primary" disabled={busy||!text.trim()||!!project?.active}>{busy?"要求を整理中":"Claude に相談"}</button></form>
    {error?<p role="alert">{error}</p>:null}
  </div>;
}
