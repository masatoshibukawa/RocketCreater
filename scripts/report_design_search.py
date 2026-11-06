"""Verify native search evidence and export a portable report and comparison figure."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json


def verified_files(root):
    count, manifests = 0, 0
    for path in (root / "projects").rglob("manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for name, expected in manifest.items():
            child = (path.parent / name).resolve()
            if (
                not child.is_relative_to(path.parent.resolve())
                or not child.is_file()
                or child.is_symlink()
                or sha(child) != expected
            ):
                raise ValueError(f"Invalid evidence: {path.parent.name}/{name}")
            count += 1
        manifests += 1
    return dict(manifests=manifests, referenced_files=count)


def runtime_view(runtime):
    return {k: v for k, v in runtime.items() if k != "calculix"}


def summary(root):
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    evidence = verified_files(root)
    learning, decisions, retrievals, failures, available_history = [], [], 0, [], 0
    for campaign in report["campaigns"]:
        state = json.loads(
            (root / "projects" / campaign["project_id"] / "state.json").read_text(encoding="utf-8")
        )
        a = state["adaptive"]
        learning.extend(a.get("observations", []))
        for row in a["decisions"]:
            choices = row.get("selection_context", {}).get("choices", {})
            selected = choices.get(row.get("action"), {})
            retrievals += int(selected.get("experience", {}).get("samples", 0) > 0)
            available_history += int(
                any(v.get("experience", {}).get("samples", 0) > 0 for v in choices.values())
            )
            decisions.append(
                dict(
                    start=campaign["label"],
                    version=row.get("version"),
                    action=row.get("action"),
                    planner=row.get("planner"),
                    model=row.get("model"),
                    reason=row.get("reason"),
                    retrieved_samples=selected.get("experience", {}).get("samples", 0),
                )
            )
        failures.extend(
            dict(start=campaign["label"], action=r["action"], status=r["execution_status"])
            for r in a["history"]
            if r["execution_status"] != "completed"
        )
    measured = [r for r in learning if r.get("status") == "measured"]
    # Public fields contain no absolute workstation paths; hashes identify the native evidence.
    observations = [
        dict(
            start=r["start"],
            version=r["version"],
            metrics=r["metrics"],
            spec=r["spec"],
            code=r["code"],
            evidence_sha256=r["evidence"]["sha256"],
        )
        for r in report["observations"]
    ]
    final = report.get("final")
    confirmation = final.get("confirmation") if final else None
    final_summary = None
    if final:
        state = json.loads(
            (root / "projects" / final["project_id"] / "state.json").read_text(encoding="utf-8")
        )
        completed = {}
        for key, result in state["adaptive"]["results"].items():
            if result["execution_status"] != "completed":
                continue
            artifact = Path(result["value"]["artifact"])
            inputs = json.loads((artifact.parent / "input.json").read_text(encoding="utf-8"))
            completed[key] = dict(
                data_sha256=result["value"]["sha256"],
                runtime=runtime_view(inputs["runtime"]),
                metrics=result["value"].get("metrics", {}),
            )
            if key == "confirm":
                data = json.loads(artifact.read_text(encoding="utf-8"))
                completed[key].update(
                    checks=data["checks"],
                    unmet=data["unmet"],
                    apogee_m=data["flight"]["apogee_m"],
                    static_margin_cal=data["static_margin_cal"],
                )
        final_summary = dict(
            status=final["status"],
            project_id=final["project_id"],
            accepted_spec_hash=final.get("accepted_spec_hash"),
            unresolved_precision=final["unresolved_precision"],
            checks=(confirmation or {}).get("checks"),
            unmet=(confirmation or {}).get("unmet"),
            apogee_m=(confirmation or {}).get("flight", {}).get("apogee_m"),
            static_margin_cal=(confirmation or {}).get("static_margin_cal"),
            latest_requested_runtime=runtime_view(state["adaptive"]["runtime"]),
            last_completed_artifacts=completed,
            artifact_scope=(
                "Completed artifacts may be superseded by requested settings; "
                "only current confirmation can pass"
            ),
            completed_gpu_case_files=len(
                list((root / "projects" / final["project_id"]).rglob("case.json"))
            ),
        )
    return dict(
        source_hash=report["source_hash"],
        requirement_hash=report["requirement_hash"],
        precision=report["precision"],
        limits=report["limits"],
        campaigns=report["campaigns"],
        selected=dict(
            start=report["selected"]["start"],
            version=report["selected"]["version"],
            spec=report["selected"]["spec"],
            metrics=report["selected"]["metrics"],
        ),
        observations=observations,
        final=final_summary,
        evidence=evidence,
        decisions=decisions,
        local_model_selections=sum(r["planner"] == "local_llm" for r in decisions),
        forced_dependency_steps=sum(r["planner"] == "forced_dependency" for r in decisions),
        execution_failures=failures,
        elapsed_s=report["elapsed_s"],
        learning=dict(
            measured_transitions=len(measured),
            height_improvements=sum(r["delta"]["apogee_m"] > 0 for r in measured),
            height_regressions=sum(r["delta"]["apogee_m"] < 0 for r in measured),
            selections_with_retrieved_outcomes=retrievals,
            decisions_offered_verified_history=available_history,
            transitions=[
                dict(
                    signature=r["signature"],
                    before=r["before"],
                    after=r["after"],
                    delta=r["delta"],
                    cost_s=r["cost_s"],
                    evidence_sha256=r["evidence"]["sha256"],
                )
                for r in measured
            ],
            automatic_weight_training=False,
            general_efficiency_improvement_proved=False,
        ),
        physical_qualification=False,
        limitations=[
            "screening ranking is provisional, not proof of an optimum",
            "current-airframe CFD and printed strength lack experimental validation",
            "reference comparison does not validate every design in this search",
        ],
    )


def figure(report, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    labels = list(dict.fromkeys(r["start"] for r in report["observations"]))
    for label in labels:
        rows = sorted(
            (r for r in report["observations"] if r["start"] == label), key=lambda r: r["version"]
        )
        short = {"provided": "Input", "independent-light": "Light geometry"}.get(label)
        if short is None:
            short = "D01" if "/D01/" in label else "D02" if "/D02/" in label else "Generated ops"
        axes[0].plot(
            [r["version"] for r in rows],
            [r["metrics"]["apogee_m"] for r in rows],
            "o-",
            label=short,
        )
        axes[1].scatter(
            [r["metrics"]["dry_mass_g"] for r in rows],
            [r["metrics"]["static_margin_cal"] for r in rows],
            label=short,
        )
    target = report["selected"]["spec"]["requirement"]["target_altitude_m"]
    axes[0].axhline(target, color="#a44738", ls="--", label=f"{target:g} m requirement")
    axes[0].set(
        xlabel="Design revision",
        ylabel="Screening altitude (m)",
        title="Actual CAD + analytic-aero 6DOF",
    )
    axes[1].axhline(report["precision"]["minimum_static_margin_cal"], color="#a44738", ls="--")
    axes[1].set(
        xlabel="Dry mass (g)",
        ylabel="Wet liftoff static margin (calibers)",
        title="Mass and restoring-margin tradeoff",
    )
    for ax in axes:
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Multi-start adaptive search — provisional screening, not hardware qualification")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summary(args.root)
    write_json(args.output.with_suffix(".json"), result)
    figure(result, args.output.with_suffix(".png"))
    print(
        json.dumps(
            dict(evidence=result["evidence"], learning=result["learning"], final=result["final"])
        )
    )


if __name__ == "__main__":
    main()
