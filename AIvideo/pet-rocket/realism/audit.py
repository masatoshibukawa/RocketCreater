"""Check the refined scenes against frozen source CAD and texture hashes."""

import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from audit_scene import vertices


def main():
    records=[]
    for film in ("design","launch"):
        bpy.ops.wm.open_mainfile(filepath=str(ROOT/"renders"/(film+".blend")))
        meshes=[]
        for name,filename in [("Exact source nose STL","nose_cone.stl"),("Exact source fin STL 1","fin_assembly.stl")]:
            obj=bpy.data.objects[name]
            actual=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
            obj.data.vertices.foreach_get("co",actual);actual=actual.reshape((-1,3))
            expected=vertices(ROOT.parent/"assets"/filename)
            assert actual.shape==expected.shape
            error=float(np.max(np.abs(actual-expected)))
            assert error<1e-7 and tuple(obj.scale)==(1,1,1)
            meshes.append({"mesh":name,"maximum_coordinate_error_m":error,"source":filename})
        fins=[bpy.data.objects[f"Exact source fin STL {i}"] for i in (1,2,3)]
        assert all(abs(obj.rotation_euler.z-math.radians(i*120))<1e-5 for i,obj in enumerate(fins))
        assert all(abs(obj.location.z-.1)<1e-7 for obj in fins)
        assert abs(bpy.data.objects["Exact source nose STL"].location.z-.262)<1e-7
        assert bpy.context.scene.render.filepath.startswith("//")
        assert all(image.filepath.replace("\\","/").startswith("//../cache/") for image in bpy.data.images if image.source=="FILE")
        records.append({"film":film,"meshes":meshes,"three_fin_placement":"passed","relative_asset_paths":"passed","saved_frame":bpy.context.scene.frame_current,"width":bpy.context.scene.render.resolution_x,"height":bpy.context.scene.render.resolution_y,"camera_z_m":float(bpy.context.scene.camera.location.z)})
    manifest=json.loads((ROOT/"asset-manifest.json").read_text())
    for record in manifest["files"]:
        assert hashlib.sha256((ROOT/record["file"]).read_bytes()).hexdigest()==record["sha256"]
    (ROOT/"geometry-audit.json").write_text(json.dumps({"checks":"passed","scenes":records,"photo_asset_hashes":"passed","scope":"Original nose/fin geometry and assembly; bottle surface detail and equipment remain unmeasured illustrative geometry"},indent=2)+"\n",encoding="utf-8")
    print("Refined scenes preserve source CAD and verified photo assets")


if __name__=="__main__":main()
