"""Render a case's observed flow and publish its progress page atomically."""

import json
from html import escape
from pathlib import Path
from urllib.parse import quote

import matplotlib
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.font_manager import fontManager
from matplotlib.text import Text
from skimage.measure import marching_cubes

matplotlib.use("Agg")


def body_faces(g, shape, cant):
    """Triangles in mm, with the same axial and fin conventions as the solver."""
    diameter = g["body_diameter"]
    azimuth = np.linspace(0, 2 * np.pi, 49)
    if shape == "empty":
        return []
    if shape == "sphere":
        t = np.linspace(0, np.pi, 25)
        stations, radii = diameter * (1 - np.cos(t)) / 2, diameter * np.sin(t) / 2
    else:
        t = np.linspace(0, 1, 18)
        tail = np.linspace(g["nose_length"], g["overall"], 49)[1:]
        stations = np.r_[t * g["nose_length"], tail]
        nose = np.sqrt(t * (2 - t)) if shape == "rounded_flat" else t
        radii = np.r_[nose, np.ones(tail.size)] * diameter / 2
    rings = np.stack(
        np.broadcast_arrays(
            stations[:, None], radii[:, None] * np.cos(azimuth), radii[:, None] * np.sin(azimuth)
        ),
        axis=-1,
    )
    strips = np.stack([rings[:-1, :-1], rings[1:, :-1], rings[1:, 1:], rings[:-1, 1:]], axis=2)
    strips = strips.reshape(-1, 4, 3)
    shell = np.concatenate((strips[:, [0, 1, 2]], strips[:, [0, 2, 3]]))
    groups = [(shell, "#465967", 1.0)]
    if shape == "sphere":
        return groups
    root = g["overall"] - g["fin_tail_inset"] - g["fin_root"]
    x = root + np.array([0, g["fin_sweep"], g["fin_sweep"] + g["fin_tip"], g["fin_root"]])
    r = diameter / 2 + np.array([0, g["fin_span"], g["fin_span"], 0])
    lateral = np.tan(np.deg2rad(cant)) * (x - root - g["fin_root"] / 2)
    fins = []
    for a in np.arange(4) * np.pi / 2:
        face = np.stack(
            [x, r * np.cos(a) - lateral * np.sin(a), r * np.sin(a) + lateral * np.cos(a)], axis=-1
        )
        fins.extend((face[[0, 1, 2]], face[[0, 2, 3]]))
    return groups + [(np.array(fins), "#cd832f", 1.0)]


def wake_view(ax, groups):
    # Fixed orthographic camera; depth-sort the body and translucent fluid together.
    az, el = np.deg2rad([15, 15])
    camera = np.array(
        [
            [np.cos(az), -np.sin(az), 0],
            [np.sin(az) * np.sin(el), np.cos(az) * np.sin(el), np.cos(el)],
            [np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), -np.sin(el)],
        ]
    )
    projected, colors = [], []
    for triangles, color, alpha in groups:
        projected.append(triangles @ camera.T)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
        shade = 0.74 + 0.26 * np.abs(normals @ np.array([0.25, -0.55, 0.79]))
        colors.append(np.column_stack([shade[:, None] * to_rgb(color), np.full(len(shade), alpha)]))
    if projected:
        faces = np.concatenate(projected)
        order = np.argsort(faces[:, :, 2].mean(axis=1))[::-1]
        ax.add_collection(
            PolyCollection(
                faces[order, :, :2],
                facecolors=np.concatenate(colors)[order],
                edgecolors="none",
                rasterized=True,
            )
        )
    ax.set_aspect("equal")
    ax.set_axis_off()


