"""Publish verified native promotions, keeping exploration and acceptance distinct."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from scripts.report_initial_models import verified


def export(roots, destination):
    batches = []
    for root in roots:
        report, files = verified(root)
        rows = [
            dict(
                label=r["label"],
                status=r["status"],
                metrics=r.get("metrics"),
                phase=r.get("phase_diagnostics"),
                temporal_pass=r.get("temporal_pass"),
                aero_domain_pass=r.get("aero_domain_pass"),
                drag_plus_10pct_height_m=r.get("drag_plus_10pct_height_m"),
                manifest_sha256=r["evidence"]["manifest_sha256"],
            )
            for r in report["results"]
        ]
        batches.append(
            dict(
                run=root.name,
                source_hash=report["source_hash"],
                report_sha256=sha(root / "report.json"),
                native_verified_files=files,
                sampled=report.get("sampled"),
                results=rows,
                acceptance_performed=False,
                physical_qualification=False,
            )
        )
    result = dict(
        batches=batches,
        mission=dict(payload_g=60, altitude_m=30, initial_gauge_kpa=400),
        scope="Analytic-aero screening; phase diagnostics are not an alternate acceptance",
        original_initial_static_margin_cal=1,
        mass_placement_note="joint1–3 lump all other mass; fixed2–3 separate a nominal 48g shell",
    )
    write_json(destination.with_suffix(".json"), result)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True, layout="constrained")
    colors = ["#9aabb7", "#ce9c35", "#197f8b", "#b47aa4", "#1c3e5a"]
    for batch, color in zip(batches, colors, strict=True):
        rows = [r for r in batch["results"] if r["status"] == "completed"]
        axes[0].scatter(
            [r["metrics"]["static_margin_cal"] for r in rows],
            [r["metrics"]["apogee_m"] for r in rows],
            label=batch["run"],
            color=color,
            s=45,
            edgecolor="white",
            linewidth=0.5,
        )
        phase = [r for r in rows if r["phase"]]
        if phase:
            axes[1].scatter(
                [r["phase"]["free_ascent_min_margin_cal"] for r in phase],
                [r["metrics"]["apogee_m"] for r in phase],
                label=batch["run"],
                color=color,
                s=45,
                edgecolor="white",
                linewidth=0.5,
            )
    for ax in axes:
        ax.axhline(30, color="#aa5555", linestyle="--", lw=1)
        ax.axvline(1, color="#aa5555", linestyle="--", lw=1)
        ax.set(ylabel="Simulated apogee (m)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.15)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=8)
    axes[0].set(
        xlabel="Initial analytic static margin (caliber)", title="Original acceptance diagnostic"
    )
    axes[1].set(
        xlabel="Minimum guided-release ascent margin (caliber)",
        title="Additional phase diagnostic; guide capacity unverified",
    )
    fig.suptitle(
        "60 g payload / fixed 400 kPa initial setting\n"
        "Fresh CAD + 6DOF screening; CFD/FEM confirmation separate",
        fontsize=12,
    )
    fig.savefig(destination.with_suffix(".png"), dpi=180)
    plt.close(fig)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("roots", nargs="+", type=Path)
    p.add_argument("--destination", required=True, type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
    export(a.roots, a.destination)
