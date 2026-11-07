"""Recompute held-out scores and audit expanded data, model gates and nominal routing."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.worker import read
from scripts.expanded_design_data import AXES, FAMILIES
from scripts.expanded_surrogate import core_coordinates, inverse, predict
from scripts.report_refined_rl import local_file
from scripts.search_surrogate import predict as dense_predict
from scripts.train_expanded_surrogate import arrays, scores


def same_scores(recorded, actual):
    counts = (
        "count",
        "false_static_headroom",
        "true_static_headroom",
        "predicted_static_headroom",
        "missed_static_headroom",
        "boundary_count",
    )
    if any(recorded[k] != actual[k] for k in counts):
        raise ValueError("Recorded evaluation counts differ")
    for key in ("mae", "maximum_error"):
        if not np.allclose(recorded[key], actual[key], rtol=1e-10, atol=1e-11):
            raise ValueError("Recorded prediction errors differ")
    if (recorded["boundary_mae"] is None) != (actual["boundary_mae"] is None):
        raise ValueError("Missing boundary evaluation")
    if actual["boundary_mae"] is not None and not np.allclose(
        recorded["boundary_mae"], actual["boundary_mae"], rtol=1e-10, atol=1e-11
    ):
        raise ValueError("Boundary evaluation differs")


def export(data, history, advisors, models, destination):
    dr, hr, ar, mr = [read(p / "report.json") for p in (data, history, advisors, models)]
    if not dr["source_unchanged"] or not mr["source_unchanged"]:
        raise ValueError("Changed implementation")
    for path, key in (
        (data, "data_report_sha256"),
        (history, "history_report_sha256"),
        (advisors, "advisor_report_sha256"),
    ):
        if sha(path / "report.json") != mr[key]:
            raise ValueError("Changed input report")
    if read(local_file(models, "frozen-models.json", mr["frozen_models_sha256"])) != mr["anchors"]:
        raise ValueError("Model selection differs from frozen manifest")
    for entry in mr["learning_curve"]:
        local_file(models, entry["model_file"], entry["model_sha256"])
    data_summary = []
    contexts = []
    for i in range(3):
        file = local_file(data, f"examples-{i}.jsonl", dr["anchors"][i]["examples_sha256"])
        rows = list(map(json.loads, file.read_text(encoding="utf-8").splitlines()))
        complete = [r for r in rows if r["status"] == "completed"]
        if (
            len(rows) != dr["anchors"][i]["evaluated"]
            or len(complete) != dr["anchors"][i]["completed"]
        ):
            raise ValueError("Recorded dataset count differs")
        old_file = local_file(history, f"examples-{i}.jsonl", hr["anchors"][i]["examples_sha256"])
        old = [
            r
            for r in map(json.loads, old_file.read_text(encoding="utf-8").splitlines())
            if r["split"] == "train"
        ]
        groups = {
            s: [r for r in complete if r["split"] == s] for s in ("train", "validation", "test")
        }
        ids = [{r["spec_hash"] for r in groups[s]} for s in groups]
        if (
            ids[0] & ids[1]
            or ids[0] & ids[2]
            or ids[1] & ids[2]
            or (ids[1] | ids[2]) & {r["spec_hash"] for r in old}
        ):
            raise ValueError("Leaked design identity")
        parents = [{r["parent"] for r in groups[s] if r["parent"]} for s in groups]
        if parents[0] & parents[1] or parents[0] & parents[2] or parents[1] & parents[2]:
            raise ValueError("Leaked residual parent")
        model = read(
            local_file(models, mr["anchors"][i]["model_file"], mr["anchors"][i]["model_sha256"])
        )
        expert = read(local_file(advisors, f"model-{i}.json", ar["anchors"][i]["model_sha256"]))
        if model["nominal_expert"] != expert:
            raise ValueError("Changed nominal expert")
        for member, entry in zip(model["members"], mr["anchors"][i]["members"], strict=True):
            if member != read(local_file(models, entry["file"], entry["sha256"])):
                raise ValueError("Embedded ensemble member differs")
        x, y = arrays(groups["test"])
        broad, hybrid = predict(model, x, hybrid=False), predict(model, x)
        expected = mr["tests"][i]
        same_scores(expected["broad"], scores(y, broad))
        same_scores(expected["hybrid"], scores(y, hybrid))
        for family in FAMILIES:
            mask = np.array([r["distribution"] == family for r in groups["test"]])
            same_scores(expected["by_distribution"][family]["broad"], scores(y[mask], broad[mask]))
            same_scores(
                expected["by_distribution"][family]["hybrid"], scores(y[mask], hybrid[mask])
            )
        original, core = core_coordinates(x, DesignSpec.model_validate(model["anchor"]))
        expert_prediction = dense_predict(expert, original[core])
        if (
            not np.array_equal(hybrid[core], expert_prediction)
            or expected["core_max_prediction_change"] != 0
        ):
            raise ValueError("Nominal routing changed expert predictions")
        for curve in expected["learning_curve"]:
            entry = next(
                r
                for r in mr["learning_curve"]
                if r["anchor"] == i
                and r["seed"] == 9021
                and r["fresh_train_count"] == curve["fresh_train_count"]
            )
            predicted = inverse(dense_predict(read(models / entry["model_file"]), x))
            same_scores(curve["test"], scores(y, predicted))
        vx, vy = arrays(groups["validation"])
        validation = predict(model, vx, hybrid=False)
        baseline = np.mean(np.r_[arrays(old)[1], arrays(groups["train"])[1]], axis=0)
        gates = []
        for family in FAMILIES:
            mask = np.array([r["distribution"] == family for r in groups["validation"]])
            actual = scores(vy[mask], validation[mask])
            recorded = mr["anchors"][i]["validation_by_distribution"][family]
            same_scores(recorded, actual)
            enabled = bool(
                mask.sum() >= 30
                and np.all(np.array(actual["mae"][:2]) < np.abs(vy[mask] - baseline).mean(0)[:2])
            )
            if enabled != recorded["enabled"]:
                raise ValueError("Validation gate differs")
            gates.append(enabled)
        if all(gates) != model["validation_enabled"]:
            raise ValueError("Incorrect advisor enablement")
        units = np.array([r["unit"] for r in complete])
        entry = {k: v for k, v in dr["anchors"][i].items() if k not in ("anchor_spec", "cad")}
        entry.update(
            non_lifting_cases=sum(not r["metrics"]["lifted"] for r in complete),
            beam_ratio_over_005=sum(
                r["metrics"]["conservative_beam_ratio"] > 0.05 for r in complete
            ),
            static_margin_below_one=sum(r["metrics"]["static_margin_cal"] < 1 for r in complete),
            observed_bounds={
                k: [
                    float(lo + units[:, j].min() * (hi - lo)),
                    float(lo + units[:, j].max() * (hi - lo)),
                ]
                for j, (k, (lo, hi)) in enumerate(AXES.items())
            },
        )
        data_summary.append(entry)
        contexts.extend(units[:: max(1, len(units) // 600), 12:15].tolist())
    public = dict(
        source_hash=mr["source_hash"],
        data_report_sha256=sha(data / "report.json"),
        model_report_sha256=sha(models / "report.json"),
        data_script_hashes=dr["script_hashes"],
        model_script_hashes=mr["script_hashes"],
        input_contract=mr["input_contract"],
        versions=mr["versions"],
        axes=dr["axes"],
        categories=dr["categories"],
        data=data_summary,
        models=mr["anchors"],
        tests=mr["tests"],
        learning_curve=mr["learning_curve"],
        family_weights=dr["family_weights"],
        evaluated=sum(r["evaluated"] for r in data_summary),
        completed=sum(r["completed"] for r in data_summary),
        screening_attempts=sum(r["screening_attempts"] for r in data_summary),
        extended_discharge_cases=sum(r["extended_discharge_cases"] for r in data_summary),
        total_historical_train=sum(r["historical_train_count"] for r in mr["anchors"]),
        total_fresh_train=sum(r["fresh_train_count"] for r in mr["anchors"]),
        total_train=sum(r["total_train_count"] for r in mr["anchors"]),
        total_validation=sum(r["validation_count"] for r in mr["anchors"]),
        total_test=sum(r["hybrid"]["count"] for r in mr["tests"]),
        data_elapsed_s=dr["elapsed_s"],
        training_elapsed_s=mr["elapsed_s"],
        sampled_context_coordinates=contexts,
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Fixed bottle envelopes; axial thermal/discharge labels, not CFD or six-DOF flight",
            "CAD-scaled volumes, constitutive and attachment assumptions remain",
            "Learning curve uses one initialization; full model uses three-member ensemble",
            "Residual test neighborhoods use old training parents with disjoint split ownership",
            "Expanded prediction coverage is not proven better flight optimization",
        ],
    )
    write_json(destination, public)
    return public


def plot(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    labels = ["Core", "Context", "Wide", "Boundary", "Residual"]
    complete = [sum(r["by_distribution"][f]["completed"] for r in report["data"]) for f in FAMILIES]
    failed = [
        sum(
            r["by_distribution"][f]["invalid_geometry"] + r["by_distribution"][f]["analysis_failed"]
            for r in report["data"]
        )
        for f in FAMILIES
    ]
    axes[0, 0].bar(labels, complete, label="Completed", color="#167e83")
    axes[0, 0].bar(labels, failed, bottom=complete, label="Rejected / incomplete", color="#c9784c")
    axes[0, 0].set(title="Fresh simulator coverage", ylabel="Design points")
    axes[0, 0].legend(frameon=False, fontsize=8)
    x = np.array(report["sampled_context_coordinates"])
    dots = axes[0, 1].scatter(
        50 + 350 * x[:, 0], 10 + 190 * x[:, 1], c=1 + 44 * x[:, 2], s=6, alpha=0.5, cmap="viridis"
    )
    axes[0, 1].set(
        title="Recorded pressure / payload / temperature",
        xlabel="Initial gauge pressure (kPa)",
        ylabel="Payload (g)",
    )
    fig.colorbar(dots, ax=axes[0, 1], label="Ambient temperature (C)")
    for row in report["tests"]:
        curves = row["learning_curve"]
        axes[1, 0].plot(
            [r["fresh_train_count"] for r in curves],
            [r["test"]["mae"][0] for r in curves],
            marker="o",
            label=f"Anchor {row['anchor']}",
        )
    axes[1, 0].set(
        title="More fresh data, same architecture / seed",
        xlabel="Fresh training points per anchor (+ fixed history)",
        ylabel="Held-out height MAE (m)",
    )
    axes[1, 0].legend(frameon=False, fontsize=8)
    for j, key in enumerate(("broad", "hybrid")):
        values = [
            np.mean([r["by_distribution"][f][key]["mae"][0] for r in report["tests"]])
            for f in FAMILIES
        ]
        axes[1, 1].bar(
            np.arange(5) + (j - 0.5) * 0.35,
            values,
            width=0.35,
            label=key,
            color=("#9eb8c2", "#167e83")[j],
        )
    axes[1, 1].set(
        xticks=range(5),
        xticklabels=labels,
        title="Distribution-specific prediction error",
        ylabel="Held-out height MAE (m)",
    )
    axes[1, 1].legend(frameon=False, fontsize=8)
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Expanded training: 20 inputs, broader bounds, five sampling distributions\n"
        "Predictions approximate simulation; no physical qualification",
        fontsize=13,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("data", "history", "advisors", "models", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.data, a.history, a.advisors, a.models, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print({k: result[k] for k in ("evaluated", "completed", "total_train", "total_test")})
