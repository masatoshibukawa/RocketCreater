"use client";

import {useEffect,useState} from "react";
import {projectRequest,type DesignProject} from "../lib/designProjects";

interface View {status:string;remaining_s:number;metrics:Record<string,number|boolean>;checks:Record<string,boolean>;
  choices:{offered:Record<string,{method:string;scope:string}>;rejected:Record<string,string[]>;unmet:string[]};
  proposals:Record<string,{reason:string;diff:{changes:{path:string;before:unknown;after:unknown}[];invalidated:string[]}}>;
  decisions:{action:string|null;reason:string;planner:string}[]}
const STATES:Record<string,string>={running:"解析中・次の候補を選択できます",unresolved:"未達・不足あり",budget_exhausted:"計算予算の上限",planner_failed:"ローカルモデルの選択に失敗",model_criteria_met:"宣言したモデル条件を確認",screening_criteria_met:"簡易スクリーニング条件を確認"};
const CHECKS:Record<string,string>={altitude:"高度",attitude:"姿勢の適用範囲",static_margin:"静安定余裕",temporal:"時間刻み",fin_deformation:"フィン変形",modes:"振動モード",frozen_pitch:"固定条件の復元性",aero_domain:"空力の適用範囲",thermal_balance:"熱収支",propulsion_balance:"推進の収支",aero_grid:"空力の格子差",aero_averaging:"空力の平均化時間",fem_mesh:"構造メッシュ差",payload_mass:"搭載質量",recovery:"回収の計算条件",cost_evidence:"調達費の根拠"};

export default function ProjectAnalysis({project,onProject}:{project:DesignProject;onProject:(p:DesignProject)=>void}) {
  const [view,setView]=useState<View|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  const [cfd,setCfd]=useState(true),[fem,setFem]=useState(true),[accuracy,setAccuracy]=useState(1.5),[budget,setBudget]=useState(3600);
  useEffect(()=>{
    if(!project.adaptive){setView(null);return;}
    const abort=new AbortController();
    void projectRequest<View>(`/${project.id}/adaptive/view`,undefined,abort.signal).then(setView).catch(e=>{if(!abort.signal.aborted)setError(String(e));});
    return()=>abort.abort();
  },[project.id,project.version,project.revision,project.adaptive?.decisions?.length,project.adaptive?.status]);
  async function action(name:string,extra:Record<string,unknown>={}){
    setBusy(true);setError(null);
    try{onProject(await projectRequest<DesignProject>(`/${project.id}/adaptive/${name}`,{revision:project.revision,...extra}));}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  const disabled=busy||!!project.active;
  return <section className="production-project" aria-label="保存案件の階層解析"><h2>{project.name} / v{project.version} の階層解析</h2>
    <p>同じ寸法・質量・材料・取付から、熱、推進、空力、構造、姿勢、回収をつなぎます。完了した計算と、精度を満たした結果を区別します。</p>
    {!project.adaptive?<><div className="project-fields">
      <label>高度の数値精度予算 m<input type="number" min=".01" max="20" step=".1" value={accuracy} onChange={e=>setAccuracy(Number(e.target.value))}/></label>
      <label>総計算予算 秒<input type="number" min="60" max="86400" value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label>
      <label><input type="checkbox" checked={cfd} onChange={e=>setCfd(e.target.checked)}/>CFDの精度確認を要求</label>
      <label><input type="checkbox" checked={fem} onChange={e=>setFem(e.target.checked)}/>FEMの精度確認を要求</label>
    </div><p>CFD/FEMを外した実行は簡易スクリーニングとして残ります。実物の検証にはなりません。</p>
      <button className="btn btn-primary" disabled={disabled||project.adopted||!project.spec.requirement} onClick={()=>void action("start",{precision:{altitude_error_m:accuracy,require_cfd:cfd,require_fem:fem},limits:{budget_s:budget}})}>この版で階層解析を始める</button>
      {!project.spec.requirement?<p>先に出力画面で高度の要求を保存してください。</p>:null}
      {project.adopted?<p>採用済みの版は保持します。編集で新しい版を作成してください。</p>:null}
    </>:<><p role="status">{STATES[project.adaptive.status]??project.adaptive.status} · 残り計算予算 {Math.floor(project.adaptive.remaining_s)} 秒</p>
      <div className="project-actions"><button className="btn" disabled={disabled} onClick={()=>void action("step")}>Gemmaが選ぶ次の1手を実行</button><button className="btn btn-primary" disabled={disabled} onClick={()=>void action("run")}>保存した上限まで進める</button></div>
      {view?<><h3>確認条件</h3>{Object.entries(view.checks).map(([key,ok])=><p key={key}>{CHECKS[key]??key}：{ok?"計算条件を通過":"未達・未確認"}</p>)}
        <details open><summary>次に使える解析・除外理由</summary>{Object.entries(view.choices.offered).map(([key,r])=><p key={key}>{key} / {r.method}：{r.scope}</p>)}
          {Object.entries(view.choices.rejected).map(([key,reasons])=><p key={key}>{key}：{reasons.join("、")}</p>)}</details>
        {Object.entries(view.proposals).map(([key,p])=><article key={key}><h3>変更案：{key}</h3><p>{p.reason}</p>
          {p.diff.changes.map(r=><p key={r.path}>{r.path}：{JSON.stringify(r.before)} → {JSON.stringify(r.after)}</p>)}<p>再確認：{p.diff.invalidated.join("、")}</p>
          <button className="btn" disabled={disabled} onClick={()=>void action("revise",{action_id:key})}>元案を残して、この変更を新しい版にする</button></article>)}
        <details><summary>選択と判断の記録</summary>{view.decisions.map((d,i)=><p key={i}>{d.action??"選択失敗"} / {d.planner}：{d.reason}</p>)}</details>
      </>:null}</>}
    {project.active?<p role="status">{project.active.phase?.startsWith("waiting_")?"計算資源の空きを待っています":"現在のジョブを実行中です"}。再接続しても同じ処理を追跡します。</p>:null}
    {error?<p role="alert">{error}</p>:null}
  </section>;
}
