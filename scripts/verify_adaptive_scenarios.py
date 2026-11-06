"""Stage 7: real solver/LLM scenarios and read-only checks of stage-6 evidence.

The small CPU scenarios isolate policy behavior; their precision profile is not
the production design's acceptance profile. No result certifies hardware.
"""

import argparse
import copy
import json
from pathlib import Path

import numpy as np

from rocketwright.adaptive import Campaign
from rocketwright.agent.design_projects import DesignProjects, DesignSpec, sha, write_json
from rocketwright.analysis import planner
from rocketwright.analysis.aero_accuracy import relative_change
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness
from rocketwright.analysis.worker import Worker, read, serial
from rocketwright.physics.stability_theorems import campaign as theorem_campaign
from scripts.report_stage6 import evidence


def isolated_spec(source, thickness):
    s = source.model_copy(deep=True)
    s.geometry = s.geometry.model_copy(update={"fin_thickness_mm": thickness})
    s.assumptions.other_mass_station_fraction = 0.30
    s.measured_printed_mass_g = None
    return s


def screening_profile():
    return Precision(require_cfd=False, require_fem=False, minimum_static_margin_cal=0.01)


def cpu_fixture(spec, folder):
    """Native CAD and actual thermal/propulsion/flight/beam calculations, without stubs."""
    artifacts, values = {}, {}
    for key in ("geometry", "thermal", "propulsion", "screen", "modes"):
        out = folder / key
        out.mkdir(parents=True)
        context = dict(
            spec=spec.model_dump(mode="json"),
            precision=screening_profile().model_dump(),
            artifacts=artifacts,
            runtime=Runtime().model_dump(),
            timeout_s=180,
        )
        write_json(out / "input.json", context)
        value = serial(Worker(context, out).run(key))
        write_json(out / "data.json", value)
        artifacts[key], values[key] = str((out / "data.json").resolve()), value
    return dict(
        dry_mass_g=values["geometry"]["record"]["assembly"]["dry_mass_g"],
        apogee_m=values["screen"]["apogee_m"],
        deflection_ratio=values["modes"]["metrics"]["fin_deflection_ratio"],
        fin_thickness_mm=spec.geometry.fin_thickness_mm,
        target_altitude_m=spec.requirement.target_altitude_m,
        evidence="native CAD, heat, discharge, analytic-aero 6DOF and warm beam",
    )


def run_design(spec, folder, *, mode, pressures, versions):
    store = DesignProjects(folder.resolve())
    h = Harness(store, runtime=Runtime())
    state = store.create(spec)
    limits = SearchLimits(
        planner=mode,
        fallback="stop",
        pressure_kpa=pressures,
        fills=(),
        nozzle_mm=(),
        max_versions=versions,
        max_actions=45,
        budget_s=1800,
    )
    state = h.start(state["id"], state["revision"], screening_profile(), limits)
    confirmations = []
    seen_confirmations = set()
    for _ in range(limits.max_actions + 1):
        state = h.step(state["id"], state["revision"])
        a = state["adaptive"]
        action = a["decisions"][-1].get("action") if a["decisions"] else None
        print(
            json.dumps(
                dict(case=folder.name, version=state["version"], action=action, status=a["status"])
            ),
            flush=True,
        )
        if (
            action == "confirm"
            and a["results"].get("confirm", {}).get("execution_status") == "completed"
        ):
            value = a["results"]["confirm"]["value"]
            if value["sha256"] not in seen_confirmations:
                result = read(value["artifact"])
                confirmations.append(
                    dict(
                        version=state["version"],
                        unmet=result["unmet"],
                        apogee_m=result["flight"]["apogee_m"],
                        sha256=value["sha256"],
                    )
                )
                seen_confirmations.add(value["sha256"])
        if a["status"] != "running":
            break
    _, _, _, manifests = evidence(store.base(state["id"]).resolve())
    return dict(
        project_id=state["id"],
        status=a["status"],
        revisions=a["revisions"],
        decisions=[
            {k: d.get(k) for k in ("action", "planner", "model", "reason", "errors")}
            for d in a["decisions"]
        ],
        executions=[{k: r.get(k) for k in ("action", "execution_status")} for r in a["history"]],
        confirmations=confirmations,
        manifests=manifests,
        physical_qualification=False,
    )


