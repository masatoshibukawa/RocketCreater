"""Render the frozen packet's actual assembly instructions as a Japanese PDF."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#173c39")
PALE = colors.HexColor("#eaf2ef")


def japanese_font() -> str:
    name = "AssemblyJapanese"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    configured = os.getenv("ROCKETWRIGHT_PDF_FONT")
    candidates = [Path(configured)] if configured else [Path("C:/Windows/Fonts/meiryo.ttc")]
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
            return name
    if configured:
        raise ValueError("ROCKETWRIGHT_PDF_FONT must point to a Japanese TrueType font")
    # Standard Japanese PDF CID font, for hosts without a redistributable TTF.
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    return "HeiseiKakuGo-W5"


def assembly_figure(plan: dict, font: str) -> Drawing:
    g = plan["dimensions_mm"]
    scale, left, y = 420 / g["overall"], 20, 165

    def x(mm):
        return left + mm * scale

    radius = g["body_diameter"] * scale / 2
    drawing = Drawing(468, 325)
    drawing.add(
        Polygon(
            [
                x(0),
                y,
                x(g["nose_length"]),
                y + radius,
                x(g["overall"]),
                y + radius,
                x(g["overall"]),
                y - radius,
                x(g["nose_length"]),
                y - radius,
            ],
            fillColor=PALE,
            strokeColor=INK,
            strokeWidth=1,
        )
    )
    root = g["overall"] - g["fin_tail_inset"] - g["fin_root"]
    for sign in (-1, 1):
        drawing.add(
            Polygon(
                [
                    x(root),
                    y + sign * radius,
                    x(root + g["fin_sweep"]),
                    y + sign * (radius + g["fin_span"] * scale),
                    x(root + g["fin_sweep"] + g["fin_tip"]),
                    y + sign * (radius + g["fin_span"] * scale),
                    x(root + g["fin_root"]),
                    y + sign * radius,
                ],
                fillColor=colors.HexColor("#c4ddd5"),
                strokeColor=INK,
            )
        )
    station = g["nose_length"]
    for length, label in ((g["egg_bay_length"], "搭載室"), (g["canopy_bay_length"], "傘室")):
        drawing.add(Line(x(station), y - radius, x(station), y + radius, strokeColor=INK))
        drawing.add(
            String(
                x(station + length / 2),
                y - 4,
                label,
                fontName=font,
                fontSize=8,
                textAnchor="middle",
            )
        )
        station += length
    drawing.add(Line(x(station), y - radius, x(station), y + radius, strokeColor=INK))
    drawing.add(
        String(
            x((station + g["overall"]) / 2),
            y - 4,
            "無加工の本体",
            fontName=font,
            fontSize=9,
            textAnchor="middle",
        )
    )
    drawing.add(
        String(
            left,
            312,
            "先端0 mm → ノズル方向が正 / 側面の模式図",
            fontName=font,
            fontSize=9,
            fillColor=INK,
        )
    )
    drawing.add(
        String(
            left,
            8,
            f"全長 {g['overall']} mm / 胴体径 {g['body_diameter']} mm / 4枚翼を90°等配",
            fontName=font,
            fontSize=9,
            fillColor=INK,
        )
    )
    return drawing


def write_manual(directory: Path, state: dict, output_directory: Path | None = None) -> Path:
    plan = json.loads((directory / "assembly.json").read_text(encoding="utf-8"))
    design = state["design_snapshot"]
    manual = (directory / "build.md").read_text(encoding="utf-8")
    steps = re.findall(r"^\d+\. (.+)$", manual, re.MULTILINE)
    if len(steps) != 6:
        raise ValueError("The frozen assembly packet must contain all six instructions")
    font = japanese_font()
    body = ParagraphStyle(
        "body", fontName=font, fontSize=9, leading=16, textColor=INK, wordWrap="CJK", spaceAfter=10
    )
    heading = ParagraphStyle("heading", parent=body, fontSize=20, leading=28, spaceAfter=18)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=12)

    def p(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    story = []

    def title(kicker, name):
        story.extend(
            [p(kicker, small), p(name, heading), HRFlowable(width="100%", color=INK), Spacer(1, 16)]
        )

    title("ROCKETWRIGHT / ASSEMBLY", "卵回収ロケット 組立手順")
    story.append(p(f"構成 {plan['key']} / 容量 {design['bottle_volume_m3'] * 1000:g} L"))
    story.append(
        p(f"プロジェクト {state['id']}\n出力元 revision {state['revision']} / 実物確認前", small)
    )
    story.append(
        p(
            "解析上の採用案から作成した仮組み用の手順です。実物への適合、取付保持、強度、回収・飛行の検証は完了していません。図は原寸型紙ではありません。"
        )
    )
    story.append(
        p(
            f"計算の仮定: 初期圧力差 {design['initial_gauge_pressure_pa'] / 1000:g} kPa / "
            f"充填率 {design['water_fill_frac'] * 100:g}%（機材の許容値ではありません）。",
            small,
        )
    )
    story.append(assembly_figure(plan, font))
    story.append(p("最初に照合するもの"))
    story.append(
        p(
            "実物のボトル寸法と、対になる噴射口・発射台を照合します。加圧される本体は無加工で使用します。スカート・搭載筒・傘室は非加圧の予備容器から作ります。"
        )
    )
    story.append(
        p(
            "併用するファイル: 原寸フィン型紙 fin-1to1.svg、配置図 vehicle.svg、"
            "購入計画 procurement.md、入力票 bench-template.json。"
            "3Dプリント部品は搭載部カラーと位置決め治具です。2 L試作例のSTLとは異なります。",
            small,
        )
    )

    story.append(PageBreak())
    title("02 / MATERIALS", "部品と製作の準備")
    rows = [
        [
            p("用意するもの", small),
            p("数量・切出し", small),
            p("質量 g", small),
            p("予算 円", small),
        ]
    ]
    for row in plan["bill"]:
        rows.append(
            [
                p(row["name"], small),
                p(row["quantity"], small),
                p(f"{row['mass_g']:.1f}", small),
                p(row["allowance_jpy"], small),
            ]
        )
    table = Table(rows, colWidths=[185, 180, 48, 55], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd8d2")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 16)])
    story.append(
        p(
            f"材料予算配分 {plan['estimated_outlay_jpy']:,}円（試算・地上機材別）。"
            f"乾燥組立の積上げ {plan['estimated_dry_mass_g']:.1f} g / "
            f"飛行計算値 {plan['dry_mass_g']:.1f} g。"
            f"搭載物 {design['payload_mass_kg'] * 1000:g} gは別です。"
        )
    )
    story.append(
        p(
            "はさみ、カッターマット、定規、はかり、計量容器、対応する発射台とガイドを用意します。STLはmm単位を前提にスライスし、材料・寸法・積層方向・取付部を現物で確認します。見積額は購入価格の保証ではありません。"
        )
    )

    story.append(PageBreak())
    title("03 / BUILD", "外装・フィン・搭載室")
    for number, text in enumerate(steps[:3], 1):
        story.append(p(f"{number:02d}  {text}"))
        story.append(Spacer(1, 10))
    story.append(
        p(
            "確認欄: 寸法照合 ______ / 型紙の50 mm線 ______ / "
            "フィン間隔 ______ / ダミーの収まり ______"
        )
    )

    story.append(PageBreak())
    title("04 / CHECK", "回収装置と無加圧での確認")
    for number, text in enumerate(steps[3:], 4):
        story.append(p(f"{number:02d}  {text}"))
    story.append(p("現物の記録 / 完了は作業者が確認"))
    for text in (
        "作業日・担当者 __________________________",
        "本体径 ______ mm / 容器長 ______ mm / 噴射口実測 ______ mm",
        "搭載物を外した乾燥質量 ______ g / 先端からの乾燥重心 ______ mm",
        "注水時重心 ______ mm / 搭載物 ______ g / 保持・放出の観察 __________",
    ):
        story.append(p(text, small))
    story.append(p("未確認: " + " / ".join(plan["pending_evidence"]), small))
    sources = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", manual)
    story.append(p("出典（採用元の図と説明を併読）", small))
    for key, url in sources:
        href = escape(url, {'"': "&quot;"})
        story.append(
            Paragraph(
                f'<link href="{href}">{escape(key)}: {escape(url)}</link>',
                small,
            )
        )

    path = (output_directory or directory) / "assembly-instructions.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_hash = hashlib.sha256(json.dumps(design, sort_keys=True).encode()).hexdigest()[:12]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(INK)
        canvas.drawString(54, 29, f"設計 {snapshot_hash} / 実物確認前")
        canvas.drawRightString(A4[0] - 54, 29, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=54,
        leftMargin=54,
        topMargin=44,
        bottomMargin=48,
        title="卵回収ロケット 組立手順",
        author="RocketWright",
        subject=f"{plan['key']} / revision {state['revision']}",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return path
