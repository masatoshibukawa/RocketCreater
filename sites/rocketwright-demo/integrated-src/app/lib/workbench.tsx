"use client";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import record from "../../public/demo-data.json";
import type { WorkbenchProject, RuntimeStatus } from "./workbench-types";
export type { WorkbenchProject, RuntimeStatus } from "./workbench-types";

const data = record as unknown as {
  snapshots: WorkbenchProject[]; files: WorkbenchProject["files"];
  print_package: WorkbenchProject["print_package"]; video_plan: NonNullable<WorkbenchProject["video_plan"]>;
};
type Flags = { production:boolean; manufacturing:boolean; manual:boolean; plan:boolean; video:boolean };
type Value = { project:WorkbenchProject; runtime:RuntimeStatus; busy:string; error:string; elapsed:number; act:(operation:string,extra?:Record<string,unknown>)=>Promise<void> };
const Context = createContext<Value | null>(null);
const complete = {production:true,manufacturing:true,manual:true,plan:true,video:true};
const empty = {production:false,manufacturing:false,manual:false,plan:false,video:false};
export function DemoProvider({children}:{children:ReactNode}) {
  const [stage,setStage] = useState(8);
  const [session,setSession] = useState(0);
  const [flags,setFlags] = useState<Flags>(complete);
  const [error,setError] = useState("");
  const project = useMemo(() => {
    const snapshot = structuredClone(data.snapshots[stage]);
    snapshot.id = `recorded-session-${session}`;
    snapshot.revision = stage;
    snapshot.files = data.files.filter(file => flags.production && file.kind === "production" || flags.manufacturing && file.kind === "manufacturing" || flags.manual && file.kind === "manual" || flags.video && file.kind === "video");
    if (flags.manufacturing) snapshot.print_package = data.print_package;
    if (flags.plan) snapshot.video_plan = {...data.video_plan,status:flags.video?"rendered":"planned"};
    return snapshot;
  },[stage,flags,session]);
  async function act(operation:string, extra:Record<string,unknown> = {}) {
    setError("");
    if (operation === "create") {setStage(0);setFlags(empty);setSession(value=>value+1);return;}
    if (operation === "complete") {setStage(8);setFlags(complete);setSession(value=>value+1);return;}
    if (operation === "steps") {
      const next = data.snapshots[stage].options[0];
      if (!next || next.id !== extra.id) {setError("この公開デモに収録された工程を選んでください。");return;}
      setStage(value=>Math.min(8,value+1));return;
    }
    if (stage < 8) {setError("収録された8工程を確認してから、成果物を開いてください。");return;}
    const key = ({exports:"production","print-package":"manufacturing","assembly-pdf":"manual","video-plan":"plan","render-video":"video"} as Record<string,keyof Flags>)[operation];
    if (key) setFlags(value=>({...value,[key]:true}));
    else setError("この操作の新規実行はローカル統合版で利用できます。公開版は保存記録の体験デモです。");
  }
  return <Context.Provider value={{project,runtime:{ollama:{available:false,models:["保存済みGemma提案"]},comfyui:{available:false}},busy:"",error,elapsed:0,act}}>{children}</Context.Provider>;
}
export function useWorkbench() {const value=useContext(Context);if(!value)throw new Error("DemoProvider is required");return value;}

export async function demoFetch(path:string, _options?:unknown) {
  const url = new URL(path,"https://demo.invalid");
  let result:unknown;
  if (url.pathname === "/workbench/library") result = record.library;
  else if (url.pathname === "/workbench/references") {
    const query = (url.searchParams.get("q")??"").normalize("NFKC").toLocaleLowerCase();
    const category = url.searchParams.get("category")??"all";
    const records = record.references.records.filter(row=>(category==="all"||row.group===category)&&JSON.stringify(row).normalize("NFKC").toLocaleLowerCase().includes(query));
    result = {counts:record.references.counts,total:records.length,records};
  } else throw new Error("公開デモに収録されていないデータです。");
  return {ok:true,status:200,json:async()=>structuredClone(result)};
}
