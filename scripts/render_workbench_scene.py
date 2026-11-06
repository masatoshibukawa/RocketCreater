"""Blender worker: geometry from one confirmed assembly; launch from its computed trace."""

import csv
import hashlib
import json
import math
import struct
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
photographic = plan.get("style") == "photographic"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "AIvideo/pet-rocket/realism"))
import appearance  # noqa: E402 -- Shared photo-based recipes, no frozen CAD/physics.

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = plan.get("samples", 8)
scene.cycles.use_denoising = True
if photographic:
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    preferences = bpy.context.preferences.addons["cycles"].preferences
    try:
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == "OPTIX"
        if any(device.use for device in preferences.devices):
            scene.cycles.device = "GPU"
    except (TypeError, RuntimeError):
        pass  # CPU remains a valid local renderer when OptiX is unavailable.
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.2
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
if photographic:
    shell = appearance.material(
        "Unmeasured clear PET wall", (0.98, 1, 1), 0.04, transmission=1, ior=1.575
    )
    appearance.surface_detail(shell)
    fin_mat = appearance.material("Assumed sheet fins", (0.25, 0.23, 0.18), 0.65)
    white = appearance.material("Unmeasured cover material", (0.72, 0.72, 0.66), 0.3)
    ground_mat = appearance.asphalt(job_path.parent / "appearance")
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
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) <= 4
    bevel = obj.modifiers.new("Small edge radius", "BEVEL")
    bevel.width = 0.001
    bevel.segments = 2
    return obj


bottle_top = length - g["nose_length"] - g["egg_bay_length"] - g["canopy_bay_length"]
if photographic:
    # Envelope dimensions are from this design. Small neck/rib details are illustrative.
    profile = [(r * 0.3, 0), (r * 0.3, bottle_top * 0.1)]
    for i in range(1, 25):
        u = i / 24
        profile.append(
            (r * (0.3 + 0.7 * (0.5 - 0.5 * math.cos(u * math.pi))), bottle_top * (0.1 + 0.25 * u))
        )
    for i in range(1, 65):
        u = i / 64
        profile.append((r - 0.00015 * math.sin(u * 35) ** 8, bottle_top * (0.35 + 0.65 * u)))
    profile.append((0, bottle_top))
    segments = 128
    vertices = [
        (radius * math.cos(i * math.tau / segments), radius * math.sin(i * math.tau / segments), z)
        for radius, z in profile
        for i in range(segments)
    ]
    faces = [
        (
            j * segments + i,
            j * segments + (i + 1) % segments,
            (j + 1) * segments + (i + 1) % segments,
            (j + 1) * segments + i,
        )
        for j in range(len(profile) - 1)
        for i in range(segments)
    ]
    mesh = bpy.data.meshes.new("Assumed PET envelope")
    mesh.from_pydata(vertices, [], faces)
    bottle = bpy.data.objects.new("Bottle", mesh)
    scene.collection.objects.link(bottle)
    bottle.parent = root
    bottle.data.materials.append(shell)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    wall = bottle.modifiers.new("Assumed PET thickness", "SOLIDIFY")
    wall.thickness = 0.00035
    wall.offset = -1
else:
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
if photographic:
    bpy.context.object.data.materials.clear()
    bpy.context.object.data.materials.append(white)
    for polygon in bpy.context.object.data.polygons:
        polygon.use_smooth = len(polygon.vertices) <= 4
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
if photographic:
    ground.hide_render = True
    bench_mat = appearance.material("Workshop bench", (0.22, 0.25, 0.27), 0.3, metallic=0.7)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.78))
    bench = bpy.context.object
    bench.name = "Illustrative workbench"
    bench.dimensions = (1.8, 1.15, 0.08)
    bench.data.materials.append(bench_mat)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.821))
    mat = bpy.context.object
    mat.name = "Cutting mat"
    mat.dimensions = (0.9, 0.7, 0.002)
    mat.data.materials.append(appearance.material("Cutting mat", (0.025, 0.07, 0.061), 0.8))
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
if photographic:
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 8


def look_at(position, target):
    camera.location = position
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


trace = job["trace"]
liquid = None
if photographic:
    water = appearance.material(
        "Clear remaining water", (1, 1, 1), 0.015, transmission=1, ior=1.333
    )
    liquid_mesh = bpy.data.meshes.new("Solver-mass water envelope")
    liquid = bpy.data.objects.new("Remaining water", liquid_mesh)
    scene.collection.objects.link(liquid)
    liquid.parent = root
    liquid.data.materials.append(water)
    # Integrate the illustrative bottle envelope; volume follows the solver mass excess.
    positive_profile = [(radius - 0.0004, z) for radius, z in profile if radius > 0.0004]
    cumulative = [0.0]
    for (ra, za), (rb, zb) in zip(positive_profile[:-1], positive_profile[1:], strict=True):
        cumulative.append(cumulative[-1] + (zb - za) * math.pi * (ra * ra + ra * rb + rb * rb) / 3)

    def water_volume(volume):
        liquid.hide_render = volume < 1e-8
        if liquid.hide_render:
            return
        k = next((i for i, v in enumerate(cumulative) if v >= volume), len(cumulative) - 1)
        k = max(1, k)
        ra, za = positive_profile[k - 1]
        rb, zb = positive_profile[k]
        fraction = max(
            0, min(1, (volume - cumulative[k - 1]) / max(1e-12, cumulative[k] - cumulative[k - 1]))
        )
        top_r, top_z = ra + (rb - ra) * fraction, za + (zb - za) * fraction
        rows = [(0, 0.001)] + positive_profile[:k] + [(top_r, top_z), (0, top_z)]
        segments = 96
        verts = [
            (
                radius * math.cos(i * math.tau / segments),
                radius * math.sin(i * math.tau / segments),
                z,
            )
            for radius, z in rows
            for i in range(segments)
        ]
        faces = [
            (
                j * segments + i,
                j * segments + (i + 1) % segments,
                (j + 1) * segments + (i + 1) % segments,
                (j + 1) * segments + i,
            )
            for j in range(len(rows) - 1)
            for i in range(segments)
        ]
        liquid_mesh.clear_geometry()
        liquid_mesh.from_pydata(verts, [], faces)
        liquid_mesh.update()
        for polygon in liquid_mesh.polygons:
            polygon.use_smooth = True