def stage6_checks(project):
    state, data, locations, manifests = evidence(project.resolve())
    a = state["adaptive"]
    final = data["confirm"]
    last = a["decisions"][-1]
    precision = dict(
        passed=bool(set(final["unmet"]) & {"aero_grid", "aero_averaging", "aero_lattice"})
        and last.get("action", "").startswith("refine/")
        and not any(k.startswith("redesign/") for k in last["offered"])
        and bool(a["quality_pending"])
        and a["accepted_spec_hash"] is None,
        unmet=final["unmet"],
        chosen=last["action"],
        offered=last["offered"],
        pending=a["quality_pending"],
        selected_full_table_runtime_executed=False,
        scope=(
            "Actual stage-6 precision rejection and refinement selection; "
            "action limit precedes recalculation"
        ),
    )
    # Restore the completed numerical settings only in a detached in-memory state.
    # No saved project input, result, precision or execution limit is changed.
    original = copy.deepcopy(state)
    original["adaptive"]["runtime"] = read(locations["confirm"] / "input.json")["runtime"]
    h = Harness(DesignProjects(project.parent.resolve()))
    before, _, _, _ = h._campaign(original)
    watched = ("geometry", "fem_fine", "modes", "stability", "confirm")
    valid_before = {k: before.current(k) for k in watched}
    changes = {}
    for kind in ("material", "mount"):
        changed = copy.deepcopy(original)
        if kind == "material":
            changed["spec"]["material"] = "Prusament PETG"
        else:
            changed["spec"]["assumptions"]["mount"] = "reinforced"
        after, _, _, _ = h._campaign(changed)
        changes[kind] = {k: after.current(k) for k in watched}
    invalidation = dict(
        passed=all(valid_before.values())
        and all(
            c["geometry"] and not any(c[k] for k in watched if k != "geometry")
            for c in changes.values()
        ),
        baseline_current=valid_before,
        current_after_changes=changes,
        scope="Detached states against hash-verified native results; original project is unchanged",
        manifests=manifests,
    )
    return precision, invalidation


def theorem_checks(folder, mode):
    problems = {
        "unforced_frozen": dict(
            kind="frozen_pitch", unforced=True, parameters=dict(inertia=1, stiffness=2, damping=3)
        ),
        "forced_frozen": dict(
            kind="frozen_pitch", unforced=False, parameters=dict(inertia=1, stiffness=2, damping=3)
        ),
        "scheduled": dict(
            kind="piecewise_affine_pitch",
            parameters=dict(times=[0, 0.5, 1], matrices=[(-np.eye(2)).tolist()] * 3),
        ),
    }
    rows = {}
    for name, problem in problems.items():
        template = theorem_campaign(folder / (name + "-baseline"), problem)
        c = Campaign(
            folder / name,
            inputs=template.inputs,
            runners=template.runners,
            pool=template.pool,
            budget_s=180,
        )
        decisions = []
        for _ in range(4):
            choices = c.options()
            if not choices["offered"]:
                break
            decision = planner.choose(
                choices,
                dict(problem=problem),
                SearchLimits(planner=mode),
                remaining_s=c.remaining_s,
            )
            decisions.append(decision)
            if decision["action"] is None:
                break
            c.step(decision["action"], decision["reason"])
        rows[name] = dict(decisions=decisions, results=c.results, next_choices=c.options())
    result_sets = {k: set(v["results"]) for k, v in rows.items()}
    passed = (
        "frozen-origin" in result_sets["unforced_frozen"]
        and "frozen-origin" not in result_sets["forced_frozen"]
        and "frozen-origin" not in result_sets["scheduled"]
        and "finite-error-bound" in result_sets["scheduled"]
        and all("asymptotic-prerequisites" not in v for v in result_sets.values())
        and all(
            r["execution_status"] == "completed"
            for v in rows.values()
            for r in v["results"].values()
        )
    )
    return dict(
        passed=passed,
        cases=rows,
        full_flight_stability_proved=False,
        scope=(
            "Exact frozen/piecewise-affine model tests; forcing and finite horizon "
            "cannot become an asymptotic flight proof"
        ),
    )


def campaign_ok(run):
    return run["status"] != "planner_failed" and all(
        x["execution_status"] == "completed" for x in run["executions"]
    )


