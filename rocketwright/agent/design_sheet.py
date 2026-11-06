"""One-page-per-topic build sheet of a bottle design, as a Japanese PDF.

The assembly manual (agent/manual.py) describes the 1.5 L recipe's own vehicle. A free design
fixes no bays, skirt or fin material, so this sheet states only what the design, its simulation
and its bill say, and no assembly steps. Every figure comes from those inputs.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from rocketwright.agent.manual import INK, PALE, japanese_font
from rocketwright.schema import BottleDesign, DispersionResult, SimResult

__all__ = ["render_design_sheet", "sheet_sections"]

NO_MARGIN = "未算出（部品のフィン未選択）"
TITLE = "ペットボトルロケット 製作票"
PENDING_CHECKS = (
    "実物のボトル・噴射口・発射台の型式、説明書、使用条件",
    "組立後の乾燥質量と重心、注水時の重心",
    "フィンの位置と取付の剛性",
    "回収装置の収納・放出、着地時の荷重",
    "材料の購入額と、実地で使用できる条件・場所",
)
SAFETY_TITLE = "打ち上げるときの安全"
# Wording drafted on 2026-11-07 from common water-rocket practice; the project owner reviews it.
_SAFETY_NOTES = (
    "加圧は、機体と発射台から離れて行う。機体の正面と真上に、顔や体を出さない",
    "傷、へこみ、白く変色した所のあるボトルは使わない。炭酸飲料用でないボトルは使わない",
    "保護めがねを着ける",
    "打ち上げの前に、周りと風下に人がいないことを確かめ、声を掛けてから発射する",
    "人、建物、道路、電線の方へ向けない。広くて、落ちてきても安全な場所で行う",
    "発射できなかったときは、すぐに近づかない。離れた位置から圧力を抜いてから近づく",
    "子どもだけで行わない",
)
RESULT_ROWS = (
    ("到達高度", "apogee_m", "m", 2),
    ("降下速度", "descent_speed_mps", "m/s", 2),
    ("最大速度", "max_speed_mps", "m/s", 2),
    ("飛行時間", "flight_time_s", "s", 2),
    ("着地点までの距離", "landing_distance_m", "m", 2),
)
MARGIN_ROWS = (
    ("静安定余裕（注水時）", "stability_margin_cal"),
    ("静安定余裕（空のとき）", "dry_stability_margin_cal"),
)


def safety_notes(design: BottleDesign) -> tuple[str, ...]:
    """Precautions printed on the sheet. The first names the pressure this design was flown at."""
    pressure = (
        f"圧力は {design.initial_gauge_pressure_pa / 1000:.0f} kPa までにする。"
        "ボトルと発射台に表示された上限も超えない"
    )
    return (pressure, *_SAFETY_NOTES)


def sheet_sections(
    design: BottleDesign,
    result: SimResult,
    summary: dict[str, Any],
    dispersion: DispersionResult | None,
) -> dict[str, dict[str, str]]:
    """Section -> label -> text, in reading order."""
    mass = summary["mass"]
    water_ml = design.bottle_volume_m3 * design.water_fill_frac * 1e6
    chute = design.parachute_diameter_m if design.has_parachute else None
    launch = {
        "ボトル容量": f"{design.bottle_volume_m3 * 1000:g} L",
        "注水量": f"{water_ml:.0f} mL",
        "初期圧力差": f"{design.initial_gauge_pressure_pa / 1000:.0f} kPa",
        "噴射口の径": f"{design.nozzle_diameter_m * 1000:.1f} mm",
        "フィン": "あり" if design.has_fins else "なし",
        "パラシュートの直径": "なし" if chute is None else f"{chute * 1000:.0f} mm",
    }
    masses = {
        "機体の乾燥質量": f"{mass['dry_mass_kg'] * 1000:.0f} g",
        "搭載質量": f"{mass['payload_mass_kg'] * 1000:.0f} g",
        "離床質量（水を含む）": f"{mass['liftoff_mass_kg'] * 1000:.0f} g",
    }
    results = {"判定": "合格" if result.success else "不合格"}
    for label, key, unit, digits in RESULT_ROWS:
        if key in result.metrics:
            results[label] = f"{result.metrics[key]:.{digits}f} {unit}"
    for label, key in MARGIN_ROWS:
        value = result.metrics.get(key)
        results[label] = NO_MARGIN if value is None else f"{value:.2f} cal"
    if dispersion is not None:
        passes = round(dispersion.n * dispersion.success_rate)
        results["多数回試行"] = (
            f"{passes} / {dispersion.n} 回 成功（{dispersion.success_rate * 100:.1f} %、"
            f"seed {dispersion.seed}）"
        )
    return {"打ち上げの条件": launch, "質量": masses, "シミュレーションの結果": results}


def render_design_sheet(
    design: BottleDesign,
    result: SimResult,
    summary: dict[str, Any],
    dispersion: DispersionResult | None,
) -> bytes:
    font = japanese_font()
    body = ParagraphStyle(
        "sheet-body", fontName=font, fontSize=9, leading=15, textColor=INK, wordWrap="CJK"
    )
    heading = ParagraphStyle("sheet-heading", parent=body, fontSize=20, leading=28, spaceAfter=12)
    section = ParagraphStyle(
        "sheet-section", parent=body, fontSize=12, leading=18, spaceBefore=12, spaceAfter=4
    )
    small = ParagraphStyle("sheet-small", parent=body, fontSize=7.5, leading=12)

    def p(text: object, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    def table(rows: list[list[Any]], widths: list[float], header: bool = False) -> Table:
        styles = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd8d2")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            styles.append(("BACKGROUND", (0, 0), (-1, 0), PALE))
        built = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        built.setStyle(TableStyle(styles))
        return built

    snapshot = design.model_dump(mode="json")
    design_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]
    story: list[Any] = [
        p("ROCKETWRIGHT / BUILD SHEET", small),
        p(TITLE, heading),
        HRFlowable(width="100%", color=INK),
        Spacer(1, 8),
        p(
            "シミュレーションの合格案から作った製作票です。この案は機体の構成（搭載部・回収装置の"
            "収め方、フィンの材料と寸法）を定めていないため、組立の手順文と原寸型紙は含みません。"
            "機体の寸法もこの案では定まっていません。側面図の寸法は代表形状の値です。"
        ),
    ]
    for title, rows in sheet_sections(design, result, summary, dispersion).items():
        story.append(p(title, section))
        story.append(table([[p(k), p(v)] for k, v in rows.items()], [190, 290]))

    story.append(PageBreak())
    story.append(p("部品表", section))
    bom = [[p("品名", small), p("数量", small), p("質量 g", small), p("価格 円", small)]]
    for row in summary["bom"]:
        grams = "—" if row["mass_kg"] is None else f"{row['mass_kg'] * 1000:.1f}"
        price = "—" if row["price_jpy"] is None else f"{row['price_jpy']:,.0f}"
        name = row["name"].replace("~", "約")  # the fallback CID font draws no ASCII tilde
        bom.append([p(name, small), p(row["qty"], small), p(grams, small), p(price, small)])
    story.append(table(bom, [270, 50, 70, 90], header=True))
    story.append(Spacer(1, 8))
    cost = f"{summary['cost_jpy']:,.0f}"
    story.append(p(f"費用の合計 {cost} 円（見積り。購入価格の保証ではありません）"))

    story.append(p(SAFETY_TITLE, section))
    story.extend(p(f"・{text}") for text in safety_notes(design))
    story.append(p("製作の前に実物で確認すること", section))
    story.extend(p(f"□ {text}") for text in PENDING_CHECKS)
    if result.warnings:
        story.append(p("シミュレーションの注意", section))
        story.extend(p(text, small) for text in result.warnings)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(INK)
        canvas.drawString(54, 29, f"設計 {design_hash} / 実物確認前")
        canvas.drawRightString(A4[0] - 54, 29, str(doc.page))
        canvas.restoreState()

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=54,
        leftMargin=54,
        topMargin=44,
        bottomMargin=48,
        title=TITLE,
        author="RocketWright",
        subject=f"design {design_hash}",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
