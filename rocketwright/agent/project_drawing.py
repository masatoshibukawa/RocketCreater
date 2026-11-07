"""Vector views for the adopted build sheet and assembly instructions."""

from math import asin, cos, pi, sin
from struct import iter_unpack, unpack_from

from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors

INK = colors.HexColor("#172c3d")
MUTED = colors.HexColor("#455b6a")
ACCENT = colors.HexColor("#006b63")
RULE = colors.HexColor("#c7d6db")
PAPER = colors.HexColor("#f3f7f8")
BODY = colors.HexColor("#e0eaf0")
PART = colors.HexColor("#a5d4c8")
ACTIVE = colors.HexColor("#46a896")


def mm(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def label(drawing, x, y, text, font, size=10, color=INK, anchor="start"):
    drawing.add(
        String(x, y, text, fontName=font, fontSize=size, fillColor=color, textAnchor=anchor)
    )


def line(drawing, x1, y1, x2, y2, color=RULE, dash=None):
    drawing.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=0.65, strokeDashArray=dash))


def panel(drawing, x, y, width, height, title, font):
    drawing.add(Rect(x, y, width, height, fillColor=PAPER, strokeColor=RULE, strokeWidth=0.65))
    label(drawing, x + 14, y + height - 22, title, font, 12)


def dimension(drawing, left, right, y, datum_y, text, font):
    """Datum extensions and ticks stay legible on small or zero-length dimensions."""
    if right - left < 0.05:
        return
    line(drawing, left, datum_y, left, y - 4)
    line(drawing, right, datum_y, right, y - 4)
    line(drawing, left, y, right, y, ACCENT)
    for x in (left, right):
        line(drawing, x - 2.5, y - 3, x + 2.5, y + 3, ACCENT)
    label(drawing, (left + right) / 2, y + 5, text, font, 8, ACCENT, "middle")


def blade_points(fin, trailing, radial, scale):
    return [
        trailing,
        radial,
        trailing + fin["tip_trailing_offset"] * scale,
        radial + fin["span"] * scale,
        trailing + (fin["tip_trailing_offset"] + fin["tip_chord"]) * scale,
        radial + fin["span"] * scale,
        trailing + fin["root_chord"] * scale,
        radial,
    ]


def side_view(drawing, g, cad, box, *, focus="", gap_mm=0):
    """Nominal axial envelope. Datum at the nozzle, with one representative blade."""
    x, cy, width, half_height = box
    f = cad["fin"]
    fit_radius = g.body_diameter_mm / 2 + g.radial_clearance_mm
    blade_root = fit_radius + f["saddle_wall"]
    nose_radius = fit_radius + g.nose_wall_mm
    extent = max(nose_radius, blade_root + f["span"] if cad["include_fins"] else 0)
    scale = min(width / (g.overall_mm + gap_mm), half_height / extent)
    radius = g.body_diameter_mm * scale / 2
    nose_base = x + g.nose_base_mm * scale
    shoulder = x + min(radius * 0.85, 0.3 * (nose_base - x))
    tail = x + g.fin_tail_inset_mm * scale
    tip = x + (g.overall_mm + gap_mm) * scale
    line(drawing, x - 8, cy, tip + 8, cy, MUTED, [4, 3])
    # The bottle is an envelope with a simplified shoulder at the nozzle end.
    drawing.add(
        Polygon(
            [
                x,
                cy - radius * 0.23,
                shoulder,
                cy - radius,
                nose_base,
                cy - radius,
                nose_base,
                cy + radius,
                shoulder,
                cy + radius,
                x,
                cy + radius * 0.23,
            ],
            fillColor=BODY,
            strokeColor=INK,
            strokeWidth=0.85,
        )
    )
    if cad["include_fins"]:
        y = cy + blade_root * scale
        drawing.add(
            Rect(
                tail,
                cy + radius,
                f["root_chord"] * scale,
                y - cy - radius,
                fillColor=PART,
                strokeColor=INK,
                strokeWidth=0.65,
            )
        )
        drawing.add(
            Polygon(
                blade_points(f, tail, y, scale),
                fillColor=ACTIVE if focus == "fin_mount" else PART,
                strokeColor=INK,
                strokeWidth=0.85,
            )
        )
    nose_x = nose_base + gap_mm * scale
    outer = nose_radius * scale
    skirt = cad["nose"]["skirt_height"] * scale
    drawing.add(
        Polygon(
            [
                nose_x,
                cy - outer,
                nose_x + skirt,
                cy - outer,
                tip,
                cy,
                nose_x + skirt,
                cy + outer,
                nose_x,
                cy + outer,
            ],
            fillColor=ACTIVE if focus == "nose_fit" else PART,
            strokeColor=INK,
            strokeWidth=0.85,
        )
    )
    return scale