def attach_refinement(report_path, project, case_folder):
    """Attach an actually executed selected-duration point, never a complete replacement table."""
    _, data, _, _ = evidence(project.resolve())
    state = read(project / "state.json")
    runtime = state["adaptive"]["runtime"]
    if state["adaptive"]["decisions"][-1]["action"] != "refine/averaging":
        raise ValueError("The recorded planner did not select averaging")
    reference = data["cfd_audit"]["cases"][str(runtime["cfd_cells_fine"])]
    current = read(case_folder / "case.json")
    fixed = (
        "geometry_sha256",
        "source_sha256",
        "grid",
        "shape",
        "wall_scheme",
        "fin_thickness_mm",
        "Re",
        "width_D",
        "upstream_D",
        "lattice_Ma",
        "speed_mps",
        "angle_deg",
        "cant_deg",
        "rotated_geometry",
        "paired_samples",
    )
    if any(current[k] != reference[k] for k in fixed):
        raise ValueError("Refinement changed something besides the selected duration")
    duration = current["averaging_tU_D"][-1]
    if abs(duration - runtime["cfd_times"]) > 0.1 or duration <= reference["averaging_tU_D"][-1]:
        raise ValueError("Refinement did not execute the selected longer duration")
    if current["surface_loads"]["integration_relative_residual"] > 2e-4:
        raise ValueError("Refined CFD load integration failed")
    names = ("Cx", "Cy", "Cm_z")
    difference = relative_change(
        [reference["mean"][k] for k in names], [current["mean"][k] for k in names]
    )
    report = read(report_path)
    report["cases"]["3_accuracy_before_design"]["point_recalculation"] = dict(
        completed=True,
        duration_before=reference["averaging_tU_D"][-1],
        duration_after=duration,
        speed_mps=current["speed_mps"],
        angle_deg=current["angle_deg"],
        cells=current["d"],
        relative_difference=difference,
        temporal_limit=state["adaptive"]["precision"]["temporal_relative_limit"],
        within_temporal_limit=(
            difference <= state["adaptive"]["precision"]["temporal_relative_limit"]
        ),
        reference_case=reference["mean"],
        refined_case=current["mean"],
        table_recalculated=False,
        entire_design_accepted=False,
        artifact_hashes={
            k: sha(case_folder / k)
            for k in (
                "case.json",
                "history.csv",
                "line-loads.json",
                "surface-loads.npz",
                "slice.npz",
            )
        },
        scope=(
            "Executed the selected averaging duration at one independent point; "
            "full-table precision remains unresolved"
        ),
    )
    write_json(report_path, report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage6_project", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--planner", choices=("local_llm", "baseline"), default="local_llm")
    p.add_argument(
        "--refinement-case",
        type=Path,
        help="Optional completed independent point using the selected averaging duration",
    )
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = DesignSpec.model_validate(read(args.stage6_project / "state.json")["spec"])
    baseline, thick = isolated_spec(source, 2.4), isolated_spec(source, 3.6)
    precision, invalidation = stage6_checks(args.stage6_project)
    report = dict(
        planner=args.planner,
        screening_precision=screening_profile().model_dump(),
        cases={"3_accuracy_before_design": precision, "4_invalidate_old_verdicts": invalidation},
        physical_qualification=False,
    )
    write_json(args.output / "report.json", report)
    thin_result = cpu_fixture(baseline, args.output / "thin-fixture")
    thick_result = cpu_fixture(thick, args.output / "thick-fixture")
    switching = run_design(
        baseline,
        args.output / "operating-to-shape",
        mode=args.planner,
        pressures=(300, 350),
        versions=3,
    )
    changes = [r["change"] for r in switching["revisions"]]
    report["cases"]["1_operating_then_shape"] = dict(
        passed=campaign_ok(switching)
        and len(changes) >= 2
        and changes[0]["section"] == "design"
        and changes[0]["field"] == "initial_gauge_pressure_pa"
        and any(r["section"] == "geometry" or r["field"] == "material" for r in changes[1:]),
        run=switching,
    )
    write_json(args.output / "report.json", report)
    return_to_design = run_design(
        thick, args.output / "thickness-tradeoff", mode=args.planner, pressures=(300,), versions=2
    )
    changes = [r["change"] for r in return_to_design["revisions"]]
    report["cases"]["2_thickness_mass_tradeoff"] = dict(
        passed=campaign_ok(return_to_design)
        and thick_result["dry_mass_g"] > thin_result["dry_mass_g"]
        and thick_result["deflection_ratio"] < thin_result["deflection_ratio"]
        and thick_result["apogee_m"]
        < thin_result["apogee_m"]
        < source.requirement.target_altitude_m
        and any(r["section"] == "geometry" or r["field"] == "material" for r in changes),
        thin=thin_result,
        thick=thick_result,
        run=return_to_design,
    )
    write_json(args.output / "report.json", report)
    report["cases"]["5_theorem_applicability"] = theorem_checks(
        args.output / "theorems", args.planner
    )
    report["passed"] = all(c["passed"] for c in report["cases"].values())
    report["scope"] = (
        "Five defined scenarios; live choices and modeled physics, "
        "not general LLM reliability or hardware safety"
    )
    write_json(args.output / "report.json", report)
    if args.refinement_case:
        attach_refinement(args.output / "report.json", args.stage6_project, args.refinement_case)
    print(json.dumps({k: v["passed"] for k, v in report["cases"].items()}), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
