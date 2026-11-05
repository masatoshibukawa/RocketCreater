"""Render representative photographs first, then produce both new scene sequences."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent


def signature():
    files=[ROOT/n for n in ("scene.py","settings.json","asset-manifest.json")]
    files += [ROOT.parent/n for n in ("scenario.json","simulation.json","render_scene.py","assets/nose_cone.stl","assets/fin_assembly.stl","renders/trajectory.npz")]
    return hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--blender",default="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--film",choices=["design","launch","both"],default="both")
    args=parser.parse_args()
    out=ROOT/"renders";out.mkdir(exist_ok=True)
    env=os.environ.copy();env["BLENDER_USER_RESOURCES"]=str(out/"blender-user")
    config=json.loads((ROOT/"settings.json").read_text())
    tasks=[("design",1),("design",170),("launch",1),("launch",80),("launch",230)] if args.preview else [(kind,None) for kind in ("design","launch") if args.film in ("both",kind)]
    for film,frame in tasks:
        directory=out/(film+"-frames");marker=directory/"input-signature.txt"
        if not frame:
            directory.mkdir(exist_ok=True)
            if marker.exists() and marker.read_text()!=signature():raise RuntimeError("Inputs changed; use a new render directory before reusing frames")
            marker.write_text(signature())
            count=config[film+"_frames"]
            missing=[i for i in range(1,count+1) if not (directory/f"frame_{i:04d}.png").exists()]
            if not missing:
                print("Reuse complete "+film,flush=True);continue
            start=min(missing) if film=="design" else 1
        command=[args.blender,"--background","--python-exit-code","1","--python",str(ROOT/"scene.py"),"--","--film",film]
        if frame:command += ["--preview",str(frame),"--width","960","--samples","32"]
        else:command += ["--start",str(start)]
        print(f"Rendering {film} "+(f"preview {frame}" if frame else f"from frame {start}"),flush=True)
        with (out/(film+(f"-preview-{frame}" if frame else "-render")+".log")).open("w",encoding="utf-8") as log:
            subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        if "Traceback (most recent call last)" in Path(log.name).read_text(encoding="utf-8"):
            raise RuntimeError("Blender handler failed; inspect "+Path(log.name).name)
    print("Rendering complete",flush=True)


if __name__=="__main__":main()
