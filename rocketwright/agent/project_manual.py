"""Assembly trial instructions from the current adopted geometry and step records."""

import csv
import json
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from rocketwright.agent.manual import japanese_font
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
    for i, step in enumerate(steps):
        if i == 3:
            story.append(PageBreak())
        story += [
            p(f"{i + 1}. {step['title']}", sub),
            p(step["instruction"]),
            p(
                "確認記録： □ 未確認　□ 要修正　□ "
                "現物確認済み\n担当：　　　　　　　　日付：　　　　　　　　測定・"
                "観察："
            ),
            Spacer(1, 18),
        ]

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
