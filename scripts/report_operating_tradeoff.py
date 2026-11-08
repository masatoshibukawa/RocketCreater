"""Audit case/CAD evidence, summarize coupled effects and plot the measured grid."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.tradeoff import check_geometry
from scripts.report_initial_models import verified


def summarize(report):
    complete = [r for r in report["results"] if r["status"] == "completed"]
    base_payload = report["baseline_requirement"]["payload_mass_kg"] * 1000
    groups = {}
    for row in complete:
        c = row["condition"]
        groups.setdefault(c["seed"], []).append(row)
    summaries = {}
    for seed, rows in groups.items():
        mission = [r for r in rows if r["condition"]["payload_g"] == base_payload]
        at_max_pressure = [
            r
            for r in mission
            if r["condition"]["pressure_kpa"] == max(report["study"]["pressures_kpa"])
        ]
        summaries[seed] = dict(
            completed=len(rows),
            mission_cases=len(mission),
            mission_screening_passes=sum(r["screening_pass"] for r in mission),
            mission_max_height_m=max(r["metrics"]["apogee_m"] for r in mission)
            if mission
            else None,
            mission_high_pressure_temperature_swing_m=(
                max(r["metrics"]["apogee_m"] for r in at_max_pressure)
                - min(r["metrics"]["apogee_m"] for r in at_max_pressure)
            )
            if at_max_pressure
            else None,
            max_gauge_kpa=max(r["metrics"]["peak_gauge_kpa"] for r in rows),
            static_margin_range_cal=[
                min(r["metrics"]["static_margin_cal"] for r in rows),
                max(r["metrics"]["static_margin_cal"] for r in rows),
            ],
        )
    # Finite differences over the declared grid, not derivatives or error bounds.
    lookup = {
        tuple(r["condition"][k] for k in ("seed", "temperature_c", "payload_g", "pressure_kpa")): r
        for r in complete
        if r["phase"] == "initial"
    }
    interaction = {}
    t0, t1 = min(report["study"]["temperatures_c"]), max(report["study"]["temperatures_c"])
    m0, m1 = min(report["study"]["payloads_g"]), max(report["study"]["payloads_g"])
    p0, p1 = min(report["study"]["pressures_kpa"]), max(report["study"]["pressures_kpa"])
    tm = sorted(report["study"]["temperatures_c"])[len(report["study"]["temperatures_c"]) // 2]
    for seed in report["study"]["seeds"]:

        def h(t, m, p, seed=seed):
            return lookup[(seed, t, m, p)]["metrics"]["apogee_m"]

        try:
            interaction[seed] = dict(
                reference_temperature_c=tm,
                pressure_gain_at_mission_mass_m=h(tm, base_payload, p1) - h(tm, base_payload, p0),
                light_minus_heavy_at_high_pressure_m=h(tm, m0, p1) - h(tm, m1, p1),
                pressure_payload_interaction_m=(h(tm, m1, p1) - h(tm, m1, p0))
                - (h(tm, m0, p1) - h(tm, m0, p0)),
                pressure_temperature_interaction_m=(
                    h(t1, base_payload, p1) - h(t0, base_payload, p1)
                )
                - (h(t1, base_payload, p0) - h(t0, base_payload, p0)),
            )
        except KeyError:
            interaction[seed] = dict(status="missing_grid_cells")
    return dict(
        completed=len(complete),
        failed=len(report["results"]) - len(complete),
        screening_passes=sum(r["screening_pass"] for r in complete),
        original_mission_screening_passes=sum(
            r["screening_pass"] for r in complete if r["condition"]["payload_g"] == base_payload
        ),
        altitude_only_passes=sum(r["checks"]["altitude"] for r in complete),
        failed_checks=dict(Counter(k for r in complete for k, v in r["checks"].items() if not v)),
        maximum_time_step_difference_m=max(
            (r["metrics"]["time_step_difference_m"] for r in complete), default=None
        ),
        by_seed=summaries,
        finite_grid_effects=interaction,
    )


def stability_details(flight, assembly):
    """Separate rail-constrained and free ascent, retaining the original gate."""
    cp = assembly["cp_mm"] / 1000
    diameter = assembly["dimensions_mm"]["body_diameter"] / 1000
    pairs = list(zip(flight["trace"]["time_s"], flight["trace"]["cg_m"], strict=True))
    ascent = [(t, (cp - cg) / diameter) for t, cg in pairs if t <= flight["apogee_s"]]
    exit_time = flight["rail_exit_s"]
    free = [margin for t, margin in ascent if exit_time is not None and t >= exit_time]
    return dict(
        initial_including_gas_cal=(cp - pairs[0][1]) / diameter,
        minimum_ascent_including_gas_cal=min(margin for _, margin in ascent),
        minimum_free_ascent_including_gas_cal=min(free) if free else None,
        rail_exit_s=exit_time,
        existing_initial_check_changed=False,
        scope="Constant analytic CP and recorded time-varying CG; "
        "sampled margin, not a dynamic stability proof",
    ), dict(time_s=[t for t, _ in ascent], margin_cal=[m for _, m in ascent])


def publish(root, destination, independent=None):
    report, files = verified(root)
    geometries = {}
    for seed, e in report["geometry"].items():
        path = Path(e["artifact"])
        context = json.loads((path.parent / "input.json").read_text(encoding="utf-8"))
        check_geometry(e, context["spec"]["geometry"], report["source_hash"])
        files += len(json.loads((path.parent / "manifest.json").read_text(encoding="utf-8")))
        geometries[seed] = dict(
            artifact_sha256=e["sha256"], manifest_sha256=e["manifest_sha256"], key=e["key"]
        )
    proof = None
    if independent:
        proof = json.loads(independent.read_text(encoding="utf-8"))
        if proof["source_hash"] != report["source_hash"] or not proof["equivalent"]:
            raise ValueError("Independent replay did not verify the same source")
        project = Path(__file__).resolve().parents[1]
        replay_results = []
        for key in ("fresh_cad_case", "cached_cad_case"):
            folder = (project / proof[key]).resolve()
            if not folder.is_relative_to(project):
                raise ValueError("Replay path leaves the project")
            manifest = folder / "manifest.json"
            if sha(manifest) != proof["manifest_sha256"][key]:
                raise ValueError("Independent replay manifest changed")
            for name, expected in json.loads(manifest.read_text(encoding="utf-8")).items():
                path = (folder / name).resolve()
                if not path.is_relative_to(folder) or sha(path) != expected:
                    raise ValueError("Independent replay artifact changed")
                files += 1
            replay_results.append(json.loads((folder / "result.json").read_text(encoding="utf-8")))
        actual = {
            k: abs(replay_results[0]["metrics"][k] - replay_results[1]["metrics"][k])
            for k in proof["differences"]
        }
        if actual != proof["differences"] or any(v > 1e-8 for v in actual.values()):
            raise ValueError("Independent replay numbers differ")
    supplemental, examples = {}, {}
    temperatures = sorted(report["study"]["temperatures_c"])
    reference_temperature = temperatures[len(temperatures) // 2]
    for row in report["results"]:
        if row["status"] != "completed":
            continue
        folder = root / row["evidence"]["directory"]
        flight = json.loads((folder / "refine/data.json").read_text(encoding="utf-8"))["fine"]
        record = json.loads((folder / "refine/record.json").read_text(encoding="utf-8"))
        supplemental[row["id"]], trace = stability_details(flight, record["assembly"])
        condition = row["condition"]
        if (
            condition["temperature_c"] == reference_temperature
            and condition["payload_g"] == report["baseline_requirement"]["payload_mass_kg"] * 1000
            and condition["pressure_kpa"] == max(report["study"]["pressures_kpa"])
        ):
            examples[row["id"]] = dict(condition=condition, **trace)
    result = {k: v for k, v in report.items() if k != "geometry"}
    result.update(
        summary=summarize(report),
        geometry=geometries,
        verified_files=files,
        raw_report_sha256=sha(root / "report.json"),
        independent_replay=proof,
        supplemental_stability=supplemental,
        stability_examples=examples,
    )
    write_json(destination, result)
    return result


def plot(report, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    initial = [
        r for r in report["results"] if r["phase"] == "initial" and r["status"] == "completed"
    ]
    temperatures, seeds = report["study"]["temperatures_c"], report["study"]["seeds"]
    masses, pressures = report["study"]["payloads_g"], report["study"]["pressures_kpa"]
    names = {
        "provided": "Current design",
        "independent-light": "Light geometry",
        "reference/D40-2l": "2 L adaptation",
    }
    fig, axes = plt.subplots(
        len(temperatures),
        len(seeds),
        figsize=(13, 10),
        squeeze=False,
        layout="constrained",
        facecolor="#f8fafb",
    )
    max_height = max(r["metrics"]["apogee_m"] for r in initial)
    for i, t in enumerate(temperatures):
        for j, seed in enumerate(seeds):
            values = np.full((len(pressures), len(masses)), np.nan)
            rows = {
                (r["condition"]["payload_g"], r["condition"]["pressure_kpa"]): r
                for r in initial
                if r["condition"]["seed"] == seed and r["condition"]["temperature_c"] == t
            }
            ax = axes[i, j]
            for a, p in enumerate(pressures):
                for b, m in enumerate(masses):
                    row = rows.get((m, p))
                    if row:
                        h = row["metrics"]["apogee_m"]
                        values[a, b] = h
                        ax.text(
                            b,
                            a,
                            f"{h:.1f}",
                            ha="center",
                            va="center",
                            fontsize=13,
                            color="white" if h < max_height * 0.6 else "#15262f",
                        )
                        if not row["checks"]["static_margin"]:
                            ax.text(
                                b + 0.29,
                                a - 0.29,
                                "x",
                                ha="center",
                                va="center",
                                fontsize=9,
                                color="#e5ebef",
                            )
            image = ax.imshow(
                values, origin="lower", vmin=0, vmax=max_height, cmap="viridis", aspect="auto"
            )
            ax.set_xticks(range(len(masses)), [f"{m:g}" for m in masses])
            ax.set_yticks(range(len(pressures)), [f"{p:g}" for p in pressures])
            ax.set_title(f"{names.get(seed, seed)} | {t:g} C", fontsize=12)
            if i == len(temperatures) - 1:
                ax.set_xlabel("Payload [g]")
            if j == 0:
                ax.set_ylabel("Initial gauge pressure [kPa]")
    fig.colorbar(image, ax=axes, label="Screened apogee [m]", shrink=0.85)
    fig.suptitle("Temperature x payload x pressure | measured simulation grid", fontsize=18)
    fig.supxlabel(
        "x: initial static margin below 1 caliber. Target: 30 m. "
        "Unmeasured cells are blank; no CFD/FEM or pressure qualification.",
        fontsize=10,
    )
    fig.savefig(output.with_suffix(".png"), dpi=155)
    plt.close(fig)

    fig, (ax, pressure_ax) = plt.subplots(
        1, 2, figsize=(13, 5), layout="constrained", facecolor="#f8fafb"
    )
    tm = sorted(temperatures)[len(temperatures) // 2]
    seed = seeds[-1]
    palette = ["#167789", "#b66c31", "#735896"]
    for m, color in zip(masses, palette, strict=False):
        rows = sorted(
            [
                r
                for r in report["results"]
                if r["status"] == "completed"
                and r["condition"]["seed"] == seed
                and r["condition"]["temperature_c"] == tm
                and r["condition"]["payload_g"] == m
            ],
            key=lambda r: r["condition"]["pressure_kpa"],
        )
        ax.plot(
            [r["condition"]["pressure_kpa"] for r in rows],
            [r["metrics"]["apogee_m"] for r in rows],
            "o--",
            label=f"{m:g} g",
            color=color,
        )
        refined = [r for r in rows if r["phase"] != "initial"]
        if refined:
            ax.scatter(
                [r["condition"]["pressure_kpa"] for r in refined],
                [r["metrics"]["apogee_m"] for r in refined],
                marker="s",
                s=70,
                color=color,
            )
    target = report["baseline_requirement"]["target_altitude_m"]
    ax.axhline(target, color="#697780", linestyle=":", label=f"{target:g} m target")
    ax.set(
        title=f"{names.get(seed, seed)} at {tm:g} C | altitude only",
        xlabel="Initial gauge pressure [kPa]",
        ylabel="Screened apogee [m]",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    mass = report["baseline_requirement"]["payload_mass_kg"] * 1000
    pressure = max(pressures)
    for i, (seed, color) in enumerate(zip(seeds, palette, strict=False)):
        rows = sorted(
            [
                r
                for r in initial
                if r["condition"]["seed"] == seed
                and r["condition"]["payload_g"] == mass
                and r["condition"]["pressure_kpa"] == pressure
            ],
            key=lambda r: r["condition"]["temperature_c"],
        )
        pressure_ax.plot(
            [r["condition"]["temperature_c"] for r in rows],
            [r["metrics"]["peak_gauge_kpa"] for r in rows],
            ["o-", "x--", "s-"][i % 3],
            color=color,
            markerfacecolor="none" if i == 0 else color,
            markersize=9 if i == 0 else 6,
            label=names.get(seed, seed),
        )
    pressure_ax.axhline(pressure, color="#697780", linestyle=":", label="Initial setpoint")
    pressure_ax.set(
        title=f"{mass:g} g / {pressure:g} kPa initial | sealed solar wait",
        xlabel="Ambient temperature [C]",
        ylabel="Peak gauge pressure [kPa]",
    )
    pressure_ax.legend()
    pressure_ax.grid(alpha=0.2)
    fig.supxlabel(
        "Squares: adaptively added pressure samples. Lines guide the eye; "
        "height crossings do not establish stability or a safe pressure limit.",
        fontsize=10,
    )
    fig.savefig(output.with_name(output.stem + "-boundary.png"), dpi=155)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained", facecolor="#f8fafb")
    exits = []
    for (key, example), color in zip(report["stability_examples"].items(), palette, strict=False):
        t, margin = np.array(example["time_s"]), np.array(example["margin_cal"])
        exit_time = report["supplemental_stability"][key]["rail_exit_s"]
        for ax in axes:
            ax.plot(t, margin, color=color, label=names.get(example["condition"]["seed"]))
            if exit_time is not None:
                ax.axvline(exit_time, color=color, linestyle=":", alpha=0.6)
        if exit_time is not None:
            exits.append(exit_time)
    axes[0].set_xlim(0, max(exits, default=0.1) * 2)
    axes[0].set_title("Launch interval | dotted lines: rail exit")
    axes[1].set_title("Ascent through apogee | moving water / gas mass")
    for ax in axes:
        ax.axhline(1, color="#697780", linestyle="--", label="1 caliber reference")
        ax.axhline(0, color="#697780", linewidth=0.5)
        ax.set(xlabel="Time after release [s]", ylabel="(CP - CG) / diameter [calibers]")
        ax.grid(alpha=0.2)
    axes[1].legend(loc="lower right")
    fig.suptitle(f"{tm:g} C / {mass:g} g / {pressure:g} kPa initial | stability by flight phase")
    fig.supxlabel(
        "Fixed analytic CP; sampled time-varying CG includes gas. "
        "This supplements the unchanged initial gate and does not prove dynamic stability.",
        fontsize=10,
    )
    fig.savefig(output.with_name(output.stem + "-stability.png"), dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--independent", type=Path)
    p.add_argument("--plot-libs", type=Path)
    args = p.parse_args()
    if args.plot_libs:
        sys.path.append(str(args.plot_libs.resolve()))
    result = publish(args.root, args.output, args.independent)
    plot(result, args.output)
    print(json.dumps(result["summary"], ensure_ascii=False))
