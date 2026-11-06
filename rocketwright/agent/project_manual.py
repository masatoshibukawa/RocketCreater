"""Assembly trial instructions from the current adopted geometry and step records."""

import csv
import json
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
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
from rocketwright.agent.project_equipment import procurement_summary
from rocketwright.drawing import render_side_view_svg
from rocketwright.schema import BottleDesign


def write_project_manual(state, steps, output):
    font = japanese_font()
    body = ParagraphStyle(
        "body", fontName=font, fontSize=10, leading=18, wordWrap="CJK", spaceAfter=10
    )
    heading = ParagraphStyle("heading", parent=body, fontSize=20, leading=28, spaceAfter=18)
    sub = ParagraphStyle("sub", parent=body, fontSize=13, leading=22, spaceBefore=12)

    def p(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    spec, analysis = state["spec"], state["analysis"]
    g = spec["geometry"]
    story = [
        p("RocketWright / 組立手順書", heading),
        p(spec["name"], sub),
        p(f"採用版 v{state['version']} / 設計ID {state['id']}"),
        p(
            "試作・仮組み用。嵌合・固定・回収機構・強度・"
            "実飛行の確認は未完了です。加圧や打上げの手順書ではありません。"
        ),
        p("寸法と材料", sub),
    ]
    rows = [[p("部位"), p("採用寸法 mm / 条件")]]
    for label, value in [
        (
            "ボトル",
            f"径{g['body_diameter_mm']:g} / 高さ{g['body_height_mm']:g}・市販品を無加工で使用",
        ),
        ("ノーズ", f"長さ{g['nose_length_mm']:g} / 肉厚{g['nose_wall_mm']:g}"),
        (
            "フィン",
            (
                f"{g['fin_count']}枚・"
                f"翼根{g['fin_root_mm']:g} / 翼端{g['fin_tip_mm']:g} / "
                f"張出し{g['fin_span_mm']:g} / 後退{g['fin_sweep_mm']:g} / "
                f"厚さ{g['fin_thickness_mm']:g}"
            )
            if spec["design"]["has_fins"]
            else "この版では未使用",
        ),
        ("材料", spec["material"]),
        ("寸法の根拠", "実測入力" if g["dimensions_measured"] else "仮定入力・実物照合が必要"),
        (
            "計算した乾燥質量",
            f"{analysis['design']['dry_mass_kg'] * 1000:.2f} g / {analysis['mass_basis']}",
        ),
    ]:
        rows.append([p(label), p(value)])
    table = Table(rows, colWidths=[100, 390], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f1")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ]
        )
    )
    figure = Drawing(490, 200)
    overall = 0.9 * g["body_height_mm"] - min(18, g["nose_length_mm"] / 4) + g["nose_length_mm"]
    scale = min(440 / overall, 140 / (g["body_diameter_mm"] + 2 * g["fin_span_mm"]))
    length = overall * scale
    nose_length = g["nose_length_mm"] * scale
    radius = g["body_diameter_mm"] * scale / 2
    figure.add(
        Polygon(
            [
                25,
                100,
                25 + nose_length,
                100 + radius,
                25 + length,
                100 + radius,
                25 + length,
                100 - radius,
                25 + nose_length,
                100 - radius,
            ],
            fillColor=colors.HexColor("#eaf2ef"),
            strokeColor=colors.darkslategray,
        )
    )
    tail = 25 + length - g["fin_tail_inset_mm"] * scale
    root = g["fin_root_mm"] * scale
    for sign in (-1, 1) if spec["design"]["has_fins"] else ():
        y = 100 + sign * radius
        figure.add(
            Polygon(
                [
                    tail - root,
                    y,
                    tail - root + g["fin_sweep_mm"] * scale,
                    y + sign * g["fin_span_mm"] * scale,
                    tail - root + (g["fin_sweep_mm"] + g["fin_tip_mm"]) * scale,
                    y + sign * g["fin_span_mm"] * scale,
                    tail,
                    y,
                ],
                fillColor=colors.lightgrey,
                strokeColor=colors.darkslategray,
            )
        )
    figure.add(
        String(
            25,
            12,
            f"v{state['version']} / 同じ採用寸法の側面模式図・原寸ではありません",
            fontName=font,
            fontSize=8,
        )
    )
    story += [figure]
    story += [
        table,
        p(
            "準備：平らな作業台、定規・ノギス、はかり、部品に適合する固定材。"
            "固定材の寸法・許容値、先端キャップ、"
            "搭載物と回収部の取付方法は現物で確定してください。"
        ),
        PageBreak(),
    ]
    from rocketwright.agent.design_projects import DesignSpec

    current_spec = DesignSpec.model_validate(spec)
    access = assembly_assessment(current_spec)
    status_names = {
        "not_evaluated": "未評価",
        "screen_pass": "公称寸法の比較を通過",
        "interference": "干渉候補",
    }
    for i, step in enumerate(steps):
        if i:
            story.append(PageBreak())
        observations = [r for r in state.get("observations", []) if r["step"] == step["id"]]
        story += [
            p(f"{i + 1}. {step['title']}", sub),
            assembly_step_figure(g, step["id"], font, spec["design"]["has_fins"]),
            p(step["instruction"]),
            p(
                "担当："
                + current_spec.equipment.operator
                + " / 手袋："
                + current_spec.equipment.glove
            ),
            p("工具：" + "、".join(step.get("tools", []))),
            p("戻し方：" + step.get("reverse", "逆順に仮固定を外して確認")),
            p(
                "確認記録： □ 未確認　□ 要修正　□ "
                "現物確認済み\n担当：　　　　　　　　日付：　　　　　　　　測定・"
                "観察："
            ),
            Spacer(1, 18),
        ]
        for row in observations[-3:]:
            story += [
                p(f"保存した観察 / {row['status']} / {row['operator']} / {row['observed_on']}"),
                p(row["note"]),
                p(json.dumps(row.get("measured_values", {}), ensure_ascii=False)),
            ]
    story += [
        PageBreak(),
        p("組立アクセスの確認", heading),
        p("公称寸法と直線の剛体包絡による近似。手の関節や接触・摩擦の解析ではありません。"),
    ]
    for check in access["checks"]:
        value = "未入力" if check["required"] is None else f"{check['required']:.2f}"
        story += [
            p(f"{check['label']} / {status_names[check['status']]}", sub),
            p(f"公称・上限 {check['available']:.2f} / 入力値 {value} {check['unit']}"),
            p(check["assumption"]),
        ]
    story += [
        p(
            "保持・視認・分解：現物記録が必要です。幾何スクリーニングの通過は実物の合格ではありません。"
        )
    ]
    cost = procurement_summary(current_spec)
    story += [
        PageBreak(),
        p("機材と調達", heading),
        p(f"{current_spec.equipment.printer_label} / {current_spec.equipment.printer_profile}"),
        p(f"材料：{spec['material']} / ロット：{current_spec.equipment.material_lot or '未記入'}"),
        p(
            f"径方向の嵌合余裕 {current_spec.geometry.radial_clearance_mm:g} mm / "
            f"固定材スロット幅 {current_spec.geometry.fin_slot_width_mm:g} mm"
        ),
    ]
    for row in cost["rows"]:
        purchase = row["supplied"] or {}
        story += [
            p(
                f"{row['part']} / 必要数 {row['required_quantity']} / "
                f"小計 {row['subtotal_jpy'] if row['subtotal_jpy'] is not None else '未確認'} 円"
            ),
            p(
                f"根拠：{purchase.get('basis', 'unknown')} / {purchase.get('source', '')} / "
                f"{purchase.get('checked_on', '')}"
            ),
        ]
    story += [
        p(f"確認済み合計：{cost['total_jpy'] if cost['total_jpy'] is not None else '未評価'} 円")
    ]
    previews = [
        ("フィン", "fin-preview.png"),
        ("ノーズ", "nose-preview.png"),
        ("試着リング", "fit-ring-preview.png"),
    ]
    actual_previews = [
        (label, output.parent.parent / "cad" / name)
        for label, name in previews
        if (output.parent.parent / "cad" / name).is_file()
    ]
    if actual_previews:
        story += [
            PageBreak(),
            p("採用CADの部品図", heading),
            p("この版の実際の生成メッシュ。工程図は同じ寸法からの模式図です。"),
        ]
        for label, path in actual_previews:
            story += [p(label, sub), Image(str(path), width=135, height=135)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.drawString(42, 25, f"v{state['version']} / 試作手順・実機未検証")
        canvas.drawRightString(A4[0] - 42, 25, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=40,
        bottomMargin=44,
        title=spec["name"] + " 組立手順",
        author="RocketWright",
    ).build(story, onFirstPage=footer, onLaterPages=footer)

    # A calculation sheet and portable data accompany the assembly instructions.
    metrics = analysis["result"]["metrics"]
    summary = [
        p("設計・計算の確認票", heading),
        p(f"{spec['name']} / v{state['version']}"),
        p(
            f"到達高度 {metrics['apogee_m']:.2f} m / "
            f"降下速度 {metrics['descent_speed_mps']:.2f} m/s"
        ),
        p(f"乾燥質量 {analysis['design']['dry_mass_kg'] * 1000:.2f} g / {analysis['mass_basis']}"),
        p("計算条件の確認", sub),
        table,
        p("未確認事項", sub),
    ]
    for check in analysis.get("requirements", {}).get("checks", []):
        summary.append(p(f"{check['label']} / {check['status']} : {check['reason']}"))
    summary += [p(text) for text in analysis["limitations"]]
    SimpleDocTemplate(
        str(output.parent / "design-sheet.pdf"),
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=40,
        bottomMargin=44,
        title=spec["name"] + " 計算確認票",
        author="RocketWright",
    ).build(summary, onFirstPage=footer, onLaterPages=footer)
    (output.parent / "calculation-report.md").write_text(
        f"# {spec['name']} / v{state['version']}\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in metrics.items())
        + "\n\n"
        + "\n".join(analysis["limitations"]),
        encoding="utf-8",
    )
    (output.parent / "side-view.svg").write_text(
        render_side_view_svg(BottleDesign.model_validate(analysis["design"])), encoding="utf-8"
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


def assembly_step_figure(g, step_id, font, has_fins=True):
    """Dimension-derived step illustration; the same geometry supplies production CAD."""
    drawing = Drawing(490, 165)
    nose_base = 0.9 * g["body_height_mm"] - min(18, g["nose_length_mm"] / 4)
    scale = min(
        370 / (nose_base + g["nose_length_mm"]),
        120 / (g["body_diameter_mm"] + 2 * g["fin_span_mm"]),
    )
    x0, y0 = 55, 85
    width = g["body_diameter_mm"] * scale
    length = g["body_height_mm"] * scale
    drawing.add(
        Rect(
            x0,
            y0 - width / 2,
            length,
            width,
            fillColor=colors.HexColor("#eaf2ef"),
            strokeColor=colors.darkslategray,
        )
    )
    root = g["fin_root_mm"] * scale
    start = x0 + g["fin_tail_inset_mm"] * scale
    nose_start = x0 + nose_base * scale
    drawing.add(
        Polygon(
            [
                nose_start,
                y0 - width / 2,
                nose_start,
                y0 + width / 2,
                nose_start + g["nose_length_mm"] * scale,
                y0,
            ],
            fillColor=colors.HexColor("#87b4a3") if step_id == "nose_fit" else colors.lightgrey,
            strokeColor=colors.darkslategray,
        )
    )
    for sign in (-1, 1) if has_fins else ():
        y = y0 + sign * width / 2
        pts = [
            start,
            y,
            start + root,
            y,
            start + root - g["fin_sweep_mm"] * scale,
            y + sign * g["fin_span_mm"] * scale,
            start + (g["fin_root_mm"] - g["fin_sweep_mm"] - g["fin_tip_mm"]) * scale,
            y + sign * g["fin_span_mm"] * scale,
        ]
        drawing.add(
            Polygon(
                pts,
                fillColor=colors.HexColor("#87b4a3")
                if step_id == "fin_mount"
                else colors.lightgrey,
                strokeColor=colors.darkslategray,
            )
        )
    if step_id in {"fin_mount", "nose_fit", "recovery"}:
        drawing.add(
            Line(
                x0 + length + 35,
                y0,
                x0 + length + 5,
                y0,
                strokeColor=colors.HexColor("#ce792e"),
                strokeWidth=3,
            )
        )
    drawing.add(
        String(
            30,
            14,
            "採用寸法の工程模式図・ノズル側が左・原寸ではありません",
            fontName=font,
            fontSize=9,
        )
    )
    return drawing
