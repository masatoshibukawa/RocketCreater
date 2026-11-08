"""Dimensioned detail sheets from the adopted CAD and its nominal dimensions."""

from reportlab.graphics.shapes import Circle, Drawing, Rect
from reportlab.lib import colors

from rocketwright.agent.project_drawing import (
    ACCENT,
    INK,
    MUTED,
    PART,
    dimension,
    draw_fin_projection,
    label,
    line,
    mm,
    panel,
    stl_triangles,
)


def detail_sheet(state, title, subtitle, number, total, font):
    d = Drawing(760, 516)
    d.add(Rect(0, 0, 760, 516, fillColor=colors.white, strokeColor=None))
    label(d, 0, 498, title, font, 23)
    label(d, 0, 472, subtitle, font, 12)
    label(
        d,
        760,
        499,
        f"RW / v{state['version']} / {number:02d} / {total:02d}",
        font,
        12,
        ACCENT,
        "end",
    )
    label(d, 760, 472, "単位 mm / 公称寸法", font, 10, MUTED, "end")
    label(d, 0, 23, "試作・仮組み用 / 図中の寸法値を参照 / 現物で嵌合を確認", font, 9, MUTED)
    label(d, 760, 23, f"入力 {state['analysis']['input_sha256'][:12]}", font, 9, MUTED, "end")
    return d


def dimension_table(d, rows, x, top, width, font):
    for i, (name, value) in enumerate(rows):
        y = top - i * 23
        line(d, x, y - 6, x + width, y - 6)
        label(d, x, y, name, font, 10, MUTED)
        label(d, x + width, y, value, font, 10, INK, "end")


def fin_detail(state, g, cad, mesh, total, font):
    fin = cad["fin"]
    d = detail_sheet(
        state, "フィン詳細図", f"F01 / {g.fin_count} 枚 / 採用STLの側面投影", 2, total, font
    )
    panel(d, 0, 139, 500, 303, "A  翼面とスロット位置", font)
    panel(d, 516, 139, 244, 303, "B  翼と取付座の公称寸法", font)
    triangles = stl_triangles(mesh)
    radial, _, axial = zip(*(point for face in triangles for point in face), strict=True)
    low = min(radial)
    scale = min(384 / max(axial), 155 / (max(radial) - low))
    fit_radius = g.body_diameter_mm / 2 + g.radial_clearance_mm + fin["saddle_wall"]

    def x_at(z):
        return 51 + z * scale

    def y_at(r):
        return 222 + (r - low) * scale

    draw_fin_projection(d, triangles, x_at, y_at)
    root = fin["root_chord"]
    tip_start = fin["tip_trailing_offset"]
    tip_y = y_at(fit_radius + fin["span"])
    dimension(
        d,
        x_at(tip_start),
        x_at(tip_start + fin["tip_chord"]),
        397,
        tip_y,
        f"翼端 {mm(fin['tip_chord'])}",
        font,
    )
    dimension(d, x_at(0), x_at(root), 176, 219, f"翼根 {mm(root)}", font)
    label(d, 51, 151, "部品基準 0 = 翼後端（ノズル側）", font, 9, MUTED)
    for i, center in enumerate(fin["slot_centers"], 1):
        x = x_at(center)
        r = fit_radius + fin.get("slot_root_offset", 1.8) + fin["slot_width"] / 2
        line(d, x, y_at(r), x, 204, MUTED, [2, 2])
        label(d, x, 193, f"S{i}", font, 9, INK, "middle")
    dimension_table(
        d,
        (
            ("翼根長", mm(root)),
            ("翼端長", mm(fin["tip_chord"])),
            ("径方向の張出し", mm(fin["span"])),
            ("先端側の後退", mm(g.fin_sweep_mm)),
            ("翼の板厚", mm(fin["thickness"])),
            ("取付座の幅", mm(fin["saddle_width"])),
            ("取付座の壁厚", mm(fin["saddle_wall"])),
            ("ノズル端から翼後端", mm(g.fin_tail_inset_mm)),
            ("配置", f"{mm(360 / g.fin_count)}° 等配"),
        ),
        531,
        389,
        214,
        font,
    )
    panel(d, 0, 44, 760, 81, "C  固定材スロット", font)
    centers = "   /   ".join(f"S{i}  {mm(z)}" for i, z in enumerate(fin["slot_centers"], 1))
    label(d, 15, 82, f"中心の軸方向位置（翼後端から）   {centers}", font, 10)
    size = f"軸方向 {mm(fin['slot_height'])} × 径方向 {mm(fin['slot_width'])}"
    offset = mm(fin.get("slot_root_offset", 1.8))
    label(d, 15, 61, f"開口 {size}   /   径方向の内側端は翼根から {offset}", font, 10)
    return d


