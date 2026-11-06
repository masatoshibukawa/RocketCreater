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
from mathutils import Matrix, Vector
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
    opening = nose.get("tip_opening_diameter", 0) / 2
    if opening:
        cut_z = math.sqrt(inner_cap * inner_cap - opening * opening)
        outside_end = math.asin(cut_z / cap)
        inside_end = math.asin(cut_z / inner_cap)
    else:
        outside_end = inside_end = math.pi / 2
    outside = [(outer, 0), (outer, skirt)]
    inside = []
    for i in range(25):
        theta = angle + (outside_end - angle) * i / 24
        outside.append((max(0.0, cap * math.cos(theta)), center_z + cap * math.sin(theta)))
        inner_theta = angle + (inside_end - angle) * i / 24
        inside.append((max(0.0, inner_cap * math.cos(inner_theta)), center_z + inner_cap * math.sin(inner_theta)))
    knee_z = skirt + (nose["wall"] - normal_wall * factor) / slope
    chamfer = nose.get("entry_chamfer", 0)
    profile = outside + inside[::-1] + [(inner, knee_z), (inner, chamfer)]
    if chamfer:
        profile.append((inner + chamfer, 0))
    return profile, {"fit_inner_diameter_mm": 2 * inner, "outer_diameter_mm": 2 * outer,
                     "normal_cone_wall_mm": normal_wall, "tip_radius_mm": cap,
                     "height_mm": outside[-1][1], "cylindrical_fit_depth_mm": knee_z,
                     "entry_lip_wall_mm": nose["wall"] - chamfer,
                     "top_opening_diameter_mm": 2 * opening,
                     "soft_cap_required": nose.get("soft_cap_required", False)}


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
    r = f.get("root_web", f.get("root_fillet", 0))
    if r > 0:
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
        x0 = base + f.get("slot_root_offset", 1.8)
        x1 = x0 + f["slot_width"]
        z0, z1 = z - f["slot_height"] / 2, z + f["slot_height"] / 2
        outline = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        if f["slot_round"]:
            outline = rounded_polygon(outline, min(f["slot_width"] / 2, 1.6), 12)
        tool = extrude_xz("BandSlot", outline, 30)
        boolean(obj, tool, "DIFFERENCE")
    return obj


def validate_parameters(c):
    if c.get("units") != "mm":
        raise ValueError("Only explicit millimetre inputs are supported")
    for group, keys in {"bottle": ["body_diameter", "height"],
                        "nose": ["skirt_height", "wall", "slope", "tip_radius"],
                        "fin": ["root_chord", "span", "tip_chord", "thickness", "saddle_width", "saddle_wall", "slot_width", "slot_height"]}.items():
        for key in keys:
            if not math.isfinite(c[group][key]) or c[group][key] <= 0:
                raise ValueError(f"{group}.{key} must be finite and positive")
    f, n, b = c["fin"], c["nose"], c["bottle"]
    if n["wall_mode"] not in ("radial", "normal"):
        raise ValueError("Unknown wall mode")
    if not isinstance(f["count"], int) or not 3 <= f["count"] <= 6:
        raise ValueError("Fin count must be an integer from 3 to 6")
    if not isinstance(c["resolution"], int) or not 32 <= c["resolution"] <= 512:
        raise ValueError("Resolution must be an integer from 32 to 512")
    if f["saddle_width"] >= b["body_diameter"]:
        raise ValueError("Saddle arc exceeds the supported geometry")
    if not 0 <= f["tip_trailing_offset"] <= f["root_chord"] - f["tip_chord"]:
        raise ValueError("Fin tip must remain inside the axial chord")
    if any(not math.isfinite(z) or z - f["slot_height"] / 2 <= 3 or
           z + f["slot_height"] / 2 >= f["root_chord"] - 3 for z in f["slot_centers"]):
        raise ValueError("Slots must leave material at both axial ends")
    for z in f["slot_centers"]:
        radial_end = f.get("slot_root_offset", 1.8) + f["slot_width"]
        offset = f["tip_trailing_offset"]
        upper_run = f["root_chord"] - offset - f["tip_chord"]
        lower = (z - f["slot_height"] / 2) * f["span"] / offset if offset else math.inf
        upper = (f["root_chord"] - z - f["slot_height"] / 2) * f["span"] / upper_run if upper_run else math.inf
        if radial_end >= min(f["span"], lower, upper):
            raise ValueError("Slot would break out of the blade outline")
    normal = n["wall"] / math.sqrt(1 + n["slope"] ** 2) if n["wall_mode"] == "radial" else n["wall"]
    if n.get("tip_opening_diameter", 0) / 2 >= (n["tip_radius"] - normal) / math.sqrt(1 + n["slope"] ** 2):
        raise ValueError("Tip opening reaches below the spherical tangent")
    if n.get("entry_chamfer", 0) >= n["wall"]:
        raise ValueError("Entry chamfer removes the skirt lip")


