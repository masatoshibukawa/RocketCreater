"""Original parametric, non-pressure fairing and fin prototype. Run with Blender Python.

blender --background --factory-startup --python build.py -- --config parameters_v1.json --out baseline
All coordinates and STL numbers are millimetres. No pressure-vessel geometry is modified.
"""

import argparse
import json
import math
from pathlib import Path
import struct
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def mesh_object(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    return obj


def revolve(name, profile, segments):
    vertices, rings, faces = [], [], []
    for radius, z in profile:
        if radius < 1e-8:
            rings.append([len(vertices)])
            vertices.append((0.0, 0.0, z))
        else:
            ring = []
            for i in range(segments):
                angle = 2 * math.pi * i / segments
                ring.append(len(vertices))
                vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
            rings.append(ring)
    for a, b in zip(rings, rings[1:] + rings[:1]):
        if len(a) == len(b) == 1:
            continue
        for i in range(segments):
            j = (i + 1) % segments
            if len(a) == 1:
                faces.append((a[0], b[i], b[j]))
            elif len(b) == 1:
                faces.append((a[i], b[0], a[j]))
            else:
                faces.append((a[i], b[i], b[j], a[j]))
    return mesh_object(name, vertices, faces)


def extrude_xz(name, points, thickness):
    n = len(points)
    vertices = [(x, y, z) for y in (-thickness / 2, thickness / 2) for x, z in points]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return mesh_object(name, vertices, faces)


def boolean(target, tool, operation):
    bpy.context.view_layer.objects.active = target
    modifier = target.modifiers.new(operation, "BOOLEAN")
    modifier.operation = operation
    modifier.solver = "EXACT"
    modifier.object = tool
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(tool, do_unlink=True)


def rounded_polygon(points, radius, steps=8):
    if radius <= 0:
        return points
    result = []
    for i, point in enumerate(points):
        p = Vector(point)
        a = Vector(points[i - 1]) - p
        b = Vector(points[(i + 1) % len(points)]) - p
        la, lb = a.length, b.length
        a.normalize()
        b.normalize()
        angle = math.acos(max(-1.0, min(1.0, a.dot(b))))
        distance = min(radius / math.tan(angle / 2), la * 0.35, lb * 0.35)
        effective = distance * math.tan(angle / 2)
        center = p + (a + b).normalized() * effective / math.sin(angle / 2)
        start, end = p + a * distance, p + b * distance
        theta0 = math.atan2(start.y - center.y, start.x - center.x)
        theta1 = math.atan2(end.y - center.y, end.x - center.x)
        delta = (theta1 - theta0 + math.pi) % (2 * math.pi) - math.pi
        for step in range(steps + 1):
            theta = theta0 + delta * step / steps
            result.append((center.x + effective * math.cos(theta), center.y + effective * math.sin(theta)))
    return result


def nose_profile(config):
    bottle, nose = config["bottle"], config["nose"]
    inner = bottle["body_diameter"] / 2 + bottle["radial_clearance"]
    outer = inner + nose["wall"]
    slope, skirt, cap = nose["slope"], nose["skirt_height"], nose["tip_radius"]
    factor = math.sqrt(1 + slope * slope)
    normal_wall = nose["wall"] / factor if nose["wall_mode"] == "radial" else nose["wall"]
    inner_cap = cap - normal_wall
    if inner_cap <= 0 or nose["wall"] <= 0:
        raise ValueError("Tip radius must exceed the shell's normal thickness")
    apex = skirt + outer / slope
    center_z = apex - cap * factor / slope
    angle = math.atan(slope)
    outside = [(outer, 0), (outer, skirt)]
    inside = []
    for i in range(25):
        theta = angle + (math.pi / 2 - angle) * i / 24
        outside.append((max(0.0, cap * math.cos(theta)), center_z + cap * math.sin(theta)))
        inside.append((max(0.0, inner_cap * math.cos(theta)), center_z + inner_cap * math.sin(theta)))
    knee_z = skirt + (nose["wall"] - normal_wall * factor) / slope
    profile = outside + inside[::-1] + [(inner, knee_z), (inner, 0)]
    return profile, {"fit_inner_diameter_mm": 2 * inner, "outer_diameter_mm": 2 * outer,
                     "normal_cone_wall_mm": normal_wall, "tip_radius_mm": cap,
                     "height_mm": center_z + cap, "cylindrical_fit_depth_mm": knee_z}


def saddle(config):
    bottle, fin = config["bottle"], config["fin"]
    radius = bottle["body_diameter"] / 2 + bottle["radial_clearance"]
    angle = math.asin(fin["saddle_width"] / (2 * radius))
    profile = []
    for i in range(33):
        theta = -angle + 2 * angle * i / 32
        profile.append(((radius + fin["saddle_wall"]) * math.cos(theta),
                        (radius + fin["saddle_wall"]) * math.sin(theta)))
    for i in range(33):
        theta = angle - 2 * angle * i / 32
        profile.append((radius * math.cos(theta), radius * math.sin(theta)))
    # Reuse the polygon extrusion along local Y, then map its axes to X/Y/Z.
    obj = extrude_xz("Fin", profile, fin["root_chord"])
    for vertex in obj.data.vertices:
        x, y, z = vertex.co
        vertex.co = (x, -z, y + fin["root_chord"] / 2)
    return obj


def make_fin(config):
    f, b = config["fin"], config["bottle"]
    base = b["body_diameter"] / 2 + b["radial_clearance"] + f["saddle_wall"]
    points = [(base - 0.65, 0), (base, 0),
              (base + f["span"], f["tip_trailing_offset"]),
              (base + f["span"], f["tip_trailing_offset"] + f["tip_chord"]),
              (base, f["root_chord"]), (base - 0.65, f["root_chord"])]
    obj = saddle(config)
    blade = extrude_xz("Blade", rounded_polygon(points, f["corner_radius"]), f["thickness"])
    boolean(obj, blade, "UNION")
    if f["root_fillet"] > 0:
        r = f["root_fillet"]
        # Symmetric triangular root webs join the blade face to the saddle.
        for sign in (-1, 1):
            vertices = []
            cross = [(base - 0.3, sign * f["thickness"] / 2),
                     (base - 0.3, sign * (f["thickness"] / 2 + r)),
                     (base + r, sign * f["thickness"] / 2)]
            for z in (3.0, f["root_chord"] - 3.0):
                vertices += [(x, y, z) for x, y in cross]
            web = mesh_object("RootWeb", vertices, [(0, 2, 1), (3, 4, 5),
                              (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)])
            boolean(obj, web, "UNION")
    for z in f["slot_centers"]:
        x0, x1 = base + 1.8, base + 1.8 + f["slot_width"]
        z0, z1 = z - f["slot_height"] / 2, z + f["slot_height"] / 2
        outline = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        if f["slot_round"]:
            outline = rounded_polygon(outline, min(f["slot_width"] / 2, 1.6), 12)
        tool = extrude_xz("BandSlot", outline, 30)
        boolean(obj, tool, "DIFFERENCE")
    return obj


def triangles(obj):
    obj.data.calc_loop_triangles()
    return [[obj.matrix_world @ obj.data.vertices[i].co for i in face.vertices]
            for face in obj.data.loop_triangles]


def save_stl(obj, path):
    faces = triangles(obj)
    with path.open("wb") as stream:
        stream.write(b"PET rocket prototype - millimetres - non-pressure part".ljust(80, b"\0"))
        stream.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            normal = (b - a).cross(c - a).normalized()
            stream.write(struct.pack("<12fH", *normal, *a, *b, *c, 0))


def inspect_mesh(obj, density):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    components, unseen = 0, set(bm.verts)
    while unseen:
        components += 1
        todo = [unseen.pop()]
        while todo:
            for edge in todo.pop().link_edges:
                for vertex in edge.verts:
                    if vertex in unseen:
                        unseen.remove(vertex)
                        todo.append(vertex)
    overlaps = BVHTree.FromBMesh(bm, epsilon=0.000001).overlap(BVHTree.FromBMesh(bm, epsilon=0.000001))
    face_verts = [set(v.index for v in f.verts) for f in bm.faces]
    intersections = sorted({tuple(sorted((a, b))) for a, b in overlaps if a != b and not face_verts[a] & face_verts[b]})
    coords = [v.co for v in bm.verts]
    volume = bm.calc_volume(signed=True)
    result = {"vertices": len(bm.verts), "triangles": len(bm.faces),
              "connected_components": components, "non_manifold_edges": sum(not e.is_manifold for e in bm.edges),
              "boundary_edges": sum(e.is_boundary for e in bm.edges),
              "zero_area_triangles": sum(f.calc_area() < 1e-9 for f in bm.faces),
              "nonadjacent_intersection_pairs": len(intersections),
              "volume_mm3": volume, "solid_mass_g_at_assumed_density": volume / 1000 * density,
              "bounds_mm": [[min(v[i] for v in coords) for i in range(3)],
                            [max(v[i] for v in coords) for i in range(3)]]}
    result["dimensions_mm"] = [result["bounds_mm"][1][i] - result["bounds_mm"][0][i] for i in range(3)]
    bm.free()
    return result


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    return mat


def label(text, location, size=9):
    data = bpy.data.curves.new(text, "FONT")
    data.body, data.size = text, size
    data.align_x = "CENTER"
    obj = bpy.data.objects.new(text, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(material("Ink", (0.07, 0.10, 0.17)))


def preview_scene(parts, config, out, render):
    orange = material("Nose", (0.98, 0.30, 0.08))
    blue = material("Fin", (0.05, 0.40, 0.82))
    green = material("Fit gauge", (0.08, 0.65, 0.40))
    cone, fin, ring = parts
    cone.data.materials.append(orange)
    fin.data.materials.append(blue)
    ring.data.materials.append(green)
    cone.location = (-150, 0, 0)
    fin.location = (0, 0, 0)
    ring.location = (200, 0, 0)
    label("NOSE / " + config["revision"], (-150, -60, -20))
    label("FIN x3", (80, -60, -20))
    label("FIT GAUGE", (200, -60, -20))
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (390, -750, 510)
    direction = Vector((10, 0, 55)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", 560
    scene.camera = camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.91, 0.94, 0.98)
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//preview.png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "parts.blend"))
    if render:
        scene.render.filepath = str(out / "preview.png")
        bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    config = json.loads(args.config.read_text(encoding="utf-8"))
    bpy.context.preferences.filepaths.save_version = 0
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    profile, nose_info = nose_profile(config)
    nose = revolve("NoseCone", profile, config["resolution"])
    fin = make_fin(config)
    ring_inner = config["bottle"]["body_diameter"] / 2 + config["bottle"]["radial_clearance"]
    ring_outer = ring_inner + config["fit_ring"]["wall"]
    ring = revolve("FitRing", [(ring_inner, 0), (ring_outer, 0),
                   (ring_outer, config["fit_ring"]["height"]), (ring_inner, config["fit_ring"]["height"])], config["resolution"])
    parts = {"nose_cone": nose, "fin": fin, "fit_ring": ring}
    report = {"revision": config["revision"], "units": "mm", "generator": "Blender " + bpy.app.version_string,
              "bottle_fit_measured": False, "physical_print_completed": False,
              "nose_analytic": nose_info, "parts": {}}
    for name, obj in parts.items():
        obj.data.update()
        result = inspect_mesh(obj, config["mass_density_g_cm3"])
        report["parts"][name] = result
        if result["non_manifold_edges"] or result["connected_components"] != 1 or result["volume_mm3"] <= 0:
            raise RuntimeError(f"Invalid solid {name}: {result}")
        save_stl(obj, out / (name + ".stl"))
    (out / "geometry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    preview_scene((nose, fin, ring), config, out, args.render)
    print("BUILD_OK", config["revision"], json.dumps({k: round(v["solid_mass_g_at_assumed_density"], 2) for k, v in report["parts"].items()}))


if __name__ == "__main__":
    main()
