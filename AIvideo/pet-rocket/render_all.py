"""Render both films sequentially, resuming from the first missing PNG."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from cache_inputs import signature

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--blender",default="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    parser.add_argument("--samples",type=int,default=24)
    parser.add_argument("--reuse-verified",action="store_true",help="Adopt legacy complete frame caches only after successful current-input verification")
    args=parser.parse_args()
    environment=os.environ.copy()
    environment["BLENDER_USER_RESOURCES"]=str(ROOT/"renders/blender-user")
    for film,count in [("design",384),("launch",336)]:
        settings=json.loads((ROOT/"render-settings.json").read_text())
        directory=ROOT/"renders"/settings[film+"_frames"]
        marker=directory/"cache-inputs.json"
        fingerprint=signature()+f":samples={args.samples}"
        if marker.exists():
            if json.loads(marker.read_text())["fingerprint"]!=fingerprint:
                raise RuntimeError("Inputs changed: choose new frame-directory names in render-settings.json instead of reusing old frames")
        elif directory.exists() and any(directory.glob("*.png")):
            verification=ROOT/"verification.json"
            if not args.reuse_verified or not verification.exists() or json.loads(verification.read_text()).get("input_signature")!=signature():
                raise RuntimeError("Untracked frame cache: verify current inputs and use --reuse-verified, or choose new frame directories")
            marker.write_text(json.dumps({"fingerprint":fingerprint,"adopted_after_current_input_verification":True},indent=2)+"\n")
        else:
            directory.mkdir(parents=True,exist_ok=True)
            marker.write_text(json.dumps({"fingerprint":fingerprint,"adopted_after_current_input_verification":False},indent=2)+"\n")
        missing=[index for index in range(1,count+1) if not (directory/f"frame_{index:04d}.png").is_file()]
        if not missing:
            print(f"Reuse {film}: all {count} frames exist",flush=True)
            continue
        start=min(missing)
        print(f"Render {film}: frames {start}..{count}",flush=True)
        with (ROOT/"renders"/(film+"-render.log")).open("a",encoding="utf-8") as log:
            subprocess.run([args.blender,"--background","--python-exit-code","1","--python",str(ROOT/"render_scene.py"),"--","--film",film,"--start",str(start),"--end",str(count),"--samples",str(args.samples)],check=True,env=environment,stdout=log,stderr=subprocess.STDOUT)
        print(f"Finished {film}",flush=True)
    print("Both scene sequences complete",flush=True)


if __name__=="__main__": main()
