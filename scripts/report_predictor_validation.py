"""Audit a presplit native benchmark and export portable, held-out prediction metrics."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import predictor
from rocketwright.analysis.worker import read


def export(source, destination, live=None):
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
    if live:
        from scripts.report_design_search import verified_files

        run = read(live / "report.json")
        if run["source_hash"] != r["source_hash"] or run["planner"] != "local_llm":
            raise ValueError("Live run uses different source or provider")
        state = read(live / "stage5/projects" / run["stage5"]["project_id"] / "state.json")
        adaptive = state["adaptive"]
        decisions = []
        for d in adaptive["decisions"]:
            chosen = d.get("selection_context", {}).get("choices", {}).get(d["action"], {})
            fit = chosen.get("learned_prediction", {})
            if fit.get("status") == "fitted":
                shown = d.get("prompt_view", {}).get("choices", {}).get(d["action"], {})
                decisions.append(
                    dict(
                        action=d["action"],
                        planner=d["planner"],
                        model=d.get("model"),
                        predictor=shown.get("predictor"),
                        cited_cases=shown.get("retrieved_cases"),
                        model_hash=fit["model_hash"],
                    )
                )
        result["live_integration"] = dict(
            source_hash=run["source_hash"],
            status=adaptive["status"],
            selected_learned_candidates=decisions,
            native_choice_count=sum(d["planner"] == "local_llm" for d in adaptive["decisions"]),
            observations=[
                dict(version=v["version"], metrics=v["metrics"])
                for v in adaptive["design_observations"]
            ],
            accepted_spec_hash=adaptive["accepted_spec_hash"],
            evidence=verified_files(live / "stage5"),
            live_report_sha256=sha(live / "report.json"),
        )
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
    p.add_argument("--live", type=Path)
    a = p.parse_args()
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
    export(a.source, a.destination, a.live)
