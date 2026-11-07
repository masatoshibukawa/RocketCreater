"""Audit fresh-seed RL comparison, surrogate errors and preserved search incumbents."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.report_design_rl import audit_runs
from scripts.report_initial_models import verified
from scripts.search_surrogate import predict, targets


def local_file(root, name, expected):
    path = root / name
    if path.parent.resolve() != root.resolve() or sha(path) != expected:
        raise ValueError("Changed or out-of-directory evidence")
    return path


def audit_incumbents(rows):
    for episode in range(32):
        group = [r for r in rows if r["episode"] == episode]
        if [r["step"] for r in group] != list(range(11)):
            raise ValueError("Missing or reordered episode step")
        best = float("inf")
        for row in group:
            improved = row["status"] == "completed" and row["loss"] < best
            if improved:
                best = row["loss"]
            expected = best if np.isfinite(best) else None
            if row["incumbent_loss"] != expected or row["incumbent_improved"] != improved:
                raise ValueError("Incumbent differs from measured best design")


def export(root, training, original, previous, destination):
    report, files = verified(root)
    tr, old, base = [read(p / "report.json") for p in (training, original, previous)]
    for folder in (training, original, previous):
        if sha(folder / "report.json") != report["input_reports"][str(folder)]:
            raise ValueError("Changed input report")
    audit_runs(root, report)
    for entry in report["frozen_baselines"] + report["training"]:
        local_file(root, entry["policy_file"], entry["policy_sha256"])
        if "transitions_file" not in entry:
            source = next(
                r for r in base["training"] if r["policy_file"] == entry["original_policy_file"]
            )
            if source["policy_sha256"] != entry["policy_sha256"]:
                raise ValueError("Baseline policy differs")
            continue
        trace_path = local_file(root, entry["transitions_file"], entry["transitions_sha256"])
        with np.load(trace_path, allow_pickle=False) as trace:
            n = entry["transitions"]
            if any(len(trace[k]) != n or not np.isfinite(trace[k]).all() for k in trace.files):
                raise ValueError("Invalid training transition archive")
            if (
                trace["observations"].shape != (n, 20)
                or trace["next_observations"].shape != (n, 20)
                or trace["actions"].shape != (n, 11)
                or np.any(np.abs(trace["actions"]) > 1.000001)
            ):
                raise ValueError("State/action contract differs")
    for seed in report["seeds"]:
        for i in range(3):
            group = [r for r in report["runs"] if r["seed"] == seed and r["anchor"] == i]
            if (
                len(group) != 5
                or len({r["initial_sha256"] for r in group}) != 1
                or {r["evaluations"] for r in group} != {352}
            ):
                raise ValueError("Unmatched evaluation budgets or initial populations")
    errors = []
    for i in range(3):
        model = read(local_file(training, f"model-{i}.json", tr["anchors"][i]["model_sha256"]))
        old_model = read(local_file(original, f"model-{i}.json", old["anchors"][i]["model_sha256"]))
        examples = local_file(training, f"examples-{i}.jsonl", tr["anchors"][i]["examples_sha256"])
        records = [json.loads(s) for s in examples.read_text(encoding="utf-8").splitlines()]
        train = {r["spec_hash"] for r in records if r["split"] == "train"}
        val = {r["spec_hash"] for r in records if r["split"] == "validation"}
        old_examples = local_file(
            original, f"examples-{i}.jsonl", old["anchors"][i]["examples_sha256"]
        )
        held = {
            r["spec_hash"]
            for r in map(json.loads, old_examples.read_text(encoding="utf-8").splitlines())
            if r["split"] == "test" and r["status"] == "completed"
        }
        if train & val or (train | val) & held:
            raise ValueError("Training/validation/old held-out overlap")
        training_units = {tuple(r["unit"]) for r in records if r["split"] == "train"}
        if any(tuple(unit) not in training_units for unit in model["curriculum_units"]):
            raise ValueError("Curriculum includes a nontraining design")
        rows = []
        for run in report["runs"]:
            if run["anchor"] != i:
                continue
            data = [
                json.loads(s)
                for s in (root / run["data_file"]).read_text(encoding="utf-8").splitlines()
            ]
            if run["method"] in ("ppo-v2", "sac-v2"):
                audit_incumbents(data)
            rows.extend(r for r in data if r["status"] == "completed")
        x, y = np.array([r["unit"] for r in rows]), np.array([targets(r["metrics"]) for r in rows])
        prediction, prior = predict(model, x), predict(old_model, x)
        errors.append(
            dict(
                anchor=i,
                samples=len(rows),
                old_mae=np.abs(prior - y).mean(0).tolist(),
                refined_mae=np.abs(prediction - y).mean(0).tolist(),
                old_max_error=np.abs(prior - y).max(0).tolist(),
                refined_max_error=np.abs(prediction - y).max(0).tolist(),
                old_false_static_headroom=int(np.sum((prior[:, 1] >= 1.12) & (y[:, 1] < 1.12))),
                refined_false_static_headroom=int(
                    np.sum((prediction[:, 1] >= 1.12) & (y[:, 1] < 1.12))
                ),
            )
        )
    first = report["results"][0]
    precision = read(root / first["evidence"]["directory"] / "geometry/input.json")["precision"]
    target = first["spec"]["requirement"]["target_altitude_m"]
    summaries = []
    for method in report["methods"]:
        runs = [r for r in report["runs"] if r["method"] == method]
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
        pairs = {}
        for other in report["methods"]:
            diffs = [
                r["best_loss"]
                - next(
                    x["best_loss"]
                    for x in report["runs"]
                    if x["method"] == other
                    and x["seed"] == r["seed"]
                    and x["anchor"] == r["anchor"]
                )
                for r in runs
            ]
            pairs[other] = dict(
                wins=sum(d < -1e-8 for d in diffs),
                losses=sum(d > 1e-8 for d in diffs),
                ties=sum(abs(d) <= 1e-8 for d in diffs),
                mean_loss_difference=float(np.mean(diffs)),
            )
        by_seed = [
            dict(seed=seed, loss=min(r["best_loss"] for r in runs if r["seed"] == seed))
            for seed in report["seeds"]
        ]
        best = max(passed, key=lambda r: r["metrics"]["apogee_m"], default=None)
        summaries.append(
            dict(
                method=method,
                by_seed=by_seed,
                median_best_loss=float(np.median([r["loss"] for r in by_seed])),
                paired_comparisons=pairs,
                simulator_evaluations=sum(r["evaluations"] for r in runs),
                rejected_proposals=sum(r["rejected"] for r in runs),
                unique_specs_per_run=[r["unique_specs"] for r in runs],
                predicted_candidates=sum(r["predicted_candidates"] for r in runs),
                native_completed=sum(r["status"] == "completed" for r in native),
                native_passes=len(passed),
                best_native_height_m=best["metrics"]["apogee_m"] if best else None,
                best_native_spec=best["spec"] if best else None,
                target_passes=sum(r["metrics"]["apogee_m"] >= target for r in passed),
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
    public = dict(
        source_hash=report["source_hash"],
        script_hashes=report["script_hashes"],
        versions=report["versions"],
        report_sha256=sha(root / "report.json"),
        training_report_sha256=sha(training / "report.json"),
        previous_report_sha256=sha(previous / "report.json"),
        methods=summaries,
        seeds=report["seeds"],
        hyperparameters=report["hyperparameters"],
        training=report["training"],
        frozen_baselines=report["frozen_baselines"],
        surrogate_transitions=sum(r["transitions"] for r in report["training"]),
        training_elapsed_s=sum(r["elapsed_s"] for r in report["training"]),
        total_elapsed_s=report["elapsed_s"],
        new_simulator_calls=sum(r["evaluations"] for r in report["runs"]),
        development_validation=tr["anchors"],
        fresh_rollout_prediction_errors=errors,
        verified_native_files=files,
        verified_search_logs=len(report["runs"]),
        target_altitude_m=target,
        screening_precision=precision,
        matched_initial_populations=True,
        matched_evaluation_counts=True,
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Combined changes, not an ablation of each improvement",
            "Additional historical data and longer training; not equal total compute cost",
            "Three fresh test seeds on known anchors, not unseen missions or hardware",
            "RL fixes material within episode; DE can change material",
            "Native finalists chosen over seeds; no seed-level native inference",
            "No CFD/FEM acceptance or upper-layer analysis scheduling in this experiment",
        ],
    )
    write_json(destination, public)
    return public


def plot(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    colors = ["#9aaec7", "#bdaa96", "#336fa7", "#b66b2b", "#07847d"]
    for i, (row, color) in enumerate(zip(report["methods"], colors, strict=True)):
        values = [r["loss"] for r in row["by_seed"]]
        axes[0].scatter(np.full(3, i), values, color=color, s=45)
        axes[0].plot([i - 0.2, i + 0.2], [np.median(values)] * 2, color=color, lw=3)
        for j, native in enumerate(row["native"]):
            if native["status"] == "completed":
                axes[1].scatter(
                    i + 0.12 * (j - 1),
                    native["metrics"]["apogee_m"],
                    s=50,
                    facecolors=color if native["screen_pass"] else "none",
                    edgecolors=color,
                )
    for ax in axes:
        ax.set(xticks=range(5), xticklabels=[r["method"].upper() for r in report["methods"]])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].set(
        ylabel="Best measured loss per seed (lower is better)", title="Fresh seeds; bar = median"
    )
    axes[1].axhline(report["target_altitude_m"], color="#ac504b", ls="--", lw=1)
    axes[1].set(
        ylabel="Fresh-CAD / 6DOF apogee (m)", title="Same native budget; filled = screening pass"
    )
    failed = sum(3 - r["native_completed"] for r in report["methods"])
    if failed:
        axes[1].text(
            0.02,
            0.92,
            f"{failed} native rejection(s), no altitude assigned",
            transform=axes[1].transAxes,
            fontsize=8,
        )
    fig.suptitle(
        "Refined PPO / SAC: retain best design, refit NN, coarse-to-fine search\n"
        "3,168 simulator calls per method; training is additional; no physical qualification",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("run", "training", "original", "previous", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.run, a.training, a.original, a.previous, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print(
        json.dumps(
            [
                {k: r[k] for k in ("method", "median_best_loss", "best_native_height_m")}
                for r in result["methods"]
            ]
        )
    )