def print_copy(obj, angle_deg=0):
    copy = bpy.data.objects.new(obj.name + "Print", obj.data.copy())
    bpy.context.collection.objects.link(copy)
    rotation = Matrix.Rotation(math.radians(angle_deg), 3, "Y")
    for vertex in copy.data.vertices:
        vertex.co = rotation @ vertex.co
    minimum = Vector([min(v.co[i] for v in copy.data.vertices) for i in range(3)])
    for vertex in copy.data.vertices:
        vertex.co -= minimum
    copy.data.update()
    return copy


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
    centroid_numerator = Vector((0, 0, 0))
    for face in bm.faces:
        a, b, c = (v.co for v in face.verts)
        tetra_volume = a.dot(b.cross(c)) / 6
        centroid_numerator += (a + b + c) * (tetra_volume / 4)
    result = {"vertices": len(bm.verts), "triangles": len(bm.faces),
              "connected_components": components, "non_manifold_edges": sum(not e.is_manifold for e in bm.edges),
              "boundary_edges": sum(e.is_boundary for e in bm.edges),
              "zero_area_triangles": sum(f.calc_area() < 1e-9 for f in bm.faces),
              "nonadjacent_intersection_pairs": len(intersections),
              "volume_mm3": volume, "solid_mass_g_at_assumed_density": volume / 1000 * density,
              "centroid_mm": list(centroid_numerator / volume),
              "bounds_mm": [[min(v[i] for v in coords) for i in range(3)],
                            [max(v[i] for v in coords) for i in range(3)]]}
    result["dimensions_mm"] = [result["bounds_mm"][1][i] - result["bounds_mm"][0][i] for i in range(3)]
    bm.free()
    return result


def require_valid_solid(result, name):
    failures = [key for key in ("non_manifold_edges", "boundary_edges", "zero_area_triangles", "nonadjacent_intersection_pairs") if result[key]]
    if failures or result["connected_components"] != 1 or result["volume_mm3"] <= 0:
        raise RuntimeError(f"Invalid solid {name}: {result}")


