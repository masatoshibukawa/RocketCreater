"""Audit PPO/SAC simulator evaluation and separate surrogate training cost."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.report_initial_models import verified


def audit_runs(root, report):
    for run in report["runs"]:
        path = root / run["data_file"]
        if path.parent.resolve() != root.resolve() or sha(path) != run["data_sha256"]:
            raise ValueError("Changed or out-of-directory search evidence")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != run["evaluations"] or min(r["loss"] for r in rows) != run["best_loss"]:
            raise ValueError("Search summary does not match recorded measurements")


def export(root, baseline, destination):
    r, files = verified(root)
    base, base_files = verified(baseline)
    if (
        sha(baseline / "report.json") != r["baseline_report_sha256"]
        or base["source_hash"] != r["source_hash"]
        or base["training_report_sha256"] != r["training_report_sha256"]
    ):
        raise ValueError("Mismatched baseline or surrogate source")
    audit_runs(root, r)
    audit_runs(baseline, base)
    for entry in r["training"]:
        for name in ("policy", "transitions"):
            path = root / entry[f"{name}_file"]
            if path.parent.resolve() != root.resolve() or sha(path) != entry[f"{name}_sha256"]:
                raise ValueError("Changed training evidence")
        with np.load(root / entry["transitions_file"], allow_pickle=False) as trace:
            if any(len(trace[k]) != entry["transitions"] for k in trace.files):
                raise ValueError("Transition count mismatch")
            if any(not np.isfinite(trace[k]).all() for k in trace.files):
                raise ValueError("Nonfinite transition")
            if (
                trace["observations"].shape != (entry["transitions"], 20)
                or trace["next_observations"].shape != (entry["transitions"], 20)
                or trace["actions"].shape != (entry["transitions"], 11)
                or np.any(np.abs(trace["actions"]) > 1.000001)
            ):
                raise ValueError("Transition state/action contract differs")
    first = r["results"][0]
    precision = read(root / first["evidence"]["directory"] / "geometry/input.json")["precision"]
    target = first["spec"]["requirement"]["target_altitude_m"]
    summaries = []
    for method in ("random-local", "ppo", "sac", "de-nn"):
        source = base if method == "de-nn" else r
        runs = [row for row in source["runs"] if row["method"] == method]
        native = [row for row in source["results"] if row["label"].rsplit("-", 1)[0] == method]
        passed = [
            row
            for row in native
            if row["status"] == "completed"
            and row["temporal_pass"]
            and row["aero_domain_pass"]
            and row["metrics"]["static_margin_cal"] >= precision["minimum_static_margin_cal"]
            and row["metrics"]["incidence_deg"] <= precision["maximum_incidence_deg"]
        ]
        by_seed, wins, losses, random_wins = [], 0, 0, 0
        for seed in r["seeds"]:
            group = [row for row in runs if row["seed"] == seed]
            by_seed.append(dict(seed=seed, loss=min(row["best_loss"] for row in group)))
        for row in runs:
            other = next(
                x
                for x in base["runs"]
                if x["method"] == "de-nn"
                and x["seed"] == row["seed"]
                and x["anchor"] == row["anchor"]
            )
            if (
                row["initial_sha256"] != other["initial_sha256"]
                or row["evaluations"] != other["evaluations"]
            ):
                raise ValueError("Initial population or evaluation budget mismatch")
            wins += row["best_loss"] < other["best_loss"] - 1e-8
            losses += row["best_loss"] > other["best_loss"] + 1e-8
            random_row = next(
                x
                for x in r["runs"]
                if x["method"] == "random-local"
                and x["seed"] == row["seed"]
                and x["anchor"] == row["anchor"]
            )
            random_wins += row["best_loss"] < random_row["best_loss"] - 1e-8
        best = max(passed, key=lambda row: row["metrics"]["apogee_m"], default=None)
        summaries.append(
            dict(
                method=method,
                by_seed=by_seed,
                median_best_loss=float(np.median([x["loss"] for x in by_seed])),
                wins_against_de_nn=int(wins),
                losses_against_de_nn=int(losses),
                wins_against_random_local=int(random_wins),
                paired_cases=len(runs),
                simulator_evaluations=sum(x["evaluations"] for x in runs),
                rejected_proposals=sum(x["rejected"] for x in runs),
                native_completed=sum(x["status"] == "completed" for x in native),
                native_passes=len(passed),
                best_native_height_m=best["metrics"]["apogee_m"] if best else None,
                best_native_spec=best["spec"] if best else None,
                target_passes=sum(x["metrics"]["apogee_m"] >= target for x in passed),
                native=[
                    dict(
                        label=x["label"],
                        status=x["status"],
                        metrics=x.get("metrics"),
                        screen_pass=x in passed,
                        manifest_sha256=x["evidence"]["manifest_sha256"],
                    )
                    for x in native
                ],
            )
        )
    result = dict(
        source_hash=r["source_hash"],
        script_hashes=r["script_hashes"],
        versions=r["versions"],
        report_sha256=sha(root / "report.json"),
        baseline_report_sha256=r["baseline_report_sha256"],
        training_report_sha256=r["training_report_sha256"],
        training=r["training"],
        surrogate_transitions=sum(x["transitions"] for x in r["training"]),
        training_elapsed_s=sum(x["elapsed_s"] for x in r["training"]),
        total_elapsed_s=r["elapsed_s"],
        new_simulator_calls=sum(x["evaluations"] for x in r["runs"]),
        methods=summaries,
        verified_native_files=files,
        verified_baseline_files=base_files,
        target_altitude_m=target,
        screening_precision=precision,
        matched_initial_populations=True,
        matched_evaluation_counts=True,
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Surrogate training is additional cost and subject to model exploitation",
            "PPO/SAC freeze material within each episode; DE can change it",
            "Three training seeds and known anchors; unseen mission generalization untested",
            "Native finalists selected over three seeds; no seed-level native statistics",
            "No upper-layer analysis scheduling or CFD/FEM acceptance in this experiment",
        ],
    )
    write_json(destination, result)
    return result


def plot(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    colors = ["#aaa", "#4a79b8", "#ab7042", "#07847d"]
    for i, (method, color) in enumerate(zip(report["methods"], colors, strict=True)):
        values = [x["loss"] for x in method["by_seed"]]
        axes[0].scatter(np.full(3, i), values, color=color, s=40)
        axes[0].plot([i - 0.2, i + 0.2], [np.median(values)] * 2, color=color, lw=3)
        for j, native in enumerate(method["native"]):
            if native["status"] == "completed":
                axes[1].scatter(
                    i + 0.12 * (j - 1),
                    native["metrics"]["apogee_m"],
                    s=50,
                    facecolors=color if native["screen_pass"] else "none",
                    edgecolors=color,
                )
    labels = [x["method"].upper() for x in report["methods"]]
    for ax in axes:
        ax.set(xticks=range(4), xticklabels=labels)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].set(
        ylabel="Best measured loss per seed (lower is better)",
        title="Three seed settings; line = median",
    )
    axes[1].axhline(report["target_altitude_m"], color="#ac504b", ls="--", lw=1)
    axes[1].set(
        ylabel="Fresh-CAD / 6DOF apogee (m)",
        title="Three native attempts per method\nFilled: screening checks pass",
    )
    failed = sum(len(x["native"]) - x["native_completed"] for x in report["methods"])
    if failed:
        axes[1].text(
            0.03,
            0.92,
            f"{failed} native rejection(s); no altitude assigned",
            transform=axes[1].transAxes,
            fontsize=8,
            color="#8a4742",
        )
    fig.suptitle(
        "PPO / SAC sequential design: frozen-surrogate training, simulator evaluation\n"
        "Training cost is additional; no physical qualification",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run", type=Path)
    p.add_argument("baseline", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    report = export(a.run, a.baseline, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(report, a.destination)
    print(
        json.dumps(
            [
                {k: x[k] for k in ("method", "median_best_loss", "best_native_height_m")}
                for x in report["methods"]
            ]
        )
    )
