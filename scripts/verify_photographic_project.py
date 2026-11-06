"""Time the registered photographic production recipe on one adopted project.

Delegates to the existing local direction, resource lease, Blender and composition
calls. Saves a measurement report outside the registered video artifacts so visual
review can be recorded without changing their verified hashes.
"""

import argparse
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from rocketwright.agent import production
from rocketwright.agent.design_projects import DesignProjects, sha, write_json
from rocketwright.agent.video_appearance import asset_files
from rocketwright.manufacturing import fingerprint


def now():
    return datetime.now(UTC).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("project_id")
    parser.add_argument("report", type=Path, help="new JSON report file")
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("Choose a new measurement report; previous records are preserved")
    store = DesignProjects(args.root.resolve())
    state = store.get(args.project_id)
    store.require_adopted(state)
    if state["active"] or any(f["kind"] == "photographic_video" for f in state["files"]):
        raise ValueError("The project is busy or already has registered photographic outputs")
    asset_files()
    directory = store.directory(args.project_id) / "video-photographic"
    inputs = {
        f["key"]: f["sha256"] for f in state["files"] if f["kind"] in {"cad", "production"}
    }
    result = dict(
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        measurement_script_sha256=sha(Path(__file__)),
        project_id=state["id"],
        version=state["version"],
        input_sha256=fingerprint(state["spec"]),
        input_artifact_sha256=inputs,
        python=platform.python_version(),
        platform=platform.system(),
        gpu=subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            text=True,
        ).strip(),
        style="photographic",
        started_at_utc=now(),
        timing_scope="direction request through verified and registered videos",
        stages=[],
        cold_frames=not any(directory.glob("*-frames/*.png")),
        passed=False,
        visual_review="pending",
        paid_api_used=False,
    )
    original_run, original_resource = production.subprocess.run, production.resource

    def measured_run(command, **kwargs):
        name = "blender_render" if "--background" in command else "compose_and_verify"
        row = dict(name=name, started_at_utc=now(), completed=False)
        result["stages"].append(row)
        start = time.perf_counter()
        try:
            outcome = original_run(command, **kwargs)
            row.update(completed=True, returncode=outcome.returncode)
            return outcome
        finally:
            row.update(elapsed_s=time.perf_counter() - start, finished_at_utc=now())
            print(json.dumps(row, ensure_ascii=False), flush=True)

    def measured_resource(*positional):
        start = time.perf_counter()
        lease = original_resource(*positional)
        result["resource_wait_s"] = time.perf_counter() - start
        return lease

    started = time.perf_counter()
    try:
        planning = time.perf_counter()
        if not state.get("photographic_video_plan"):
            state = production.plan_video(
                store, state["id"], state["revision"], local=True, style="photographic"
            )
        result["direction_s"] = time.perf_counter() - planning
        result["direction_model"] = state["photographic_video_plan"]["model"]
        result["plan_reused"] = result["direction_s"] < 0.01
        print("DIRECTION", result["direction_s"], result["direction_model"], flush=True)
        with patch.object(production.subprocess, "run", measured_run), patch.object(
            production, "resource", measured_resource
        ):
            state = production.render_video(
                store, state["id"], state["revision"], style="photographic"
            )
        if state["version"] != result["version"] or fingerprint(state["spec"]) != result[
            "input_sha256"
        ]:
            raise ValueError("Design inputs changed during generation")
        for key, expected in inputs.items():
            if sha(store.file(state["id"], key)) != expected:
                raise ValueError("Source artifact changed during generation: " + key)
        result["verification"] = json.loads(
            (directory / "verification.json").read_text(encoding="utf-8")
        )
        checkpoint = json.loads((directory / "frame-checkpoint.json").read_text(encoding="utf-8"))
        result["frame_render_s_by_clip"] = {
            mode: sum(
                r["seconds"] for p, r in checkpoint["frames"].items() if p.startswith(mode)
            )
            for mode in ("design", "launch")
        }
        result["progress"] = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
        result["outputs"] = [
            dict(name=p.name, bytes=p.stat().st_size, sha256=sha(p))
            for p in directory.glob("*.mp4")
        ]
        result["passed"] = result["verification"]["passed"]
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        result.update(total_s=time.perf_counter() - started, finished_at_utc=now())
        write_json(args.report.resolve(), result)
        print("REPORT", args.report.resolve(), result["total_s"], flush=True)


if __name__ == "__main__":
    main()
