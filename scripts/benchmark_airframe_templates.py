"""Native multi-template CAD/cache/flight and reference-model drawing experiment; no printing."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from rocketwright.agent import production
from rocketwright.agent.airframe_parts import FILES, publish_parts
from rocketwright.agent.airframe_templates import (
    TemplateRequest,
    catalog,
    create,
    make_spec,
    visual_recipe,
)
from rocketwright.agent.design_projects import DesignProjects
from rocketwright.agent.video_appearance import freeze_assets, recipe
from rocketwright.agent.video_cache import atomic_json, digest, file_sha

ROOT = Path(__file__).resolve().parents[1]


def analyse(store, request):
    start = time.perf_counter()
    state = create(store, request)
    reused = bool(state.get("cad_reuse"))
    state = store.analyse(state["id"], state["revision"])
    elapsed = time.perf_counter() - start
    publish_parts(store, state)
    return state, dict(
        elapsed_s=elapsed,
        cad_reused=reused,
        project_id=state["id"],
        input=state["spec"],
        printed_mass_g=state["analysis"]["printed_mass_used_g"],
        apogee_m=state["analysis"]["result"]["metrics"]["apogee_m"],
        cad_sha256={
            name: sha for name, sha in state["analysis"]["cad_sha256"].items() if name in FILES
        },
    )


def draw(store, state, directory, *, legacy=False):
    directory.mkdir()
    base = store.directory(state["id"])
    report = json.loads((base / "production/report.json").read_text(encoding="utf-8"))
    assembly = json.loads((base / "production/assembly.json").read_text(encoding="utf-8"))
    direction = production.Direction(
        design_focus="assembly_dimensions",
        launch_focus="trajectory_replay",
        camera="slow_orbit",
        launch_motion="tracking_ascent",
        reason="共有CADと参照機体の構成を確認する",
    )
    job = dict(
        dimensions_mm=assembly["dimensions_mm"],
        plan=production.bind_direction(direction) | recipe("photographic"),
        design=report["design"],
        source_id=report["sim_source_id"],
        trace=json.loads((base / "production/trace.json").read_text(encoding="utf-8")),
        cad_files={
            "nose": str((base / "cad/nose-mm.stl").resolve()),
            "fin": str((base / "cad/fin-assembly-mm.stl").resolve()),
        },
        appearance_sha256=digest(freeze_assets(directory)),
        cache_directory=str((directory.parent / "render-cache").resolve()),
        airframe=None if legacy else visual_recipe(state),
    )
    path = directory / "job.json"
    atomic_json(path, job)
    start = time.perf_counter()
    with (directory / "render.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [
                str(production.media_settings()["blender"]),
                "--background",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "scripts/render_workbench_scene.py"),
                "--",
                str(path),
                "--preview",
            ],
            cwd=ROOT,
            check=True,
            timeout=600,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    result = dict(
        elapsed_s=time.perf_counter() - start,
        actual_stills=6,
        cache=json.loads((directory / "preview/render-cache.json").read_text()),
        scene=json.loads((directory / "preview/scene-source.json").read_text()),
    )
    atomic_json(directory / "measurement.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["ROCKETWRIGHT_AIRFRAME_CACHE"] = str(out / "part-cache")
    store = DesignProjects(out / "projects")
    report = dict(
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        paid_api_used=False,
        template_results=[],
        physical_validation="not_performed",
    )
    for item in catalog()["templates"]:
        request = TemplateRequest(template_id=item["id"])
        state, cold = analyse(store, request)
        warm_state, warm = analyse(store, request.model_copy(update={"payload_g": 80}))
        assert warm["cad_reused"] and cold["cad_sha256"] == warm["cad_sha256"]
        assert cold["apogee_m"] != warm["apogee_m"]
        state = store.adopt(state["id"], state["revision"])
        cold_draw = draw(store, state, out / (item["id"] + "-draw"))
        warm_draw = draw(store, state, out / (item["id"] + "-repeat"))
        assert warm_draw["cache"]["body"]["reused"]
        assert all(c["rendered"] == 0 for c in warm_draw["cache"]["clips"].values())
        for p in (out / (item["id"] + "-draw/preview")).glob("*-frames/*.png"):
            assert file_sha(p) == file_sha(
                out / (item["id"] + "-repeat/preview") / p.parent.name / p.name
            )
        row = dict(id=item["id"], cold=cold, payload_changed=warm, draw=cold_draw, repeat=warm_draw)
        if item["id"] == "pet-15l":
            geometry = make_spec(request).geometry.model_dump()
            geometry["fin_span_mm"] += 5
            _, row["geometry_changed"] = analyse(
                store, TemplateRequest(template_id=item["id"], geometry=geometry)
            )
            assert not row["geometry_changed"]["cad_reused"]
            row["legacy_draw"] = draw(store, state, out / "pet-15l-legacy", legacy=True)
        report["template_results"].append(row)
        atomic_json(out / "report.json", report)
        print(
            item["id"],
            "CAD",
            cold["elapsed_s"],
            warm["elapsed_s"],
            "six stills",
            cold_draw["elapsed_s"],
            warm_draw["elapsed_s"],
            flush=True,
        )
    report["passed"] = True
    atomic_json(out / "report.json", report)


if __name__ == "__main__":
    main()
