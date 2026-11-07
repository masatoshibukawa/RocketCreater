"""Audit a matched GA/DE pilot; no general optimizer or flight-accuracy claim."""

import argparse
import sys
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read
from scripts.report_initial_models import verified


def export(ga_root, de_root, destination):
    runs, populations, input_hashes, pools = [], [], [], []
    for root in (ga_root, de_root):
        report, files = verified(root)
        exploration = read(root / "exploration.json")
        if (
            exploration["source_hash"] != report["source_hash"]
            or len(exploration["results"]) != report["sampled"]
        ):
            raise ValueError("Exploration source or counts differ")
        pool = dict(report["pool"])
        method = pool.pop("evolutionary_optimizer")
        pools.append(pool)
        input_hashes.append(sha(root / "input.json"))
        hashes, optimizers = [], []
        for i in range(3):
            op = read(root / f"optimizer-{i}.json")
            checksum = sha(root / f"population-{i}.json")
            if checksum != op["initial_sha256"] or op["method"] != method:
                raise ValueError("Optimizer initial population changed")
            hashes.append(checksum)
            optimizers.append(op)
        populations.append(hashes)
        completed = [r for r in report["results"] if r["status"] == "completed"]
        p = report["pool"]["unchanged_acceptance"]
        eligible = [
            r
            for r in completed
            if r["temporal_pass"]
            and r["aero_domain_pass"]
            and r["metrics"]["static_margin_cal"] >= p["minimum_static_margin_cal"]
            and r["metrics"]["incidence_deg"] <= p["maximum_incidence_deg"]
        ]
        best = max(eligible, key=lambda r: r["metrics"]["apogee_m"], default=None)
        runs.append(
            dict(
                method=method,
                source_hash=report["source_hash"],
                script_sha256=report["script_sha256"],
                report_sha256=sha(root / "report.json"),
                exploration_sha256=sha(root / "exploration.json"),
                evaluated=report["sampled"],
                rejected=report["failed"],
                optimizer_evaluations=sum(r["evaluations"] for r in optimizers),
                initial_population_hashes=hashes,
                elapsed_s=report["elapsed_s"],
                completed_native=len(completed),
                initial_screen_check_passes=len(eligible),
                target_height_passes=report["screening_feasible"],
                best_initial_screen_height_m=best["metrics"]["apogee_m"] if best else None,
                best_initial_screen=(
                    {k: best[k] for k in ("metrics", "spec", "drag_plus_10pct_height_m")}
                    if best
                    else None
                ),
                evidence_files=files,
                native=[
                    dict(
                        label=r["label"],
                        status=r["status"],
                        metrics=r.get("metrics"),
                        manifest_sha256=r["evidence"]["manifest_sha256"],
                        initial_screen_check_pass=r in eligible,
                    )
                    for r in report["results"]
                ],
            )
        )
    if (
        [r["method"] for r in runs] != ["ga", "de"]
        or input_hashes[0] != input_hashes[1]
        or pools[0] != pools[1]
        or populations[0] != populations[1]
        or any(
            runs[0][k] != runs[1][k]
            for k in ("source_hash", "script_sha256", "optimizer_evaluations", "evaluated")
        )
    ):
        raise ValueError("Comparison does not have matched source, inputs, populations and counts")
    result = dict(
        runs=runs,
        pool=pools[0],
        input_sha256=input_hashes[0],
        matching_initial_populations=True,
        matching_evaluation_counts=True,
        independent_optimizer_seed_replicates=1,
        general_optimizer_superiority_proved=False,
        physical_qualification=False,
        scope="One matched-seed analytic-screen pilot; CFD/FEM and global optimum unproved",
        interrupted_attempts=[
            "ga-pilot1: decoded geometry rejected and batch aborted",
            "de-pilot1: deliberately interrupted before restarting matched code",
        ],
    )
    write_json(destination.with_suffix(".json"), result)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
    for run, color, marker in zip(runs, ("#117d8a", "#b46636"), ("o", "s"), strict=True):
        rows = [r for r in run["native"] if r["status"] == "completed"]
        ax.scatter(
            [r["metrics"]["static_margin_cal"] for r in rows],
            [r["metrics"]["apogee_m"] for r in rows],
            label=run["method"].upper(),
            marker=marker,
            color=color,
            s=65,
            edgecolors="white",
            linewidths=0.7,
        )
    ax.axvline(1, color="#777", ls="--", lw=1)
    ax.axhline(pools[0]["requirement"]["target_altitude_m"], color="#a34a4a", ls="--", lw=1)
    ax.set(
        xlabel="Initial analytic static margin (caliber)",
        ylabel="Simulated apogee (m)",
        title=(
            "Matched GA / DE pilot: six fresh-CAD promotions per method\n"
            "60 g payload; 400 kPa initial setting; original screening criteria"
        ),
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.15)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    fig.savefig(destination.with_suffix(".png"), dpi=180)
    plt.close(fig)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ga", type=Path)
    p.add_argument("de", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libraries", type=Path)
    a = p.parse_args()
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
    r = export(a.ga, a.de, a.destination)
    print([(run["method"], run["best_initial_screen_height_m"]) for run in r["runs"]])
