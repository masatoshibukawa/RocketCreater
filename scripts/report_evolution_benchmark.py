"""Verify recorded simulations and publish a compact, paired evolutionary comparison."""

import argparse
import json
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.worker import read
from scripts.report_initial_models import verified


def export(training, benchmark, destination):
    report, files = verified(benchmark)
    training_report = read(training / "report.json")
    if sha(training / "report.json") != report["training_report_sha256"]:
        raise ValueError("Training report changed")
    for entry in training_report["anchors"]:
        i = entry["anchor"]
        for stem, suffix in (("model", "json"), ("examples", "jsonl")):
            if sha(training / f"{stem}-{i}.{suffix}") != entry[f"{stem}_sha256"]:
                raise ValueError("Training evidence changed")
    measured, failures = 0, 0
    for run in report["runs"]:
        path = benchmark / run["data_file"]
        if path.parent.resolve() != benchmark.resolve() or sha(path) != run["data_sha256"]:
            raise ValueError("Candidate evidence changed")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != run["evaluations"] or len(rows) != run["expected_evaluations"]:
            raise ValueError("Measured counts differ")
        best = min(rows, key=lambda r: r["loss"])
        if best["loss"] != run["best_loss"] or best != run["best"]:
            raise ValueError("Incumbent does not match recorded evaluations")
        measured += len(rows)
        failures += sum(r["status"] != "completed" for r in rows)
    summaries = []
    for method in report["methods"]:
        group = [r for r in report["runs"] if r["method"] == method]
        native = [r for r in report["results"] if r["label"].rsplit("-", 1)[0] == method]
        passed = [
            r
            for r in native
            if r["status"] == "completed"
            and r["temporal_pass"]
            and r["aero_domain_pass"]
            and r["metrics"]["static_margin_cal"] >= 1
            and r["metrics"]["incidence_deg"] <= Precision().maximum_incidence_deg
        ]
        by_seed = []
        for seed in report["seeds"]:
            selected = [r for r in group if r["seed"] == seed]
            stable = [
                r["best_stable_screen_height_m"]
                for r in selected
                if r["best_stable_screen_height_m"] is not None
            ]
            by_seed.append(
                dict(
                    seed=seed,
                    best_loss=min(r["best_loss"] for r in selected),
                    stable_screen_height_m=max(stable) if stable else None,
                )
            )
        baseline = method.split("-")[0]
        paired = []
        for row in group:
            old = next(
                r
                for r in report["runs"]
                if r["method"] == baseline
                and r["seed"] == row["seed"]
                and r["anchor"] == row["anchor"]
            )
            paired.append(row["best_loss"] - old["best_loss"])
        best_native = max(passed, key=lambda r: r["metrics"]["apogee_m"], default=None)
        summaries.append(
            dict(
                method=method,
                measured_evaluations=sum(r["evaluations"] for r in group),
                predicted_candidates=sum(r["predicted_candidates"] for r in group),
                by_seed=by_seed,
                median_best_loss=float(np.median([r["best_loss"] for r in by_seed])),
                better_paired_anchor_runs=int(np.sum(np.array(paired) < -1e-8)),
                worse_paired_anchor_runs=int(np.sum(np.array(paired) > 1e-8)),
                paired_anchor_runs=len(paired),
                native_completed=sum(r["status"] == "completed" for r in native),
                native_screen_passes=len(passed),
                best_native_height_m=best_native["metrics"]["apogee_m"] if best_native else None,
                native_height_target_passes=sum(r["metrics"]["apogee_m"] >= 30 for r in passed),
                best_native_spec=best_native["spec"] if best_native else None,
                native=[
                    dict(
                        label=r["label"],
                        status=r["status"],
                        metrics=r.get("metrics"),
                        screen_pass=r in passed,
                        manifest_sha256=r["evidence"]["manifest_sha256"],
                    )
                    for r in native
                ],
            )
        )
    portable = dict(
        source_hash=report["source_hash"],
        script_hashes=report["script_hashes"],
        training=training_report,
        benchmark_report_sha256=sha(benchmark / "report.json"),
        benchmark_elapsed_s=report["elapsed_s"],
        measured_search_evaluations=measured,
        rejected_search_evaluations=failures,
        native_evidence_files_verified=files,
        methods=summaries,
        independent_seed_settings=len(report["seeds"]),
        matched_initial_populations=report["matched_initial_populations"],
        matched_evaluations=report["matched_evaluations"],
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Analytic aerodynamic exploration, not CFD/FEM acceptance",
            "Three seeds and three fixed anchors, no general optimizer superiority",
            "NN uses additional offline simulations; no equal-total-cost speed claim",
            "Native promotions select the best incumbent across seeds for each anchor",
            "Concurrent execution times are not controlled speed comparisons",
        ],
    )
    write_json(destination, portable)
    return portable


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("benchmark", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    result = export(a.training, a.benchmark, a.destination)
    print(
        json.dumps(
            [
                {k: r[k] for k in ("method", "median_best_loss", "best_native_height_m")}
                for r in result["methods"]
            ]
        )
    )
