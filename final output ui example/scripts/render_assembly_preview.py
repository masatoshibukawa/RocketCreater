#!/usr/bin/env python3
"""Create a four-page assembly-manual layout preview from the example data.

Requires reportlab 4.4.9 and explicitly supplied Japanese TrueType/TTC fonts.
Writes only the requested PDF and optional Markdown paths. It does not update
the package manifest, generate CAD, or approve a manufacturing procedure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

INK = colors.HexColor("#17202c")
MUTED = colors.HexColor("#4b5869")
BLUE = colors.HexColor("#2459a6")
LINE = colors.HexColor("#cad2dd")
PALE = colors.HexColor("#f2f5f9")
PENDING = colors.HexColor("#725020")
WIDTH = A4[0] - 36 * mm


def read(root: Path, name: str) -> dict:
    path = root / name
    path.resolve(strict=True).relative_to(root)
    return json.loads(path.read_text(encoding="utf-8"))


def markdown(steps: dict) -> str:
    lines = [
        "# 組立手順書 / 内容設計見本", "",
        f"設計版：{steps['design_revision']}。手順版：{steps['procedure_revision']}。",
        "状態：未発行。実機用の確定手順ではありません。", "",
        "工程IDはWeb・PDF・動画で共通にします。未確定の作業値・図・経路を補完しません。",
        "",
    ]
    for step in steps["steps"]:
        lines += [
            f"## {step['step_id']} / {step['title']}", "",
            "対象部品：" + "、".join(step["part_ids"]) + "。",
            "前提工程：" + ("、".join(step["depends_on"]) or "なし") + "。",
            f"状態：{step['status']}。",
            "操作：" + (step["operation"]["text"] or "未確定。実行手順は未発行。"),
            "担当・工具・向き・保持・手と工具の経路・完了基準：未確定。",
            "", "確認が必要なこと：", "",
            *["- " + item for item in step["blockers"]],
            "",
        ]
    lines += [
        "## 実作業の記録", "",
        "工程ID・版・作業者・工具・日付・観察方法・結果・資料を記録します。",
        "初期状態は未記録。手順の閲覧や記入欄の存在を実施済みにはしません。", "",
    ]
    return "\n".join(lines)


def build(root: Path, output: Path, font: Path, bold: Path) -> None:
    procedure = read(root, "assembly/steps.json")
    design = read(root, "design/design.json")
    equipment = read(root, "design/equipment.json")
    status = read(root, "verification/technical-status.json")
    sources = read(root, "provenance/sources.json")
    for record in (design, equipment, status, sources):
        if (record["package_id"], record["design_revision"]) != (
            procedure["package_id"], procedure["design_revision"]
        ):
            raise ValueError("Input versions differ")
    pdfmetrics.registerFont(TTFont("JP", str(font), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("JP-Bold", str(bold), subfontIndex=0))
    pdfmetrics.registerFontFamily("JP", normal="JP", bold="JP-Bold")
    styles = {
        "title": ParagraphStyle("title", fontName="JP-Bold", fontSize=25,
                                leading=36, textColor=INK, spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName="JP-Bold", fontSize=18,
                             leading=28, textColor=INK, spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName="JP-Bold", fontSize=12,
                             leading=19, textColor=INK, spaceBefore=12, spaceAfter=5),
        "body": ParagraphStyle("body", fontName="JP", fontSize=10.5,
                               leading=17, textColor=INK, spaceAfter=7, wordWrap="CJK"),
        "small": ParagraphStyle("small", fontName="JP", fontSize=8.5,
                                leading=13, textColor=MUTED, spaceAfter=5, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName="JP", fontSize=9.5,
                               leading=15, textColor=INK, wordWrap="CJK"),
        "badge": ParagraphStyle("badge", fontName="JP-Bold", fontSize=10.5,
                                leading=18, textColor=PENDING, spaceAfter=8),
    }

    def p(text, style="body"):
        return Paragraph(escape(str(text)), styles[style])

    def table(rows, widths, header=False):
        converted = [[p(value, "cell") for value in row] for row in rows]
        t = Table(converted, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, -1), .5, LINE),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), PALE)]
        t.setStyle(TableStyle(commands))
        return t

    class FigureArea(Flowable):
        """A labelled layout area, deliberately not a manufacturing illustration."""
        def __init__(self):
            super().__init__()
            self.width, self.height = WIDTH, 57 * mm

        def draw(self):
            c = self.canv
            c.setFillColor(PALE)
            c.setStrokeColor(LINE)
            c.rect(0, 0, self.width, self.height, fill=1, stroke=1)
            c.setFillColor(MUTED)
            c.setFont("JP-Bold", 12)
            c.drawCentredString(self.width / 2, 34 * mm, "採用CADからの組立図を配置")
            c.setFont("JP", 9.5)
            c.drawCentredString(self.width / 2, 25 * mm, "部品ID・向き・保持・手と工具の経路")
            c.drawCentredString(self.width / 2, 16 * mm, "図版の配置例 / 形状と位置は未確定")

    titles = ["読む順序と対象", "部品・工具・作業条件", "工程 A-020 のページ例", "実作業の記録と未完了事項"]
    page_count = []

    def page(canvas, doc):
        n = doc.page
        page_count.append(n)
        canvas.saveState()
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(18 * mm, 278 * mm, A4[0] - 18 * mm, 278 * mm)
        canvas.setFont("JP-Bold", 9)
        canvas.setFillColor(INK)
        canvas.drawString(18 * mm, 282 * mm, "RocketWright / ASSEMBLY GUIDE")
        canvas.setFont("JP", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 18 * mm, 282 * mm, "内容設計見本")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(.5)
        canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
        footer = (
            f"設計 {procedure['design_revision']} / 手順 {procedure['procedure_revision']}"
            " / 実機用は未発行"
        )
        canvas.setFont("JP", 8)
        canvas.drawString(18 * mm, 10 * mm, footer)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{n} / 4")
        if n <= len(titles):
            canvas.bookmarkPage(f"page{n}")
            canvas.addOutlineEntry(titles[n - 1], f"page{n}", level=0)
        canvas.restoreState()

    story = []
    story += [
        p("組立手順書", "title"),
        p("ペットボトル水ロケット / 内容設計見本", "h1"),
        p("下書き・未確定 / 実機用の手順は未発行", "badge"),
        p("このPDFは、印刷して使う手順書の情報と配置を確認するための見本です。"
          "部品・寸法・取付方法・工具・作業条件は確定していません。"),
        table([
            ["対象", "ペットボトル水ロケット"],
            ["設計版 / 手順版", f"{procedure['design_revision']} / {procedure['procedure_revision']}"],
            ["対象者", "成人 / 子ども＋成人。年齢帯・手・役割は未設定"],
            ["発行状態", "未発行。機体の技術評価・製作承認を含まない"],
        ], [43 * mm, WIDTH - 43 * mm]),
        p("読む順序", "h2"),
        p("1. 部品と作業条件を確認する。"),
        p("2. 工程ごとの図・操作・確認基準を読む。未確定なら条件を決める。"),
        p("3. 実物で行った作業と観察だけを記録する。"),
        p("この見本で確認すること", "h2"),
        p("対象版と工程IDが分かること、必要な部品・道具へ辿れること、"
          "図と本文・記録欄が対応することを確認します。"),
        p("まだ含めないもの", "h2"),
        p("確定した製作図、具体的な締付け・接着・加圧操作、合格した組立評価、"
          "実機の試験結果は含めません。"),
        PageBreak(),
    ]
    part_rows = [["部品ID / 版", "部品名", "数量 / 調達"]]
    for part in design["parts"]:
        quantity = "未確定" if part["quantity"] is None else str(part["quantity"])
        procurement = "購入・未選定" if part["procurement"] == "purchase" else "方法未確定"
        part_rows.append([f"{part['part_id']}\n{part['revision']}", part["name_ja"],
                          f"{quantity}\n{procurement}"])
    story += [
        p("01 / 部品・工具・作業条件", "h1"),
        p("工程 A-010 / 部品と条件を照合する", "h2"),
        table(part_rows, [45 * mm, 76 * mm, WIDTH - 121 * mm], header=True),
        p("作業者・工具・治具", "h2"),
        table([
            ["作業者", "成人、子ども＋成人の条件を別に確認する。役割は未確定"],
            ["手袋・手の条件", "未設定。対象者のデータと適用範囲が必要"],
            ["工具・保持具", "未選定。機種・寸法・必要な保持を確認する"],
            ["作業条件・根拠", "未確定。選んだ部品と製品資料に結び付ける"],
        ], [43 * mm, WIDTH - 43 * mm]),
        p("作業前の確認欄", "h2"),
        p("[ ] 部品ID・版・数量を照合した。"),
        p("[ ] 作業者・工具・保持具の条件を記録した。"),
        p("[ ] 未確定項目を設計の確認へ戻した。"),
        p("上の欄は未記入です。チェック欄があることや手順を閲覧したことを、"
          "実作業の実施・完了とは扱いません。", "small"),
        PageBreak(),
    ]
    active = next(item for item in procedure["steps"] if item["step_id"] == "A-020")
    story += [
        p("02 / " + active["title"], "h1"),
        p(f"工程 {active['step_id']} / 前提 A-010 / 状態：保留", "badge"),
        FigureArea(), Spacer(1, 3 * mm),
        p("図版は表示領域の見本です。実機の取付形状・経路を示した図ではありません。", "small"),
        table([
            ["対象部品", "、".join(active["part_ids"])],
            ["操作", "取付構成が未確定のため、実行する手順は未発行"],
            ["担当・保持", "未確定。両手と支援者・治具の役割を決める"],
            ["手と工具の経路", "進入・操作・離脱を別々に確認する。評価は未実施"],
            ["作業条件と根拠", "未確定。根拠のない取付・締付け値を補わない"],
            ["完了基準", "未確定。確認箇所・方法・許容条件を決める"],
        ], [43 * mm, WIDTH - 43 * mm]),
        p("条件がそろわないとき", "h2"),
        p("不足事項を記録して設計確認へ戻します。このページを具体的な製作・加工操作に"
          "読み替えず、確定した部品・手順と評価をそろえてから発行します。"),
        PageBreak(),
    ]
    story += [
        p("03 / 実作業の記録", "h1"),
        p("以下は印刷用の未記入欄です。紙への記入と、Web側の実施記録への登録は別に扱います。"),
        table([
            ["日付 / 記録者", "________________________________"],
            ["作業者・工具の条件", "________________________________"],
            ["対象版", f"{procedure['design_revision']} / {procedure['procedure_revision']}"],
        ], [52 * mm, WIDTH - 52 * mm]),
        Spacer(1, 4 * mm),
        table([
            ["工程ID", "観察する項目", "結果・方法・資料"],
            ["A-010", "部品・版・数量", "________________"],
            ["A-020", "向き・保持", "________________"],
            ["A-020", "手と工具の進入・操作・離脱", "________________"],
            ["A-020", "操作後の状態・完了基準", "________________"],
        ], [27 * mm, 88 * mm, WIDTH - 115 * mm], header=True),
        p("現在の未完了事項", "h2"),
    ]
    story += [p("- " + item) for item in status["blockers"]]
    story += [
        p("出典と対象データ", "h2"),
        p("ユーザーの要求：user-water-rocket、user-equipment、user-assembly、user-output。", "small"),
        p("工程：assembly/steps.json / 部品：design/design.json / "
          "条件：design/equipment.json / 状態：verification/technical-status.json。", "small"),
        p("Web・PDF・動画は同じ工程IDと対象版へ結び付けます。変更後は、影響する図・手順・"
          "確認結果を旧版として再確認します。", "small"),
    ]
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=25 * mm, bottomMargin=23 * mm,
        title="RocketWright 組立手順書 - 内容設計見本",
        author="RocketWright", subject="組立手順書のレイアウトと内容を検討する下書き",
        pageCompression=1,
    )
    doc.build(story, onFirstPage=page, onLaterPages=page)
    if max(page_count, default=0) != 4:
        raise ValueError("Preview overflowed the intended four-page layout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1] / "export-example")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--font-bold", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".pdf":
        parser.error("PDF output must have a .pdf extension")
    if args.markdown_output and args.markdown_output.suffix.lower() != ".md":
        parser.error("Markdown output must have a .md extension")
    targets = [args.output] + ([args.markdown_output] if args.markdown_output else [])
    for path in targets:
        if path.exists() and not args.overwrite:
            parser.error("Output exists; choose a new path or specify --overwrite")
    if len({path.resolve() for path in targets}) != len(targets):
        parser.error("PDF and Markdown output paths must differ")
    root = args.root.resolve(strict=True)
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
    build(root, args.output, args.font, args.font_bold or args.font)
    if args.markdown_output:
        args.markdown_output.write_text(
            markdown(read(root, "assembly/steps.json")), encoding="utf-8", newline="\n"
        )
    print("Layout preview created; operational instructions remain unreleased.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
