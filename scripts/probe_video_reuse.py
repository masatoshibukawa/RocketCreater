"""Measure caption/trajectory cache boundaries using isolated, non-adopted visual fixtures.

The trajectory perturbation is ONLY a software cache probe, not a new physical prediction.
Run after the registered preview has populated its cache. No project state is edited here.
"""

import argparse
import copy
import json
import os
import subprocess
import time
from pathlib import Path

from rocketwright.agent.production import Direction, bind_direction, media_settings
from rocketwright.agent.video_appearance import freeze_assets, recipe
from rocketwright.agent.video_cache import atomic_json, digest, file_sha

ROOT = Path(__file__).resolve().parents[1]


def run(job, directory, *, stills=False):
    directory.mkdir(parents=True, exist_ok=False)
    job = copy.deepcopy(job)
    job["appearance_sha256"] = digest(freeze_assets(directory))
    job.pop("cancel_file", None)
    job.pop("job_id", None)
    path = directory / "job.json"
    atomic_json(path, job)
    settings = media_settings()
    commands = [
        [
            str(settings["blender"]),
            "--background",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "scripts/render_workbench_scene.py"),
            "--",
            str(path),
        ]
    ]
    if stills:
        commands[0].append("--preview")
    else:
        commands.append(
            [
                str(settings["python"]),
                str(ROOT / "scripts/compose_workbench_video.py"),
                str(path),
                "--libs",
                str(settings["libs"]),
            ]
        )
    timings = []
    start = time.perf_counter()
    with (directory / "render.log").open("w", encoding="utf-8") as log:
        for command in commands:
            stamp = time.perf_counter()
            subprocess.run(
                command,
                cwd=ROOT,
                check=True,
                timeout=1200,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            timings.append(time.perf_counter() - stamp)
    output = directory / "preview" if stills else directory
    result = dict(
        total_s=time.perf_counter() - start,
        stages_s=timings,
        cache=json.loads((output / "render-cache.json").read_text()),
        scene=json.loads((output / "scene-source.json").read_text()),
        isolated_fixture=True,
    )
    if not stills:
        result["verification"] = json.loads((output / "verification.json").read_text())
        assert result["verification"]["passed"]
    atomic_json(directory / "measurement.json", result)
    print(directory.name, result["total_s"], result["cache"]["clips"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = json.loads(args.job.read_text(encoding="utf-8"))
    original = file_sha(args.job)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = dict(
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        source_job_sha256=original,
        paid_api_used=False,
        variants={},
    )
    variant = copy.deepcopy(source)
    variant["source_id"] = "isolated-cache-probe:caption"
    direction = Direction.model_validate({k: variant["plan"][k] for k in Direction.model_fields})
    direction.design_focus = (
        "assembly_dimensions"
        if direction.design_focus != "assembly_dimensions"
        else "payload_and_recovery"
    )
    variant["plan"].update(bind_direction(direction))
    report["variants"]["caption"] = run(variant, root / "caption")
    assert all(v["rendered"] == 0 for v in report["variants"]["caption"]["cache"]["clips"].values())
    assert report["variants"]["caption"]["cache"]["clips"]["launch"]["composition_reused"]
    assert not report["variants"]["caption"]["cache"]["clips"]["design"]["composition_reused"]
    variant = copy.deepcopy(source)
    variant["source_id"] = "isolated-cache-probe:synthetic-trajectory-not-a-design"
    for point in variant["trace"]:
        point["altitude_m"] *= 1.01
    report["variants"]["trajectory"] = run(variant, root / "trajectory")
    clips = report["variants"]["trajectory"]["cache"]["clips"]
    assert clips["design"]["rendered"] == 0 and clips["design"]["composition_reused"]
    assert clips["launch"]["rendered"] == source["plan"]["launch_frames"]
    variant = copy.deepcopy(source)
    variant["plan"].update(recipe("photographic"))
    variant["plan"]["quality"] = "final"
    report["variants"]["full_resolution_stills"] = run(
        variant, root / "full-resolution", stills=True
    )
    assert file_sha(args.job) == original
    report["passed"] = True
    atomic_json(root / "probe-report.json", report)


if __name__ == "__main__":
    main()
