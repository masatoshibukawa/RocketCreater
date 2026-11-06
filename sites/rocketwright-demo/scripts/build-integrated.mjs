import {spawnSync} from "node:child_process";
import {cpSync,mkdirSync,existsSync,lstatSync,realpathSync,rmSync} from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";
const site=fileURLToPath(new URL("../",import.meta.url));
const app=path.join(site,"integrated-src");
const build=spawnSync(process.execPath,[path.join(app,"node_modules/next/dist/bin/next"),"build"],{cwd:app,stdio:"inherit",env:{...process.env,NEXT_TELEMETRY_DISABLED:"1"}});
if(build.status!==0)process.exit(build.status??1);
const destination=path.resolve(site,"dist/functional");
if(existsSync(destination)){
  if(lstatSync(destination).isSymbolicLink()||path.relative(realpathSync(site),realpathSync(destination))!==path.join("dist","functional"))throw new Error("Unexpected generated output path");
  rmSync(destination,{recursive:true});
}
mkdirSync(destination,{recursive:true});
cpSync(path.join(app,"out"),destination,{recursive:true});
console.log("Built integrated workbench demo at dist/functional/.");
