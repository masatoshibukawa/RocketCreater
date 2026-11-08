"""Read-only adopted-CAD audit: Blender --background --python FILE -- V4 REPORT [VIDEO_DIR]."""

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def mesh_signature(obj):
    content = {
        "vertices": [tuple(v.co) for v in obj.data.vertices],
        "faces": [tuple(p.vertices) for p in obj.data.polygons],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


base = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
report = Path(sys.argv[sys.argv.index("--") + 2]).resolve()
arguments = sys.argv[sys.argv.index("--") + 1 :]
directory = base / (arguments[2] if len(arguments) > 2 else "video-photographic")
job = json.loads((directory / "job.json").read_text(encoding="utf-8"))
geometry = json.loads((base / "cad/geometry-check.json").read_text(encoding="utf-8"))
parameters = json.loads((base / "cad/parameters.json").read_text(encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=str(directory / "assembly.blend"))
rows = []
dimensions = job["dimensions_mm"]
for part, count in (("fin", dimensions["fin_count"]), ("nose", 1)):
    source = base / "cad" / ("fin-assembly-mm.stl" if part == "fin" else "nose-mm.stl")
    bpy.ops.wm.stl_import(filepath=str(source))
    reference = bpy.context.object
    expected_signature = mesh_signature(reference)
    for i in range(count):
        obj = bpy.data.objects["Adopted CAD " + part + str(i)]
        # The checked fin STL has a rotated, bed-normalized print pose. The movie
        # uses the corresponding assembly STL; compare bounds in the print pose.
        points = [v.co.copy() for v in obj.data.vertices]
        if part == "fin":
            rotation = Matrix.Rotation(
                math.radians(parameters["fin"]["print_rotation_y_deg"]), 3, "Y"
            )
            points = [rotation @ point for point in points]
            minimum = Vector([min(point[j] for point in points) for j in range(3)])
            points = [point - minimum for point in points]
        actual = [
            [min(point[j] for point in points) for j in range(3)],
            [max(point[j] for point in points) for j in range(3)],
        ]
        expected = geometry[part]["bounds_mm"]
        error = max(abs(actual[k][j] - expected[k][j]) for k in range(2) for j in range(3))
        position = (
            dimensions["fin_tail_inset"]
            if part == "fin"
            else dimensions["overall"] - dimensions["nose_length"]
        ) / 1000
        angle = i * 2 * math.pi / count
        assert mesh_signature(obj) == expected_signature, obj.name + ": CAD mesh changed"
        assert error < 0.001, (obj.name, error)
        assert not obj.modifiers, obj.name + ": unexpected modifiers"
        assert all(abs(s - 0.001) < 1e-8 for s in obj.scale)
        assert max(abs(obj.location[j] - (position if j == 2 else 0)) for j in range(3)) < 1e-7
        assert max(abs(obj.rotation_euler[j] - (angle if j == 2 else 0)) for j in range(3)) < 1e-6
        rows.append(
            dict(
                object=obj.name,
                mesh_sha256=expected_signature,
                source_stl_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                maximum_print_pose_bounds_error_mm=error,
                scale=list(obj.scale),
                local_position_m=list(obj.location),
                local_rotation_rad=list(obj.rotation_euler),
            )
        )
    bpy.data.objects.remove(reference, do_unlink=True)
report.write_text(
    json.dumps(
        dict(
            passed=True,
            source_id=job["source_id"],
            video_directory=directory.name,
            scope="saved design scene; exact CAD vertices/faces, bounds, scale and placement",
            blender_version=bpy.app.version_string,
            render_engine=bpy.context.scene.render.engine,
            cycles_device=bpy.context.scene.cycles.device,
            samples=bpy.context.scene.cycles.samples,
            objects=rows,
        ),
        indent=2,
    ),
    encoding="utf-8",
)
print("MESH_VERIFIED", len(rows))
