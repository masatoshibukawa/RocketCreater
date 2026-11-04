#!/usr/bin/env python
"""Pre-freeze inspection of every scenario in scenarios/ (dummy client, no network).

    uv run python scripts/check_scenarios.py [--json-dir DIR] [scenarios/*.yaml ...]

For each scenario the design loop is run with the scripted fake client and the event log is
checked for: a `final` event with at least one passing design, no provenance violations, at
least one `review` event, `derive_requirements` / `find_reference_designs` / `run_dispersion`
tool results, a final `reference_id` that is a catalog reference id and `derived_targets` that
is the derive_requirements tool_use id, and that every tool_use id cited in a final design's
`sources` map (and `source_id`) is the id of a `tool_call` event seen earlier.
Wall time per scenario is printed (the commercial seed is pitch-tuned: a few seconds);
`--json-dir` writes the final payload of each scenario.
Exit status is 1 when any check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import FakeAnthropicClient, build_demo_script
from rocketwright.agent.loop import AgentConfig, run_design_loop
from rocketwright.references import load_references

ROOT = Path(__file__).resolve().parent.parent
MAX_WALL_S = 10.0


async def _collect(scenario: dict[str, Any]) -> list[AgentEvent]:
    text = scenario["request_text"]
    env = scenario.get("env") or {}
    seed = scenario.get("seed")
    tier = (scenario.get("expected") or {}).get("tier")
    client = FakeAnthropicClient(
        build_demo_script(tier, text, env, seed, reviews=True, story=scenario.get("story"))
    )
    cfg = AgentConfig.load()
    return [ev async for ev in run_design_loop(text, client=client, config=cfg, env=env, seed=seed)]


def check_events(events: list[AgentEvent], expected_tier: str | None) -> list[str]:
    """Return the list of problems found (empty = all checks pass)."""
    problems: list[str] = []
    types = [e.type for e in events]
    if not events or events[-1].type != "final":
        problems.append(f"last event is {types[-1] if types else None!r}, not 'final'")
        return problems
    final = events[-1].payload
    result = final.get("result")
    if not isinstance(result, dict):
        problems.append(f"final.result is not a dict (parse_error={final.get('parse_error')!r})")
        return problems
    designs = [d for d in result.get("designs", []) if isinstance(d, dict)]
    passing = [d for d in designs if d.get("passed")]
    if not passing:
        problems.append("no passing design in final.result.designs")
    if final.get("provenance_violations"):
        problems.append(f"provenance violations: {final['provenance_violations']}")
    if "review" not in types:
        problems.append("no review event")
    tool_ids_before: set[str] = set()
    for e in events:
        if e.type == "tool_call":
            tool_ids_before.add(str(e.payload.get("id")))
    results = [e for e in events if e.type == "tool_result"]
    for tool in ("derive_requirements", "find_reference_designs", "run_dispersion"):
        if not any(e.payload.get("name") == tool for e in results):
            problems.append(f"no {tool} tool_result")
    derive_ids = [
        e.payload.get("id") for e in results if e.payload.get("name") == "derive_requirements"
    ]
    if result.get("derived_targets") not in derive_ids:
        problems.append(
            f"final.derived_targets {result.get('derived_targets')!r} is not a derive_requirements "
            f"tool_use id {derive_ids}"
        )
    catalog_ids = {entry.id for entry in load_references()}
    if result.get("reference_id") not in catalog_ids:
        problems.append(
            f"final.reference_id {result.get('reference_id')!r} is not a catalog reference id"
        )
    if any(e.payload.get("is_error") for e in results):
        bad = [e.payload.get("name") for e in results if e.payload.get("is_error")]
        problems.append(f"tool errors: {bad}")
    classified = next(
        (
            (e.payload.get("result") or {}).get("tier")
            for e in results
            if e.payload.get("name") == "classify_requirement"
        ),
        None,
    )
    if expected_tier and classified != expected_tier:
        problems.append(f"classified tier {classified!r} != expected {expected_tier!r}")
    for i, d in enumerate(designs):
        sources = d.get("sources")
        if not isinstance(sources, dict) or not sources:
            problems.append(f"design[{i}] has no sources map")
            continue
        for key, sid in sources.items():
            if str(sid) not in tool_ids_before:
                problems.append(f"design[{i}].sources[{key!r}] cites unknown tool_use id {sid!r}")
        for key in d.get("metrics", {}) or {}:
            if key not in sources:
                problems.append(f"design[{i}] metric {key!r} has no entry in sources")
        if d.get("source_id") and str(d["source_id"]) not in tool_ids_before:
            problems.append(f"design[{i}].source_id {d['source_id']!r} is not a tool_use id")
        rate = d.get("success_rate")
        if rate is not None and "success_rate" not in sources:
            problems.append(f"design[{i}] quotes success_rate without a source")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenarios", nargs="*", type=Path)
    parser.add_argument("--json-dir", type=Path, help="write <name>.final.json per scenario")
    args = parser.parse_args(argv)
    files = args.scenarios or sorted((ROOT / "scenarios").glob("*.yaml"))
    status = 0
    for path in files:
        with path.open(encoding="utf-8") as f:
            scenario = yaml.safe_load(f)
        t0 = time.perf_counter()
        events = asyncio.run(_collect(scenario))
        wall = time.perf_counter() - t0
        problems = check_events(events, (scenario.get("expected") or {}).get("tier"))
        if wall > MAX_WALL_S:
            problems.append(f"wall time {wall:.1f}s > {MAX_WALL_S}s")
        final = events[-1].payload if events else {}
        designs = (final.get("result") or {}).get("designs", []) if final else []
        rates = [d.get("success_rate") for d in designs if isinstance(d, dict)]
        print(
            f"{path.name:<22} wall={wall:5.2f}s events={len(events):3d} "
            f"designs={len(designs)} success_rate={rates} "
            f"{'OK' if not problems else 'FAIL'}"
        )
        for p in problems:
            print(f"    - {p}")
        if problems:
            status = 1
        if args.json_dir and events:
            args.json_dir.mkdir(parents=True, exist_ok=True)
            out = args.json_dir / f"{path.stem}.final.json"
            out.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    return status


if __name__ == "__main__":
    sys.exit(main())
