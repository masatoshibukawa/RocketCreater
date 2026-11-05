"""Blender worker: geometry from one confirmed assembly; launch from its computed trace."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

job_path = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
job = json.loads(job_path.read_text(encoding="utf-8"))
output = job_path.parent
preview = "--preview" in sys.argv
if preview:
    output = output / "preview"
    output.mkdir(exist_ok=True)
g = {k: v / 1000 for k, v in job["dimensions_mm"].items()}
plan = job["plan"]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8
scene.cycles.use_denoising = True
scene.render.resolution_x = plan["width"]
scene.render.resolution_y = plan["height"]
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = plan["fps"]
scene.world.color = (0.12, 0.15, 0.2)


def material(name, color, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = 0.32
    return mat


shell = material("Bottle exterior representation", (0.16, 0.29, 0.32), 0.4)
white = material("Payload and recovery covers", (0.68, 0.72, 0.7), 0.25)
fin_mat = material("Fin sheet", (0.19, 0.4, 0.4), 0.1)
ground_mat = material("Ground", (0.055, 0.065, 0.07))
root = bpy.data.objects.new("Confirmed assembly", None)
scene.collection.objects.link(root)
r = g["body_diameter"] / 2
length = g["overall"]


def cylinder(name, radius, depth, z, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    obj.parent = root
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Small edge radius", "BEVEL")
    bevel.width = 0.001
    bevel.segments = 2
    return obj


bottle_top = length - g["nose_length"] - g["egg_bay_length"] - g["canopy_bay_length"]
cylinder("Bottle", r, bottle_top, bottle_top / 2, shell)
cylinder("Recovery bay", r, g["canopy_bay_length"], bottle_top + g["canopy_bay_length"] / 2, white)
cylinder(
    "Payload bay",
    r,
    g["egg_bay_length"],
    length - g["nose_length"] - g["egg_bay_length"] / 2,
    white,
)
bpy.ops.mesh.primitive_cone_add(
    vertices=48,
    radius1=r,
    radius2=0,
    depth=g["nose_length"],
    location=(0, 0, length - g["nose_length"] / 2),
)
bpy.context.object.parent = root
bpy.context.object.data.materials.append(shell)
for i in range(4):
    z = g["fin_tail_inset"]
    vertices = [
        (r, 0, z),
        (r + g["fin_span"], 0, z + g["fin_root"] - g["fin_sweep"] - g["fin_tip"]),
        (r + g["fin_span"], 0, z + g["fin_root"] - g["fin_sweep"]),
        (r, 0, z + g["fin_root"]),
    ]
    mesh = bpy.data.meshes.new("Fin outline")
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("Fin " + str(i + 1), mesh)
    scene.collection.objects.link(obj)
    obj.parent = root
    obj.rotation_euler.z = i * math.pi / 2
    obj.data.materials.append(fin_mat)
    solid = obj.modifiers.new("Sheet thickness representation", "SOLIDIFY")
    solid.thickness = 0.001

bpy.ops.mesh.primitive_plane_add(size=400)
ground = bpy.context.object
ground.location.z = -0.01
ground.data.materials.append(ground_mat)
bpy.ops.object.light_add(type="AREA", location=(2, -2, 4))
bpy.context.object.data.energy = 350
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 4
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.context.object.data.energy = 1.5
bpy.ops.object.camera_add()
camera = bpy.context.object
scene.camera = camera
camera.data.lens = 45


def look_at(position, target):
    camera.location = position
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


trace = job["trace"]
fps = plan["fps"]
count = plan["frames_per_clip"]
if preview:
    count = 1
camera_distance = length * 4.5  # Complete assembly inside the caption-safe frame.
for mode in ("design", "launch"):
    frames = output / (mode + "-frames")
    frames.mkdir(exist_ok=True)
    for index in range(count):
        progress = index / max(1, count - 1)
        if mode == "design":
            root.location = (0, 0, 0)
            angle = -math.pi / 2 + progress * (0.6 if plan["camera"] == "slow_orbit" else 1.2)
            look_at(
                (
                    camera_distance * math.cos(angle),
                    camera_distance * math.sin(angle),
                    length * 0.8,
                ),
                (0, 0, length / 2),
            )
        else:
            # Replay the sampled solver trajectory; animation duration is presentation time.
            t = progress * trace[-1]["t_s"]
            right = next((i for i, p in enumerate(trace) if p["t_s"] >= t), len(trace) - 1)
            a, b = trace[max(0, right - 1)], trace[right]
            mix = (t - a["t_s"]) / max(1e-9, b["t_s"] - a["t_s"])
            position = [a[k] + (b[k] - a[k]) * mix for k in ("east_m", "north_m", "altitude_m")]
            root.location = position
            look_at(
                (
                    position[0] + camera_distance * 0.55,
                    position[1] - camera_distance * 0.85,
                    position[2] + length * 0.9,
                ),
                (position[0], position[1], position[2] + length / 2),
            )
        scene.render.filepath = str(frames / f"{index:04d}.png")
        bpy.ops.render.render(write_still=True)
    if mode == "design" and not preview:
        bpy.ops.wm.save_as_mainfile(filepath=str(output / "assembly.blend"))
