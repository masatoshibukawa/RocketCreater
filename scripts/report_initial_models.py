"""Verify native initial-model evidence and publish a compact comparison and figure."""

import argparse
import json
import sys
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import sha, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verified(root):
    report = read(root / "report.json")
    if not report["source_unchanged"]:
        raise ValueError("Changed source cannot be reported as a verified comparison")
    files = 0
    for row in report["results"]:
        folder = (root / row["evidence"]["directory"]).resolve()
        if not folder.is_relative_to(root.resolve()):
            raise ValueError("Evidence path leaves the run")
        manifest = folder / "manifest.json"
        if sha(manifest) != row["evidence"]["manifest_sha256"]:
            raise ValueError("Changed case manifest")
        for name, expected in read(manifest).items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder) or sha(path) != expected:
                raise ValueError("Changed case artifact: " + name)
            files += 1
        raw = read(folder / "result.json")
        if any(raw[k] != row[k] for k in raw):
            raise ValueError("Summary differs from sealed case result")
    return report, files


def compare(parallel, serial):
    keys = ("source_hash", "requirement", "precision", "controlled_fields", "budget_s")
    if any(parallel[k] != serial[k] for k in keys):
        raise ValueError("Serial and parallel runs have different inputs or numerical source")
    first = {r["label"]: r for r in parallel["results"]}
    second = {r["label"]: r for r in serial["results"]}
    if first.keys() != second.keys() or any(first[k]["spec"] != second[k]["spec"] for k in first):
        raise ValueError("Serial and parallel candidates differ")
    diffs = {}
    completed = True
    for key, row in first.items():
        other = second[key]
        if row["status"] != "completed" or other["status"] != "completed":
            completed = False
            continue
        for name, value in row["metrics"].items():
            diffs[name] = max(diffs.get(name, 0), abs(value - other["metrics"][name]))
    equivalent = completed and all(v <= 1e-8 for v in diffs.values())
    return dict(
        all_completed=completed,
        max_absolute_metric_differences=diffs,
        equivalence_tolerance=1e-8,
        numerically_equivalent=equivalent,
        same_ranking=parallel["ranked_ids"] == serial["ranked_ids"],
        wall_time_ratio_serial_over_parallel=(serial["elapsed_s"] / parallel["elapsed_s"])
        if equivalent
        else None,
        scope="One sequential comparison on the same PC; cache/order/background activity "
        "are uncontrolled. Not an accuracy gain or a general speed guarantee.",
    )


def publish(parallel_root, destination, serial_root=None):
    p, files = verified(parallel_root)
    s, serial_files = verified(serial_root) if serial_root else (None, 0)
    keys = (
        "source_hash",
        "workers",
        "elapsed_s",
        "charged_case_s",
        "budget_s",
        "aliases",
        "requirement",
        "precision",
        "ranked_ids",
        "selected",
        "selected_cfd_compatible",
    )
    result = {k: p[k] for k in keys}
    result.update(
        candidate_count=p["candidate_count"],
        common_operation={k: p["results"][0]["spec"]["design"][k] for k in p["controlled_fields"]},
        catalog_hash=digest(p["registered_sources"]),
        verified_files=files + serial_files,
        raw_reports=dict(
            parallel=sha(parallel_root / "report.json"),
            serial=sha(serial_root / "report.json") if serial_root else None,
        ),
        comparison=compare(p, s) if s else None,
        serial_elapsed_s=s["elapsed_s"] if s else None,
        physical_qualification=False,
        acceptance_performed=False,
        results=[{k: v for k, v in r.items() if k != "spec"} for r in p["results"]],
    )
    write_json(destination, result)
    return result


