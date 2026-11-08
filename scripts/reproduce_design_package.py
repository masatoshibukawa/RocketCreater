"""Rebuild a verified package in a new directory with the bundled trusted source.

Run --check first. This never contacts a printer, cloud model or local LLM.
Numerical agreement is compared separately from integrity and hardware evidence.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="partial check, never reported as a full reproduction",
    )
    args = parser.parse_args()
    package = args.package.resolve()
    source = package / "source"
    sys.path.insert(0, str(source))
    from scripts.verify_design_package import verify

    verify(package)
    from rocketwright.agent.design_projects import DesignProjects, DesignSpec, write_json
    from rocketwright.manufacturing import tools

    expected = json.loads((package / "reproduction/input.json").read_text(encoding="utf-8"))
    env = json.loads((package / "reproduction/environment.json").read_text(encoding="utf-8"))
    import importlib.metadata

    dependencies = {
        name: importlib.metadata.version(name) for name in env["packages"] if env["packages"][name]
    }
    mismatches = {
        name: dict(expected=env["packages"][name], actual=version)
        for name, version in dependencies.items()
        if version != env["packages"][name]
    }
    if mismatches:
        raise RuntimeError("Dependency versions differ: " + json.dumps(mismatches))
    required = ["blender"] + (["engine", "material"] if expected["print_required"] else [])
    availability = {name: tools()[name].is_file() for name in required}
    print(json.dumps(dict(dependencies=dependencies, tools=availability), ensure_ascii=False))
    if not all(availability.values()):
        raise RuntimeError("Configure missing Blender/Cura tools before reproduction")
    os.environ["ROCKETWRIGHT_MEDIA_ROOT"] = str(source / "AIvideo")
    if "photographic" in expected["video_styles"] or any(
        output["style"] == "photographic" for output in expected.get("video_outputs", [])
    ):
        from rocketwright.agent.video_appearance import asset_files

        asset_files()
    if args.check:
        return
    if args.output is None or args.output.resolve().exists():
        raise ValueError("Choose a new output directory; existing work is never overwritten")
    os.environ["ROCKETWRIGHT_ENABLE_CLOUD_DESIGN"] = "0"
    os.environ["ROCKETWRIGHT_MEDIA_ROOT"] = str(source / "AIvideo")
    store = DesignProjects(args.output.resolve() / "projects")
    state = store.create(DesignSpec.model_validate(expected["spec"]))
    if expected.get("airframe_template"):
        state["airframe_template"] = expected["airframe_template"]
        store._write(state)
    if expected["adaptive_required"]:
        from rocketwright.analysis.runtime import Runtime
        from rocketwright.analysis.schema import Precision, SearchLimits
        from rocketwright.analysis.service import Harness

        configuration = expected["adaptive_configuration"]
        installed = Runtime.installed().model_dump()
        installed.update(configuration["runtime"])
        runtime = Runtime.model_validate(installed)
        harness = Harness(store, runtime=runtime)
        limits = {**configuration["limits"], "planner": "baseline", "max_versions": 1}
        state = harness.start(
            state["id"],
            state["revision"],
            Precision.model_validate(configuration["precision"]),
            SearchLimits.model_validate(limits),
        )
        state = harness.run(state["id"], state["revision"])
        if state["adaptive"]["status"] != "model_criteria_met":
            raise RuntimeError(
                "Current design's adaptive criteria were not reproduced; no adoption bypass"
            )
    state = store.analyse(state["id"], state["revision"])
    if not state["analysis"]["result"]["success"]:
        raise RuntimeError("Reproduced nominal analysis does not pass")
    state = store.adopt(state["id"], state["revision"])
    state = store.manual(state["id"], state["revision"])
    if expected["print_required"]:
        state = store.print_package(state["id"], state["revision"])
    from rocketwright.agent.production import plan_video, render_video

    outputs = expected.get(
        "video_outputs", [dict(style=s, quality="final") for s in expected["video_styles"]]
    )
    for output in [] if args.skip_video else outputs:
        style = output["style"]
        key = "photographic_video_plan" if style == "photographic" else "video_plan"
        if not state.get(key):
            state = plan_video(store, state["id"], state["revision"], local=False, style=style)
        state = render_video(
            store, state["id"], state["revision"], style=style, quality=output["quality"]
        )
    state = store.archive(state["id"], state["revision"])
    geometry = json.loads(
        store.file(state["id"], "cad/geometry-check.json").read_text(encoding="utf-8")
    )
    comparisons = {}
    for part, row in expected["geometry"].items():
        actual = geometry[part]
        comparisons[part] = abs(actual["volume_mm3"] - row["volume_mm3"]) <= max(
            0.01, abs(row["volume_mm3"]) * 1e-6
        )
        comparisons[part] &= actual["non_manifold_edges"] == 0 and actual["boundary_edges"] == 0
    for key, value in expected["metrics"].items():
        observed = state["analysis"]["result"]["metrics"].get(key)
        comparisons[key] = observed is not None and abs(value - observed) <= max(
            1e-6, abs(value) * 1e-5
        )
    result = dict(
        passed=all(comparisons.values()),
        full_reproduction=not args.skip_video and bool(outputs) and expected["print_required"],
        comparisons=comparisons,
        project_id=state["id"],
        source_project_id=expected["source_project_id"],
        source_project_version=expected["source_version"],
        regenerated_archive=str(store.file(state["id"], "package/design-package.zip").resolve()),
        environment=dependencies,
        scope=("new environment/work directory on this host; another PC requires a separate run"),
        physical_qualification=False,
    )
    write_json(args.output.resolve() / "reproduction-check.json", result)
    if not result["passed"]:
        raise RuntimeError("Reproduction differs; inspect reproduction-check.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