def finished_grids(root):
    """Only the five matched axial cases in study.py belong on the refinement curve."""
    points = []
    for cells in (10, 16, 24, 32, 40):
        record = root / f"rocket{cells}" / "case.json"
        if record.is_file():
            case = json.loads(record.read_text(encoding="utf-8"))
            points.append((cells, float(case["mean"]["Cd"])))
    if not points:
        return ""
    high = max(value for _, value in points) * 1.15 or 1
    xy = [(42 + 10 * (n - 10), 90 - 66 * v / high) for n, v in points]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    case_links = " ・ ".join(
        f'<a href="rocket{n}/progress.html">{n}分割</a>'
        for n, _ in points
        if (root / f"rocket{n}" / "progress.html").is_file()
    )
    labels = "".join(
        f'<circle cx="{x}" cy="{y:.1f}" r="3" fill="#19778a"/>'
        f'<text x="{x}" y="{y - 9:.1f}">{v:.3f}</text>'
        f'<text x="{x}" y="108">{n}</text>'
        for (n, v), (x, y) in zip(points, xy, strict=True)
    )
    return (
        "<figure><figcaption>格子を細かくしたときの平均抗力係数（完了ケース）</figcaption>"
        '<svg viewBox="0 0 386 135" width="100%" style="max-width:580px" '
        'role="img" aria-label="完了した正面風ケースの格子比較">'
        '<g font-size="11" text-anchor="middle" fill="#173744">'
        '<path d="M42 22 V90 H344" fill="none" stroke="#b8c8ce"/>'
        f'<polyline points="{line}" fill="none" stroke="#19778a" stroke-width="2"/>'
        f'{labels}<text x="193" y="128">胴径あたりの格子数</text></g></svg>'
        f"<figcaption>{case_links}</figcaption></figure>"
    )


