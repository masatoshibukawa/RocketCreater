"""Versioned assembly instructions, vector design sheet and calculation record."""

import csv
import json
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Polygon
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from rocketwright.agent.manual import japanese_font
from rocketwright.agent.project_assembly import assembly_assessment
from rocketwright.agent.project_drawing import (
    ACCENT,
    INK,
    MUTED,
    PAPER,
    RULE,
    design_plate,
    dimension,
    end_view,
    fin_projection,
    fit_labels,
    label,
    line,
    mm,
    panel,
    plate_svg,
    side_view,
)
from rocketwright.agent.project_equipment import procurement_summary

WIDTH = 490
CHECKS = {
    "parts": "PDF・部品表・印刷データの版を照合し、部品の数とボトルの胴径を記録する。",
    "finish": (
        "ブリム除去後の外周、割れ、反りを確認する。"
        "フィンがある場合は固定材がスロットを通るか確認する。"
    ),
    "fin_mount": "全ての翼後端が同じ位置にあり、軸方向にねじれていないかを横と後ろから見る。",
    "nose_fit": "はめ込みと取外しを試し、がたつき・浮き・ボトルの傷を記録する。",
    "recovery": "搭載物を入れた状態で、保持と取出し・展開の経路を別途確認する。",
    "measure": "実測質量と重心の測定条件を記録し、設計を更新する。",
}
ACCESS_STATUS = {
    "not_evaluated": "未評価",
    "screen_pass": "公称寸法を比較済み",
    "interference": "干渉候補",
}
OBS_STATUS = {"unconfirmed": "未確認", "needs_change": "要修正", "observed": "現物確認"}
PART_NAMES = {
    "bottle": "ボトル",
    "nose": "ノーズ",
    "soft_cap": "軟質キャップ",
    "fixing": "固定材",
    "other": "その他",
    "fin": "フィン",
    "payload": "搭載物",
    "recovery": "回収部",
}
REQUIREMENT_STATUS = {
    "pass": "計算・入力確認済み",
    "fail": "未達",
    "not_required": "要求なし",
    "not_evaluated": "未評価",
}


def step_figure(g, cad, step, font):
    d = Drawing(WIDTH, 166)
    captions = {
        "parts": "基準をそろえる",
        "finish": "仕上げ後の外周を確認",
        "fin_mount": "後端位置と等配角",
        "nose_fit": "ノーズを先端側から合わせる",
        "recovery": "搭載物・回収部の取付は現物で決定",
        "measure": "ノズル端を基準に測定",
    }
    panel(d, 0, 0, WIDTH, 166, captions[step], font)
    if step == "fin_mount" and not cad["include_fins"]:
        label(d, 17, 88, "この版はフィンなし。この工程を飛ばします。", font, 12)
        return d
    fins = step == "fin_mount"
    nose = step == "nose_fit"
    gap = 0.21 * g.overall_mm if nose else 0
    x, cy = 32, 85
    scale = side_view(d, g, cad, (x, cy, 289 if fins else 416, 50), focus=step, gap_mm=gap)
    if fins:
        end_view(d, g, cad, 405, 83, 38)
        label(d, 405, 31, f"{g.fin_count} 枚 / {mm(360 / g.fin_count)}°", font, 10, INK, "middle")
        label(d, 405, 15, "ノズル側から見る", font, 8, MUTED, "middle")
        tail = x + g.fin_tail_inset_mm * scale
        dimension(d, x, tail, 30, cy, f"翼後端 {mm(g.fin_tail_inset_mm)} mm", font)
        if g.fin_tail_inset_mm == 0:
            label(d, x, 31, "翼後端はノズル基準と同じ位置", font, 9, ACCENT)
    elif nose:
        left = x + g.nose_base_mm * scale
        right = left + gap * scale
        line(d, right - 3, cy, left + 3, cy, ACCENT)
        d.add(
            Polygon(
                [left + 3, cy, left + 9, cy + 4, left + 9, cy - 4],
                fillColor=ACCENT,
                strokeColor=None,
            )
        )
        for pos, text in zip((18, 180, 350), fit_labels(g), strict=True):
            label(d, pos, 19, text, font, 8.6)
    elif step == "measure":
        dimension(d, x, x + g.overall_mm * scale, 29, cy, f"全長 {mm(g.overall_mm)} mm", font)
    else:
        label(d, 17, 17, "ノズル側  0 mm", font, 9, MUTED)
        label(d, 473, 17, "先端側", font, 9, MUTED, "end")
    return d


