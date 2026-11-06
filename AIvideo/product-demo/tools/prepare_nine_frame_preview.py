"""Lay out the nine discussion images without altering their pixels."""

from html import escape
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def main():
    plan = json.loads((ROOT / "nine-frame-plan.json").read_text(encoding="utf-8"))
    target = REPO / "output/media/product-demo/planning/nine-frame-board.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    assert len(plan["scenes"]) == 9
    previous = 0
    cards = []
    for scene in plan["scenes"]:
        assert scene["start_s"] == previous < scene["end_s"]
        previous = scene["end_s"]
        path = REPO / scene["image"]
        assert path.is_file() and path.resolve().is_relative_to(REPO / "output/media/product-demo")
        href = Path(os.path.relpath(path, target.parent)).as_posix()
        period = "–".join(f"{t//60:02}:{t%60:02}" for t in (scene["start_s"], scene["end_s"]))
        cards.append(f'<article><a href="{escape(href)}"><img src="{escape(href)}" alt="{escape(scene["title"])}"></a><div><small>{scene["id"][:2]} / {period}</small><h2>{escape(scene["title"])}</h2><p>{escape(scene["note"])}</p></div></article>')
    assert previous == plan["duration_s"] == 175
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RocketWright / 9枚の構成イメージ</title><style>
    *{box-sizing:border-box}body{margin:0;background:#070b14;color:#f2f5fa;font:16px/1.65 system-ui,'Yu Gothic',sans-serif}main{max-width:1700px;margin:auto;padding:32px}h1{font-size:30px;line-height:1.3}header{margin-bottom:28px}header p{max-width:1000px;color:#b4c8be}strong,small{color:#78efb6}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}article{background:#101b23;border:1px solid #29483e;border-radius:10px;overflow:hidden}article img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#030709}article div{padding:14px 18px}h2{font-size:19px;margin:5px 0}article p{font-size:13px;color:#a8b9b5;margin:7px 0}a:focus-visible{outline:3px solid #78efb6;outline-offset:3px}@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){main{padding:18px}.grid{grid-template-columns:1fr}} </style><main><header><p>ROCKETWRIGHT / STRUCTURE & LOOK DISCUSSION</p><h1>なぜ必要か → この2人が取り組む理由 → どうつなぐか → 実物へ</h1><p><strong>冒頭3場面・50秒で必要性を伝える175秒案。</strong>画像を開くと元サイズで確認できます。7枚はAIによる構図案、7番は既存UI資料、8番は印刷実写です。実行時のデモ・物理的検証・完成動画とは区別します。</p></header><section class="grid" aria-label="9枚の絵コンテ">'''
    target.write_text(page + "".join(cards) + "</section></main></html>\n", encoding="utf-8")
    print(json.dumps({"images": len(cards), "duration_s": previous, "preview": target.relative_to(REPO).as_posix()}))


if __name__ == "__main__":
    main()