class FlowPreview:
    def __init__(
        self,
        directory,
        dims,
        shape,
        angle,
        cant,
        speed,
        reynolds,
        cells,
        upstream,
        study_position=None,
    ):
        self.directory = directory
        self.dims, self.shape, self.angle = dims, shape, angle
        self.cant, self.speed, self.reynolds = cant, speed, reynolds
        self.cells, self.upstream = cells, upstream
        self.frames = []
        self.study_position = study_position
        names = {f.name for f in fontManager.ttflist}
        self.jp_font = next(
            (f for f in ("Meiryo", "Yu Gothic", "Noto Sans CJK JP", "Hiragino Sans") if f in names),
            None,
        )
        self.template = Path(__file__).with_name("progress.html").read_text(encoding="utf-8")
        self.body = body_faces(dims, shape, cant)
        self.page("計算中")

    def page(self, status):
        self._write_page(self.directory, "", status, "", status == "計算中")
        if self.study_position:
            i, n = self.study_position
            self._write_page(
                self.directory.parent,
                quote(self.directory.name, safe="") + "/",
                status,
                f"ケース {i} / {n} · ",
                status == "計算中" or (i < n and status == "計算完了"),
            )

    def _write_page(self, destination, prefix, status, position, live):
        buttons = "".join(
            f'<a href="{prefix}frame-{p:03d}.png" data-percent="{p}">{p}%</a>' for p in self.frames
        )
        image = (
            f'<a id="full" href="{prefix}frame-{self.frames[-1]:03d}.png"><img id="frame" '
            f'src="{prefix}frame-{self.frames[-1]:03d}.png" '
            'alt="後流の三次元表示・速度断面・抗力履歴"></a>'
            if self.frames
            else '<p class="waiting">最初の速度場を計算しています。</p>'
        )
        values = {
            "CASE": escape(self.directory.name),
            "STATUS": position + status,
            "IMAGE": image,
            "PERCENT": str(self.frames[-1] if self.frames else 0),
            "BUTTONS": buttons,
            "GRIDS": finished_grids(destination) if position else "",
            "LIVE": "true" if live else "false",
        }
        html = self.template
        for k, v in values.items():
            html = html.replace("{{" + k + "}}", v)
        tmp = destination / "progress.tmp"
        tmp.write_text(html, encoding="utf-8")
        tmp.replace(destination / "progress.html")

    def snapshot(self, percent, velocity, inside, stride, section, section_solid, times, cd):
        diameter = self.dims["body_diameter"]
        dx = diameter / self.cells
        center = section.shape[0] / 2
        length = diameter if self.shape in ("sphere", "empty") else self.dims["overall"]
        x = ((np.arange(velocity.shape[2]) * stride + 0.5) - self.upstream * self.cells) * dx
        keep = (x >= -diameter * 0.5) & (x <= length + 4 * diameter)
        field = np.ascontiguousarray(velocity[:, :, keep], dtype="f")
        fluid = np.ascontiguousarray(~inside[:, :, keep])
        field[~fluid] = 1
        groups = list(self.body)
        if field.min() < 0.8 < field.max():
            verts, faces, _, _ = marching_cubes(field, 0.8, mask=fluid, allow_degenerate=False)
            xyz = verts[:, ::-1] * stride * dx + [
                x[keep][0],
                (0.5 - center) * dx,
                (0.5 - center) * dx,
            ]
            groups.append((xyz[faces], "#459eb0", 0.34))
        fig = Figure(figsize=(10.4, 6.8), dpi=125, layout="constrained", facecolor="#f7fafb")
        grid = fig.add_gridspec(2, 2, height_ratios=[1.32, 1])
        ax = fig.add_subplot(grid[0, :])
        wake_view(ax, groups)
        ax.set_xlim(-diameter * 0.7, length + 4.2 * diameter)
        ax.set_ylim(-2.45 * diameter, 2.45 * diameter)
        jp = self.jp_font
        ax.set_title(
            "三次元後流　／　青は流れ方向の速度が主流の80%になる面"
            if jp
            else "3D wake    /    axial velocity = 0.80 U",
            loc="left",
            fontsize=11,
        )
        label = f"Re = {self.reynolds:,.0f}"
        if self.shape != "sphere":
            label = f"{self.speed:g} m/s   ·   {label}"
        fig.suptitle(
            f"{percent}%    |    {label}    |    {self.cells} cells/D    |    α = {self.angle:g}°",
            fontsize=13,
            color="#203d4d",
        )
        ax = fig.add_subplot(grid[1, 0])
        field2 = np.ma.array(section, mask=section_solid)
        cmap = matplotlib.colormaps["viridis"].with_extremes(bad="#394752")
        im = ax.imshow(
            field2,
            origin="lower",
            cmap=cmap,
            vmin=-0.25,
            vmax=1.25,
            extent=(
                -self.upstream * diameter,
                section.shape[1] * dx - self.upstream * diameter,
                -center * dx,
                center * dx,
            ),
            interpolation="nearest",
            aspect="equal",
        )
        ax.set_xlim(-0.5 * diameter, length + 4 * diameter)
        ax.set_ylim(-2.2 * diameter, 2.2 * diameter)
        ax.set(
            title="機体中心付近の速度断面" if jp else "Center section   /   axial speed",
            xlabel="先端からの距離 (mm)" if jp else "Axial position (mm)",
            ylabel="y (mm)",
        )
        fig.colorbar(im, ax=ax, shrink=0.72, label="u / U")
        ax = fig.add_subplot(grid[1, 1])
        ax.plot(times, cd, color="#268093", linewidth=1.3)
        ax.grid(alpha=0.18)
        ax.set(
            title="この時点までの抗力履歴" if jp else "Drag history",
            xlabel="無次元時間 (tU/D)" if jp else "Elapsed flow time (tU/D)",
            ylabel="抗力係数" if jp else "Drag coefficient",
        )
        if jp:
            for text_item in fig.findobj(Text):
                text_item.set_fontfamily(jp)
        fig.savefig(self.directory / f"frame-{percent:03d}.png", facecolor=fig.get_facecolor())
        self.frames.append(percent)
        self.page("計算完了" if percent == 100 else "計算中")
        print(
            f"CFD {percent}%: {(self.directory / f'frame-{percent:03d}.png').resolve()}", flush=True
        )