fps = plan["fps"]
count = plan["frames_per_clip"]
if preview:
    count = 1
camera_distance = length * 4.5  # Complete assembly inside the caption-safe frame.
geometry_source = hashlib.sha256(
    json.dumps(job["dimensions_mm"], sort_keys=True).encode()
).hexdigest()
mesh_hashes = {
    obj.name: hashlib.sha256(
        b"".join(struct.pack("<3d", *v.co) for v in obj.data.vertices)
    ).hexdigest()
    for obj in root.children
    if obj.type == "MESH"
}
for mode in ("design", "launch"):
    count = plan.get(mode + "_frames", plan["frames_per_clip"])
    if photographic:
        appearance.photo_world(mode, job_path.parent / "appearance")
        ground.hide_render = mode == "design"
        bench.hide_render = mat.hide_render = mode != "design"
    states = []
    frames = output / (mode + "-frames")
    frames.mkdir(exist_ok=True)
    for index in [0, count // 2, count - 1] if preview else range(count):
        progress = index / max(1, count - 1)
        if mode == "design":
            base_height = 0.823 if photographic else 0
            root.location = (0, 0, base_height)
            if photographic:
                water_volume(job["design"]["bottle_volume_m3"] * job["design"]["water_fill_frac"])
            angle = -math.pi / 2 + progress * (0.6 if plan["camera"] == "slow_orbit" else 1.2)
            look_at(
                (
                    camera_distance * math.cos(angle),
                    camera_distance * math.sin(angle),
                    base_height + length * 0.8,
                ),
                (0, 0, base_height + length / 2),
            )
        else:
            # Replay the sampled solver trajectory; animation duration is presentation time.
            t = progress * trace[-1]["t_s"]
            right = next((i for i, p in enumerate(trace) if p["t_s"] >= t), len(trace) - 1)
            a, b = trace[max(0, right - 1)], trace[right]
            mix = (t - a["t_s"]) / max(1e-9, b["t_s"] - a["t_s"])
            position = [a[k] + (b[k] - a[k]) * mix for k in ("east_m", "north_m", "altitude_m")]
            root.location = position
            if photographic:
                # A ground-based camera pans/zooms; it does not fly alongside the rocket.
                horizontal = max(8, max(p["altitude_m"] for p in trace) * 1.25)
                camera.data.lens = max(
                    45,
                    min(
                        850,
                        45
                        * math.dist(
                            (horizontal, -horizontal, 0.8),
                            (position[0], position[1], position[2] + length / 2),
                        )
                        / camera_distance,
                    ),
                )
                look_at(
                    (horizontal, -horizontal, 0.8),
                    (position[0], position[1], position[2] + length / 2),
                )
                remaining = max(
                    0,
                    a["mass_kg"]
                    + (b["mass_kg"] - a["mass_kg"]) * mix
                    - job["design"]["dry_mass_kg"]
                    - job["design"]["payload_mass_kg"],
                )
                water_volume(remaining / 1000)
            else:
                look_at(
                    (
                        position[0] + camera_distance * 0.55,
                        position[1] - camera_distance * 0.85,
                        position[2] + length * 0.9,
                    ),
                    (position[0], position[1], position[2] + length / 2),
                )
            states.append(
                {
                    "frame": index,
                    "simulation_time_s": t,
                    "east_m": position[0],
                    "north_m": position[1],
                    "altitude_m": position[2],
                    "camera_altitude_m": camera.location.z,
                }
            )
        if photographic:
            camera.data.dof.focus_distance = (
                camera.location - root.location - Vector((0, 0, length / 2))
            ).length
        scene.render.filepath = str(frames / f"{index:04d}.png")
        bpy.ops.render.render(write_still=True)
    if mode == "design" and not preview:
        # Pack licensed textures so the saved scene has no absolute image paths.
        if photographic:
            bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(output / "assembly.blend"))
    if states:
        with (output / "rendered-trajectory.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(states[0]))
            writer.writeheader()
            writer.writerows(states)
(output / "scene-source.json").write_text(
    json.dumps(
        {
            "style": plan.get("style", "engineering"),
            "dimensions_sha256": geometry_source,
            "mesh_vertex_hashes": mesh_hashes,
            "source_id": job["source_id"],
            "bottle_detail": "unmeasured illustrative PET envelope",
            "physical_validation": "not_performed",
        },
        indent=2,
    ),
    encoding="utf-8",
)
