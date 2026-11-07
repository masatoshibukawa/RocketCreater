"""Blender-only diagnostic: preserve a rejected print mesh for an independent STL audit."""

import hashlib
import json
import runpy
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

root = Path(__file__).resolve().parents[1]
parent, output = map(Path, sys.argv[sys.argv.index("--") + 1 :])
output.mkdir(parents=True, exist_ok=False)
config_path = parent / "parameters.json"
config = json.loads(config_path.read_text(encoding="utf-8"))
cad = runpy.run_path(str(root / "3d model/prototypes/pet-rocket-coke-2l/build.py"))
cad["validate_parameters"](config)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
assembly = cad["make_fin"](config)
cad["clean_numeric_seams"](assembly)
cad["save_stl"](assembly, output / "assembly.stl")
original = (parent / "fin-assembly-mm.stl").read_bytes()
if original != (output / "assembly.stl").read_bytes():
    raise ValueError("Regenerated assembly differs from rejected candidate")
obj = cad["print_copy"](assembly, config["fin"]["print_rotation_y_deg"])
cad["clean_numeric_seams"](obj)
inspection = cad["inspect_mesh"](obj, config["mass_density_g_cm3"])
cad["save_stl"](obj, output / "rejected-print.stl")
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.triangulate(bm, faces=list(bm.faces))
bm.verts.ensure_lookup_table()
bm.faces.ensure_lookup_table()
tree = BVHTree.FromBMesh(bm, epsilon=0.000001)
face_verts = [set(v.index for v in face.verts) for face in bm.faces]
pairs = sorted(
    {
        tuple(sorted((a, b)))
        for a, b in tree.overlap(tree)
        if a != b and not face_verts[a] & face_verts[b]
    }
)
result = dict(
    purpose="diagnose rejection; no candidate substitution or acceptance",
    parameter_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
    assembly_identical=True,
    inspection=inspection,
    pairs=[
        dict(indices=[a, b], triangles=[[list(v.co) for v in bm.faces[i].verts] for i in (a, b)])
        for a, b in pairs
    ],
)
bm.free()
(output / "probe.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(result, flush=True)
