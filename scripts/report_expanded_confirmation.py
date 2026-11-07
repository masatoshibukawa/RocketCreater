"""Compare two source-bound finalists after complete coupled CFD/FEM confirmation."""

import argparse
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import integrated_coefficients, read, serial
from rocketwright.physics.flight_loads import TunnelDatabase
from scripts.report_joint_confirmation import export as export_candidate


def method_folder(root, report, method):
    row = next(r for r in report["results"] if r["method"] == method)
    base = Path(report["resumed_from"]["root"]) if row.get("reused_from") else root
    return base / method


def numerical_details(root, report):
    """Describe the sealed model and load transfer, not inferred physical fidelity."""
    fem_cases, decks = [], {}
    for method in ("fem_coarse", "fem_fine"):
        folder = method_folder(root, report, method)
        data = read(folder / "data.json")
        paths = sorted(folder.glob("*.inp"))
        if len(paths) != len(data["cases"]) or not all(
            "*STEP,NLGEOM" in p.read_text(encoding="utf-8").upper() for p in paths
        ):
            raise ValueError("Missing nonlinear FEM input-deck evidence")
        decks[method] = {p.name: sha(p) for p in paths}
        if method == "fem_fine":
            fem_cases = [
                {
                    k: v
                    for k, v in case.items()
                    if k
                    in (
                        "condition",
                        "mapping",
                        "max_displacement_m",
                        "p95_integration_vm_pa",
                        "max_integration_vm_pa",
                    )
                }
                for case in data["cases"]
            ]
    cases = []
    for method in ("cfd_coarse", "cfd_fine", "cfd_audit"):
        folder = method_folder(root, report, method)
        for path in sorted(folder.rglob("case.json")):
            case = read(path)
            spacing = case["dimensions_mm"]["body_diameter"] / case["d"]
            cases.append(
                dict(
                    method=method,
                    case=path.parent.relative_to(folder).as_posix(),
                    sha256=sha(path),
                    speed_mps=case["speed_mps"],
                    angle_deg=case["angle_deg"],
                    cells_per_diameter=case["d"],
                    spacing_mm=spacing,
                    fin_thickness_cells=case["fin_thickness_mm"] / spacing,
                    wall_scheme=case["wall_scheme"],
                    reynolds=case["Re"],
                    width_d=case["width_D"],
                    seconds=case["seconds"],
                )
            )
    fine = read(method_folder(root, report, "cfd_fine") / "data.json")
    coarse = read(method_folder(root, report, "cfd_coarse") / "data.json")
    assembly = read(method_folder(root, report, "geometry") / "data.json")["record"]["assembly"]
    table = TunnelDatabase(fine["table_folder"])
    args = (table.stations, table.diameter, assembly["loaded_cg_mm"] / 1000)
    before = integrated_coefficients(np.asarray(coarse["coefficients"]), *args)
    after = integrated_coefficients(table.table, *args)
    delta = abs(after - before)
    denominator = np.maximum(np.max(abs(after), axis=(0, 1)), 0.01)
    ratios = np.max(delta, axis=(0, 1)) / denominator
    component = int(np.argmax(ratios))
    i, j = np.unravel_index(np.argmax(delta[:, :, component]), delta.shape[:2])
    if not np.isclose(ratios[component], fine["grid_relative_change"], rtol=1e-12):
        raise ValueError("Grid diagnostic differs from sealed worker metric")
    driver = serial(
        dict(
            component=("Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z")[component],
            speed_mps=table.speeds[i],
            angle_deg=table.angles[j],
            coarse=before[i, j, component],
            fine=after[i, j, component],
            component_scale=denominator[component],
            relative_change=ratios[component],
            scope="Maximum over all tabulated conditions; separate from trajectory propagation",
        )
    )
    return dict(
        fem_geometric_nonlinearity=True,
        fem_input_deck_hashes=decks,
        fine_fem_cases=fem_cases,
        cfd_cases=cases,
        grid_change_driver=driver,
        geometry_resolution_note=(
            "Interpolated walls place specified surfaces between nodes; spacing ratios alone "
            "do not establish near-wall/thin-fin flow resolution or model validity"
        ),
    )


