"use client";

import { defaultEquipment, type ProductionSpec, type ProjectEquipment } from "../lib/designProjects";

const NUMBERS = [
  ["hand_width_mm", "手の幅 mm"], ["glove_allowance_mm", "手袋の片側余裕 mm"],
  ["strap_width_mm", "固定材の幅 mm"], ["strap_thickness_mm", "固定材の厚さ mm"],
  ["tool_radius_mm", "工具の包絡半径 mm"], ["workbench_clear_width_mm", "作業台の空き幅 mm"],
  ["required_force_n", "操作に必要な力 N（測定）"], ["allowable_force_n", "担当者の操作力上限 N（確認）"],
] as const;
const PARTS = {bottle:"ボトル", fin:"フィン", nose:"ノーズ", fixing:"固定材一式", payload:"搭載物", recovery:"回収装置", soft_cap:"軟質先端", other:"工具・送料・その他"};

export default function ProjectEquipmentEditor({spec, onChange}: {spec: ProductionSpec; onChange:(value: ProductionSpec)=>void}) {
  const equipment = spec.equipment ?? defaultEquipment();
  function change(value: Partial<ProjectEquipment>) { onChange({...spec, equipment:{...equipment,...value}}); }
  function purchase(part: string, patch: Partial<ProjectEquipment["procurement"][number]>) {
    const previous = equipment.procurement.find(r=>r.part===part) ?? {part, quantity:part==="fin"?spec.geometry.fin_count:1, unit_price_jpy:null, basis:"unknown" as const, source:"", checked_on:""};
    change({procurement:[...equipment.procurement.filter(r=>r.part!==part), {...previous,...patch}]});
  }
  return <details><summary>機材・工具・調達と組立条件</summary>
    <p className="wb-note">S5 / Tough PLA Gray / AA 0.4 / ガラス。未確認の寸法・価格・操作力は空欄のまま保存できます。</p>
    <div className="project-fields">
      {(["printer_label","material_lot","operator","glove"] as const).map((key,i)=><label key={key}>{["機材名","材料ロット","作業担当","手袋の種類"][i]}<input value={equipment[key]} maxLength={80} onChange={e=>change({[key]:e.target.value})}/></label>)}
      {NUMBERS.map(([key,label])=><label key={key}>{label}<input type="number" min="0" step="any" value={equipment[key]??""} onChange={e=>change({[key]:e.target.value===""?null:Number(e.target.value)})}/></label>)}
      <label>工具（読点で区切る）<input value={equipment.tools.join("、")} onChange={e=>change({tools:e.target.value.split("、").filter(Boolean)})}/></label>
    </div>
    <p className="wb-note">フィン等は1個当たりの価格。固定材とその他は一式です。数量・根拠・確認日が揃った見積／購入額だけで予算を評価します。</p>
    {Object.entries(PARTS).filter(([key])=>!(key==="fin"&&!spec.design.has_fins)&&!(key==="recovery"&&!spec.design.has_parachute)&&!(key==="payload"&&!spec.design.payload_mass_kg)).map(([key,label])=>{
      const row=equipment.procurement.find(r=>r.part===key);
      return <fieldset key={key}><legend>{label}</legend><div className="project-fields">
        <label>数量<input type="number" min="1" max="100" value={row?.quantity??(key==="fin"?spec.geometry.fin_count:1)} onChange={e=>purchase(key,{quantity:Number(e.target.value)})}/></label>
        <label>単価 円<input type="number" min="0" value={row?.unit_price_jpy??""} onChange={e=>purchase(key,{unit_price_jpy:e.target.value===""?null:Number(e.target.value)})}/></label>
        <label>価格の根拠<select value={row?.basis??"unknown"} onChange={e=>purchase(key,{basis:e.target.value as ProjectEquipment["procurement"][number]["basis"]})}>{[["unknown","未確認"],["estimate","仮定"],["quote","見積"],["paid","購入済み"]].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
        <label>出典・見積番号<input value={row?.source??""} onChange={e=>purchase(key,{source:e.target.value})}/></label>
        <label>確認日<input type="date" value={row?.checked_on??""} onChange={e=>purchase(key,{checked_on:e.target.value})}/></label>
      </div></fieldset>;
    })}
  </details>;
}
