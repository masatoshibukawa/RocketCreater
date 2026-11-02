#!/usr/bin/env python
"""Run a demo scenario through the design loop and print one line per event.

    uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml [--dummy]

`--dummy` uses the scripted fake client (rocketwright.agent.fake_client): no network, no API
key. Without it the real Claude API is used (ANTHROPIC_API_KEY must be set in the environment).
Exit status is 1 when the classified tier differs from `expected.tier` or the loop ends in error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import FakeAnthropicClient, build_demo_script
from rocketwright.agent.loop import AgentConfig, run_design_loop

_MAX_LINE = 220


def _compact(payload: dict[str, Any]) -> str:
    slim = dict(payload)
    result = slim.get("result")
    if isinstance(result, dict) and "trace" in result:
        result = {**result, "trace": f"<{len(result['trace'])} points>"}
        slim["result"] = result
    text = json.dumps(slim, ensure_ascii=False, default=str)
    return text if len(text) <= _MAX_LINE else text[: _MAX_LINE - 3] + "..."


def _format(ev: AgentEvent) -> str:
    return f"[{ev.t_s:7.3f}s] attempt={ev.attempt:2d} {ev.type:<11} {_compact(ev.payload)}"


async def _run(scenario: dict[str, Any], dummy: bool) -> int:
    text = scenario["request_text"]
    env = scenario.get("env") or {}
    seed = scenario.get("seed")
    expected_tier = (scenario.get("expected") or {}).get("tier")
    client = None
    if dummy:
        client = FakeAnthropicClient(build_demo_script(expected_tier, text, env, seed))
    cfg = AgentConfig.load()
    print(f"# scenario {scenario.get('name')}  model={cfg.design_model}  dummy={dummy}")
    print(f"# request: {text}")
    classified: str | None = None
    last: AgentEvent | None = None
    async for ev in run_design_loop(text, client=client, config=cfg, env=env, seed=seed):
        print(_format(ev), flush=True)
        last = ev
        if ev.type == "tool_result" and ev.payload.get("name") == "classify_requirement":
            classified = (ev.payload.get("result") or {}).get("tier")
    status = 0
    if expected_tier and classified != expected_tier:
        print(f"# tier mismatch: expected {expected_tier}, got {classified}")
        status = 1
    if last is None or last.type == "error":
        status = 1
    print(
        f"# done: classified tier={classified} final={last.type if last else None} status={status}"
    )
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scenario", type=Path, help="scenario YAML (scenarios/*.yaml)")
    parser.add_argument("--dummy", action="store_true", help="use the scripted fake client")
    args = parser.parse_args(argv)
    with args.scenario.open(encoding="utf-8") as f:
        scenario = yaml.safe_load(f)
    return asyncio.run(_run(scenario, args.dummy))


if __name__ == "__main__":
    sys.exit(main())