def end_view(drawing, g, cad, cx, cy, radius):
    """Show equal angular placement viewed from the nozzle."""
    f = cad["fin"]
    inner = g.body_diameter_mm / 2 + g.radial_clearance_mm
    root = inner + f["saddle_wall"]
    span = f["span"] if cad["include_fins"] else 0
    scale = radius / (root + span)
    line(drawing, cx - radius - 5, cy, cx + radius + 5, cy, MUTED, [3, 3])
    line(drawing, cx, cy - radius - 5, cx, cy + radius + 5, MUTED, [3, 3])
    drawing.add(Circle(cx, cy, g.body_diameter_mm * scale / 2, fillColor=BODY, strokeColor=INK))
    if cad["include_fins"]:
        half_angle = asin(f["saddle_width"] / (2 * inner))
        for i in range(g.fin_count):
            angle = pi / 2 + 2 * pi * i / g.fin_count
            angles = [angle - half_angle + 2 * half_angle * j / 12 for j in range(13)]
            saddle = [(root, a) for a in angles] + [(inner, a) for a in reversed(angles)]
            points = [
                coord
                for r, a in saddle
                for coord in (cx + scale * r * cos(a), cy + scale * r * sin(a))
            ]
            drawing.add(Polygon(points, fillColor=PART, strokeColor=INK, strokeWidth=0.5))
            u, v = cos(angle), sin(angle)
            h = f["thickness"] / 2
            points = [
                (cx + scale * (r * u - t * v), cy + scale * (r * v + t * u))
                for r, t in ((root, -h), (root + span, -h), (root + span, h), (root, h))
            ]
            drawing.add(Polygon([v for pt in points for v in pt], fillColor=PART, strokeColor=INK))
    drawing.add(Circle(cx, cy, 2, fillColor=INK, strokeColor=None))


def fin_projection(path):
    """Orthographic blade-face projection of the registered assembly STL."""
    data = path.read_bytes()
    if len(data) < 84 or len(data) != 84 + 50 * unpack_from("<I", data, 80)[0]:
        raise ValueError("Expected a binary assembly fin STL")
    triangles = [
        [(row[i + 2], row[i]) for i in (3, 6, 9)]
        for row in iter_unpack("<12fH", memoryview(data)[84:])
    ]
    if not triangles:
        raise ValueError("The assembly fin mesh is empty")
    axial, radial = zip(*(point for triangle in triangles for point in triangle), strict=True)
    left, right = min(axial), max(axial)
    low, high = min(radial), max(radial)
    scale = min(126 / (right - left), 98 / (high - low))
    drawing = Drawing(144, 126)
    drawing.add(Rect(0, 0, 144, 126, fillColor=colors.white, strokeColor=RULE, strokeWidth=0.5))
    for triangle in triangles:
        points = [
            coord for x, y in triangle for coord in (9 + (x - left) * scale, 14 + (y - low) * scale)
        ]
        drawing.add(Polygon(points, fillColor=ACCENT, strokeColor=None))
    return drawing


def fit_labels(g):
    return (
        f"ボトル胴径  {mm(g.body_diameter_mm)} mm",
        f"ノーズ公称内径  {mm(g.body_diameter_mm + 2 * g.radial_clearance_mm)} mm",
        f"片側の嵌合余裕  {mm(g.radial_clearance_mm)} mm",
    )


