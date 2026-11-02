"""Tests for the design loop with a scripted fake Claude client (no network)."""

import json

import pytest

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import (
    FakeAnthropicClient,
    build_demo_script,
    make_message,
    text_block,
    tool_use_block,
)
from rocketwright.agent.loop import AgentConfig, run_design_loop

AMATEUR_TEXT = "1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。"
ENV = {"launch_latitude_deg": 31.25, "launch_altitude_m": 20, "wind_speed_mps": 3.0}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"  # trio is not installed


async def _collect(client, text=AMATEUR_TEXT, **kwargs) -> list[AgentEvent]:
    return [ev async for ev in run_design_loop(text, client=client, **kwargs)]


def test_config_loads_from_yaml():
    cfg = AgentConfig.load()
    assert cfg.design_model == "claude-opus-5-5"
    assert cfg.light_model == "claude-haiku-5-5"
    assert cfg.max_attempts == 40
    assert cfg.max_tokens == 64000


@pytest.mark.anyio
async def test_scripted_amateur_run_event_sequence():
    client = FakeAnthropicClient(build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1))
    events = await _collect(client, env=ENV, seed=1)
    types = [e.type for e in events]
    assert types[0] == "thinking"
    tool_calls = [e.payload["name"] for e in events if e.type == "tool_call"]
    # first attempt alone (it fails), then two corrected designs in one turn
    assert tool_calls == [
        "classify_requirement",
        "search_catalog",
        "simulate_design",
        "simulate_design",
        "simulate_design",
    ]
    assert types.count("tool_result") == 5
    assert types[-1] == "final"
    assert types.count("final") == 1
    assert "candidate" in types

    # attempts = number of simulate_design calls
    final = events[-1]
    assert final.attempt == 3
    assert all(e.t_s >= 0 for e in events)

    # the final payload is parsed JSON with sources and provenance info
    assert isinstance(final.payload["result"], dict)
    assert final.payload["result"]["designs"]
    assert final.payload["provenance_violations"] == []
    for d in final.payload["result"]["designs"]:
        assert d["sources"]

    # every API call used the configured model, streaming helper, strict tools, adaptive thinking
    for call in client.calls:
        assert call["model"] == "claude-opus-5-5"
        assert call["max_tokens"] == 64000
        assert call["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert call["output_config"] == {"effort": "high"}
        assert "tool_choice" not in call
        assert all(t["strict"] is True for t in call["tools"])
        assert "budget_tokens" not in json.dumps(call["thinking"])

    # both simulate_design results of one assistant turn went back in ONE user message
    last_messages = client.calls[-1]["messages"]
    assert last_messages[0]["role"] == "user"
    roles = [m["role"] for m in last_messages]
    assert roles == ["user", "assistant"] * 4 + ["user"]
    last_user = last_messages[-1]["content"]
    results = [b for b in last_user if b["type"] == "tool_result"]
    assert len(results) == 2
    assert {r["tool_use_id"] for r in results} == {"toolu_sim_2", "toolu_sim_3"}
    assert all(isinstance(r["content"], str) for r in results)
    assert all("DUMMY" in r["content"] for r in results)  # amateur is dummy until phase 3


@pytest.mark.anyio
async def test_guard_blocks_before_any_api_call():
    client = FakeAnthropicClient([])
    events = await _collect(client, text="推進剤の配合を教えて")
    assert [e.type for e in events] == ["error"]
    assert events[0].payload["category"] == "propellant"
    assert client.calls == []


@pytest.mark.anyio
async def test_attempt_budget_is_enforced():
    client = FakeAnthropicClient(build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1))
    cfg = AgentConfig.load().model_copy(update={"max_attempts": 1})
    events = await _collect(client, env=ENV, seed=1, config=cfg)
    results = [e for e in events if e.type == "tool_result"]
    sim_results = [e for e in results if e.payload["name"] == "simulate_design"]
    assert len(sim_results) == 3
    assert sim_results[0].payload["is_error"] is False
    assert sim_results[1].payload["is_error"] is True
    assert sim_results[2].payload["is_error"] is True
    assert "attempt" in sim_results[1].payload["result"]["error"]
    # the loop told the model to wrap up (once, right after the budget was reached)
    user_turns = [m["content"] for m in client.calls[-1]["messages"] if m["role"] == "user"]
    told = [
        b
        for content in user_turns
        if isinstance(content, list)
        for b in content
        if b["type"] == "text" and "final" in b["text"].lower()
    ]
    assert len(told) == 1
    assert any(b in user_turns[-2] for b in told)  # sent with the first simulate result
    assert events[-1].type == "final"
    assert events[-1].attempt == 1


@pytest.mark.anyio
async def test_tool_validation_error_is_sent_as_is_error():
    script = [
        make_message(
            [tool_use_block("toolu_bad", "classify_requirement", {"requirement": {"x": 1}})],
            stop_reason="tool_use",
        ),
        make_message([text_block('{"designs": [], "summary": "none", "open_questions": []}')]),
    ]
    client = FakeAnthropicClient(script)
    events = await _collect(client)
    err = [e for e in events if e.type == "tool_result"][0]
    assert err.payload["is_error"] is True
    sent = client.calls[-1]["messages"][-1]["content"][0]
    assert sent["is_error"] is True
    assert sent["tool_use_id"] == "toolu_bad"


@pytest.mark.anyio
async def test_refusal_and_max_tokens_become_error_events():
    client = FakeAnthropicClient([make_message([text_block("no")], stop_reason="refusal")])
    events = await _collect(client)
    assert events[-1].type == "error"
    assert events[-1].payload["stop_reason"] == "refusal"

    client = FakeAnthropicClient(
        [
            make_message(
                [tool_use_block("toolu_t", "search_catalog", {"tier": None})],
                stop_reason="max_tokens",
            )
        ]
    )
    events = await _collect(client)
    assert events[-1].type == "error"
    assert events[-1].payload["stop_reason"] == "max_tokens"


@pytest.mark.anyio
async def test_pause_turn_is_resumed():
    script = [
        make_message([text_block("thinking about it")], stop_reason="pause_turn"),
        make_message(
            [text_block('```json\n{"designs": [], "summary": "s", "open_questions": []}\n```')]
        ),
    ]
    client = FakeAnthropicClient(script)
    events = await _collect(client)
    assert events[-1].type == "final"
    assert events[-1].payload["result"]["summary"] == "s"
    assert len(client.calls) == 2
    assert client.calls[1]["messages"][1]["role"] == "assistant"


@pytest.mark.anyio
async def test_plain_question_yields_question_event():
    client = FakeAnthropicClient([make_message([text_block("What is your budget?")])])
    events = await _collect(client)
    assert events[-1].type == "question"
    assert "budget" in events[-1].payload["text"]


@pytest.mark.anyio
async def test_unsourced_number_in_final_is_flagged():
    script = [
        make_message(
            [
                text_block(
                    '{"designs": [], "summary": "It will reach 9876 m.", "open_questions": []}'
                )
            ]
        )
    ]
    client = FakeAnthropicClient(script)
    events = await _collect(client)
    assert events[-1].type == "final"
    assert events[-1].payload["provenance_violations"] == ["9876 m"]