def clean_numeric_seams(obj):
    """Weld only sub-0.00001 mm Boolean roundoff, then keep strict output gates."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = bm.calc_volume(signed=True)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.00001)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    after = bm.calc_volume(signed=True)
    if abs(after - before) > max(0.001, abs(before) * 0.000001):
        raise RuntimeError("Numeric-seam cleanup changed a material amount of volume")
    bm.to_mesh(obj.data)
    bm.free()
    return after - before


def assembly_scene(nose, fin, config, out, render):
    bottle, f = config["bottle"], config["fin"]
    scene = bpy.data.scenes.new("Assembly_reference_unmeasured")
    def put(obj, name):
        result = obj.copy()
        result.data = obj.data.copy()
        result.name = name
        scene.collection.objects.link(result)
        return result
    base_z = bottle.get("cylinder_end_z", bottle["height"] - 35) - config["nose"].get("insertion_depth", config["nose"]["skirt_height"])
    hood = put(nose, "Nose_reference")
    hood.location = (0, 0, base_z)
    placements = []
    for i in range(f["count"]):
        part = put(fin, f"Fin_{i + 1}")
        angle = 2 * math.pi * i / f["count"]
        part.rotation_euler.z = angle
        part.location = (0, 0, f["mount_tail_z"])
        placements.append({"index": i + 1, "azimuth_deg": math.degrees(angle), "tail_z_mm": f["mount_tail_z"]})
    r = bottle["body_diameter"] / 2
    z0, z1 = bottle.get("cylinder_start_z", 100), bottle.get("cylinder_end_z", 280)
    neck_z, neck_r = bottle.get("neck_height", 35), bottle.get("neck_radius", 15)
    # Curves are only a dimensional envelope, not a copy of an actual bottle.
    radii = [(neck_r, 0), (neck_r, neck_z), (r, z0), (r, z1)]
    for i in range(1, 17):
        t = i / 16
        radii.append((r * math.sqrt(max(0, 1 - t * t)), z1 + (bottle["height"] - z1) * t))
    curve = bpy.data.curves.new("Assumed_bottle_envelope", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.24
    for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        spline = curve.splines.new("POLY")
        spline.points.add(len(radii) - 1)
        for p, (radius, z) in zip(spline.points, radii):
            p.co = (radius * math.cos(angle), radius * math.sin(angle), z, 1)
    for radius, z in radii[:-1]:
        spline = curve.splines.new("POLY")
        spline.points.add(95)
        for i, point in enumerate(spline.points):
            angle = 2 * math.pi * i / 96
            point.co = (radius * math.cos(angle), radius * math.sin(angle), z, 1)
        spline.use_cyclic_u = True
    guide = bpy.data.objects.new("Bottle_envelope_not_measured", curve)
    scene.collection.objects.link(guide)
    guide.data.materials.append(material("Reference", (0.36, 0.45, 0.52)))
    camera_data = bpy.data.cameras.new("AssemblyCamera")
    camera = bpy.data.objects.new("AssemblyCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (460, -800, 550)
    camera.rotation_euler = (Vector((0, 0, 200)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", 510
    camera_data.clip_end = 5000
    scene.camera = camera
    scene.world = bpy.data.worlds.new("AssemblyWorld")
    scene.world.color = (0.92, 0.95, 0.98)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.render.resolution_x, scene.render.resolution_y = 1000, 1400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//assembly.png"
    if render:
        scene.render.filepath = str(out / "assembly.png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        scene.render.filepath = "//assembly.png"
    (out / "assembly.json").write_text(json.dumps({"bottle_is_unmeasured_envelope": True, "axis": "nozzle at z=0, nose toward +z", "nose_base_z_mm": base_z, "fins": placements,
        "launcher_envelope_known": False, "retention_verified": False, "recovery_system_designed": False,
        "soft_cap_supplied": False, "flight_released": False}, indent=2), encoding="utf-8")


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
    fin.data.materials.clear()
    fin.data.materials.append(blue)
    for face in fin.data.polygons:
        face.material_index = 0
    ring.data.materials.append(green)
    cone.location = (-150, 0, 0)
    fin.location = (0, 0, 0)
    ring.location = (200, 0, 0)
    label("NOSE / " + config["revision"], (-150, -110, -15))
    label("FIN x" + str(config["fin"]["count"]) + (" / PRINT 45" if config["revision"] != "v1" else ""), (60, -110, -15))
    label("FIT GAUGE", (200, -110, -15))
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
    camera_data.clip_end = 5000
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
        scene.render.filepath = "//preview.png"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    config = json.loads(args.config.read_text(encoding="utf-8"))
    validate_parameters(config)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.file_preview_type = "NONE"
    bpy.context.preferences.filepaths.use_auto_save_temporary_files = False
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    profile, nose_info = nose_profile(config)
    nose = revolve("NoseCone", profile, config["resolution"])
    fin = make_fin(config)
    ring_inner = config["bottle"]["body_diameter"] / 2 + config["bottle"]["radial_clearance"]
    ring_outer = ring_inner + config["fit_ring"]["wall"]
    chamfer = config["fit_ring"].get("entry_chamfer", 0)
    ring_profile = [(ring_inner + chamfer, 0), (ring_outer, 0),
                    (ring_outer, config["fit_ring"]["height"]), (ring_inner, config["fit_ring"]["height"])]
    if chamfer:
        ring_profile.append((ring_inner, chamfer))
    ring = revolve("FitRing", ring_profile, config["resolution"])
    parts = {"nose_cone": nose, "fin": fin, "fit_ring": ring}
    report = {"revision": config["revision"], "units": "mm", "generator": "Blender " + bpy.app.version_string,
              "bottle_fit_measured": False, "physical_print_completed": False,
              "nose_analytic": nose_info, "parts": {}}
    for name, obj in parts.items():
        cleanup_delta = clean_numeric_seams(obj)
        obj.data.update()
        result = inspect_mesh(obj, config["mass_density_g_cm3"])
        result["numeric_seam_cleanup_volume_delta_mm3"] = cleanup_delta
        result["filename"] = "fin_assembly.stl" if name == "fin" and config["revision"] != "v1" else name + ".stl"
        result["coordinate_frame"] = "bottle_axis_local" if name == "fin" else "part_local_z_up"
        report["parts"][name] = result
        require_valid_solid(result, name)
        save_stl(obj, out / (name + ".stl"))
    display_fin = fin
    if config["revision"] != "v1":
        save_stl(fin, out / "fin_assembly.stl")
        printable = print_copy(fin, config["fin"].get("print_rotation_y_deg", 0))
        clean_numeric_seams(printable)
        fin_print_report = inspect_mesh(printable, config["mass_density_g_cm3"])
        fin_print_report["filename"] = "fin.stl"
        fin_print_report["coordinate_frame"] = f"print_pose_y{config['fin'].get('print_rotation_y_deg', 0):g}_min_xyz_zero"
        require_valid_solid(fin_print_report, "fin_print")
        save_stl(printable, out / "fin.stl")
        report["parts"]["fin_print"] = fin_print_report
        gauge = saddle(config)
        # Lay one radial end face on the bed; keep the 100 mm axis horizontal.
        # Convex-side-down would grow almost 2 mm per side between early layers.
        angle = math.asin(config["fin"]["saddle_width"] / (2 * ring_inner))
        cosine, sine = math.cos(angle), math.sin(angle)
        for vertex in gauge.data.vertices:
            x, y, z = vertex.co
            vertex.co = (z, cosine * x - sine * y, sine * x + cosine * y)
        minimum = Vector([min(v.co[i] for v in gauge.data.vertices) for i in range(3)])
        for vertex in gauge.data.vertices:
            vertex.co -= minimum
        clean_numeric_seams(gauge)
        gauge_report = inspect_mesh(gauge, config["mass_density_g_cm3"])
        gauge_report["filename"] = "mount_gauge.stl"
        gauge_report["coordinate_frame"] = "print_pose_radial_end_face_down_long_axis_horizontal"
        require_valid_solid(gauge_report, "mount_gauge")
        save_stl(gauge, out / "mount_gauge.stl")
        report["parts"]["mount_gauge"] = gauge_report
        gauge.hide_render = True
        printable.hide_render = True
        # Colour the source parts before copying them into the assembly scene.
        nose.data.materials.append(material("Assembly nose", (0.98, 0.30, 0.08)))
        fin.data.materials.clear()
        fin.data.materials.append(material("Assembly fin", (0.05, 0.40, 0.82)))
        for face in fin.data.polygons:
            face.material_index = 0
        assembly_scene(nose, fin, config, out, args.render)
        fin.hide_render = True
        fin.hide_set(True)
        printable.hide_render = False
        printable.hide_set(False)
        display_fin = printable
    (out / "geometry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    preview_scene((nose, display_fin, ring), config, out, args.render)
    print("BUILD_OK", config["revision"], json.dumps({k: round(v["solid_mass_g_at_assumed_density"], 2) for k, v in report["parts"].items()}))


if __name__ == "__main__":
    main()
