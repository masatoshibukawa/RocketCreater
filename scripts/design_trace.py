#!/usr/bin/env python
"""Run one design and keep every step: what Claude tried, what the code returned, what changed.

    set -a; . ./.env; set +a
    uv run python scripts/design_trace.py "要求文" --out output/trace --env '{"wind_speed_mps": 2}'

Writes events.jsonl (every event in full) and trace.md (one row per simulation). This calls
the paid API: --effort, --max-attempts and --max-turns bound the cost. Default effort is medium.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import anthropic

from rocketwright.agent.loop import AgentConfig, run_design_loop

SIMULATION_TOOLS = {"simulate_design", "design_from_parts", "design_stage", "auto_design"}
METRICS = ("apogee_m", "perigee_m", "descent_speed_mps", "rail_exit_speed_mps", "max_q_pa")


class Usage:
    """Adds up the tokens of every response the design loop and the reviewers receive."""

    def __init__(self) -> None:
        self.by_model: dict[str, dict[str, int]] = {}

    def add(self, message: Any) -> None:
        row = self.by_model.setdefault(
            message.model, {"calls": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        )
        usage = message.usage
        row["calls"] += 1
        row["input"] += usage.input_tokens or 0
        row["output"] += usage.output_tokens or 0
        row["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        row["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0


class _CountedStream:
    def __init__(self, manager: Any, usage: Usage) -> None:
        self.manager, self.usage = manager, usage

    async def __aenter__(self) -> Any:
        stream = await self.manager.__aenter__()
        final = stream.get_final_message

        async def counted() -> Any:
            message = await final()
            self.usage.add(message)
            return message

        stream.get_final_message = counted
        return stream

    async def __aexit__(self, *exc: Any) -> Any:
        return await self.manager.__aexit__(*exc)


def counted_client(usage: Usage) -> anthropic.AsyncAnthropic:
    client = anthropic.AsyncAnthropic()
    stream, parse = client.messages.stream, client.messages.parse

    async def counted_parse(**kwargs: Any) -> Any:
        message = await parse(**kwargs)
        usage.add(message)
        return message

    client.messages.stream = lambda **kwargs: _CountedStream(stream(**kwargs), usage)
    client.messages.parse = counted_parse
    return client


def _design_of(call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tool_input = call.get("input") or {}
    return result.get("design") or tool_input.get("design") or {}


def _changed(previous: dict[str, Any], design: dict[str, Any]) -> str:
    keys = sorted(set(previous) | set(design))
    changes = [
        f"{key}: {previous.get(key)} → {design.get(key)}"
        for key in keys
        if previous and previous.get(key) != design.get(key)
    ]
    return "<br>".join(changes) or "—"


def _stage_row(number: int, result: dict[str, Any]) -> str:
    """A stage returns ranked candidates, not one design: show how many survived."""
    counts = ", ".join(
        f"{key} {result[key]}" for key in ("enumerated", "simulated", "passed") if key in result
    )
    return f"| {number} | design_stage: {result.get('stage')} | 候補の絞り込み | {counts} | — |"


def trace_table(events: list[dict[str, Any]]) -> str:
    calls = {e["payload"].get("id"): e["payload"] for e in events if e["type"] == "tool_call"}
    rows = ["| # | ツール | 前回からの変更 | 結果 | 不合格の理由 |", "|---|---|---|---|---|"]
    previous: dict[str, Any] = {}
    number = 0
    for event in events:
        payload = event["payload"]
        if event["type"] != "tool_result" or payload.get("name") not in SIMULATION_TOOLS:
            continue
        result = payload.get("result") or {}
        number += 1
        if payload.get("name") == "design_stage":
            rows.append(_stage_row(number, result))
            continue
        design = _design_of(calls.get(payload.get("id"), {}), result)
        metrics = result.get("metrics") or (result.get("sim") or {}).get("metrics") or {}
        shown = ", ".join(f"{k} {metrics[k]:.2f}" for k in METRICS if k in metrics) or "—"
        reasons = result.get("failure_reasons") or (result.get("sim") or {}).get("failure_reasons")
        rows.append(
            f"| {number} | {payload.get('name')} | {_changed(previous, design)} | {shown} "
            f"| {'; '.join(reasons or []) or '合格'} |"
        )
        previous = design or previous
    return "\n".join(rows)


async def run(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = AgentConfig.load().model_copy(
        update={
            "effort": args.effort,
            "max_attempts": args.max_attempts,
            "max_turns": args.max_turns,
        }
    )
    usage = Usage()
    started = time.time()
    events: list[dict[str, Any]] = []
    with (out / "events.jsonl").open("w", encoding="utf-8") as log:
        async for event in run_design_loop(
            args.request,
            client=counted_client(usage),
            config=config,
            env=json.loads(args.env),
            seed=args.seed,
        ):
            row = event.model_dump(mode="json")
            events.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            print(f"[{time.time() - started:6.1f}s] {event.type}", flush=True)
    summary = f"所要時間 {time.time() - started:.0f} 秒、使用量 {json.dumps(usage.by_model)}"
    table = trace_table(events)
    (out / "trace.md").write_text(
        f"# 設計の記録\n\n要求：{args.request}\n\n{summary}\n\n{table}\n", encoding="utf-8"
    )
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("--out", default="output/trace")
    parser.add_argument("--env", default="{}", help="Env fields as JSON")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--max-turns", type=int, default=16)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
