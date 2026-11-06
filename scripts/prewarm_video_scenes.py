"""Blender --background --python FILE -- JOB CACHE: prepare three packed stage libraries."""

import json
import sys
import time
from pathlib import Path

import bpy

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / "scripts"), str(root / "AIvideo/pet-rocket/realism")]
import appearance  # noqa: E402
from video_scene_templates import stage  # noqa: E402

from rocketwright.agent.video_cache import atomic_json, template_for  # noqa: E402

job_path, cache_root = map(Path, sys.argv[sys.argv.index("--") + 1 :])
job = json.loads(job_path.read_text(encoding="utf-8"))
job["asset_directory"] = str(job_path.resolve().parent / "appearance")
rows = []
for name in ("compact", "standard", "large"):
    started = time.perf_counter()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for world in list(bpy.data.worlds):
        bpy.data.worlds.remove(world)
    template = template_for(job["dimensions_mm"]) | {"id": name}
    _, report = stage(job, cache_root, appearance, template)
    rows.append(report | {"elapsed_s": time.perf_counter() - started})
atomic_json(cache_root / "prewarm.json", dict(templates=rows, physical_geometry_in_templates=False))
print(json.dumps(rows, indent=2))