def failed_attempt(root, selected):
    """Include an unsuccessful narrower-domain attempt without counting reused work twice."""
    report = read(root / "report.json")
    runtime = {k: v for k, v in report["runtime"].items() if k != "calculix"}
    final_runtime = dict(selected["runtime"])
    initial_width, final_width = runtime.pop("cfd_width"), final_runtime.pop("cfd_width")
    if (
        report["complete"]
        or not report["source_unchanged"]
        or report["source_hash"] != selected["source_hash"]
        or report["spec"] != selected["spec"]
        or report["precision"] != selected["precision"]
        or runtime != final_runtime
        or initial_width >= final_width
    ):
        raise ValueError("Initial attempt differs beyond corrected domain width")
    files, cases = 0, 0
    for row in report["results"]:
        folder = root / row["method"]
        if sha(folder / "manifest.json") != row["manifest_sha256"]:
            raise ValueError("Initial-attempt manifest changed")
        for name, expected in read(folder / "manifest.json").items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or sha(path) != expected:
                raise ValueError("Initial-attempt artifact changed")
            files += 1
            cases += path.name == "case.json"
    return dict(
        report_sha256=sha(root / "report.json"),
        width_d=initial_width,
        elapsed_s=report["elapsed_s"],
        completed_cfd_cases=cases,
        verified_files=files,
        failed_methods=[r["method"] for r in report["results"] if r["status"] == "failed"],
    )


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
        data["numerical_details"] = numerical_details(folder, raw)
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
            "One-way CFD load transfer to FEM; deformed geometry is not fed back into CFD/flight",
            "Point-mass equipment/payload placement omits volumetric packaging checks",
            "FEM stress is reported without qualified material strength allowables",
            "Local linear stability does not prove full-flight nonlinear stability",
        ],
    )
    write_json(destination, result)
    return result


def plot(result, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, panels = plt.subplots(2, 2, figsize=(13, 11), layout="constrained")
    axes = panels.flat
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
    for i, (row, color) in enumerate(zip(rows, colors, strict=True)):
        values = [
            row["beam"]["metrics"]["fin_deflection_ratio"],
            row["structure"]["metrics"]["fem_deflection_ratio"],
        ]
        axes[2].bar(
            np.arange(2) + (i - 0.5) * 0.35,
            100 * np.asarray(values),
            width=0.35,
            color=color,
            label=row["method"],
        )
    limit = rows[0]["precision"]["deflection_span_limit"] * 100
    axes[2].axhline(limit, color="#ad5045", ls="--", lw=1, label=f"Limit {limit:g}%")
    axes[2].set(
        xticks=[0, 1],
        xticklabels=("Linear beam", "Geometric nonlinear FEM"),
        ylabel="Deflection / span (%)",
        title="Concurrent CFD loads; assumed material and root",
    )
    axes[2].legend(frameon=False)
    names = sorted(set().union(*(r["checks"] for r in rows)))
    table = np.array([[bool(r["checks"][key]) for r in rows] for key in names])
    from matplotlib.colors import ListedColormap

    axes[3].imshow(
        table, aspect="auto", cmap=ListedColormap(["#e6a094", "#83c1af"]), vmin=0, vmax=1
    )
    axes[3].set(
        xticks=[0, 1],
        xticklabels=[r["method"] for r in rows],
        yticks=np.arange(len(names)),
        yticklabels=names,
        title="Unchanged confirmation gates",
    )
    axes[3].tick_params(axis="y", labelsize=8)
    for j in range(len(names)):
        for i in range(2):
            axes[3].text(
                i, j, "pass" if table[j, i] else "fail", ha="center", va="center", fontsize=8
            )
    for ax in axes[:3]:
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
    p.add_argument("--initial-old", type=Path)
    p.add_argument("--initial-new", type=Path)
    a = p.parse_args()
    result = export(a.search, a.old, a.new, a.destination)
    if bool(a.initial_old) != bool(a.initial_new):
        p.error("Include both initial attempts together")
    if a.initial_old:
        attempts = [
            failed_attempt(root, row)
            for root, row in zip((a.initial_old, a.initial_new), result["methods"], strict=True)
        ]
        result["initial_attempts"] = attempts
        result["all_completed_cfd_cases"] = result["total_gpu_cases"] + sum(
            r["completed_cfd_cases"] for r in attempts
        )
        result["summed_execution_s_including_failed_attempts"] = sum(
            r["elapsed_s"] for r in result["methods"] + attempts
        )
        result["execution_cost_scope"] = (
            "Sum of simultaneous candidate executions including failed domain attempts and "
            "resumed-parent time; not wall time or training/diagnostic/development cost"
        )
        write_json(a.destination, result)
    if a.plot_libraries:
        sys.path.append(str(a.plot_libraries.resolve()))
        plot(result, a.destination)
    print(
        {
            r["method"]: dict(height=r["heights_m"]["confirm"], unmet=r["unmet"])
            for r in result["methods"]
        }
    )
