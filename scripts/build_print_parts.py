"""Build design-bound non-pressure parts with the existing inspected Blender CAD functions."""

import json
import runpy
import sys
from pathlib import Path

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[1]
config_path, output_path = sys.argv[sys.argv.index("--") + 1 :]
config = json.loads(Path(config_path).read_text(encoding="utf-8"))
out = Path(output_path)
out.mkdir(parents=True, exist_ok=True)
cad = runpy.run_path(str(root / "3d model/prototypes/pet-rocket-coke-2l/build.py"))
cad["validate_parameters"](config)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
assembly_fin = cad["make_fin"](config)
cad["clean_numeric_seams"](assembly_fin)
cad["save_stl"](assembly_fin, out / "fin-assembly-mm.stl")
fin = cad["print_copy"](assembly_fin, config["fin"]["print_rotation_y_deg"])
bpy.data.objects.remove(assembly_fin, do_unlink=True)
profile, _ = cad["nose_profile"](config)
nose = cad["revolve"]("Nose", profile, config["resolution"])
r = config["bottle"]["body_diameter"] / 2 + config["bottle"]["radial_clearance"]
h, wall = config["fit_ring"]["height"], config["fit_ring"]["wall"]
ring = cad["revolve"](
    "FitRing", [(r, 0), (r + wall, 0), (r + wall, h), (r, h)], config["resolution"]
)
parts = {"fin": fin, "nose": nose, "fit-ring": ring}
if not config.get("include_fins", True):
    parts.pop("fin")
    bpy.data.objects.remove(fin, do_unlink=True)
report = {}
for name, obj in parts.items():
    cad["clean_numeric_seams"](obj)
    result = cad["inspect_mesh"](obj, config["mass_density_g_cm3"])
    cad["require_valid_solid"](result, name)
    cad["save_stl"](obj, out / f"{name}-mm.stl")
    report[name] = result
    material = bpy.data.materials.new(name)
    material.diffuse_color = (0.22, 0.38, 0.56, 1)
    obj.data.materials.append(material)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8
scene.render.resolution_x = 300
scene.render.resolution_y = 300
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.4, 0.4, 0.4)
bpy.ops.object.light_add(type="SUN", location=(100, -100, 200))
bpy.context.object.data.energy = 3
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
scene.camera = camera
for name, obj in parts.items():
    for other in parts.values():
        other.hide_render = other != obj
    report[name]["preview_visible_meshes"] = [
        other.name for other in bpy.data.objects if other.type == "MESH" and not other.hide_render
    ]
    if len(report[name]["preview_visible_meshes"]) != 1:
        raise ValueError("A part preview must contain only its own mesh")
    center = sum((obj.matrix_world @ Vector(v) for v in obj.bound_box), Vector()) / 8
    extent = max(obj.dimensions)
    camera.location = center + Vector((extent * 2, -extent * 3, extent * 2))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = extent * 1.7
    scene.render.filepath = str(out / f"{name}-preview.png")
    bpy.ops.render.render(write_still=True)
(out / "geometry-check.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
