"""Audit paired search logs, frozen predictors and native promotions before reporting."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.worker import read
from scripts.benchmark_expanded_search import (
    METHODS,
    expanded_points,
    fixed_mission,
    initial_population,
    native_pass,
)
from scripts.expanded_design_data import decode
from scripts.expanded_surrogate import core_coordinates, predict
from scripts.report_initial_models import verified
from scripts.search_surrogate import predict as expert_predict
from scripts.search_surrogate import targets


def local_file(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence path escapes the run")
    return path


def audit_rows(rows, run, anchor, population, generations):
    if len(rows) != population * (generations + 1) or len(rows) != run["evaluations"]:
        raise ValueError("Objective-call count differs")
    initial = initial_population(
        population, run["seed"] + run["anchor"], anchor, run["method"].split("-")[0]
    )
    expected = expanded_points(initial, anchor, run["method"].split("-")[0])
    if (
        digest(initial.tolist()) != run["initial_sha256"]
        or digest(expected.tolist()) != run["expanded_initial_sha256"]
        or [r["unit"] for r in rows[:population]] != expected.tolist()
    ):
        raise ValueError("Initial population differs from frozen plan")
    completed = []
    for row in rows:
        if row["status"] == "completed":
            spec = decode(anchor, row["unit"])
            fixed_mission(spec, anchor)
            if (
                spec.model_dump(mode="json") != row["spec"]
                or digest(row["spec"]) != row["spec_hash"]
            ):
                raise ValueError("Recorded candidate differs from decoded input")
            y = targets(row["metrics"])
            expected_loss = 2000 * max(0, 1.12 - y[1]) - y[0]
            if not np.isfinite(y).all() or row["loss"] != expected_loss:
                raise ValueError("Recorded loss differs from physical metrics")
            completed.append(row)
        elif row["loss"] != 1e12 or "metrics" in row:
            raise ValueError("Failure has fabricated physical metrics")
    best = min(completed, key=lambda r: r["loss"], default=None)
    if best != run["best"] or (best is not None and best["loss"] != run["best_loss"]):
        raise ValueError("Best measured candidate differs")
    history = run["history"]
    for i, row in enumerate(history):
        subset = rows[: population * (i + 1)]
        if row["best"] != min(r["loss"] for r in subset):
            raise ValueError("A measured incumbent was lost")
    if (
        len(history) != generations + 1
        or run["predicted_candidates"] != 3 * population * generations
    ):
        raise ValueError("Proposal-count budget differs")
    if sum(r["screening_attempts"] for r in rows) != run["screening_attempts"]:
        raise ValueError("Physics-call count differs")
    return completed


def errors(truth, predicted):
    delta = np.abs(np.asarray(truth) - np.asarray(predicted))
    return dict(count=len(delta), mae=delta.mean(0).tolist(), maximum=delta.max(0).tolist())


def export(root, training, destination):
    report, files = verified(root)
    if sha(training / "report.json") != report["training_report_sha256"]:
        raise ValueError("Training report changed")
    bundles = []
    for i in range(3):
        name = f"context-model-{i}.json"
        if sha(training / name) != report["model_hashes"][name]:
            raise ValueError("Frozen model changed")
        bundles.append(read(training / name))
    if len(report["runs"]) != len(METHODS) * 3 * len(report["seeds"]):
        raise ValueError("Missing search run")
    ids, logs, prediction_scores = set(), {}, []
    for run in report["runs"]:
        key = (run["method"], run["anchor"], run["seed"])
        if key in ids:
            raise ValueError("Repeated search run")
        ids.add(key)
        path = local_file(root, run["data_file"])
        if sha(path) != run["data_sha256"]:
            raise ValueError("Search log changed")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        bundle = bundles[run["anchor"]]
        anchor = DesignSpec.model_validate(bundle["anchor"])
        valid = audit_rows(rows, run, anchor, report["population"], report["generations"])
        logs[key] = rows
        x = np.array([r["unit"] for r in valid])
        truth = np.array([targets(r["metrics"]) for r in valid])
        original, supported = core_coordinates(x, anchor)
        hybrid = predict(bundle, x)
        broad = predict(bundle, x, hybrid=False)
        old = expert_predict(bundle["nominal_expert"], original[supported])
        prediction_scores.append(
            dict(
                method=key[0],
                anchor=key[1],
                seed=key[2],
                broad=errors(truth, broad),
                hybrid=errors(truth, hybrid),
                old_supported=errors(truth[supported], old) if supported.any() else None,
                routed_identity=np.array_equal(hybrid[supported], old),
                false_headroom=int(np.sum((hybrid[:, 1] >= 1.12) & (truth[:, 1] < 1.12))),
            )
        )
    for domain in ("core", "wide"):
        methods = [m for m in METHODS if m.startswith(domain)]
        for index in range(3):
            for seed in report["seeds"]:
                first = logs[(methods[0], index, seed)][: report["population"]]
                second = logs[(methods[1], index, seed)][: report["population"]]
                if first != second:
                    raise ValueError("Paired initial measurements differ")
    if len(report["results"]) != 12:
        raise ValueError("Native promotion count differs")
    for native in report["results"]:
        method, index = native["label"].rsplit("-", 1)
        group = [r for r in report["runs"] if r["method"] == method and r["anchor"] == int(index)]
        best = min(group, key=lambda r: r["best_loss"])
        if native["spec"] != best["best"]["spec"]:
            raise ValueError("Native promotion differs from measured objective winner")
    summary = []
    for method in METHODS:
        group = [r for r in report["runs"] if r["method"] == method]
        baseline = method.split("-")[0] + "-old"
        deltas = []
        for run in group:
            old = next(
                r
                for r in report["runs"]
                if r["method"] == baseline
                and r["anchor"] == run["anchor"]
                and r["seed"] == run["seed"]
            )
            deltas.append(run["best_loss"] - old["best_loss"])
        native = [r for r in report["results"] if r["label"].rsplit("-", 1)[0] == method]
        passed = [r for r in native if native_pass(r, Precision())]
        best_native = max(passed, key=lambda r: r["drag_plus_10pct_height_m"], default=None)
        seed_best = [
            min(r["best_loss"] for r in group if r["seed"] == seed) for seed in report["seeds"]
        ]
        summary.append(
            dict(
                method=method,
                objective_calls=sum(r["evaluations"] for r in group),
                physics_calls=sum(r["screening_attempts"] for r in group),
                rejected=sum(r["rejected"] for r in group),
                median_portfolio_loss=float(np.median(seed_best)),
                median_anchor_loss=float(np.median([r["best_loss"] for r in group])),
                paired_deltas=deltas,
                wins=sum(d < -1e-8 for d in deltas),
                losses=sum(d > 1e-8 for d in deltas),
                ties=sum(abs(d) <= 1e-8 for d in deltas),
                native_pass_count=len(passed),
                native_height_target_count=sum(r["metrics"]["apogee_m"] >= 30 for r in passed),
                best_native_height_m=best_native["metrics"]["apogee_m"] if best_native else None,
                best_drag_plus_10pct_height_m=best_native["drag_plus_10pct_height_m"]
                if best_native
                else None,
                best_native_label=best_native["label"] if best_native else None,
                native=[
                    dict(
                        label=r["label"],
                        status=r["status"],
                        metrics=r.get("metrics"),
                        error=r.get("error"),
                        screening_pass=native_pass(r, Precision()),
                        completed_methods=r["completed_methods"],
                        time_step_difference_m=r.get("time_step_difference_m"),
                        drag_plus_10pct_height_m=r.get("drag_plus_10pct_height_m"),
                        spec=r["spec"],
                    )
                    for r in native
                ],
            )
        )
    result = dict(
        source_hash=report["source_hash"],
        report_sha256=sha(root / "report.json"),
        script_hashes=report["script_hashes"],
        model_hashes=report["model_hashes"],
        objective_calls=sum(r["evaluations"] for r in report["runs"]),
        physics_calls=sum(r["screening_attempts"] for r in report["runs"]),
        native_evidence_files_verified=files,
        search_logs_verified=len(logs),
        methods=summary,
        prediction_on_search_samples=prediction_scores,
        elapsed_s=report["elapsed_s"],
        detailed_candidates=report["detailed_candidates"],
        seeds=report["seeds"],
        population=report["population"],
        generations=report["generations"],
        matched_initial_measurements=True,
        matched_objective_budgets=True,
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Three seeds and three fixed anchors; not general optimizer superiority",
            "Geometry rejection consumes budget; completed physics counts may differ",
            "Prediction errors on adaptively selected designs are not independent test accuracy",
            "Broad training and ensembles are combined; this is not a pure data-only ablation",
            "Offline training costs are additional; no equal-total-cost speed claim",
            "Fresh CAD/analytic 6DOF is separate from subsequent CFD/FEM confirmation",
        ],
    )
    write_json(destination, result)
    return result


def plot(root, result, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = read(root / "report.json")
    colors = {
        "core-old": "#809295",
        "core-broad": "#008c82",
        "wide-old": "#9b7653",
        "wide-new": "#1679ad",
    }
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), layout="constrained")
    for ax, domain in zip(axes[:2], ("core", "wide"), strict=True):
        for method in [m for m in METHODS if m.startswith(domain)]:
            curves = []
            for seed in report["seeds"]:
                group = [r for r in report["runs"] if r["method"] == method and r["seed"] == seed]
                curves.append(np.min([[h["best"] for h in r["history"]] for r in group], axis=0))
            curves = np.asarray(curves)
            x = np.arange(1, curves.shape[1] + 1) * report["population"] * 3
            ax.plot(x, np.median(curves, axis=0), label=method, color=colors[method])
            ax.fill_between(x, curves.min(0), curves.max(0), color=colors[method], alpha=0.15)
        ax.set(
            title=f"{domain.capitalize()} domain: measured objective",
            xlabel="Candidate evaluations per seed (3 anchors)",
            ylabel="Best objective: median and range of 3 seeds",
        )
        ax.legend(frameon=False)
    for i, method in enumerate(result["methods"]):
        for j, row in enumerate(method["native"]):
            if row["status"] == "completed":
                axes[2].scatter(
                    i + (j - 1) * 0.13,
                    row["metrics"]["apogee_m"],
                    s=60,
                    facecolors=colors[method["method"]] if row["screening_pass"] else "none",
                    edgecolors=colors[method["method"]],
                )
    axes[2].axhline(30, color="#af5245", ls="--", lw=1)
    axes[2].set(
        xticks=np.arange(4),
        xticklabels=METHODS,
        title="Fresh CAD / analytic 6DOF\nFilled: original screening checks pass",
        ylabel="Simulated apogee (m)",
    )
    axes[2].tick_params(axis="x", rotation=25)
    for ax in axes:
        ax.grid(axis="y", alpha=0.15)
        ax.spines[["right", "top"]].set_visible(False)
    fig.suptitle(
        "Expanded training: does prediction improvement help design search?\n"
        "Fixed 60 g payload and 400 kPa; matched candidate budgets, frozen models",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "training", "destination"):
        p.add_argument(name, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.root, a.training, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(a.root, result, a.destination)
    print(
        json.dumps(
            [
                {k: r[k] for k in ("method", "wins", "losses", "best_native_height_m")}
                for r in result["methods"]
            ]
        )
    )
