"""Audit and compare the 400 kPa / 40 g / 20 m mission against saved 50 g results."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.preview_coarse_flight import verify_folder
from scripts.reevaluate_fixed_mission import MISSION, mission_spec, violation
from scripts.verify_payload_change import check_payload_only


def values(report):
    a = report["assembly"]
    return dict(
        payload_g=report["spec"]["design"]["payload_mass_kg"] * 1000,
        target_m=report["spec"]["requirement"]["target_altitude_m"],
        height_m=report["heights_m"]["confirm"],
        sensitivity_height_m=report["heights_m"]["coefficient_plus_10pct"],
        static_margin_cal=(a["cp_mm"] - a["wet_cg_mm"]) / a["dimensions_mm"]["body_diameter"],
        deflection_ratio=report["structure"]["metrics"]["fem_deflection_ratio"],
        fem_mesh_change=report["structure"]["metrics"]["fem_mesh_change"],
        grid_relative_change=report["aero"]["grid_relative_change"],
        grid_altitude_difference_m=report["aero"]["grid_altitude_difference_m"],
        dry_mass_g=a["dry_mass_g"],
        checks=report["checks"], unmet=report["unmet"], criteria_met=report["criteria_met"],
    )


def export(folder, pool_root, destination):
    inputs, candidates = {}, []
    for name in ("old", "new"):
        paths = [folder / f"payload{mass}-{name}.json" for mass in (50, 40)]
        before, after = (read(p) for p in paths)
        ancestor = read(folder / f"expanded-confirmation-wide-{name}.json")
        check_payload_only(before["spec"], after["spec"])
        if (
            after["spec"] != mission_spec(before["spec"]).model_dump(mode="json")
            or before["source_hash"] != after["source_hash"]
            or after["source_hash"] != code_hash()
            or before["precision"] != after["precision"]
            or before["runtime"] != after["runtime"]
            or after["parent_report_sha256"] != ancestor["report_sha256"]
            or after["gpu_cases"] != 0 or after["cfd_cases_reused"] != 34
        ):
            raise ValueError("Mission or unchanged-geometry CFD comparison mismatch")
        inputs.update({p.name: sha(p) for p in paths})
        candidates.append(dict(candidate=name, values=[values(before), values(after)]))
    pool = read(pool_root / "report.json")
    if (
        not pool["source_unchanged"]
        or pool["source_hash"] != code_hash()
        or pool["mission"] != MISSION
    ):
        raise ValueError("Pool mission/source changed")
    for name, expected in pool["script_hashes"].items():
        if sha(Path(__file__).with_name(name)) != expected:
            raise ValueError("Pool recipe changed")
    parent_files = 0
    for name, expected in pool["inputs"].items():
        parent = pool_root.parent / name
        if sha(parent / "report.json") != expected:
            raise ValueError("Pool input changed")
        for case in read(parent / "report.json")["results"]:
            path = (parent / case["evidence"]["directory"]).resolve()
            if (
                not path.is_relative_to(parent.resolve())
                or sha(path / "manifest.json") != case["evidence"]["manifest_sha256"]
            ):
                raise ValueError("Pool parent manifest changed")
            parent_files += verify_folder(path)
    for row in pool["rows"]:
        if (
            row["spec"] != mission_spec(row["spec"]).model_dump(mode="json")
            or violation(row["metrics"]) != row["violation"]
        ):
            raise ValueError("Incorrect mission/constraint score")
    expected_selection = [
        min(
            (r for r in pool["rows"] if r["anchor"] == anchor),
            key=lambda r: (r["violation"], -r["metrics"]["scenario_height_m"][0]),
        )["label"]
        for anchor in range(3)
    ]
    if expected_selection != pool["selected"]:
        raise ValueError("Native selection differs from declared ranking")
    native, native_files = [], 0
    for case in pool["native"]:
        path = pool_root / case["evidence"]["directory"]
        if sha(path / "manifest.json") != case["evidence"]["manifest_sha256"]:
            raise ValueError("Native comparison changed")
        native_files += verify_folder(path)
        expected = next(r for r in pool["rows"] if r["label"] == case["label"])
        if case["spec"] != expected["spec"]:
            raise ValueError("Native mission differs from selected input")
        native.append({k: v for k, v in case.items() if k not in ("error", "phase_diagnostics")})
    result = dict(
        mission=MISSION, source_hash=code_hash(), inputs=inputs, candidates=candidates,
        pool_report_sha256=sha(pool_root / "report.json"),
        pool=dict(
            rows=pool["rows"], excluded=pool["excluded"], aliases=pool["aliases"],
            selected=pool["selected"], native=native, elapsed_s=pool["elapsed_s"],
            verified_parent_files=parent_files, verified_native_files=native_files,
            feasible_screen_count=sum(r["violation"] == 0 for r in pool["rows"]),
        ),
        redesign=False, new_cfd_solves=0, physical_qualification=False,
        limitations=[
            "Two unchanged-shape finalists use reused CFD and recomputed nonlinear FEM",
            "Three pool finalists use analytic aerodynamics; no new CFD/FEM for their shapes",
            "No physical qualification, material allowables or full-flight stability proof",
        ],
    )
    write_json(destination, result)
    return result


def plot(result, destination):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), layout="constrained")
    settings = (
        ("height_m", 1, 20, "CFD-based apogee (m)", 26),
        ("static_margin_cal", 1, 1, "Initial static margin (cal)", 1.3),
        ("deflection_ratio", 100, 5, "Nonlinear FEM deflection / span (%)", 16),
    )
    for ax, (metric, scale, limit, title, upper) in zip(axes, settings, strict=True):
        for i, (payload, color) in enumerate(((50, "#8b9ca8"), (40, "#177f85"))):
            bars = ax.bar(
                np.arange(2) + (i - 0.5) * 0.34,
                [r["values"][i][metric] * scale for r in result["candidates"]],
                0.34, color=color, label=f"{payload} g",
            )
            ax.bar_label(bars, fmt="%.3f" if metric == "static_margin_cal" else "%.2f", padding=3)
        ax.axhline(limit, color="#b64e43", ls="--", label=f"Current criterion: {limit:g}")
        ax.set(xticks=[0, 1], xticklabels=["Previous search", "Expanded NN search"],
               title=title, ylim=(0, upper))
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("400 kPa / 40 g / target 20 m\nSame geometry; conditional simulation results")
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("folder", "pool_root", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.folder, a.pool_root, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print({r["candidate"]: r["values"][1]["height_m"] for r in result["candidates"]})
