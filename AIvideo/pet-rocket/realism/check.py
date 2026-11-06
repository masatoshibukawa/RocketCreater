"""Normalize scene metadata, audit CAD, decode all films and check disclosure metadata."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import av
from PIL import Image

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import audit_metadata
import sanitize_scenes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--blender",default="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    args=parser.parse_args()
    sanitize_scenes.ROOT=ROOT;sanitize_scenes.main()
    env=os.environ.copy();env["BLENDER_USER_RESOURCES"]=str(ROOT/"renders/blender-user")
    subprocess.run([args.blender,"--background","--python-exit-code","1","--python",str(ROOT/"audit.py")],env=env,check=True)
    subprocess.run([sys.executable,str(ROOT/"verify.py")],check=True)
    audit_metadata.ROOT=ROOT;audit_metadata.main()
    report=json.loads((ROOT/"artifact-audit.json").read_text())
    for kind,name in [("design","pet_rocket_design_cinematic.mp4"),("launch","pet_rocket_launch_cinematic.mp4")]:
        with av.open(str(ROOT/"renders"/name)) as source:
            metadata={"container":dict(source.metadata),"streams":[dict(s.metadata) for s in source.streams]}
        assert not any(term in json.dumps(metadata).encode().lower() for term in audit_metadata.FORBIDDEN)
        report["records"].append({"file":"renders/"+name,"metadata":metadata})
        for suffix in ("-cinematic-poster.png","-cinematic-contact.jpg"):
            with Image.open(ROOT/"renders"/(kind+suffix)) as image:
                assert not any(term in str(image.info).encode().lower() for term in audit_metadata.FORBIDDEN)
    report["film_count"]=4;report["image_count"]=8
    (ROOT/"artifact-audit.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("All four films, source CAD, photo assets and metadata pass")


if __name__=="__main__":main()
