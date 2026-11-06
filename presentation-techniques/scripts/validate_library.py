#!/usr/bin/env python3
"""Check presentation taxonomy coverage, skill routing and local references."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIRS = (
    "research", "ted-talks", "fundraising", "by-duration",
    "hackathon-demos", "domain-hackathons", "academic-presentations", "demo-videos",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def main() -> None:
    catalog = json.loads(read(ROOT / "catalog.json"))
    records = catalog["documents"]
    recorded = {r["path"] for r in records}
    actual = {"README.md", "pitch-demo-strategy.md"}
    for dirname in RESEARCH_DIRS:
        actual.update(p.relative_to(ROOT).as_posix() for p in (ROOT / dirname).rglob("*.md"))
    require(len(records) == len(recorded), "Duplicate research document records")
    require(recorded == actual, f"Research coverage differs: {recorded ^ actual}")

    expected = {ROOT / "SKILL.md"}
    subskills = {}
    for category in catalog["categories"]:
        category_dir = ROOT / "categories" / category["skill"]
        expected.add(category_dir / "SKILL.md")
        for sub in category["subs"]:
            require(sub["skill"] not in subskills, "Duplicate subskill")
            subskills[sub["skill"]] = category_dir / sub["skill"] / "SKILL.md"
            expected.add(subskills[sub["skill"]])
    skill_files = set(ROOT.rglob("SKILL.md"))
    require(expected == skill_files, "Skill files differ from category catalog")
    for record in records:
        require(record["primary"] in subskills, f"Unknown primary route: {record['path']}")
        require(all(s in subskills for s in record["related"]), f"Unknown related route: {record['path']}")

    names = set()
    for skill_file in sorted(skill_files):
        body = read(skill_file)
        require(body.startswith("---\n"), f"No frontmatter: {skill_file}")
        name = re.search(r"^name: ([a-z0-9-]+)$", body, re.M)
        require(name is not None, f"Invalid name: {skill_file}")
        skill_name = name.group(1)
        require(skill_name == skill_file.parent.name, f"Folder/name mismatch: {skill_file}")
        require(len(skill_name) < 64 and skill_name not in names, f"Duplicate/long name: {skill_name}")
        names.add(skill_name)
        ui = read(skill_file.parent / "agents" / "openai.yaml")
        short = re.search(r'^  short_description: (".*")$', ui, re.M)
        require(short is not None, f"No UI short description: {skill_name}")
        require(25 <= len(json.loads(short.group(1))) <= 64, f"Invalid UI description length: {skill_name}")
        require(f"$" + skill_name in ui, f"No invocation in default prompt: {skill_name}")

    links = 0
    graph = {}
    for path in ROOT.rglob("*.md"):
        body = read(path)
        targets = []
        for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", body):
            target = target.split(' "')[0].strip("<>")
            if re.match(r"[a-zA-Z][\w+.-]*:", target):
                continue
            target = target.split("#")[0]
            if not target:
                continue
            resolved = (path.parent / unquote(target)).resolve()
            require(resolved.is_relative_to(ROOT), f"Reference leaves package: {path}: {target}")
            require(resolved.exists(), f"Broken reference: {path}: {target}")
            links += 1
            if resolved.suffix == ".md":
                targets.append(resolved)
        graph[path.resolve()] = targets
        for block in re.split(r"\n\s*\n", body):
            rows = [line for line in block.splitlines() if line.startswith("|")]
            if len(rows) > 1:
                require(len({line.count("|") for line in rows}) == 1, f"Uneven table: {path}")

    seen = set()
    pending = [(ROOT / "SKILL.md").resolve()]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        pending.extend(graph.get(path, []))
    require(all(p.resolve() in seen for p in expected), "Unreachable skill module")
    require(all((ROOT / p).resolve() in seen for p in recorded), "Unreachable research document")

    source = read(ROOT / "academic-presentations" / "sources.md")
    source_ids = re.findall(r"^\| ((?:S|R|F)\d+) \|", source, re.M)
    require(len(source_ids) == len(set(source_ids)) == 26, "Academic source IDs differ")
    timing = read(ROOT / "academic-presentations" / "05-timing-and-workbook.md")
    duration_rows = [line for line in timing.splitlines() if re.match(r"^\| \d+分 \|", line)]
    require(len(duration_rows) == 6, "Missing academic timing examples")
    for line in duration_rows:
        minutes = int(re.search(r"\| (\d+)分", line).group(1))
        seconds = [int(x) for x in re.findall(r"(\d+)秒", line)]
        total = int(line.split("|")[-2].strip())
        require(sum(seconds) == total == minutes * 60, f"Academic timing sum differs: {line}")

    demo = read(ROOT / "domain-hackathons" / "04-demo-playbook.md")
    intervals = re.findall(r"^\| (\d+):(\d+)–(\d+):(\d+) \| (\d+) \|", demo, re.M)
    require(len(intervals) == 7, "Missing 180-second demo intervals")
    end = 0
    for row in intervals:
        sm, ss, em, es, length = map(int, row)
        start, finish = sm * 60 + ss, em * 60 + es
        require(start == end and finish - start == length, "Discontinuous demo timeline")
        end = finish
    require(end == 180, "Demo timeline does not end at 180 seconds")

    video_sources = read(ROOT / "demo-videos" / "sources.md")
    video_ids = re.findall(r"^\| ([GC]\d+) \|", video_sources, re.M)
    require(len(video_ids) == len(set(video_ids)) == 16, "Demo-video source IDs differ")
    observations = json.loads(read(ROOT / "demo-videos" / "media-observations.json"))["items"]
    require(len(observations) == 8, "Media observation inventory differs")
    for item in observations:
        require(bool(re.fullmatch(r"[a-f0-9]{64}", item["sha256"])), "Invalid media hash")
        require(item["samples"] == sorted(set(item["samples"])), "Invalid sample order")
        require(all(0 <= t < item["duration_seconds"] for t in item["samples"]), "Sample outside media")

    video_workbook = read(ROOT / "demo-videos" / "04-workbook.md")
    for line in video_workbook.splitlines():
        if re.match(r"^\| \d+秒 \|", line):
            seconds = [int(x) for x in re.findall(r"(\d+)秒", line)]
            require(sum(seconds[1:]) == seconds[0], "Short video duration sum differs")
    video_intervals = re.findall(r"^\| (\d+):(\d+)–(\d+):(\d+) \| (\d+) \|", video_workbook, re.M)
    end = 0
    for row in video_intervals:
        sm, ss, em, es, length = map(int, row)
        start, finish = sm * 60 + ss, em * 60 + es
        require(start == end and finish - start == length, "Discontinuous video workbook timeline")
        end = finish
    require(len(video_intervals) == 7 and end == 180, "Video workbook does not total 180 seconds")

    print(json.dumps({
        "research_documents": len(records),
        "coverage": "complete",
        "categories": len(catalog["categories"]),
        "subcategories": len(subskills),
        "skill_documents": len(skill_files),
        "ui_metadata": len(skill_files),
        "valid_local_links": links,
        "all_modules_and_documents_reachable": True,
        "academic_source_ids": len(source_ids),
        "demo_video_source_ids": len(video_ids),
        "observed_media_files": len(observations),
        "timing_checks": "passed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
