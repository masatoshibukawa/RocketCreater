"""Export portable native learning evidence and two held-out prediction comparisons."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import predictor


def export(source, target):
    report = json.loads(source.read_text(encoding="utf-8"))
    if not all(predictor.sealed(t["row"]) for t in report["trials"]):
        raise ValueError("Learning evidence changed")
    if set(report["training_ids"]) & set(report["evaluation_ids"]):
        raise ValueError("Training/evaluation overlap")
    output = {
        k: report[k]
        for k in (
            "source_hash",
            "training_ids",
            "evaluation_ids",
            "audits",
            "raw_mae_m",
            "corrected_mae_m",
            "cost_mae_s",
            "evidence",
            "reused_training_evidence",
            "elapsed_s",
            "general_efficiency_improvement_proved",
            "physical_qualification",
            "live_llm_calls",
            "scope",
        )
    }
    output["raw_report_sha256"] = sha(source)
    output["trials"] = [
        dict(
            split=t["split"],
            transition_id=t["row"]["transition_id"],
            fill=t["spec"]["design"]["water_fill_frac"],
            root_mm=t["spec"]["geometry"]["fin_root_mm"],
            forecast_delta_m=t["row"]["prediction"]["delta_height_m"],
            actual_delta_m=t["row"]["delta"]["apogee_m"],
            cost_s=t["row"]["cost_s"],
            observation_sha256=t["row"]["learning_evidence"]["sha256"],
        )
        for t in report["trials"]
    ]
    output["limits"] = [
        "Four training transitions and two held-out geometries only; no general efficiency proof",
        "Predicts simulated altitude changes, not actual flight altitude accuracy",
        "Prescribed host experiments; no live Claude request in this collection",
        "An earlier out-of-range evaluation requested 74.8 mm root; retained but excluded",
        "Verified training trials reused unchanged; elapsed time covers evaluation rerun only",
    ]
    write_json(target.with_suffix(".json"), output)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), layout="constrained")
    audits = report["audits"]
    x = np.arange(len(audits))
    width = 0.34
    axes[0].bar(
        x - width / 2,
        [abs(r["raw_error_m"]) for r in audits],
        width,
        label="Physics forecast",
        color="#8596a0",
    )
    axes[0].bar(
        x + width / 2,
        [abs(r["corrected_error_m"]) for r in audits],
        width,
        label="Learned residual",
        color="#177e89",
    )
    axes[0].set(
        ylabel="Absolute error in simulated altitude change (m)", title="Held-out prediction errors"
    )
    axes[1].bar(
        x - width / 2,
        [r["actual_cost_s"] for r in audits],
        width,
        label="Measured",
        color="#8596a0",
    )
    axes[1].bar(
        x + width / 2,
        [r["prediction"]["predicted_cost_s"] for r in audits],
        width,
        label="Predicted",
        color="#177e89",
    )
    axes[1].set(ylabel="Follow-up computation time (s)", title="Held-out computation costs")
    for ax in axes:
        ax.set_xticks(x, ["Root 92 mm", "Root 94 mm"])
        ax.legend(frameon=False)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.18)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "4 native training transitions / 2 held-out geometries\n"
        "LLM weights unchanged / simulated evidence only",
        fontsize=12,
    )
    fig.savefig(target.with_suffix(".png"), dpi=180)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("target", type=Path)
    a = p.parse_args()
    export(a.source, a.target)


if __name__ == "__main__":
    main()
