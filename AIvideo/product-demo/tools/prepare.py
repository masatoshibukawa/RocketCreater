"""Validate the demo plan and prepare scripts, draft subtitles and a rough storyboard.

Only Python's standard library is needed. No capture, model call or publication occurs.
"""

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
EXPECTED_PATHS = {
    "source": "AIvideo/product-demo",
    "work": "output/media/product-demo",
    "release": "assets/product-demo/overview",
}


def timestamp(seconds):
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def mmss(seconds):
    return f"{int(seconds)//60:02d}:{int(seconds)%60:02d}"


def wrap_caption(text):
    if len(text) <= 30:
        return text
    low, high = max(1, len(text) - 30), min(30, len(text) - 1)
    breaks = [i + 1 for i, char in enumerate(text) if char in "、。" and low <= i + 1 <= high]
    cut = min(breaks, key=lambda i: abs(i - len(text) / 2)) if breaks else len(text) // 2
    while cut < len(text) - 1 and text[cut] in "、。，．！？」』）":
        cut += 1
    return text[:cut] + "\n" + text[cut:]


def validate(plan):
    assert plan["schema_version"] == 1 and plan["status"] == "planning"
    assert plan["event"]["language"] == "ja"
    assert sum(plan["event"]["rubric_percent"].values()) == 100
    assert datetime.fromisoformat(plan["event"]["deadline"]).utcoffset() is not None
    production = plan["production"]
    assert production["paths"] == EXPECTED_PATHS
    for relative in EXPECTED_PATHS.values():
        assert (REPO / relative).resolve().is_relative_to(REPO)
    assert production["width"] >= 1920 and production["height"] >= 1080
    assert production["target_duration_s"] < plan["event"]["max_duration_s"] <= 180
    scenario = (REPO / plan["scenario"]["source"]).read_text(encoding="utf-8")
    request = re.search(r'^request_text:\s*("[^\n]*")\s*$', scenario, re.MULTILINE)
    seed = re.search(r'^seed:\s*(\d+)\s*$', scenario, re.MULTILINE)
    assert request and json.loads(request.group(1)) == plan["scenario"]["request_text"]
    assert seed and int(seed.group(1)) == plan["scenario"]["seed"]
    assert production["capture_execution"] == "not_run"
    previous = 0
    seen = set()
    for shot in plan["shots"]:
        assert shot["id"] not in seen
        seen.add(shot["id"])
        assert shot["start_s"] == previous and shot["end_s"] > previous
        assert shot["stage"] in {"design", "analysis", "exports"}
        assert shot["media_kind"] == "app_capture" and shot["status"] == "planned"
        assert shot["voice_lines"] and all(0 < len(s) <= 54 for s in shot["voice_lines"])
        assert (shot["end_s"] - shot["start_s"]) / len(shot["voice_lines"]) >= 1.25
        assert all(key in plan["evidence"] for key in shot["evidence_ids"])
        previous = shot["end_s"]
    assert previous == production["target_duration_s"]
    assert all(e["status"] == "not_collected" and not e["artifacts"] for e in plan["evidence"].values())
    release = json.loads((REPO / EXPECTED_PATHS["release"] / "manifest.json").read_text(encoding="utf-8"))
    assert release["status"] == "planning" and release["artifacts"] == []
    assert release["published_url"] is None
    assert all(value == "not_run" for value in release["verification"].values())
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", EXPECTED_PATHS["work"] + "/capture/check.mp4"], cwd=REPO)
    assert ignored.returncode == 0, "Working media must be ignored by Git"


def source_documents(plan):
    script = ["# 日本語ナレーション初稿", "", "`plan.json`から生成。未収録の仮台本。実行の結果に合わせて言葉を確定し、録音後に字幕を同期する。", ""]
    board = ["# 絵コンテ初稿", "", "`plan.json`から生成。実画面は未収録で、これは操作・構図・証拠を決めるための表。", "", "| ID・時刻 | 伝えること | 画面・操作 | 見る場所 | 必要な証拠 | 編集・確認 |", "| --- | --- | --- | --- | --- | --- |"]
    cues = []
    cue_no = 1
    for shot in plan["shots"]:
        period = mmss(shot["start_s"]) + "–" + mmss(shot["end_s"])
        script += [f"## {shot['id']} / {period} / {shot['message']}", ""]
        script += shot["voice_lines"]
        script += ["", f"画面：{shot['visual']}", "", f"確認：{shot['disclosure']}", ""]
        board.append("| " + " | ".join([shot["id"] + " / " + period, shot["message"], shot["visual"], shot["focus"], ", ".join(shot["evidence_ids"]), shot["disclosure"]]) + " |")
        duration = shot["end_s"] - shot["start_s"]
        for index, line in enumerate(shot["voice_lines"]):
            start = shot["start_s"] + duration * index / len(shot["voice_lines"])
            end = shot["start_s"] + duration * (index + 1) / len(shot["voice_lines"])
            wrapped = wrap_caption(line)
            cues += [str(cue_no), timestamp(start) + " --> " + timestamp(end), wrapped, ""]
            cue_no += 1
    return {
        ROOT / "script.ja.md": "\n".join(script).rstrip() + "\n",
        ROOT / "storyboard.md": "\n".join(board) + "\n",
        ROOT / "captions/overview.ja.srt": "\n".join(cues).rstrip() + "\n",
    }


