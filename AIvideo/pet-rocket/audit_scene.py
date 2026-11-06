"""Check stored Blender geometry against the original binary STL data."""

import json
import math
from pathlib import Path
import struct

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parent


def vertices(path):
    data=path.read_bytes()
    count=struct.unpack_from("<I",data,80)[0]
    result=[]
    for index in range(count):
        numbers=struct.unpack_from("<12fH",data,84+50*index)
        result.extend(tuple(numbers[3+3*j+k]*.001 for k in range(3)) for j in range(3))
    return np.asarray(result)


def main():
    reports=[]
    for film in ("design","launch"):
        bpy.ops.wm.open_mainfile(filepath=str(ROOT/"renders"/(film+".blend")))
        entries=[]
        for label,source in [("Exact source nose STL","nose_cone.stl"),("Exact source fin STL 1","fin_assembly.stl")]:
            obj=bpy.data.objects[label]
            actual=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
            obj.data.vertices.foreach_get("co",actual)
            actual=actual.reshape((-1,3))
            expected=vertices(ROOT/"assets"/source)
            error=float(np.max(np.abs(actual-expected)))
            assert actual.shape==expected.shape and error<1e-7
            entries.append({"mesh":label,"source":source,"maximum_coordinate_difference_m":error,"bounds_m":[actual.min(axis=0).tolist(),actual.max(axis=0).tolist()]})
        fins=[bpy.data.objects[f"Exact source fin STL {i}"] for i in (1,2,3)]
        azimuth=[float(obj.rotation_euler.z)*180/math.pi for obj in fins]
        assert all(abs(value-target)<1e-4 for value,target in zip(azimuth,[0,120,240]))
        assert all(abs(obj.location.z-.100)<1e-7 for obj in fins)
        assert abs(bpy.data.objects["Exact source nose STL"].location.z-.262)<1e-7
        assert not bpy.context.scene.render.filepath.lower().startswith("c:")
        reports.append({"film":film,"meshes":entries,"fin_count":len(fins),"azimuth_deg":azimuth,"fin_tail_z_m":.1,"nose_base_z_m":.262,"render_path":bpy.context.scene.render.filepath})
    (ROOT/"geometry-audit.json").write_text(json.dumps({"checks":"passed","scenes":reports},indent=2)+"\n",encoding="utf-8")
    print("Stored Blender meshes and assembly positions match source STL")


if __name__=="__main__":main()
