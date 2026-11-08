"""Plot saved CFD data in its actual rotated computational frame."""

import argparse
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read


def render(folder, destination):
    from matplotlib.figure import Figure
    from matplotlib.font_manager import fontManager
    from matplotlib.text import Text
    from skimage.measure import marching_cubes

    from scenarios.cfd.flow_preview import body_faces, wake_view

    case = read(folder / "case.json")
    volume, plane = np.load(folder / "volume.npz"), np.load(folder / "slice.npz")
    history = np.loadtxt(folder / "history.csv", delimiter=",", skiprows=1)
    dims, d = case["dimensions_mm"], case["d"]
    diameter, stride = dims["body_diameter"], int(volume["stride"])
    dx, field = diameter / d, volume["ux_U"].copy()
    nx, ny, nz = case["grid"]
    offset = np.array(
        [(0.5 - case["upstream_D"] * d) * dx, (0.5 - ny / 2) * dx, (0.5 - nz / 2) * dx]
    )
    x = np.arange(field.shape[2]) * stride * dx + offset[0]
    keep = (x >= -diameter / 2) & (x <= dims["overall"] + 4 * diameter)
    fluid = np.ascontiguousarray(~volume["solid"][:, :, keep])
    field = np.ascontiguousarray(field[:, :, keep])
    field[~fluid] = 1
    groups = body_faces(dims, case["shape"], case["cant_deg"])
    # Solver maps domain -> body about loaded CG. Invert it for the mesh overlay.
    if case["rotated_geometry"]:
        c, s = np.cos(np.deg2rad(case["angle_deg"])), np.sin(np.deg2rad(case["angle_deg"]))
        rotation = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        center = np.array([case["cg_mm"], 0, 0])
        groups = [
            ((triangles - center) @ rotation.T + center, color, alpha)
            for triangles, color, alpha in groups
        ]
    vertices, faces, _, _ = marching_cubes(field, 0.8, mask=fluid, allow_degenerate=False)
    origin = offset.copy()
    origin[0] = x[keep][0]
    xyz = vertices[:, ::-1] * stride * dx + origin
    groups.append((xyz[faces], "#459eb0", 0.32))
    fig = Figure(figsize=(11, 7.2), dpi=140, layout="constrained", facecolor="#f7fafb")
    grid = fig.add_gridspec(2, 2, height_ratios=[1.3, 1])
    ax = fig.add_subplot(grid[0, :])
    wake_view(ax, groups)
    ax.set_xlim(-0.6 * diameter, dims["overall"] + 4 * diameter)
    ax.set_ylim(-3.1 * diameter, 2.5 * diameter)
    ax.set_title("瞬時の三次元後流：青は流れ方向速度が主流の80%になる面", loc="left", fontsize=11)
    fig.suptitle(
        f"設計途中のCFD  |  {case['speed_mps']:g} m/s・迎角{case['angle_deg']:g}°"
        f"  |  {d} cells/D・{case['averaging_tU_D'][-1]:g} D/U",
        fontsize=14,
    )
    ax = fig.add_subplot(grid[1, 0])
    solid = plane["solid"]
    im = ax.imshow(
        np.ma.array(plane["ux_U"], mask=solid),
        origin="lower",
        cmap="viridis",
        extent=[offset[0] - dx / 2, offset[0] + (nx - 0.5) * dx, -ny * dx / 2, ny * dx / 2],
        vmin=-0.25,
        vmax=1.25,
    )
    ax.set_facecolor("#465967")
    ax.set(
        xlim=(-0.5 * diameter, dims["overall"] + 4 * diameter),
        ylim=(-2.5 * diameter, 2.5 * diameter),
        xlabel="計算領域の x (mm)",
        ylabel="y (mm)",
        title="中心断面の流れ方向速度",
    )
    fig.colorbar(im, ax=ax, shrink=0.7, label="u / U")
    ax = fig.add_subplot(grid[1, 1])
    ax.plot(history[:, 0], history[:, 1], color="#268093", linewidth=1)
    ax.axvspan(*case["averaging_tU_D"], color="#268093", alpha=0.08, label="平均に使用した区間")
    ax.axhline(case["mean"]["Cd"], color="#b87829", linestyle="--", label="区間平均")
    ax.set(xlabel="無次元時間 tU/D", ylabel="抗力係数 Cd", title="抗力の時間履歴（収束検証中）")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    jp = next((f.name for f in fontManager.ttflist if f.name in {"Meiryo", "Yu Gothic"}), None)
    if jp:
        for item in fig.findobj(Text):
            item.set_fontfamily(jp)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, facecolor=fig.get_facecolor())
    write_json(
        destination.with_suffix(".audit.json"),
        dict(
            inputs={
                name: sha(folder / name)
                for name in ("case.json", "volume.npz", "slice.npz", "history.csv")
            },
            script_sha256=sha(Path(__file__)),
            image_sha256=sha(destination),
            computational_frame=True,
            acceptance_performed=False,
            scope="Instantaneous speed isosurface and recorded drag; not experimental validation",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--plot-libs", type=Path)
    a = p.parse_args()
    if a.plot_libs:
        sys.path.append(str(a.plot_libs.resolve()))
    render(a.folder, a.destination)