def plot(report, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in report["results"] if r["status"] == "completed"]
    fig = plt.figure(figsize=(13, 9), layout="constrained", facecolor="#f8fafb")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.2, 1])
    ax, bars, table_ax = (
        fig.add_subplot(gs[0, 0]),
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, :]),
    )
    names = [r["label"].replace("reference/", "") for r in rows]
    colors = ["#167789" if r["detailed_cfd_available"] else "#b66c31" for r in rows]
    target = report["requirement"]["target_altitude_m"]
    margin = report["precision"]["minimum_static_margin_cal"]
    for i, (r, color) in enumerate(zip(rows, colors, strict=True), 1):
        m = r["metrics"]
        ax.scatter(m["static_margin_cal"], m["apogee_m"], color=color, s=90, zorder=3)
        ax.annotate(
            str(i),
            (m["static_margin_cal"], m["apogee_m"]),
            xytext=(7, 6),
            textcoords="offset points",
            fontsize=10,
        )
    ax.axvline(margin, color="#697780", linestyle="--", linewidth=1)
    ax.axhline(target, color="#697780", linestyle="--", linewidth=1)
    ax.set(
        xlabel="Initial wet static margin [calibers]",
        ylabel="Screened apogee [m]",
        title="Altitude and stability must improve together",
    )
    ax.set_xlim(
        min(-0.2, min(r["metrics"]["static_margin_cal"] for r in rows) - 0.2),
        max(margin + 0.3, max(r["metrics"]["static_margin_cal"] for r in rows) + 0.2),
    )
    ax.grid(alpha=0.18)
    bars.barh(
        [f"{i + 1}. {n}" for i, n in enumerate(names)],
        [r["metrics"]["dry_mass_g"] for r in rows],
        color=colors,
    )
    bars.invert_yaxis()
    bars.set(xlabel="Recomputed dry mass [g]", title="Fresh CAD for each adapted airframe")
    bars.grid(axis="x", alpha=0.18)
    table_ax.axis("off")
    values = []
    for i, (r, n) in enumerate(zip(rows, names, strict=True), 1):
        m = r["metrics"]
        values.append(
            [
                f"{i}. {n}",
                f"{m['apogee_m']:.2f}",
                f"{m['static_margin_cal']:.3f}",
                f"{m['incidence_deg']:.2f}",
                f"{r['time_step_difference_m']:.3g}",
                "yes" if r["aero_domain_pass"] else "NO",
                "4 fins" if r["detailed_cfd_available"] else "adapter needed",
            ]
        )
    t = table_ax.table(
        cellText=values,
        colLabels=[
            "Adapted start",
            "Height [m]",
            "Margin [cal]",
            "Incidence [deg]",
            "dt change [m]",
            "Aero domain",
            "CFD adapter",
        ],
        colWidths=[0.25, 0.11, 0.12, 0.13, 0.13, 0.11, 0.15],
        loc="center",
    )
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    t.scale(1, 1.9)
    for (r, _c), cell in t.get_celld().items():
        cell.set_edgecolor("#dce3e8")
        cell.set_facecolor("#e6eef2" if r == 0 else "white")
    fig.suptitle(f"{len(rows)} initial airframes | provisional simulation comparison", fontsize=18)
    fig.supxlabel(
        f"{report['common_operation']['initial_gauge_pressure_pa'] / 1000:g} kPa gauge / "
        f"{report['common_operation']['payload_mass_kg'] * 1000:g} g payload / "
        f"target {target:g} m and {margin:g} caliber. "
        "Small-angle model; no CFD/FEM or physical qualification.",
        fontsize=10,
    )
    fig.savefig(destination, dpi=155)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parallel", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--serial", type=Path)
    p.add_argument("--plot-libs", type=Path)
    args = p.parse_args()
    if args.plot_libs:
        sys.path.append(str(args.plot_libs.resolve()))
    result = publish(args.parallel, args.output, args.serial)
    plot(result, args.output.with_suffix(".png"))
    print(json.dumps({k: result[k] for k in ("candidate_count", "verified_files", "comparison")}))


if __name__ == "__main__":
    main()
