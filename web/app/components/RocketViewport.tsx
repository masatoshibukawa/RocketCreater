"use client";

import { useId } from "react";
import type { WorkbenchProject } from "../lib/workbench";

export default function RocketViewport({ project, working }: { project: WorkbenchProject | null; working: boolean }) {
  const unique = useId().replace(/:/g, "");
  const g = project?.plan?.dimensions_mm;
  if (!g) return <div className="wb-empty-model">
    <svg viewBox="0 0 200 300" width="100" aria-hidden="true"><path d="M100 15 124 60v180l28 38-28-13H76l-28 13 28-38V60Z" fill="none" stroke="currentColor" strokeWidth="1"/><path d="M76 96h48M76 210h48M100 0v300" stroke="currentColor" strokeDasharray="3 5"/></svg>
    <h2>要求から、構成を確かめる</h2><p>右のパネルから最初の工程を開始します。</p>
  </div>;
  const scale = 490 / g.overall;
  const top = 85, bottom = top + 490, radius = g.body_diameter * scale / 2;
  const noseEnd = top + g.nose_length * scale;
  const eggEnd = noseEnd + g.egg_bay_length * scale;
  const canopyEnd = eggEnd + g.canopy_bay_length * scale;
  const finBottom = bottom - g.fin_tail_inset * scale;
  const finTop = finBottom - g.fin_root * scale;
  const outer = radius + g.fin_span * scale;
  return <div className="wb-viewport">
    <svg viewBox="0 0 760 650" role="img" aria-label="現在の構成案から計算したロケット外形と配置寸法">
      <defs>
        <linearGradient id={`${unique}-body`}><stop stopColor="#263638"/><stop offset=".45" stopColor="#a1b6b5"/><stop offset=".55" stopColor="#697f80"/><stop offset="1" stopColor="#1b282b"/></linearGradient>
        <linearGradient id={`${unique}-cap`}><stop stopColor="#455252"/><stop offset=".45" stopColor="#e0e4dd"/><stop offset="1" stopColor="#485654"/></linearGradient>
        <pattern id={`${unique}-grid`} width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="#1a2022" strokeWidth=".7"/></pattern>
      </defs>
      <rect width="760" height="650" fill={`url(#${unique}-grid)`}/>
      <ellipse cx="365" cy="596" rx="144" ry="14" fill="#000" opacity=".45"/>
      <path d={`M365 ${top - 25}V600`} stroke="#3c4a4b" strokeDasharray="4 7"/>
      <g transform="translate(365 0)">
        <path d={`M0 ${top}Q${radius * .8} ${top + 15} ${radius} ${noseEnd}H${-radius}Q${-radius * .8} ${top + 15} 0 ${top}`} fill={`url(#${unique}-body)`} stroke="#7d9999"/>
        <rect x={-radius} y={noseEnd} width={radius * 2} height={canopyEnd - noseEnd} fill={`url(#${unique}-cap)`} stroke="#566868"/>
        <rect x={-radius} y={canopyEnd} width={radius * 2} height={bottom - canopyEnd} fill={`url(#${unique}-body)`} stroke="#566868"/>
        <path d={`M${-radius} ${eggEnd}H${radius}M${-radius} ${canopyEnd + 5}H${radius}`} stroke="#2a393b" strokeWidth="3"/>
        {[-1, 1].map(side => <polygon key={side} points={`${side * radius},${finTop} ${side * outer},${finTop + g.fin_sweep * scale} ${side * outer},${finTop + (g.fin_sweep + g.fin_tip) * scale} ${side * radius},${finBottom}`} fill="#477e80" stroke="#8bb1af"/>) }
        <path d={`M0 ${finTop}V${finBottom}`} stroke="#aad6ce" strokeWidth="3"/>
      </g>
      <g stroke="#66827f" fill="none"><path d={`M175 ${top}V${bottom}M168 ${top}h14M168 ${bottom}h14M190 ${top}H350M190 ${bottom}H350`}/><path d={`M${365 + radius} ${eggEnd - 20}H520l25 -25H680M${365 + radius} ${canopyEnd - 15}H540l25 15H690M${365 + outer} ${finTop + 25}H575l20 30H690`}/></g>
      <g fill="#91a7a8" fontSize="12" fontFamily="system-ui,sans-serif">
        <text x="150" y="340" transform="rotate(-90 150 340)" textAnchor="middle">全長 {g.overall.toFixed(0)} mm</text>
        <text x="548" y={eggEnd - 52}>搭載室</text><text x="568" y={canopyEnd - 8}>回収装置</text><text x="600" y={finTop + 49}>フィン</text>
        <text x="38" y="34">ASSEMBLY / {project?.history.at(-1)?.chosen.split("/")[1]}</text>
        <text x="38" y="626">外形の概形 · 寸法 mm · {project?.confirmed ? "独立確認済みの解析案" : "構成を検討中"}</text>
      </g>
    </svg>
    {working ? <div className="wb-worker" aria-hidden="true"><span className="wb-helmet"/><span className="wb-worker-body"/><span className="wb-tool"/></div> : null}
  </div>;
}
