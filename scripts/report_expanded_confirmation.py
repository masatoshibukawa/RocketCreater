"""Compare two source-bound finalists after complete coupled CFD/FEM confirmation."""

import argparse
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.report_joint_confirmation import export as export_candidate


def export(search, old, new, destination):
    source = read(search / "report.json")
    result = dict(
        source_hash=source["source_hash"],
        search_report_sha256=sha(search / "report.json"),
        methods=[],
        physical_qualification=False,
    )
    for method, folder in (("wide-old", old), ("wide-new", new)):
        raw = read(folder / "report.json")
        label = source["detailed_candidates"][method]
        selected = next(r for r in source["results"] if r["label"] == label)
        if raw["source_hash"] != source["source_hash"] or raw["spec"] != selected["spec"]:
            raise ValueError("Detailed result differs from selected candidate/source")
        data = export_candidate(folder, destination.with_name(destination.stem + f"-{method}.json"))
        result["methods"].append(dict(method=method, selected_label=label, **data))
    a, b = result["methods"]
    if a["runtime"] != b["runtime"] or a["precision"] != b["precision"]:
        raise ValueError("Paired confirmation settings differ")
    if a["spec"]["requirement"] != b["spec"]["requirement"]:
        raise ValueError("Paired missions differ")
    result.update(
        confirmation_height_change_m=b["heights_m"]["confirm"] - a["heights_m"]["confirm"],
        total_gpu_cases=sum(r["gpu_cases"] for r in result["methods"]),
        verified_files=sum(r["verified_files"] for r in result["methods"]),
        conditional_acceptance={r["method"]: r["criteria_met"] for r in result["methods"]},
        limitations=[
            "Two selected finalists; not independent estimates of general optimizer performance",
            "Grid/time/parameter sensitivity is not experimental validation",
            "Constitutive and mount scenarios are unmeasured; no hardware qualification",
            "Local linear stability does not prove full-flight nonlinear stability",
        ],
    )
    write_json(destination, result)
    return result


def plot(result, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), layout="constrained")
    rows, colors = result["methods"], ("#9b7653", "#1679ad")
    x = np.arange(3)
    keys = ("screen", "cfd", "confirm")
    for i, (row, color) in enumerate(zip(rows, colors, strict=True)):
        axes[0].bar(
            x + (i - 0.5) * 0.35,
            [row["heights_m"][k] for k in keys],
            width=0.35,
            label=row["method"],
            color=color,
        )
    axes[0].axhline(30, color="#ad5045", ls="--", lw=1)
    axes[0].set(
        xticks=x,
        xticklabels=("Analytic 6DOF", "CFD 6DOF", "Confirmation"),
        ylabel="Apogee (m)",
        title="Same 60 g mission / 400 kPa setting",
    )
    axes[0].legend(frameon=False)
    for i, (row, color) in enumerate(zip(rows, colors, strict=True)):
        values = [
            row["aero"]["grid_relative_change"],
            row["aero"]["averaging_relative_change"],
            row["aero"]["audit_differences"]["interpolation"],
        ]
        axes[1].bar(x + (i - 0.5) * 0.35, 100 * np.asarray(values), width=0.35, color=color)
    axes[1].set(
        xticks=x,
        xticklabels=("Grid", "Averaging", "Interpolation"),
        ylabel="Relative difference (%)",
        title="Numerical sensitivity; not real-flight error",
    )
    names = sorted(set().union(*(r["checks"] for r in rows)))
    table = np.array([[bool(r["checks"][key]) for r in rows] for key in names])
    from matplotlib.colors import ListedColormap

    axes[2].imshow(
        table, aspect="auto", cmap=ListedColormap(["#e6a094", "#83c1af"]), vmin=0, vmax=1
    )
    axes[2].set(
        xticks=[0, 1],
        xticklabels=[r["method"] for r in rows],
        yticks=np.arange(len(names)),
        yticklabels=names,
        title="Unchanged confirmation gates",
    )
    axes[2].tick_params(axis="y", labelsize=7)
    for j in range(len(names)):
        for i in range(2):
            axes[2].text(
                i, j, "pass" if table[j, i] else "fail", ha="center", va="center", fontsize=6
            )
    for ax in axes[:2]:
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
        ax.spines[["right", "top"]].set_visible(False)
    fig.suptitle(
        "Expanded-surrogate finalists: coupled CFD, structure and flight\n"
        "Simulation evidence; physical qualification remains unknown",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("search", "old", "new", "destination"):
        p.add_argument(field, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    result = export(a.search, a.old, a.new, a.destination)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print(
        {
            r["method"]: dict(height=r["heights_m"]["confirm"], unmet=r["unmet"])
            for r in result["methods"]
        }
    )
