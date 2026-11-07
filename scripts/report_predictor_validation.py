"""Audit a presplit native benchmark and export portable, held-out prediction metrics."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import predictor
from rocketwright.analysis.worker import read


def export(source, destination):
    r = read(source)
    if set(r["training_ids"]) & set(r["evaluation_ids"]):
        raise ValueError("Training/evaluation transition overlap")
    if not all(predictor.sealed(t["row"]) for t in r["trials"]):
        raise ValueError("Changed raw learning evidence")
    training = {t["spec"]["geometry"]["fin_root_mm"] for t in r["trials"] if t["split"] == "train"}
    evaluating = {
        t["spec"]["geometry"]["fin_root_mm"] for t in r["trials"] if t["split"] == "evaluate"
    }
    if training & evaluating:
        raise ValueError("Held-out initial root lengths entered training")
    for audit in r["audits"]:
        if not set(audit["prediction"]["model"]["training_ids"]) <= set(r["training_ids"]):
            raise ValueError("A model used non-training outcomes")
    result = {
        k: r[k]
        for k in (
            "source_hash",
            "training_ids",
            "evaluation_ids",
            "audits",
            "raw_mae_m",
            "corrected_mae_m",
            "legacy_ridge_mae_m",
            "mean_mae_m",
            "cost_mae_s",
            "elapsed_s",
            "protocol_hash",
            "general_efficiency_improvement_proved",
            "physical_qualification",
            "live_llm_calls",
            "scope",
        )
    }
    result.update(
        raw_report_sha256=sha(source),
        training_root_lengths_mm=sorted(training),
        evaluation_root_lengths_mm=sorted(evaluating),
    )
    result["trials"] = [
        dict(
            split=t["split"],
            transition_id=t["row"]["transition_id"],
            fill=t["spec"]["design"]["water_fill_frac"],
            root_mm=t["spec"]["geometry"]["fin_root_mm"],
            forecast_delta_m=t["row"]["prediction"]["delta_height_m"],
            actual_delta_m=t["row"]["delta"]["apogee_m"],
            observation_sha256=t["row"]["learning_evidence"]["sha256"],
        )
        for t in r["trials"]
    ]
    write_json(destination.with_suffix(".json"), result)
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    names = ["Raw physics", "Mean correction", "Fixed ridge", "Validated selection"]
    values = [r[k] for k in ("raw_mae_m", "mean_mae_m", "legacy_ridge_mae_m", "corrected_mae_m")]
    axes[0].barh(names, values, color=["#8596a0", "#d9a441", "#7693b4", "#177e89"])
    axes[0].set(xlabel="Held-out mean absolute error (m)", title="Simulated altitude CHANGE")
    for i, value in enumerate(values):
        axes[0].text(value, i, f"  {value:.5f}", va="center", fontsize=9)
    axes[0].set_xlim(0, max(values) * 1.4)
    audits = r["audits"]
    x = np.arange(len(audits))
    for key, label in [
        ("raw_error_m", "Raw"),
        ("legacy_ridge_error_m", "Fixed ridge"),
        ("corrected_error_m", "Validated selection"),
    ]:
        axes[1].plot(x, [a[key] for a in audits], "o-", label=label)
    axes[1].axhline(0, color="#aaa", lw=1)
    axes[1].set(
        xlabel="Predeclared held-out case",
        ylabel="Signed residual error (m)",
        title="All six held-out conditions",
    )
    axes[1].legend(frameon=False)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "8 native training transitions / 6 held-out conditions\n"
        "Root-length redesign only; no real-flight validation",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=180)
    plt.close(fig)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
    export(a.source, a.destination)