def rough_html(plan):
    cards = []
    labels = {"design": "設計", "analysis": "解析", "exports": "出力"}
    for shot in plan["shots"]:
        tabs = "".join(f"<span class='{('active' if key == shot['stage'] else '')}'>{label}</span>" for key, label in labels.items())
        cards.append(f"""<section id='{shot['id']}'><h2>{shot['id']} / {mmss(shot['start_s'])}–{mmss(shot['end_s'])}</h2><h3>{escape(shot['message'])}</h3><div class='frame'><nav>{tabs}</nav><div class='layout'><aside>設計の相談<br><small>要求・条件・実際の説明</small></aside><article><strong>{labels[shot['stage']]}の実画面</strong><p>構成ラフ・未収録</p><small>数値と実行結果は未確定</small></article><aside>根拠と結果<br><small>同じ案件・設計・版</small></aside></div></div><p><b>操作：</b>{escape(shot['visual'])}</p><p><b>見る場所：</b>{escape(shot['focus'])}</p><p><b>声：</b>{escape(''.join(shot['voice_lines']))}</p><p class='note'>{escape(shot['disclosure'])}</p></section>""")
    return """<!doctype html><html lang='ja'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>RocketWright デモ絵コンテ初稿</title><style>body{margin:0;background:#f3f0e9;color:#202e32;font:16px 'Yu Gothic',system-ui}main{max-width:1050px;margin:auto;padding:30px}section{background:white;border:1px solid #d1d7d3;border-radius:10px;padding:24px;margin:24px 0}p{line-height:1.7}.frame{border:2px solid #58756b;border-radius:8px;overflow:hidden}nav{display:flex;gap:8px;background:#edf1ee;padding:10px}nav span{padding:8px 20px}.active{background:#315d50;color:white;border-radius:5px}.layout{display:grid;grid-template-columns:1fr 2fr 1fr;min-height:200px}aside,article{padding:20px;border-right:1px solid #d1d7d3}article{background:#f6f8f6;text-align:center}small{color:#5a6865}.note{border-left:4px solid #b77e36;padding-left:12px}@media(max-width:650px){.layout{grid-template-columns:1fr}main{padding:12px}}</style><main><h1>RocketWright / 175秒のデモ設計</h1><p>Built with Claude: Japan 2026向け。全て構成ラフで、実アプリのスクリーンショットや完成動画ではありません。</p>""" + "".join(cards) + "</main></html>\n"


def check_links():
    files = list(ROOT.glob("*.md")) + [REPO / EXPECTED_PATHS["release"] / "README.md"]
    for path in files:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = unquote(target.split("#")[0])
            assert (path.parent / target).exists(), (path.relative_to(REPO).as_posix(), target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check the plan and generated source documents without writing")
    args = parser.parse_args()
    plan = json.loads((ROOT / "plan.json").read_text(encoding="utf-8"))
    validate(plan)
    documents = source_documents(plan)
    work = REPO / EXPECTED_PATHS["work"]
    if not args.check:
        for path, content in documents.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for name in ("capture", "audio", "generated", "edit", "review", "planning"):
            (work / name).mkdir(parents=True, exist_ok=True)
        (work / "planning/storyboard.html").write_text(rough_html(plan), encoding="utf-8")
        template = work / "capture/capture-log.template.json"
        if not template.exists():
            template.write_text(json.dumps({"status": "template_not_a_record", "recording_started_at": None, "build_sha": None, "execution_mode": None, "run_id": None, "source_id": None, "project_id": None, "version": None, "model_id": None, "source_files": [], "cuts": [], "actual_elapsed_s": None, "verification": "not_run"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path, expected in documents.items():
        assert path.read_text(encoding="utf-8") == expected, f"Regenerate the source document: {path.name}"
    check_links()
    result = {"status": "passed", "scope": "planning integrity only", "duration_s": plan["production"]["target_duration_s"], "shots": len(plan["shots"]), "subtitle_cues": sum(len(s["voice_lines"]) for s in plan["shots"]), "work_media_ignored": True, "adopted_media": 0, "capture_and_media_validation": "not_run"}
    if not args.check:
        (work / "review/plan-validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
