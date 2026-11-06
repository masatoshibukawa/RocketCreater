"use client";
import WorkbenchPanel from "./components/WorkbenchPanel";
import {DemoProvider,useWorkbench} from "./lib/workbench";
function Demo() {
  const {act}=useWorkbench();
  return <><div className="recorded-banner"><div><b>統合版の機能デモ</b><span>実行済み8工程・成果物・動画の保存記録を操作できます。新規の解析・LLM・スライス・動画生成は行いません。</span></div><nav><button onClick={()=>void act("complete")}>完成例を見る</button><button onClick={()=>void act("create")}>工程を最初から</button><a href="/">画面デモへ</a></nav></div><WorkbenchPanel onOpenDesign={()=>{window.location.href="/";}}/></>;
}
export default function Page(){return <DemoProvider><Demo/></DemoProvider>;}
