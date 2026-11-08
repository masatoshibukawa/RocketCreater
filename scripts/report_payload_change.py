"""Compare sealed 60 g / 50 g results without changing design or precision criteria."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.verify_payload_change import check_payload_only


def compare(folder, destination):
    rows, inputs = [], {}
    for name in ("old", "new"):
        base_file = folder / f"expanded-confirmation-wide-{name}.json"
        case_file = folder / f"payload50-{name}.json"
        before, after = read(base_file), read(case_file)
        check_payload_only(before["spec"], after["spec"])
        if (
            before["source_hash"] != after["source_hash"]
            or before["precision"] != after["precision"]
            or before["runtime"] != after["runtime"]
            or after["parent_report_sha256"] != before["report_sha256"]
            or before["spec"]["design"]["payload_mass_kg"] != 0.06
            or after["spec"]["design"]["payload_mass_kg"] != 0.05
            or after["spec"]["requirement"]["target_altitude_m"] != 30
        ):
            raise ValueError("Not a matched 60 g / 50 g comparison")
        inputs.update({p.name: sha(p) for p in (base_file, case_file)})
        values = []
        for report in (before, after):
            assembly = report["assembly"]
            values.append(
                dict(
                    payload_g=report["spec"]["design"]["payload_mass_kg"] * 1000,
                    height_m=report["heights_m"]["confirm"],
                    coefficient_plus_10pct_height_m=report["heights_m"]["coefficient_plus_10pct"],
                    dry_mass_g=assembly["dry_mass_g"],
                    loaded_cg_mm=assembly["loaded_cg_mm"],
                    wet_cg_mm=assembly["wet_cg_mm"],
                    static_margin_cal=(assembly["cp_mm"] - assembly["wet_cg_mm"])
                    / assembly["dimensions_mm"]["body_diameter"],
                    fem_deflection_ratio=report["structure"]["metrics"]["fem_deflection_ratio"],
                    fem_mesh_change=report["structure"]["metrics"]["fem_mesh_change"],
                    grid_relative_change=report["aero"]["grid_relative_change"],
                    checks=report["checks"],
                    unmet=report["unmet"],
                    criteria_met=report["criteria_met"],
                )
            )
        rows.append(
            dict(
                candidate=name,
                values=values,
                height_gain_m=values[1]["height_m"] - values[0]["height_m"],
                height_shortfall_m=30 - values[1]["height_m"],
            )
        )
    result = dict(
        inputs=inputs,
        candidates=rows,
        payload_g=50,
        target_altitude_m=30,
        same_shape_pressure_environment=True,
        new_cfd_solves=0,
        physical_qualification=False,
        model_validation_complete=False,
    )
    write_json(destination, result)
    return result


def plot(result, destination):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), layout="constrained")
    settings = [
        ("height_m", 1, 30, "Apogee (m)", 34),
        ("static_margin_cal", 1, 1, "Initial static margin (cal)", 1.4),
        ("fem_deflection_ratio", 100, 5, "FEM deflection / span (%)", 16),
    ]
    for ax, (metric, scale, limit, title, upper) in zip(axes, settings, strict=True):
        for i, (payload, color) in enumerate(((60, "#8496a5"), (50, "#167b83"))):
            values = [r["values"][i][metric] * scale for r in result["candidates"]]
            bars = ax.bar(
                np.arange(2) + (i - 0.5) * 0.32,
                values,
                0.32,
                color=color,
                label=f"{payload} g payload",
            )
            ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        ax.axhline(limit, color="#b85040", ls="--", lw=1.2, label=f"Criterion {limit:g}")
        ax.set(
            xticks=[0, 1],
            xticklabels=["Previous search", "Expanded NN search"],
            title=title,
            ylim=(0, upper),
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.spines[["right", "top"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle(
        "50 g / 30 m mission: payload change only\n"
        "Same geometry and 400 kPa setting; conditional simulation results",
        fontsize=13,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = compare(a.folder, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print({r["candidate"]: r["height_gain_m"] for r in result["candidates"]})
