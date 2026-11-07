"""Verify every fixed-candidate artifact and export conditional numerical results."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read


def export(root, destination):
    report = read(root / "report.json")
    if not report["complete"] or not report["source_unchanged"]:
        raise ValueError("An unchanged, complete fixed-candidate run is required")
    files, cases = 0, 0
    folders = {}
    parent = report.get("resumed_from")
    if parent and sha(Path(parent["root"]) / "report.json") != parent["report_sha256"]:
        raise ValueError("Parent report changed")
    for row in report["results"]:
        base = Path(parent["root"]) if row.get("reused_from") and parent else root
        folder = (base / row["method"]).resolve()
        if not folder.is_relative_to(base.resolve()):
            raise ValueError("Method path escapes verification root")
        if row.get("reused_from") and folder != Path(row["reused_from"]):
            raise ValueError("Unexpected reused method path")
        folders[row["method"]] = folder
        manifest = folder / "manifest.json"
        if row["status"] != "completed" or sha(manifest) != row["manifest_sha256"]:
            raise ValueError("Unfinished or changed method")
        for name, expected in read(manifest).items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder) or sha(path) != expected:
                raise ValueError("Changed native artifact: " + name)
            files += 1
            cases += path.name == "case.json"
    data = {method: read(folder / "data.json") for method, folder in folders.items()}
    final = data["confirm"]
    if final != report["confirmation"]:
        raise ValueError("Confirmation report differs from its sealed worker result")
    record = data["geometry"]["record"]
    parent_elapsed = read(Path(parent["root"]) / "report.json")["elapsed_s"] if parent else 0
    solver = Path(report["runtime"]["calculix"])
    build = read(solver.parent / "build.json")
    if sha(solver) != build["adapter_sha256"] or any(
        c["solver_sha256"] != build["adapter_sha256"] for c in data["fem_fine"]["cases"]
    ):
        raise ValueError("Solver transport differs from executed artifact")
    result = dict(
        source_hash=report["source_hash"],
        report_sha256=sha(root / "report.json"),
        spec=report["spec"],
        runtime={k: v for k, v in report["runtime"].items() if k != "calculix"},
        reused_methods=[r["method"] for r in report["results"] if r.get("reused_from")],
        parent_report_sha256=parent["report_sha256"] if parent else None,
        precision=report["precision"],
        elapsed_s=report["elapsed_s"] + parent_elapsed,
        resume_elapsed_s=report["elapsed_s"] if parent else None,
        parent_elapsed_s=parent_elapsed,
        solver_build=build,
        verified_files=files,
        gpu_cases=cases,
        assembly=record["assembly"],
        checks=final["checks"],
        unmet=final["unmet"],
        criteria_met=final["metrics"]["criteria_met"],
        physical_qualification=False,
        model_validation_complete=False,
        heights_m=dict(
            screen=data["screen"]["apogee_m"],
            cfd=data["flight"]["apogee_m"],
            finer_time=data["refine"]["fine"]["apogee_m"],
            confirm=final["flight"]["apogee_m"],
            coefficient_plus_10pct=data["refine"]["sensitivity_flight"]["apogee_m"],
        ),
        incidence_deg=dict(
            base=data["flight"]["ascent_incidence_deg"],
            confirm=final["flight"]["ascent_incidence_deg"],
            perturbation=data["stability"]["metrics"]["perturbation_incidence_deg"],
        ),
        phase_diagnostics=data["stability"]["phase_diagnostics"],
        aero=dict(
            grid_relative_change=data["cfd_fine"]["grid_relative_change"],
            averaging_relative_change=data["cfd_fine"]["averaging_relative_change"],
            allowed_relative_change=data["refine"]["allowed_aero_relative_change"],
            grid_altitude_difference_m=data["refine"]["grid_propagation"]["altitude_difference_m"],
            grid_attitude_difference_deg=data["refine"]["grid_propagation"][
                "incidence_difference_deg"
            ],
            audit_condition=data["cfd_audit"]["condition"],
            audit_differences=data["cfd_audit"]["differences"],
            observed_orders=data["cfd_audit"]["observed_orders"],
        ),
        beam={
            k: v
            for k, v in data["modes"].items()
            if k in ("first_modes_hz", "max_deflection_m", "metrics", "temperature_c", "load_scope")
        },
        structure={k: v for k, v in data["fem_fine"].items() if k != "cases"},
        stability={
            k: v
            for k, v in data["stability"].items()
            if k
            in (
                "completed",
                "frozen_asymptotic_count",
                "analyzed_points",
                "metrics",
                "barbalat",
                "full_flight_stability_proved",
                "omitted",
            )
        },
        thermal=dict(final_c=data["thermal"]["final_c"], metrics=data["thermal"]["metrics"]),
        limitations=record["limitations"],
    )
    write_json(destination, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    print(export(a.root, a.destination)["unmet"])