def write_project_manual(state, steps, output):
    from rocketwright.agent.design_projects import DesignSpec, sha
    from rocketwright.agent.workbench import Conflict

    font = japanese_font()
    body = ParagraphStyle(
        "body",
        fontName=font,
        fontSize=10.5,
        leading=16,
        wordWrap="CJK",
        textColor=INK,
        spaceAfter=8,
    )
    title = ParagraphStyle("title", parent=body, fontSize=23, leading=31, spaceAfter=11)
    sub = ParagraphStyle(
        "sub", parent=body, fontSize=13, leading=19, textColor=ACCENT, spaceBefore=8
    )
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=14, spaceAfter=0)

    def p(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    def grid(rows, widths, *, header=True):
        table = Table(
            [[p(value, small) for value in row] for row in rows],
            colWidths=widths,
            hAlign="LEFT",
            repeatRows=int(header),
        )
        rules = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, PAPER]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.35, RULE),
        ]
        if header:
            rules.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#deeeeb")))
        table.setStyle(TableStyle(rules))
        return table

    spec, analysis = state["spec"], state["analysis"]
    current = DesignSpec.model_validate(spec)
    g = current.geometry
    access = assembly_assessment(current)
    cad = access["cad_parameters"]
    identity = f"v{state['version']}   /   入力 {analysis['input_sha256'][:12]}"
    basis = "実測入力" if g.dimensions_measured else "公称値。現物を測って照合する。"
    parts = [
        ("B01", "市販PETボトル", 1, "無加工で使用", None),
        (
            "N01",
            "ノーズ",
            1,
            f"{spec['material']} / 長さ {mm(g.nose_length_mm)} mm",
            "nose-preview.png",
        ),
    ]
    if cad["include_fins"]:
        parts.append(
            (
                "F01",
                "フィン",
                g.fin_count,
                f"{spec['material']} / 板厚 {mm(g.fin_thickness_mm)} mm",
                "fin-preview.png",
            )
        )
    parts.append(("J01", "試着リング", 1, "嵌合確認用の治具", "fit-ring-preview.png"))
    previews = []
    files = {row["key"]: row for row in state["files"]}
    for ident, name, _, _, filename in parts:
        row = files.get(f"cad/{filename}")
        if row is None:
            continue
        path = output.parent.parent / "cad" / filename
        if not path.is_file() or sha(path) != row["sha256"]:
            raise Conflict("CAD部品図が採用版と一致しません。再解析が必要です。")
        mesh_row = files.get("cad/fin-assembly-mm.stl") if ident == "F01" else None
        if mesh_row is not None:
            mesh = path.with_name("fin-assembly-mm.stl")
            if not mesh.is_file() or sha(mesh) != mesh_row["sha256"]:
                raise Conflict("フィンCADが採用版と一致しません。再解析が必要です。")
            previews.append([p(f"{ident}  {name}・側面投影", small), fin_projection(mesh)])
            continue
        preview = Image(str(path))
        scale = min(145 / preview.imageWidth, 126 / preview.imageHeight)
        preview.drawWidth = preview.imageWidth * scale
        preview.drawHeight = preview.imageHeight * scale
        previews.append([p(f"{ident}  {name}", small), preview])
    preview_table = (
        Table([previews], colWidths=[WIDTH / len(previews)] * len(previews)) if previews else None
    )
    if preview_table is not None:
        preview_table.setStyle(
            TableStyle(
                [("BACKGROUND", (0, 0), (-1, -1), PAPER), ("VALIGN", (0, 0), (-1, -1), "TOP")]
            )
        )
    part_table = [["ID", "部品", "数", "材料・用途"], *[row[:4] for row in parts]]
    story = [
        p("組立手順書", title),
        p(spec["name"]),
        p(identity, small),
        Spacer(1, 12),
        grid(
            [
                ["用途", "試作の仮組みと現物照合"],
                ["確認範囲", "取付保持・回収・実飛行は現物検証待ち。加圧・打上げ手順は別途確定。"],
            ],
            [96, 394],
            header=False,
        ),
        Spacer(1, 14),
        step_figure(g, cad, "parts", font),
        p("部品と治具", sub),
        grid(part_table, [54, 106, 36, 294]),
        p("作業前に", sub),
        p(f"胴径 {mm(g.body_diameter_mm)} mm / ボトル全高 {mm(g.body_height_mm)} mm。{basis}"),
        p(
            "定規・ノギス・はかりを用意する。固定材と軟質キャップは現物に合わせて選ぶ。位置と寸法は同じ版の組立設計図を参照。"
        ),
    ]

    for number, step in enumerate(steps, 1):
        key = step["id"]
        check = CHECKS[key]
        if key == "fin_mount" and not cad["include_fins"]:
            check = "この工程を飛ばし、ノーズの仮合わせへ進む。"
        story += [
            PageBreak(),
            p(f"工程 {number:02d} / {len(steps):02d}", sub),
            p(step["title"], title),
            preview_table
            if key == "finish" and preview_table is not None
            else step_figure(g, cad, key, font),
            Spacer(1, 12),
            p("作業", sub),
            p(step["instruction"]),
            p("現物で見る場所", sub),
            p(check),
            grid(
                [
                    ["準備", "、".join(step.get("tools", [])) or "作業に必要な工具を確認"],
                    ["担当・手袋", f"{current.equipment.operator} / {current.equipment.glove}"],
                    ["戻し方", step.get("reverse") or "仮固定を逆順に外す"],
                ],
                [96, 394],
                header=False,
            ),
            p("現物記録", sub),
            p("□ 未確認　 □ 要修正　 □ 現物確認", small),
            Spacer(1, 8),
            grid(
                [
                    ["担当・日付", "　　　　　　　　　 / 　　　　　　　　　"],
                    ["測定・観察", "　"],
                    ["修正点", "　"],
                ],
                [96, 394],
                header=False,
            ),
        ]
        observations = [row for row in state.get("observations", []) if row["step"] == key]
        for row in observations[-3:]:
            story += [
                p(
                    f"保存済み / {OBS_STATUS.get(row['status'], row['status'])} / "
                    f"{row['operator']} / {row['observed_on']}",
                    sub,
                ),
                p(row["note"]),
            ]
            if row.get("measured_values"):
                story.append(
                    grid([["測定項目", "値"], *row["measured_values"].items()], [340, 150])
                )

    story += [PageBreak(), p("仮組みの確認票", title), p(identity, small), Spacer(1, 12)]
    story.append(
        grid(
            [
                ["確認箇所", "公称・上限", "入力値", "比較結果"],
                *[
                    (
                        check["label"],
                        "未入力"
                        if check["available"] == 0 and check["required"] is None
                        else f"{check['available']:.2f} {check['unit']}",
                        "未入力"
                        if check["required"] is None
                        else f"{check['required']:.2f} {check['unit']}",
                        ACCESS_STATUS[check["status"]],
                    )
                    for check in access["checks"]
                ],
            ],
            [192, 92, 86, 120],
        )
    )
    story += [
        p("判定の範囲", sub),
        p("直線での出し入れと公称寸法の比較。手の動き、摩擦、印刷誤差、保持強度は現物で確認。"),
        p("機材と材料", sub),
        p(f"{current.equipment.printer_label} / {current.equipment.printer_profile}"),
        p(f"{spec['material']} / ロット {current.equipment.material_lot or '未記入'}"),
    ]
    cost = procurement_summary(current)
    story += [
        p("調達記録", sub),
        grid(
            [
                ["部品", "必要数", "小計", "根拠・確認日"],
                *[
                    (
                        PART_NAMES.get(row["part"], row["part"]),
                        row["required_quantity"],
                        "未確認" if row["subtotal_jpy"] is None else f"{row['subtotal_jpy']} 円",
                        " / ".join(
                            str(purchase[k])
                            for k in ("basis", "source", "checked_on")
                            if purchase.get(k)
                        )
                        or "未入力",
                    )
                    for row in cost["rows"]
                    for purchase in [row["supplied"] or {}]
                ],
            ],
            [100, 60, 85, 245],
        ),
        p(
            f"確認済み合計 {cost['total_jpy']} 円"
            if cost["total_jpy"] is not None
            else "合計は未評価"
        ),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(47, 39, A4[0] - 47, 39)
        canvas.setFillColor(MUTED)
        canvas.setFont(font, 8)
        canvas.drawString(47, 25, f"RocketWright   /   {identity}")
        canvas.drawRightString(A4[0] - 47, 25, f"{doc.page:02d}")
        canvas.restoreState()

    def build(path, content, name):
        SimpleDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=46,
            rightMargin=46,
            topMargin=39,
            bottomMargin=52,
            title=spec["name"] + " " + name,
            author="RocketWright",
        ).build(content, onFirstPage=footer, onLaterPages=footer)

    build(output, story, "組立手順書")
    plate = design_plate(state, g, cad, font)
    width, height = landscape(A4)
    drawing = Canvas(str(output.parent / "design-drawing.pdf"), pagesize=(width, height))
    drawing.setTitle(spec["name"] + " 組立設計図")
    drawing.setAuthor("RocketWright")
    renderPDF.draw(plate, drawing, (width - plate.width) / 2, (height - plate.height) / 2)
    drawing.save()
    (output.parent / "side-view.svg").write_text(plate_svg(plate, font), encoding="utf-8")

    metrics = analysis["result"]["metrics"]
    mass_basis = {
        "measured": "印刷部品は実測入力",
        "solid_CAD_estimate": "印刷部品はCADの一様固体推定",
    }
    basis_label = mass_basis.get(analysis["mass_basis"], analysis["mass_basis"])
    summary = [
        p("設計・計算の確認票", title),
        p(spec["name"]),
        p(identity, small),
        Spacer(1, 12),
        grid(
            [
                ["計算項目", "値と根拠"],
                ["到達高度", f"{metrics['apogee_m']:.2f} m"],
                ["降下速度", f"{metrics['descent_speed_mps']:.2f} m/s"],
                [
                    "乾燥質量",
                    f"{analysis['design']['dry_mass_kg'] * 1000:.2f} g / {basis_label}",
                ],
                ["寸法の根拠", basis],
            ],
            [128, 362],
        ),
        p("要求ごとの確認", sub),
    ]
    for check in analysis.get("requirements", {}).get("checks", []):
        status = REQUIREMENT_STATUS.get(check["status"], check["status"])
        summary.append(p(f"{check['label']} / {status} / {check['reason']}"))
    summary += [p("計算の適用範囲", sub), *[p(text) for text in analysis["limitations"]]]
    build(output.parent / "design-sheet.pdf", summary, "計算確認票")
    (output.parent / "calculation-report.md").write_text(
        f"# {spec['name']} / v{state['version']}\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in metrics.items())
        + "\n\n"
        + "\n".join(analysis["limitations"]),
        encoding="utf-8",
    )
    trace = analysis["result"]["trace"]
    if trace:
        with (output.parent / "flight.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(trace[0]))
            writer.writeheader()
            writer.writerows(trace)
    (output.parent / "provenance.json").write_text(
        json.dumps(
            {
                "project_id": state["id"],
                "version": state["version"],
                "input_sha256": analysis["input_sha256"],
                "geometry_sha256": analysis["geometry_sha256"],
                "implementation_sha256": analysis["implementation_sha256"],
                "physical_print_verified": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
