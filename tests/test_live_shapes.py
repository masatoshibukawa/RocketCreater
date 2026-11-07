"""Live-API readiness without network: the exact kwargs loop.py passes to
`client.messages.stream` and review.py passes to `client.messages.parse`, captured through the
fake client, must have the shape the Claude API accepts for claude-haiku-5-5
(adaptive thinking, no budget_tokens, no forced tool_choice, tool_results leading the user turn
that follows every tool_use turn, all of them in ONE message)."""

from __future__ import annotations

from typing import Any

import pytest

from rocketwright.agent.fake_client import FakeAnthropicClient, build_demo_script
from rocketwright.agent.loop import AgentConfig, run_design_loop
from rocketwright.agent.review import ReviewVerdict
from rocketwright.agent.tools import TOOL_NAMES
from rocketwright.schema import Tier

TEXT = "1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。"
ENV = {"launch_latitude_deg": 36.0, "launch_altitude_m": 300, "wind_speed_mps": 3.0}
DESIGN_MODEL = "claude-haiku-5-5"
LIGHT_MODEL = "claude-haiku-5-5"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def captured() -> dict[str, list[dict[str, Any]]]:
    """Run the amateur demo script once (real solid physics) and keep every API call's kwargs."""
    import asyncio

    client = FakeAnthropicClient(build_demo_script("amateur", TEXT, ENV, seed=42, reviews=True))
    cfg = AgentConfig.load().model_copy(update={"allowed_tiers": tuple(Tier)})

    async def run() -> None:
        async for _ in run_design_loop(TEXT, client=client, config=cfg, env=ENV, seed=42):
            pass

    asyncio.run(run())
    assert client.calls, "the design model was never called"
    assert client.parse_calls, "the reviewers were never called"
    return {"stream": client.calls, "parse": client.parse_calls}


def _block_type(block: Any) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def _block_id(block: Any) -> str | None:
    return block.get("id") if isinstance(block, dict) else getattr(block, "id", None)


def test_design_stream_kwargs(captured):
    cfg = AgentConfig.load()
    for kw in captured["stream"]:
        assert kw["model"] == DESIGN_MODEL
        assert kw["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert "budget_tokens" not in kw and "budget_tokens" not in kw["thinking"]
        choice = kw.get("tool_choice")
        assert choice is None or choice.get("type") not in ("any", "tool")
        assert isinstance(kw["max_tokens"], int) and kw["max_tokens"] > 0
        assert kw["max_tokens"] == cfg.max_tokens
        assert kw["output_config"]["effort"] in ("low", "medium", "high", "xhigh", "max")
        assert "temperature" not in kw  # thinking forbids temperature overrides
        system = kw["system"]
        assert isinstance(system, str) or (
            isinstance(system, list) and all(b.get("type") == "text" for b in system)
        )
        assert all("strict" not in t for t in kw["tools"])  # API limit on nullable params
        assert len(kw["tools"]) == len(TOOL_NAMES)


def test_message_history_alternates_and_tool_results_lead_the_user_turn(captured):
    last = captured["stream"][-1]["messages"]
    assert last[0]["role"] == "user"
    assert isinstance(last[0]["content"], str) and TEXT in last[0]["content"]
    for prev, nxt in zip(last, last[1:], strict=False):
        assert prev["role"] != nxt["role"], "roles must alternate user/assistant"
    for i, msg in enumerate(last):
        if msg["role"] != "assistant":
            continue
        tool_ids = [_block_id(b) for b in msg["content"] if _block_type(b) == "tool_use"]
        if not tool_ids:
            continue
        assert i + 1 < len(last), "a tool_use turn must be answered"
        reply = last[i + 1]
        assert reply["role"] == "user" and isinstance(reply["content"], list)
        leading = []
        for b in reply["content"]:
            if _block_type(b) != "tool_result":
                break
            leading.append(b)
        assert [b["tool_use_id"] for b in leading] == tool_ids, (
            "every tool_use of the turn must be answered, in order, by tool_result blocks at the "
            "start of ONE user message"
        )
        assert all(isinstance(b["content"], str) for b in leading)
        trailing = reply["content"][len(leading) :]
        assert all(_block_type(b) == "text" for b in trailing)
        assert all(_block_type(b) != "tool_result" for b in trailing)


def test_reviewer_parse_kwargs(captured):
    cfg = AgentConfig.load()
    for kw in captured["parse"]:
        assert kw["model"] == LIGHT_MODEL
        assert kw["model"] == (cfg.reviewers.model or cfg.light_model)
        thinking = kw.get("thinking")
        assert thinking is None or thinking.get("type") == "adaptive"
        assert thinking is None or "budget_tokens" not in thinking
        assert "budget_tokens" not in kw
        choice = kw.get("tool_choice")
        assert choice is None or choice.get("type") not in ("any", "tool")
        assert "tools" not in kw
        assert isinstance(kw["max_tokens"], int) and kw["max_tokens"] > 0
        assert kw["output_config"]["effort"] in ("low", "medium", "high", "xhigh", "max")
        assert kw["output_format"] is ReviewVerdict
        assert isinstance(kw["system"], str) and kw["system"]
        msgs = kw["messages"]
        assert len(msgs) == 1 and msgs[0]["role"] == "user"
        assert isinstance(msgs[0]["content"], str)
        assert "trace" not in msgs[0]["content"] or "trace_point_count" in msgs[0]["content"]
