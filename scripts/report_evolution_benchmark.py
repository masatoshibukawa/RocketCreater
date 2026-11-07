"""Verify recorded simulations and publish a compact, paired evolutionary comparison."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.report_initial_models import verified


def export(training, benchmark, destination):
    report, files = verified(benchmark)
    first = report["results"][0]
    precision = read(benchmark / first["evidence"]["directory"] / "geometry/input.json")[
        "precision"
    ]
    target = first["spec"]["requirement"]["target_altitude_m"]
    if any(r["spec"]["requirement"] != first["spec"]["requirement"] for r in report["results"]):
        raise ValueError("Native requirements differ")
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
            and r["metrics"]["static_margin_cal"] >= precision["minimum_static_margin_cal"]
            and r["metrics"]["incidence_deg"] <= precision["maximum_incidence_deg"]
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
                native_height_target_passes=sum(r["metrics"]["apogee_m"] >= target for r in passed),
                best_native_spec=best_native["spec"] if best_native else None,
                native=[
                    dict(
                        label=r["label"],
                        status=r["status"],
                        metrics=r.get("metrics"),
                        screen_pass=r in passed,
                        completed_methods=r["completed_methods"],
                        failed_stage=next(
                            (
                                stage
                                for stage in (
                                    "geometry",
                                    "thermal",
                                    "propulsion",
                                    "screen",
                                    "refine",
                                )
                                if stage not in r["completed_methods"]
                            ),
                            None,
                        )
                        if r["status"] != "completed"
                        else None,
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
        target_altitude_m=target,
        screening_precision=precision,
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


def plot(benchmark, report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw = read(benchmark / "report.json")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), layout="constrained")
    colors = {"ga": "#8e8f98", "de": "#b18b59", "ga-nn": "#3274a1", "de-nn": "#07847d"}
    count = raw["population_size"]
    for method, color in colors.items():
        curves = []
        for seed in raw["seeds"]:
            anchor_curves = []
            for run in raw["runs"]:
                if run["method"] != method or run["seed"] != seed:
                    continue
                values = [
                    json.loads(line)["loss"]
                    for line in (benchmark / run["data_file"])
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                anchor_curves.append(np.minimum.accumulate(values)[count - 1 :: count])
            curves.append(np.min(anchor_curves, axis=0))
        curves = np.asarray(curves)
        x = np.arange(1, curves.shape[1] + 1) * count * 3
        axes[0].plot(x, np.median(curves, axis=0), label=method.upper(), color=color)
        axes[0].fill_between(x, curves.min(0), curves.max(0), color=color, alpha=0.10)
    axes[0].set(
        title="Measured search objective",
        xlabel="Simulator calls per seed (3 anchors)",
        ylabel="Best loss: median and range of 3 seeds (lower is better)",
    )
    axes[0].legend(frameon=False, fontsize=8)
    for i, method in enumerate(report["methods"]):
        for j, row in enumerate(method["native"]):
            if row["status"] != "completed":
                continue
            axes[1].scatter(
                i + (j - 1) * 0.13,
                row["metrics"]["apogee_m"],
                s=55,
                facecolors=colors.get(method["method"], "#aaa") if row["screen_pass"] else "none",
                edgecolors="#34454b",
            )
    axes[1].axhline(report["target_altitude_m"], color="#ac504b", ls="--", lw=1)
    axes[1].set(
        xticks=np.arange(len(report["methods"])),
        xticklabels=[r["method"].upper().replace("-ADAPTIVE", "-A") for r in report["methods"]],
        ylabel="Fresh-CAD / 6DOF apogee (m)",
        title="3 native promotions per method\nFilled: original screening checks pass",
    )
    axes[1].tick_params(axis="x", rotation=40)
    rejected = sum(len(r["native"]) - r["native_completed"] for r in report["methods"])
    if rejected:
        axes[1].text(
            0.03,
            0.92,
            f"{rejected} native rejection(s); no altitude assigned",
            transform=axes[1].transAxes,
            fontsize=8,
            color="#8a4742",
        )
    training = report["training"]["anchors"]
    x = np.arange(len(training))
    axes[2].bar(
        x - 0.18,
        [r["test_mean_baseline_mae"][0] for r in training],
        width=0.36,
        color="#c3c6ca",
        label="Training mean",
    )
    axes[2].bar(
        x + 0.18, [r["test_mae"][0] for r in training], width=0.36, color="#07847d", label="MLP"
    )
    axes[2].set(
        xticks=x,
        xticklabels=["Anchor 1", "Anchor 2", "Anchor 3"],
        title="Held-out surrogate error\n308 new examples per anchor",
        ylabel="Conservative-height prediction MAE (m)",
    )
    axes[2].legend(frameon=False)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Adaptive evolutionary search + neural proposal ranking\n"
        "6,144 offline training/validation/test simulations are additional cost; "
        "no CFD/FEM or hardware acceptance",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("benchmark", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.training, a.benchmark, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(a.benchmark, result, a.destination)
    print(
        json.dumps(
            [
                {k: r[k] for k in ("method", "median_best_loss", "best_native_height_m")}
                for r in result["methods"]
            ]
        )
    )
