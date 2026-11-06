"use client";

import {useEffect,useState} from "react";
import {projectRequest,type DesignProject} from "../lib/designProjects";

interface Comparison {from_version:number;to_version:number;changes:{path:string;before:unknown;after:unknown}[];
  invalidated:string[];preserved:string[];result_delta:Record<string,number>}

export default function ProjectComparison({project}:{project:DesignProject}) {
  const [result,setResult]=useState<Comparison|null>(null),[error,setError]=useState<string|null>(null);
  const [selected,setSelected]=useState("");
  useEffect(()=>{
    setResult(null);setError(null);
    if(!selected)return;
    const controller=new AbortController();
    void projectRequest<Comparison>(`/${project.id}/compare/${selected}`,undefined,controller.signal)
      .then(setResult).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return()=>controller.abort();
  },[project.id,project.version,project.revision,selected]);
  return project.versions.length ? <details><summary>版の差分と再解析の範囲</summary>
    <label>比較する旧版<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">旧版を選択</option>{project.versions.map(v=><option key={v.version} value={v.version}>v{v.version}</option>)}</select></label>
    {error?<p role="alert">{error}</p>:null}
    {result?<><p>v{result.from_version} → v{result.to_version}</p>
      <table><thead><tr><th>変更した値</th><th>旧版</th><th>現在</th></tr></thead><tbody>{result.changes.map(r=><tr key={r.path}><th>{r.path}</th><td>{JSON.stringify(r.before)}</td><td>{JSON.stringify(r.after)}</td></tr>)}</tbody></table>
      <p>再評価・再生成：{result.invalidated.join("、")||"変更なし"}</p><p>同じ入力を保持：{result.preserved.join("、")||"なし"}</p>
      {Object.entries(result.result_delta).map(([k,v])=><p key={k}>{k}の差：{v.toFixed(3)}</p>)}
    </>:null}
  </details>:null;
}