def design_plate(state, g, cad, font):
    d = Drawing(760, 516)
    d.add(Rect(0, 0, 760, 516, fillColor=colors.white, strokeColor=None))
    label(d, 0, 498, "組立設計図", font, 23)
    label(d, 0, 472, state["spec"]["name"][:45], font, 12)
    label(d, 760, 499, f"RW / v{state['version']} / 01", font, 12, ACCENT, "end")
    basis = "実測入力" if g.dimensions_measured else "公称値・現物照合待ち"
    label(d, 760, 472, f"寸法 mm　/　{basis}", font, 10, MUTED, "end")
    side_title = "A  側面・ノズル端を 0 mm"
    if cad["include_fins"]:
        side_title += " / フィン代表1枚"
    panel(d, 0, 229, 501, 223, side_title, font)
    panel(d, 517, 229, 243, 223, "B  ノズル側から見る", font)
    x, cy = 49, 346
    scale = side_view(d, g, cad, (x, cy, 400, 56))
    nose_base = x + g.nose_base_mm * scale
    tip = x + g.overall_mm * scale
    label(d, x, 307, "ノズル", font, 8, MUTED, "middle")
    label(d, tip, 307, "先端", font, 8, MUTED, "middle")
    dimension(d, x, tip, 246, 300, f"全長 {mm(g.overall_mm)}", font)
    dimension(d, nose_base, tip, 270, 310, f"ノーズ {mm(g.nose_length_mm)}", font)
    if cad["include_fins"]:
        tail = x + g.fin_tail_inset_mm * scale
        dimension(d, x, tail, 270, 300, f"翼後端 {mm(g.fin_tail_inset_mm)}", font)
        if g.fin_tail_inset_mm == 0:
            label(d, x, 275, "翼後端 0", font, 8, ACCENT)
    end_view(d, g, cad, 638, 346, 63)
    fins = (
        f"{g.fin_count} 枚 / {mm(360 / g.fin_count)}° 等配" if cad["include_fins"] else "フィンなし"
    )
    label(d, 638, 253, fins, font, 11, INK, "middle")
    panel(d, 0, 43, 501, 170, "C  F01 フィン公称寸法・ノズル側が左", font)
    if cad["include_fins"]:
        f = cad["fin"]
        scale = min(206 / f["root_chord"], 63 / f["span"])
        x, y = 33, 88
        d.add(Polygon(blade_points(f, x, y, scale), fillColor=PART, strokeColor=INK))
        for z in f["slot_centers"]:
            sw, sh = f["slot_width"], f["slot_height"]
            d.add(
                Rect(
                    x + (z - sh / 2) * scale,
                    y + f.get("slot_root_offset", 1.8) * scale,
                    sh * scale,
                    sw * scale,
                    fillColor=PAPER,
                    strokeColor=ACCENT,
                    strokeWidth=0.65,
                )
            )
        dimension(d, x, x + f["root_chord"] * scale, 62, y, f"翼根 {mm(f['root_chord'])}", font)
        for i, text in enumerate(
            (
                f"翼端 {mm(g.fin_tip_mm)}　張出し {mm(g.fin_span_mm)}",
                f"後退 {mm(g.fin_sweep_mm)}　板厚 {mm(g.fin_thickness_mm)}",
                f"スロット {mm(f['slot_width'])} × {mm(f['slot_height'])}",
                "スロット中心 / 翼後端から",
                "、".join(mm(z) for z in f["slot_centers"]),
                "スロット寸法は径方向 × 軸方向",
            )
        ):
            label(d, 274, 167 - i * 21, text, font, 10)
    else:
        label(d, 15, 143, "この版はフィンなし", font, 11)
    panel(d, 517, 43, 243, 170, "D  N01 嵌合と基準位置", font)
    for i, text in enumerate(
        (
            *fit_labels(g),
            f"ノーズ基部  {mm(g.nose_base_mm)} mm",
            f"ボトル全高  {mm(g.body_height_mm)} mm",
            f"ノーズ肉厚  {mm(g.nose_wall_mm)} mm",
        )
    ):
        label(d, 531, 168 - i * 18, text, font, 9.6)
    label(d, 0, 23, "試作・仮組み用　/　外形と角部は模式　/　縮尺なし", font, 9, MUTED)
    label(d, 760, 23, f"入力 {state['analysis']['input_sha256'][:12]}", font, 9, MUTED, "end")
    return d


def plate_svg(plate, font):
    # The registered PDF font name is local to ReportLab, so let browsers use CJK fallback.
    svg = renderSVG.drawToString(plate)
    return (
        svg[svg.index("<svg ") :]
        .replace(f"font-family: {font};", "font-family: Meiryo, sans-serif;")
        .replace("<title>...</title>", "<title>組立設計図</title>")
        .replace("<desc>...</desc>", "<desc>採用版の側面・後面・部品の公称寸法</desc>")
    )
