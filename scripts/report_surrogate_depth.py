"""Verify architecture comparison and package the validation-selected frozen advisor."""

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.benchmark_surrogate_depth import ARCHITECTURES, SEEDS, select_architecture
from scripts.report_refined_rl import local_file
from scripts.search_surrogate import predict, targets


def export(root, training, original, destination, bundle=None):
    report = read(root / "report.json")
    if (
        not report["source_unchanged"]
        or sha(training / "report.json") != report["training_report_sha256"]
    ):
        raise ValueError("Changed training or implementation")
    selection = read(local_file(root, "selection.json", report["selection_sha256"]))
    if selection != select_architecture(report["rows"]) or selection != report["selection"]:
        raise ValueError("Architecture differs from validation-only selection")
    for row in report["rows"]:
        model = read(local_file(root, row["model_file"], row["model_sha256"]))
        if (
            model["architecture"][1:-1] != row["architecture"]
            or model["validation_mae"] != row["validation_mae"]
        ):
            raise ValueError("Model differs from reported architecture or validation")
    if sha(original / "report.json") != report["original_report_sha256"]:
        raise ValueError("Changed held-out report")
    old = read(original / "report.json")
    for i in range(3):
        data = local_file(original, f"examples-{i}.jsonl", old["anchors"][i]["examples_sha256"])
        held = [
            r
            for r in map(json.loads, data.read_text(encoding="utf-8").splitlines())
            if r["split"] == "test" and r["status"] == "completed"
        ]
        x, y = np.array([r["unit"] for r in held]), np.array([targets(r["metrics"]) for r in held])
        for entry in report["held_out"]:
            if entry["anchor"] != i:
                continue
            row = next(
                r
                for r in report["rows"]
                if r["anchor"] == i
                and r["architecture"] == entry["architecture"]
                and r["seed"] == entry["seed"]
            )
            error = np.abs(predict(read(root / row["model_file"]), x) - y)
            if (
                entry["count"] != len(x)
                or not np.allclose(error.mean(0), entry["mae"], rtol=0, atol=1e-12)
                or not np.allclose(error.max(0), entry["maximum_error"], rtol=0, atol=1e-12)
            ):
                raise ValueError("Held-out error differs from frozen model prediction")
    held_summaries = []
    for architecture in (list(ARCHITECTURES[0]), selection["selected"]):
        if architecture in [r["architecture"] for r in held_summaries]:
            continue
        rows = [r for r in report["held_out"] if r["architecture"] == architecture]
        if len(rows) != 9:
            raise ValueError("Incomplete held-out results")
        held_summaries.append(
            dict(
                architecture=architecture,
                mean_mae=np.mean([r["mae"] for r in rows], axis=0).tolist(),
                worst_error=np.max([r["maximum_error"] for r in rows], axis=0).tolist(),
                distinct_test_examples=sum(r["count"] for r in rows if r["seed"] == SEEDS[0]),
            )
        )
    result = dict(
        source_hash=report["source_hash"],
        script_hashes=report["script_hashes"],
        report_sha256=sha(root / "report.json"),
        training_report_sha256=report["training_report_sha256"],
        selection_sha256=report["selection_sha256"],
        selection=selection,
        architectures=[
            dict(
                **r,
                parameters=next(
                    x["parameters"]
                    for x in report["rows"]
                    if x["architecture"] == r["architecture"]
                ),
            )
            for r in selection["summaries"]
        ],
        held_out=held_summaries,
        held_out_by_anchor_seed=report["held_out"],
        fitted_models=len(report["rows"]),
        total_elapsed_s=report["elapsed_s"],
        sklearn_version=report["sklearn_version"],
        new_physics_evaluations=0,
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "Width/depth changes parameter count too; not a fixed-parameter depth ablation",
            "924 held-out examples are approximate simulator data, not physical measurements",
            "Policy network depth and flight-search benefit are not tested by this comparison",
        ],
    )
    if bundle:
        existing = bundle.exists()
        if not existing:
            bundle.mkdir(parents=True)
        tr = read(training / "report.json")
        packaged = dict(
            source_hash=report["source_hash"],
            source_unchanged=True,
            anchors=[],
            depth_report_sha256=sha(root / "report.json"),
            selected_architecture=selection["selected"],
            fixed_training_seed=SEEDS[0],
            physical_qualification=False,
            acceptance_performed=False,
        )
        for i in range(3):
            row = next(
                r
                for r in report["rows"]
                if r["anchor"] == i
                and r["architecture"] == selection["selected"]
                and r["seed"] == SEEDS[0]
            )
            source_model = local_file(root, row["model_file"], row["model_sha256"])
            source_examples = local_file(
                training, f"examples-{i}.jsonl", tr["anchors"][i]["examples_sha256"]
            )
            if existing:
                local_file(bundle, f"model-{i}.json", sha(source_model))
                local_file(bundle, f"examples-{i}.jsonl", sha(source_examples))
            else:
                shutil.copyfile(source_model, bundle / f"model-{i}.json")
                shutil.copyfile(source_examples, bundle / f"examples-{i}.jsonl")
            packaged["anchors"].append(
                dict(**tr["anchors"][i], selected_model_file=row["model_file"])
            )
            packaged["anchors"][-1].update(
                model_sha256=row["model_sha256"], validation_mae=row["validation_mae"]
            )
        if existing:
            if read(bundle / "report.json") != packaged:
                raise ValueError("Existing model bundle differs")
        else:
            write_json(bundle / "report.json", packaged)
        result["selected_bundle"] = dict(
            report_sha256=sha(bundle / "report.json"),
            training_seed=SEEDS[0],
            model_hashes=[r["model_sha256"] for r in packaged["anchors"]],
        )
    write_json(destination, result)
    return result


def plot(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), layout="constrained")
    rows = report["architectures"]
    labels = [" / ".join(map(str, r["architecture"])) for r in rows]
    colors = [
        "#167b7a" if r["architecture"] == report["selection"]["selected"] else "#9db1be"
        for r in rows
    ]
    for ax, metric, title, ylabel in zip(
        axes,
        (0, 1, None),
        ("Validation: height", "Validation: static margin", "Training cost, 9 fits"),
        ("MAE (m)", "MAE (calibers)", "Elapsed seconds"),
        strict=True,
    ):
        values = [
            r["mean_validation_mae"][metric] if metric is not None else r["training_elapsed_s"]
            for r in rows
        ]
        ax.bar(range(4), values, color=colors)
        ax.set(xticks=range(4), xticklabels=labels, title=title, ylabel=ylabel)
        ax.tick_params(axis="x", rotation=25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "More hidden layers: same data, 3 anchors x 3 initializations\n"
        "Green: validation-selected architecture; simulator prediction, not flight accuracy",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("run", "training", "original", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--bundle", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    report = export(a.run, a.training, a.original, a.destination, a.bundle)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(report, a.destination)
    print(report["selection"])
    print(report["held_out"])