def axial_section(triangles):
    """Intersect the mesh with Y=0. Each segment is (axial Z, signed radial X)."""
    segments = set()
    for triangle in triangles:
        hits = set()
        for a, b in zip(triangle, (*triangle[1:], triangle[0]), strict=True):
            ya = 0 if abs(a[1]) < 1e-6 else a[1]
            yb = 0 if abs(b[1]) < 1e-6 else b[1]
            if ya == 0:
                hits.add((round(a[2], 5), round(a[0], 5)))
            if ya * yb < 0:
                fraction = ya / (ya - yb)
                z = a[2] + fraction * (b[2] - a[2])
                x = a[0] + fraction * (b[0] - a[0])
                hits.add((round(z, 5), round(x, 5)))
        if len(hits) == 2:
            segments.add(tuple(sorted(hits)))
    return sorted(segments)


def diameter_marker(d, x, part_x, cy, radius, name, font):
    for direction in (-1, 1):
        y = cy + direction * radius
        line(d, part_x, y, x, y)
        line(d, x - 3, y - 2, x + 3, y + 2, ACCENT)
    line(d, x, cy - radius, x, cy + radius, ACCENT)
    label(d, x, cy + radius + 7, name, font, 9, ACCENT, "middle")


def nose_detail(state, g, cad, mesh, number, total, font):
    d = detail_sheet(state, "ノーズ詳細図", "N01 / 1 個 / 採用STLの軸心断面", number, total, font)
    panel(d, 0, 139, 500, 303, "A-A  中央断面・左がボトル側", font)
    panel(d, 516, 139, 244, 303, "B  嵌合と開口の公称寸法", font)
    segments = axial_section(stl_triangles(mesh))
    if not segments:
        raise ValueError("The adopted nose mesh does not intersect its axis plane")
    points = [point for segment in segments for point in segment]
    height = max(z for z, _ in points)
    max_radius = max(abs(r) for _, r in points)
    scale = min(342 / height, 100 / max_radius)
    x, cy = 87, 288
    tip = x + height * scale
    line(d, x - 22, cy, tip + 31, cy, MUTED, [4, 3])
    for (z0, r0), (z1, r1) in segments:
        line(d, x + z0 * scale, cy + r0 * scale, x + z1 * scale, cy + r1 * scale, INK)
    inner = g.body_diameter_mm / 2 + g.radial_clearance_mm
    nose = cad["nose"]
    opening = nose["tip_opening_diameter"]
    diameter_marker(d, 56, x + nose["entry_chamfer"] * scale, cy, inner * scale, "D1", font)
    if opening:
        diameter_marker(d, tip + 22, tip, cy, opening * scale / 2, "D2", font)
    dimension(d, x, tip, 158, 185, f"軸方向全長 {mm(g.nose_length_mm)}", font)
    label(d, 480, 400, "実線はCAD断面 / 破線は軸心", font, 9, MUTED, "end")
    fit_depth = max(
        (
            z
            for segment in segments
            if all(abs(abs(r) - inner) < 0.005 for _, r in segment)
            for z, _ in segment
        ),
        default=None,
    )
    dimension_table(
        d,
        (
            ("D1 嵌合部内径", mm(2 * inner)),
            ("ボトル胴径", mm(g.body_diameter_mm)),
            ("片側の嵌合余裕", mm(g.radial_clearance_mm)),
            ("D2 先端開口", mm(opening)),
            ("円筒部の外径", mm(2 * (inner + g.nose_wall_mm))),
            ("円筒部の肉厚", mm(g.nose_wall_mm)),
            ("入口の面取り", mm(nose["entry_chamfer"])),
            ("円筒嵌合の深さ", "未計測" if fit_depth is None else mm(fit_depth)),
            ("組立時の基部位置", mm(g.nose_base_mm)),
        ),
        531,
        389,
        214,
        font,
    )
    label(d, 531, 186, "基部位置は機体のノズル端から測る", font, 9, MUTED)
    label(d, 531, 163, "軟質キャップは現物に合わせて選定", font, 9, MUTED)
    ring = cad["fit_ring"]
    panel(d, 0, 44, 760, 81, "C  J01 試着リング・公称寸法", font)
    outer = inner + ring["wall"]
    d.add(Circle(37, 72, 18, fillColor=PART, strokeColor=INK, strokeWidth=0.6))
    d.add(
        Circle(37, 72, 18 * inner / outer, fillColor=colors.white, strokeColor=INK, strokeWidth=0.6)
    )
    label(
        d,
        72,
        80,
        f"内径 {mm(2 * inner)}   /   外径 {mm(2 * outer)}   /   高さ {mm(ring['height'])}",
        font,
        10,
    )
    label(d, 72, 61, "実物のボトルで入り具合とがたつきを確認し、ノーズの仮合わせへ進む。", font, 9)
    return d
