"""Build the editable RocketWright fairing scene and render selected frames."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
TAU = math.tau


def material(name, color, metal=0.0, roughness=0.4, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return mat


def apply(obj, name, mat):
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def box(name, location, scale, mat, bevel=0.03):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = apply(bpy.context.object, name, mat)
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Edge highlights", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def tube(name, a, b, radius, mat, vertices=16):
    delta = Vector(b) - Vector(a)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=delta.length, location=(Vector(a) + Vector(b)) / 2)
    obj = apply(bpy.context.object, name, mat)
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def ring(name, radius, z, thickness, mat, center=(0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=72, minor_segments=10, location=(*center, z), major_radius=radius, minor_radius=thickness)
    return apply(bpy.context.object, name, mat)


def lathe(name, profile, mat, center=(0, 0), segments=64):
    vertices = [(center[0] + r * math.cos(TAU * j / segments), center[1] + r * math.sin(TAU * j / segments), z) for r, z in profile for j in range(segments)]
    faces = []
    for i in range(len(profile) - 1):
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((i * segments + j, i * segments + k, (i + 1) * segments + k, (i + 1) * segments + j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def curve(name, points, radius, mat, parent=None):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, xyz in zip(spline.points, points):
        point.co = (*xyz, 1)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def carbon_material():
    mat = material("Carbon composite appearance", (0.018, 0.027, 0.036), 0.46, 0.29)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.pi / 4
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    waves = []
    for direction in ["X", "Y"]:
        wave = nodes.new("ShaderNodeTexWave")
        wave.bands_direction = direction
        wave.inputs["Scale"].default_value = 130
        wave.inputs["Distortion"].default_value = 0.4
        links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
        waves.append(wave)
    multiply = nodes.new("ShaderNodeMath")
    multiply.operation = "MULTIPLY"
    links.new(waves[0].outputs["Fac"], multiply.inputs[0])
    links.new(waves[1].outputs["Fac"], multiply.inputs[1])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.008, 0.012, 0.019, 1)
    ramp.color_ramp.elements[1].color = (0.035, 0.048, 0.063, 1)
    links.new(multiply.outputs[0], ramp.inputs[0])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.19
    bump.inputs["Distance"].default_value = 0.008
    links.new(multiply.outputs[0], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return mat


def fairing(side, carbon, white, silver, dark):
    parent = bpy.data.objects.new(f"Fairing {'right' if side > 0 else 'left'}", None)
    bpy.context.collection.objects.link(parent)
    parent.location = (side * 1.9, 0.3, 0.12)
    parent.rotation_euler[1] = -side * 0.10
    levels, arcs = 48, 56

    def radius(z):
        u = max(0, (z - 2.05) / 4.2)
        return max(0.014, 1.39 * (1 - u * u))

    for outer, mat in [(False, carbon), (True, white)]:
        vertices = []
        for i in range(levels + 1):
            z = 6.2 * i / levels
            r = radius(z) + (0.045 if outer else 0)
            for j in range(arcs + 1):
                theta = math.pi * j / arcs
                vertices.append((r * math.cos(theta), r * math.sin(theta), z))
        faces = []
        for i in range(levels):
            for j in range(arcs):
                a = i * (arcs + 1) + j
                face = (a, a + 1, a + arcs + 2, a + arcs + 1)
                faces.append(face if outer else tuple(reversed(face)))
        mesh = bpy.data.meshes.new("Fairing curved surface")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new("Fairing exterior" if outer else "Fairing interior", mesh)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(mat)
        obj.parent = parent
        for poly in obj.data.polygons:
            poly.use_smooth = True
    for edge in [-1, 1]:
        points = [(edge * radius(6.2 * i / 100), -0.018, 6.2 * i / 100) for i in range(101)]
        curve("Separation flange", points, 0.065, silver, parent)
        for i in range(1, 24):
            z = 6.1 * i / 24
            bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=0.022, location=(0, 0, 0))
            bolt = apply(bpy.context.object, "Flange fastener", dark)
            bolt.parent = parent
            bolt.location = (edge * radius(z), -0.073, z)
    for z in [0.2, 1.2, 2.3, 3.4, 4.5]:
        r = radius(z) - 0.025
        points = [(r * math.cos(math.pi * i / 45), r * math.sin(math.pi * i / 45), z) for i in range(46)]
        curve("Interior stiffener", points, 0.014, dark, parent)
    return parent


def add_light(name, location, target, power, color, size, size_y=None):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.color = power, color
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = size_y or size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def build(args):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    device_name = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
            if device.use:
                device_name = device.name
        if device_name != "CPU":
            scene.cycles.device = "GPU"
    except Exception as error:
        print("GPU selection:", error)
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 3
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 1, 310
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.26, 0.30, 0.36)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.37, 0.46, 0.56, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    white = material("Pearl outer composite", (0.61, 0.66, 0.68), 0.12, 0.37)
    silver = material("Brushed separation rim", (0.52, 0.59, 0.64), 0.65, 0.28)
    truss = material("Structural alloy", (0.30, 0.35, 0.39), 0.78, 0.31)
    dark = material("Graphite", (0.012, 0.018, 0.023), 0.35, 0.36)
    engine = material("Engine graphite alloy", (0.052, 0.061, 0.073), 0.72, 0.31)
    wall = material("Hangar panels", (0.37, 0.45, 0.50), 0.14, 0.6)
    beam = material("Blue steel", (0.065, 0.13, 0.18), 0.45, 0.35)
    floor = material("Concrete floor", (0.22, 0.28, 0.31), 0.14, 0.48)
    yellow = material("Gantry safety yellow", (0.73, 0.34, 0.035), 0.2, 0.36)
    lamp = material("Skylight diffusers", (0.76, 0.9, 1), 0, 0.3, 2.8)

    box("Factory floor", (0, 2, -0.11), (28, 42, 0.22), floor)
    box("Rear wall", (0, 15, 5), (28, 0.24, 10), wall)
    box("Ceiling", (0, 2, 10.1), (28, 35, 0.16), wall)
    for x in [-12, 12]:
        box("Side wall", (x, 2, 5), (0.18, 35, 10), wall)
        for y in range(-12, 16, 4):
            box("Column", (x * 0.98, y, 5), (0.3, 0.3, 10), beam)
            tube("Sidewall diagonal", (x * 0.975, y, 0.2), (x * 0.975, y + 4, 5), 0.055, beam)
    for y in range(-10, 17, 3):
        box("Roof lower chord", (0, y, 9.45), (24, 0.13, 0.16), beam)
        box("Roof upper chord", (0, y, 9.95), (24, 0.10, 0.12), beam)
        for x in range(-12, 12, 2):
            tube("Roof web", (x, y, 9.45), (x + 1, y, 9.95), 0.035, beam, 8)
            tube("Roof web", (x + 1, y, 9.95), (x + 2, y, 9.45), 0.035, beam, 8)
    for x in range(-10, 12, 2):
        box("Ceiling seam", (x, 2, 9.99), (0.04, 34, 0.04), silver, 0)
    for y in [-4, 3, 10]:
        box("Ceiling light strip", (0, y, 9.85), (18, 0.42, 0.05), lamp)
        add_light("Soft roof lighting", (0, y, 9.5), (0, 0, 0), 2300, (0.81, 0.9, 1), 10, 2)
    for x in [-8, -4, 0, 4, 8]:
        box("Rear panel seam", (x, 14.82, 5), (0.05, 0.05, 10), beam, 0)
    for z in [2.5, 5, 7.5]:
        box("Rear horizontal seam", (0, 14.82, z), (27, 0.05, 0.045), beam, 0)
    for x in [-7, 7]:
        box("Service platform", (x, 8, 1.3), (3, 2, 0.16), silver)
        for dx in [-1.3, 1.3]:
            box("Gantry leg", (x + dx, 8, 2.8), (0.18, 0.3, 5.6), yellow)
        box("Gantry crossbar", (x, 8, 5.6), (3.2, 0.45, 0.45), yellow)
        tube("Service hoist", (x, 8, 5.3), (x, 8, 3.3), 0.025, dark)
    for x in [-9.5, 9.5]:
        box("Floor walkway", (x, 0, 0.008), (0.07, 22, 0.012), yellow, 0)

    carbon = carbon_material()
    fairing(-1, carbon, white, silver, dark)
    fairing(1, carbon, white, silver, dark)
    for z, r in [(1.87, 1.13), (2.20, 1.10), (3.10, 0.95), (3.66, 0.67)]:
        ring("Assembly ring", r, z, 0.064, truss)
    for j in range(8):
        a = TAU * j / 8
        b = TAU * (j + 1) / 8
        tube("Main diagonal", (1.13 * math.cos(a), 1.13 * math.sin(a), 1.87), (0.67 * math.cos(b), 0.67 * math.sin(b), 3.66), 0.075, silver)
        tube("Cross brace", (1.10 * math.cos(a), 1.10 * math.sin(a), 2.20), (0.95 * math.cos(b), 0.95 * math.sin(b), 3.10), 0.056, truss)
    lathe("Upper stage body", [(0.65, 3.1), (0.68, 3.25), (0.68, 4.02), (0.76, 4.06), (0.76, 4.14), (0.64, 4.15)], engine)
    ring("Upper collar", 0.75, 4.15, 0.065, truss)
    lathe("Upper aperture", [(0.64, 4.15), (0.56, 4.13), (0.56, 3.91)], dark)
    for center in [(-0.66, -0.37), (0.66, -0.37), (0, 0.62)]:
        lathe("Nozzle exterior", [(0.46, 0.2), (0.46, 0.29), (0.41, 0.52), (0.32, 0.89), (0.19, 1.35), (0.15, 1.61), (0.19, 1.8)], engine, center)
        lathe("Nozzle interior", [(0.43, 0.20), (0.38, 0.52), (0.28, 0.91), (0.14, 1.36)], dark, center)
        ring("Nozzle lip", 0.454, 0.22, 0.028, truss, center)
        tube("Feed support", (*center, 1.7), (*center, 2.2), 0.09, truss)
    add_light("Front softbox", (-5, -7, 5.5), (0, 0, 2.8), 1800, (0.72, 0.84, 1), 6, 7)
    add_light("Right rim", (7, 3, 7), (0, 0, 3), 2500, (0.75, 0.88, 1), 5, 7)

    data = bpy.data.cameras.new("Inspection camera")
    camera = bpy.data.objects.new("Inspection camera", data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    data.lens = 31
    data.dof.use_dof = True
    data.dof.aperture_fstop = 5.6
    focus = bpy.data.objects.new("Assembly focus", None)
    bpy.context.collection.objects.link(focus)
    focus.location = (0, 0, 3)
    data.dof.focus_object = focus
    for frame in range(1, 311):
        t = (frame - 1) / 30
        p = max(0, min(1, (t - 3.8) / 1.4))
        p = p * p * (3 - 2 * p)
        camera.location = (0.10 + 0.11 * math.sin(t * 0.65), -9.7 - 0.8 * p, 0.70 + 1.15 * p)
        target = Vector((0, 0.2, 4.0 - 1.0 * p + 0.025 * math.sin(t * 1.2)))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.rotation_euler.rotate_axis("Z", math.radians(-1.4 + 0.6 * math.sin(t * 0.6)))
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    scene["Purpose"] = "RocketWright concept visualization; not a flight or structural result"
    scene.render.filepath = "//frames/"
    output = ROOT / "renders"
    output.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "rocketwright_fairing.blend"))
    (output / "render_settings.json").write_text(json.dumps({"blender": bpy.app.version_string, "engine": scene.render.engine, "device": device_name, "samples": args.samples, "width": args.width, "height": args.height, "fps": 30, "timeline_frames": 310, "scene_frames_before_black_tail": 263}, indent=2), encoding="utf-8")
    if args.still:
        scene.frame_set(args.still)
        scene.render.filepath = str(output / f"preview_{args.still:04d}.png")
        bpy.ops.render.render(write_still=True)
    elif args.animate:
        frames = output / "frames"
        frames.mkdir(exist_ok=True)
        scene.render.filepath = str(frames / "frame_")
        scene.frame_end = 263
        bpy.ops.render.render(animation=True)
    print("ROCKETWRIGHT_SCENE_COMPLETE", device_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--still", type=int)
    parser.add_argument("--animate", action="store_true")
    build(parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
