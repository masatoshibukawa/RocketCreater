"""Audit duration studies and expose all force components without relaxing their gates."""

import argparse
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read


def export(root, destination, *, partial=False):
    if partial:
        report = dict(
            read(root / "protocol.json"),
            results=read(root / "progress.json"),
            source_unchanged=True,
            elapsed_s=None,
        )
        # Audit only completed cases. The active solver's unfinished files are omitted.
        files = [root / "protocol.json", root / "progress.json"]
        for row in report["results"]:
            if row["status"] == "completed":
                files += [p for p in (root / row["label"]).rglob("*") if p.is_file()]
        manifest = {p.relative_to(root).as_posix(): sha(p) for p in files}
    else:
        report = read(root / "report.json")
        manifest = read(root / "manifest.json")
    if report["source_hash"] != code_hash() or not report["source_unchanged"]:
        raise ValueError("Use the experiment's frozen numerical source")
    for name, expected in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path) != expected:
            raise ValueError("Changed native duration artifact")
    for name, expected in report["inputs"].items():
        if sha(Path(name)) != expected:
            raise ValueError("Changed duration input")
    rows, histories = [], {}
    for result in report["results"]:
        row = {k: v for k, v in result.items() if k != "case"}
        if result["status"] == "completed":
            folder = root / result["label"]
            case = read(folder / "case.json")
            if case != result["case"]:
                raise ValueError("Case differs from report")
            history = np.genfromtxt(folder / "history.csv", delimiter=",", names=True)
            names = history.dtype.names[1:]
            selected = history[history["tU_D"] > case["averaging_tU_D"][0]]
            components = {}
            for name in names:
                before, after = np.array_split(selected[name], 2)
                mean = float(selected[name].mean())
                delta = float(after.mean() - before.mean())
                if not np.allclose(
                    [mean, delta],
                    [case["mean"][name], case["split_window_difference"][name]],
                    rtol=1e-10,
                    atol=1e-12,
                ):
                    raise ValueError("CSV means do not reproduce case")
                components[name] = dict(
                    mean=mean,
                    split_difference=delta,
                    relative_difference=abs(delta) / max(abs(mean), 0.05),
                )
            averaging = max(v["relative_difference"] for v in components.values())
            if not np.isclose(averaging, result["averaging"], rtol=1e-12, atol=1e-12):
                raise ValueError("Averaging gate differs")
            row.update(
                components=components,
                worst_component=max(
                    components, key=lambda name: components[name]["relative_difference"]
                ),
                case_sha256=sha(folder / "case.json"),
                history_sha256=sha(folder / "history.csv"),
                simulated_duration_s=(
                    case["averaging_tU_D"][1]
                    * case["dimensions_mm"]["body_diameter"]
                    / 1000
                    / case["speed_mps"]
                ),
            )
            # A centerline-equivalent resultant position at this incidence is NOT
            # the small-disturbance CP obtained from derivatives near zero angle.
            if abs(case["mean"]["Cy"]) > 0.05:
                row["equivalent_normal_force_station_mm"] = (
                    case["cg_mm"]
                    + case["mean"]["Cm_z"]
                    / case["mean"]["Cy"]
                    * case["dimensions_mm"]["body_diameter"]
                )
                row["station_scope"] = (
                    "Centerline-equivalent resultant at fixed incidence; not a CP derivative "
                    "or a static-stability acceptance test"
                )
            histories[result["label"]] = history
        rows.append(row)
    public = dict(
        source_hash=report["source_hash"],
        status="partial; solver still running" if partial else "completed diagnostic",
        manifest_sha256=None if partial else sha(root / "manifest.json"),
        report_sha256=sha(root / ("progress.json" if partial else "report.json")),
        partial_artifact_hashes=manifest if partial else None,
        verified_files=len(manifest),
        precision=report["context"]["precision"],
        scope=report["scope"],
        elapsed_s=report["elapsed_s"],
        acceptance_performed=False,
        physical_qualification=False,
        results=rows,
    )
    write_json(destination.with_suffix(".json"), public)
    from matplotlib.figure import Figure
    from matplotlib.font_manager import fontManager
    from matplotlib.text import Text

    fig = Figure(figsize=(11, 7), dpi=140, layout="constrained", facecolor="#f7fafb")
    axes = fig.subplots(2, 1)
    for row in rows:
        if row["status"] == "completed" and row["angle_deg"] == 10:
            h = histories[row["label"]]
            axes[0].plot(
                h["tU_D"],
                h["Cd"],
                linewidth=0.7,
                alpha=0.75,
                label=f"独立計算 {row['duration_D_U']:g} D/U",
            )
    axes[0].set(
        xlabel="無次元時間 tU/D",
        ylabel="抗力係数 Cd",
        title="迎角10°の抗力履歴：初期過渡を含む全履歴",
    )
    axes[0].legend(fontsize=9)
    completed = [r for r in rows if r["status"] == "completed"]
    xs = np.arange(len(completed))
    for name in ("Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z"):
        ys = [100 * r["components"][name]["relative_difference"] for r in completed]
        axes[1].plot(xs, ys, "o-", linewidth=1, label=name)
    axes[1].axhline(3, color="#a95338", linestyle="--", label="合格基準 3%")
    axes[1].set_xticks(xs, [f"{r['angle_deg']}° / {r['duration_D_U']} D/U" for r in completed])
    axes[1].set(
        yscale="log",
        ylabel="二分区間の平均差 (%)",
        title="検査対象の全6力・モーメント成分（対称性で除外しない）",
    )
    axes[1].legend(ncols=4, fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle("CFDの時間平均診断  |  18 m/s・20 cells/D  |  設計の合否判定前", fontsize=14)
    jp = next((f.name for f in fontManager.ttflist if f.name in {"Meiryo", "Yu Gothic"}), None)
    if jp:
        for item in fig.findobj(Text):
            item.set_fontfamily(jp)
    fig.savefig(destination.with_suffix(".png"), facecolor=fig.get_facecolor())
    print(
        dict(
            verified_files=len(manifest),
            results=[
                {k: r.get(k) for k in ("label", "averaging", "duration_change", "worst_component")}
                for r in rows
            ],
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--partial", action="store_true")
    a = p.parse_args()
    sys.path.append(
        str(
            Path(
                "../../.local/retired-worktrees/bottle-generation/output/cfd-preview-runtime"
            ).resolve()
        )
    )
    export(a.root, a.destination, partial=a.partial)
