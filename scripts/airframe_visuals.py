"""Reusable fitted reference bottle meshes. These are visualization assets, never print parts."""

import json
import math
from pathlib import Path

import bmesh
import bpy

from rocketwright.agent.video_cache import MediaCache, digest, file_sha

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "rocketwright/catalog/airframes"


def legacy_profile(radius, height):
    profile = [(radius * 0.3, 0), (radius * 0.3, height * 0.1)]
    for i in range(1, 25):
        u = i / 24
        profile.append(
            (radius * (0.3 + 0.7 * (0.5 - 0.5 * math.cos(u * math.pi))), height * (0.1 + 0.25 * u))
        )
    for i in range(1, 65):
        u = i / 64
        profile.append((radius - 0.00015 * math.sin(u * 35) ** 8, height * (0.35 + 0.65 * u)))
    return profile + [(0, height)]


def lathe(profile):
    segments = 128
    vertices = [
        (r * math.cos(i * math.tau / segments), r * math.sin(i * math.tau / segments), z)
        for r, z in profile
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
    mesh = bpy.data.meshes.new("Reusable bottle")
    mesh.from_pydata(vertices, [], faces)
    return mesh


def body(job, radius, height, parent, material, cache_root):
    recipe = job.get("airframe")
    reference_height = job["dimensions_mm"].get("bottle_length", height * 1000) / 1000
    profile = legacy_profile(radius, height)
    wall = True
    if recipe and recipe["kind"] == "schlatter-profile":
        # Adapted from Adrian Schlatter's BSD-2-Clause bottle.scad (26.19 / 92 neck ratio).
        profile = [
            (0, 0),
            (radius * 26.19 / 92, 0),
            (radius * 26.19 / 92, height * 20 / 320),
            (radius, height * 90 / 320),
            (radius, height * 274 / 320),
        ]
        profile += [
            (
                radius * math.cos(i * math.pi / 64),
                height * (274 + 46 * math.sin(i * math.pi / 64)) / 320,
            )
            for i in range(1, 33)
        ]
    if recipe and recipe["kind"] == "reference-mesh":
        metadata = json.loads((REFERENCES / recipe["profile"]).read_text())
        mesh_path = REFERENCES / recipe["mesh"]
        if file_sha(mesh_path) != metadata["mesh_sha256"]:
            raise ValueError("Reference bottle mesh changed after conversion")
        original_profile = [
            (r * radius, z * reference_height)
            for r, z in metadata.get("liquid_profile", metadata["outer_profile"])
        ]
        profile = [point for point in original_profile if point[1] <= height]
        right = next(i for i, point in enumerate(original_profile) if point[1] >= height)
        ra, za = original_profile[max(0, right - 1)]
        rb, zb = original_profile[right]
        profile.append((ra + (rb - ra) * (height - za) / max(1e-12, zb - za), height))
        wall = metadata["add_illustrative_wall"]
    identity = digest(
        dict(
            radius=radius,
            height=height,
            reference_height=reference_height,
            recipe=recipe,
            code=file_sha(__file__),
            blender=bpy.app.version_string,
        )
    )
    cache = MediaCache(cache_root)
    directory = cache.directory("bodies", identity)
    library = directory / "body.blend"
    row = cache.manifest("bodies", identity).get("body.blend")
    reused = bool(row and library.is_file() and file_sha(library) == row["sha256"])
    if reused:
        with bpy.data.libraries.load(str(library)) as (_, target):
            target.meshes = ["Reusable bottle"]
        mesh = target.meshes[0]
    else:
        if recipe and recipe["kind"] == "reference-mesh":
            bpy.ops.wm.stl_import(filepath=str(mesh_path))
            imported = bpy.context.object
            mesh = imported.data
            bpy.data.objects.remove(imported, do_unlink=True)
            mesh.name = "Reusable bottle"
            for vertex in mesh.vertices:
                vertex.co.x *= radius
                vertex.co.y *= radius
                vertex.co.z *= reference_height
            # The reference bottle continues inside the opaque nose cover. Hide that
            # covered region at the shared mounting station; never change print CAD.
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.bisect_plane(
                bm,
                geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                plane_co=(0, 0, height),
                plane_no=(0, 0, 1),
                dist=1e-7,
                clear_outer=True,
            )
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(mesh)
            bm.free()
        else:
            mesh = lathe(profile)
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / "body-building.blend"
        bpy.data.libraries.write(str(temp), {mesh}, fake_user=True, compress=True)
        cache.store("bodies", identity, "body.blend", temp)
        temp.unlink()
    bottle = bpy.data.objects.new("Bottle", mesh)
    bpy.context.scene.collection.objects.link(bottle)
    bottle.parent = parent
    mesh.materials.clear()
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if wall:
        solidify = bottle.modifiers.new("Assumed PET thickness", "SOLIDIFY")
        solidify.thickness, solidify.offset = 0.00035, -1
    return profile, dict(
        identity=identity,
        reused=reused,
        template=recipe,
        wall_basis="illustrative 0.35 mm" if wall else "reference CAD wall; unmeasured",
    )
