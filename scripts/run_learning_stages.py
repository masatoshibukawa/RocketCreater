"""Run stage 5 redesign, stage 6 one complete CFD/FEM audit, then stage 7 scenarios."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rocketwright.agent.design_projects import DesignProjects, DesignSpec, write_json
from rocketwright.analysis import predictor
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.screening import violation
from rocketwright.analysis.service import Harness, code_hash
from scripts.report_design_search import verified_files
from scripts.report_stage6 import summary


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def execute(h, store, state, source, *, stop_at_confirmation=False):
    while state["adaptive"]["status"] == "running":
        if code_hash() != source:
            raise RuntimeError("Source changed during stage execution")
        state = h.step(state["id"], state["revision"])
        a = state["adaptive"]
        decision = a["decisions"][-1] if a["decisions"] else {}
        print(
            json.dumps(
                dict(
                    project=state["id"],
                    version=state["version"],
                    action=decision.get("action"),
                    planner=decision.get("planner"),
                    status=a["status"],
                    remaining_s=a["remaining_s"],
                )
            ),
            flush=True,
        )
        if (
            stop_at_confirmation
            and decision.get("action") == "confirm"
            and a["results"].get("confirm", {}).get("execution_status") == "completed"
        ):
            break
    write_json(
        store.base(state["id"]) / "verification-boundary.json",
        dict(
            stop_at_first_complete_confirmation=stop_at_confirmation,
            saved_status=state["adaptive"]["status"],
            source_hash=source,
        ),
    )
    return state


def run(template, training, root, runtime, planner, through):
    source = code_hash()
    if training["source_hash"] != source:
        raise ValueError("Training source differs; regenerate trials rather than relabel them")
    memory = training["training_rows"]
    if len(memory) < 4 or not all(predictor.sealed(r) for r in memory):
        raise ValueError("Four bound training observations required")
    if planner == "claude":
        from rocketwright.analysis.claude import ClaudeDirector

        ClaudeDirector()  # Credentials required before creating a partially run experiment.
    root.mkdir(parents=True, exist_ok=False)
    spec = template.model_copy(deep=True)
    spec.design = spec.design.model_copy(
        update=dict(nozzle_diameter_m=0.022, initial_gauge_pressure_pa=350000, water_fill_frac=0.30)
    )
    spec.assumptions.other_mass_station_fraction = 0.25
    store = DesignProjects(root / "stage5" / "projects")
    h = Harness(store, runtime=Runtime(), prior_experience=memory)
    state = store.create(spec)
    limits = SearchLimits(
        planner=planner,
        fallback="stop",
        max_versions=3,
        max_actions=60,
        budget_s=1800,
        memory_gib=24,
        reserve_confirmation_fraction=0.1,
    )
    precision = Precision(require_cfd=False, require_fem=False)
    state = h.start(state["id"], state["revision"], precision, limits)
    state = execute(h, store, state, source)
    a = state["adaptive"]
    fitted_offers = [
        dict(
            version=d["version"],
            action=key,
            selected=d["action"] == key,
            planner=d["planner"],
            model_hash=row["learned_prediction"]["model_hash"],
        )
        for d in a["decisions"]
        for key, row in d.get("selection_context", {}).get("choices", {}).items()
        if row.get("learned_prediction", {}).get("status") == "fitted"
    ]
    report = dict(
        source_hash=source,
        planner=planner,
        physical_qualification=False,
        stage5=dict(
            project_id=state["id"],
            status=a["status"],
            versions=state["version"],
            learned_offers=fitted_offers,
            revisions=a["revisions"],
            decisions=[
                {k: d.get(k) for k in ("action", "planner", "model", "api_requests")}
                for d in a["decisions"]
            ],
            observations=a["design_observations"],
            accepted_spec_hash=a["accepted_spec_hash"],
        ),
    )
    write_json(root / "report.json", report)
    if a["status"] == "planner_failed" or not fitted_offers or state["version"] < 2:
        raise RuntimeError("Stage 5 did not execute redesign with learned candidates")
    if through == 5:
        return report
    observations = a["design_observations"]
    selected = min(
        observations,
        key=lambda r: violation(
            r["metrics"], spec.requirement.target_altitude_m, precision.minimum_static_margin_cal
        ),
    )
    final_spec = DesignSpec.model_validate(selected["spec"])
    final_store = DesignProjects(root / "stage6" / "projects")
    h = Harness(final_store, runtime=runtime, prior_experience=memory)
    state = final_store.create(final_spec)
    state = h.start(
        state["id"],
        state["revision"],
        Precision(),
        SearchLimits(
            planner=planner,
            fallback="stop",
            max_versions=1,
            max_actions=40,
            budget_s=12000,
            memory_gib=24,
            exploratory_redesign=False,
        ),
    )
    state = execute(h, final_store, state, source, stop_at_confirmation=True)
    project = final_store.base(state["id"]).resolve()
    report["stage6_project"] = str(project)
    stage6, _ = summary(project, "source-hash:" + source)
    stage6["verification_scope"] = (
        "One complete audit at unchanged precision; no full refinement table rerun"
    )
    stage6["next_choices"] = h.options(state["id"])
    write_json(root / "stage6-summary.json", stage6)
    report["stage6"] = dict(
        status=state["adaptive"]["status"],
        checks=stage6["checks"],
        unmet=stage6["unmet"],
        source_hash=source,
        completed_one_confirmation=True,
    )
    report["evidence"] = verified_files(root)
    write_json(root / "report.json", report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", type=Path)
    p.add_argument("training", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("runtime", type=Path)
    p.add_argument("--planner", choices=("claude", "local_llm", "baseline"), default="claude")
    p.add_argument("--through", type=int, choices=(5, 6, 7), default=7)
    args = p.parse_args()
    report = run(
        DesignSpec.model_validate(read(args.spec)),
        read(args.training),
        args.output.resolve(),
        Runtime.model_validate(read(args.runtime)),
        args.planner,
        args.through,
    )
    if args.through == 7:
        subprocess.run(
            [
                sys.executable,
                "-u",
                "-m",
                "scripts.verify_adaptive_scenarios",
                report["stage6_project"],
                str((args.output / "stage7").resolve()),
                "--planner",
                args.planner,
                "--experience",
                str(args.training.resolve()),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
