"""Audit actual variable-payload outcomes, transition archives and native promotions."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.benchmark_pressure_payload import METHODS, pareto
from scripts.expanded_surrogate import predict
from scripts.pressure_payload_search import candidate, expanded, initial, loss, metrics_vector
from scripts.preview_coarse_flight import verify_folder
from scripts.report_refined_rl import local_file


def export(training, root, destination):
    report, tr = read(root / "report.json"), read(training / "report.json")
    if (
        not report["source_unchanged"]
        or not tr["source_unchanged"]
        or report["source_hash"] != code_hash()
        or tr["source_hash"] != code_hash()
        or sha(training / "report.json") != report["training_report_sha256"]
        or len(report["runs"]) != 54
        or len(report["results"]) != 18
    ):
        raise ValueError("Incomplete or changed source/protocol")
    for recorded in (report, tr):
        for name, expected in recorded["script_hashes"].items():
            if sha(Path(__file__).with_name(name)) != expected:
                raise ValueError("Study recipe changed")
    if sha(root / "frozen-policies.json") != report["frozen_policies_sha256"]:
        raise ValueError("Policy freeze record changed")
    if sha(training / "frozen-models.json") != tr["frozen_models_sha256"]:
        raise ValueError("NN freeze record changed")
    bundles = [
        read(local_file(training, r["model_file"], r["model_sha256"])) for r in tr["anchors"]
    ]
    for entry in report["training"]:
        local_file(root, entry["policy_file"], entry["policy_sha256"])
        path = local_file(root, entry["transitions_file"], entry["transitions_sha256"])
        with np.load(path, allow_pickle=False) as trace:
            n = entry["transitions"]
            if (
                entry["device"] != "cuda"
                or n != report["training_steps"]
                or any(len(trace[k]) != n or not np.isfinite(trace[k]).all() for k in trace.files)
                or trace["observations"].shape != (n, 23)
                or trace["actions"].shape != (n, 13)
                or np.any(abs(trace["actions"]) > 1.00001)
                or np.any(trace["next_observations"][trace["terminated"], -1] != 0)
            ):
                raise ValueError("Invalid training state/action/termination archive")
    logs, identities, prediction_errors = {}, set(), {}
    for run in report["runs"]:
        key = (run["method"], run["seed"], run["anchor"])
        if key in identities:
            raise ValueError("Repeated search")
        identities.add(key)
        rows = list(
            map(
                json.loads,
                local_file(root, run["data_file"], run["data_sha256"])
                .read_text(encoding="utf-8")
                .splitlines(),
            )
        )
        anchor = DesignSpec.model_validate(bundles[run["anchor"]]["anchor"])
        starts = initial(32, run["seed"] + run["anchor"], anchor)
        actual_initial = [
            r["unit"] for r in (rows[::16] if run["method"] in ("sac", "ppo") else rows[:32])
        ]
        if (
            len(rows) != 512
            or digest(starts.tolist()) != run["initial_sha256"]
            or actual_initial != starts.tolist()
        ):
            raise ValueError("Unmatched starts or evaluation count")
        valid = []
        for row in rows:
            if row["status"] == "completed":
                spec = candidate(anchor, row["unit"])
                if (
                    spec.model_dump(mode="json") != row["spec"]
                    or digest(row["spec"]) != row["spec_hash"]
                ):
                    raise ValueError("Candidate differs from decoded parameters")
                value = float(loss(metrics_vector(row["metrics"]), row["payload_g"])[0])
                if value != row["loss"]:
                    raise ValueError("Score differs from measured physics")
                valid.append(row)
            elif row["loss"] != 1e9 or "metrics" in row:
                raise ValueError("Failed analysis contains fabricated metrics")
        if (
            min(valid, key=lambda r: r["loss"], default=None) != run["best"]
            or len(valid) != run["completed"]
        ):
            raise ValueError("Measured best/count mismatch")
        if pareto(rows) != run["front"]:
            raise ValueError("Incorrect Pareto front")
        logs[key] = rows
        y = np.array([metrics_vector(r["metrics"]) for r in valid])
        estimate = predict(
            bundles[run["anchor"]], expanded([r["unit"] for r in valid], anchor), hybrid=False
        )
        prediction_errors[key] = np.abs(estimate - y)
    files = 0
    native = []
    for row in report["results"]:
        folder = root / row["evidence"]["directory"]
        if sha(folder / "manifest.json") != row["evidence"]["manifest_sha256"]:
            raise ValueError("Native evidence changed")
        files += verify_folder(folder)
        method, index = row["label"].rsplit("-", 1)
        expected = min(
            (
                r["best"]
                for r in report["runs"]
                if r["method"] == method and r["anchor"] == int(index) and r["best"]
            ),
            key=lambda r: r["loss"],
        )
        if row["spec"] != expected["spec"]:
            raise ValueError("Native promotion differs from predeclared selection")
        native.append({k: v for k, v in row.items() if k not in {"error", "phase_diagnostics"}})
        native[-1].update(
            payload_g=row["spec"]["design"]["payload_mass_kg"] * 1000,
            pressure_kpa=row["spec"]["design"]["initial_gauge_pressure_pa"] / 1000,
            screening_height_m=expected["metrics"]["scenario_height_m"][0],
            screening_beam_ratio=expected["metrics"]["conservative_beam_ratio"],
        )
        if row["status"] != "completed":
            native[-1]["failure_scope"] = "Native stage failed; consult local worker logs"
    summary, fronts = [], {}
    for method in METHODS:
        runs = [r for r in report["runs"] if r["method"] == method]
        rows = [row for key, entries in logs.items() if key[0] == method for row in entries]
        valid = [r for r in rows if r["status"] == "completed"]
        frontier = pareto(rows)
        feasible = [r for r in valid if r["loss"] <= 0]
        at50 = [
            r
            for r in valid
            if r["payload_g"] >= 50
            and r["metrics"]["static_margin_cal"] >= 1.12
            and r["metrics"]["conservative_beam_ratio"] <= 0.05
        ]
        successful = [
            r
            for r in native
            if r["label"].rsplit("-", 1)[0] == method and r["status"] == "completed"
        ]
        summary.append(
            dict(
                method=method,
                evaluations=len(rows),
                completed=len(valid),
                rejected=len(rows) - len(valid),
                feasible=len(feasible),
                median_best_loss=float(np.median([r["best"]["loss"] for r in runs])),
                best_loss_range=[
                    float(min(r["best"]["loss"] for r in runs)),
                    float(max(r["best"]["loss"] for r in runs)),
                ],
                maximum_payload_at_30m_g=max((r["payload_g"] for r in feasible), default=None),
                maximum_screen_height_at_least_50g_m=max(
                    (r["metrics"]["scenario_height_m"][0] for r in at50), default=None
                ),
                native_completed=len(successful),
                native_best=max(successful, key=lambda r: r["metrics"]["apogee_m"], default=None),
                search_prediction_mae=np.concatenate(
                    [v for k, v in prediction_errors.items() if k[0] == method]
                )
                .mean(0)
                .tolist(),
            )
        )
        fronts[method] = [
            dict(
                payload_g=r["payload_g"],
                pressure_kpa=r["spec"]["design"]["initial_gauge_pressure_pa"] / 1000,
                height_m=r["metrics"]["scenario_height_m"][0],
                static_margin_cal=r["metrics"]["static_margin_cal"],
                beam_ratio=r["metrics"]["conservative_beam_ratio"],
                spec_hash=r["spec_hash"],
            )
            for r in frontier
        ]
    result = dict(
        source_hash=report["source_hash"],
        pressure_range_kpa=report["pressure_range_kpa"],
        dimensions=report["dimensions"],
        report_sha256=sha(root / "report.json"),
        training_report_sha256=sha(training / "report.json"),
        methods=summary,
        paired_nn_wins={
            base: sum(
                next(
                    r["best"]["loss"]
                    for r in report["runs"]
                    if r["method"] == base + "-nn" and r["anchor"] == i and r["seed"] == seed
                )
                < next(
                    r["best"]["loss"]
                    for r in report["runs"]
                    if r["method"] == base and r["anchor"] == i and r["seed"] == seed
                )
                for i in range(3)
                for seed in report["seeds"]
            )
            for base in ("ga", "de")
        },
        fronts=fronts,
        native=native,
        verified_native_files=files,
        evaluations=sum(r["evaluations"] for r in report["runs"]),
        completed=sum(r["completed"] for r in report["runs"]),
        screening_attempts=sum(r["screening_attempts"] for r in report["runs"]),
        training_transitions=sum(r["transitions"] for r in report["training"]),
        elapsed_s=report["elapsed_s"],
        gpu_monitor=report["gpu_monitor"],
        policies=report["training"],
        nn_training=tr,
        objective=report["objective"],
        hyperparameters=report["hyperparameters"],
        seeds=report["seeds"],
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "NN predicts axial screening, not validated flight",
            "Initial static and assumed beam constraints; no new CFD or FEM",
            "Training cost excluded from equal simulator budgets",
            "RL material is fixed per episode; GA/DE can mutate it",
        ],
    )
    write_json(destination, result)
    return result


def plot(result, destination):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    colors = ("#889499", "#546e7a", "#42938a", "#005e64", "#b57b37", "#8c6499")
    for color, (method, rows) in zip(colors, result["fronts"].items(), strict=True):
        if rows:
            axes[0, 0].plot(
                [r["payload_g"] for r in rows],
                [r["height_m"] for r in rows],
                ".-",
                label=method,
                color=color,
            )
    axes[0, 0].axhline(30, color="#b64f45", ls="--")
    axes[0, 0].axvline(50, color="#a1a1a1", ls=":")
    axes[0, 0].set(
        xlabel="Payload (g)",
        ylabel="Axial conservative height (m)",
        title="Measured Pareto fronts: static + beam filter",
    )
    axes[0, 0].legend(fontsize=8)
    for color, row in zip(colors, result["methods"], strict=True):
        for native in result["native"]:
            if (
                native["label"].rsplit("-", 1)[0] == row["method"]
                and native["status"] == "completed"
            ):
                axes[0, 1].scatter(
                    native["payload_g"], native["metrics"]["apogee_m"], color=color, s=35
                )
    axes[0, 1].axhline(30, color="#b64f45", ls="--")
    axes[0, 1].axvline(50, color="#a1a1a1", ls=":")
    axes[0, 1].set(
        xlabel="Payload (g)",
        ylabel="6DOF height (m)",
        title="Fresh CAD / analytic-aero 6DOF; not acceptance",
    )
    x = np.arange(3)
    for j, key in enumerate(("before", "selected")):
        values = [t[key]["mae"][0] for t in result["nn_training"]["tests"]]
        bars = axes[1, 0].bar(
            x + (j - 0.5) * 0.35, values, 0.35, label=key, color=("#a0a9b1", "#187f85")[j]
        )
        axes[1, 0].bar_label(bars, fmt="%.3f", fontsize=8)
    axes[1, 0].set(
        xticks=x,
        xticklabels=["Anchor 0", "Anchor 1", "Anchor 2"],
        ylabel="Height MAE (m)",
        title="Held-out screening prediction error",
    )
    axes[1, 0].legend()
    for i, (color, row) in enumerate(zip(colors, result["methods"], strict=True)):
        axes[1, 1].bar(i, row["median_best_loss"], color=color)
        low, high = row["best_loss_range"]
        middle = row["median_best_loss"]
        axes[1, 1].errorbar(
            i,
            middle,
            yerr=[[middle - low], [high - middle]],
            fmt="none",
            color="#333333",
            capsize=3,
        )
    axes[1, 1].set(
        xticks=np.arange(6),
        xticklabels=list(result["fronts"]),
        ylabel="Median best constraint loss (lower is better)",
        title="9 matched runs per method / 512 evaluations each",
    )
    for ax in axes.flat:
        ax.grid(alpha=0.15)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Pressure and payload as design variables: GPU learning and measured search\n"
        "10–200 g / 50–400 kPa gauge / target 30 m / fixed environment",
        fontsize=13,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("training", "root", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    r = export(a.training, a.root, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(r, a.destination)
    print(
        [(r["method"], r["median_best_loss"], r["maximum_payload_at_30m_g"]) for r in r["methods"]]
    )
