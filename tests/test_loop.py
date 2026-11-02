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
from rocketwright.agent.loop import (
    AgentConfig,
    ReviewerConfig,
    _apply_review_gate,
    run_design_loop,
)

AMATEUR_TEXT = "1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。"
# the demo_amateur scenario env: the seeded first attempt is about a tenth too high there
ENV = {"launch_latitude_deg": 36.0, "launch_altitude_m": 300, "wind_speed_mps": 3.0}


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
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, dispersion=False)
    )
    events = await _collect(client, env=ENV, seed=1)
    types = [e.type for e in events]
    assert types[0] == "thinking"
    tool_calls = [e.payload["name"] for e in events if e.type == "tool_call"]
    # classify; derive + catalog in one turn; reference seed; the seed-based first attempt
    # alone (it fails: buildability error); then two corrected part builds in one turn
    assert tool_calls == [
        "classify_requirement",
        "derive_requirements",
        "search_catalog",
        "find_reference_designs",
        "design_from_parts",
        "design_from_parts",
        "design_from_parts",
    ]
    assert types.count("tool_result") == 7
    assert types[-1] == "final"
    assert types.count("final") == 1
    assert "candidate" in types

    # attempts = number of design_from_parts (or simulate_design) calls
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

    # both design_from_parts results of one assistant turn went back in ONE user message
    last_messages = client.calls[-1]["messages"]
    assert last_messages[0]["role"] == "user"
    roles = [m["role"] for m in last_messages]
    assert roles == ["user", "assistant"] * 5 + ["user"]
    last_user = last_messages[-1]["content"]
    results = [b for b in last_user if b["type"] == "tool_result"]
    assert len(results) == 2
    assert {r["tool_use_id"] for r in results} == {"toolu_sim_2", "toolu_sim_3"}
    assert all(isinstance(r["content"], str) for r in results)
    assert all("apogee_m" in r["content"] for r in results)  # real solid-model results


@pytest.mark.anyio
async def test_guard_blocks_before_any_api_call():
    client = FakeAnthropicClient([])
    events = await _collect(client, text="推進剤の配合を教えて")
    assert [e.type for e in events] == ["error"]
    assert events[0].payload["category"] == "propellant"
    assert client.calls == []


@pytest.mark.anyio
async def test_attempt_budget_is_enforced():
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, dispersion=False)
    )
    cfg = AgentConfig.load().model_copy(update={"max_attempts": 1})
    events = await _collect(client, env=ENV, seed=1, config=cfg)
    results = [e for e in events if e.type == "tool_result"]
    sim_results = [e for e in results if e.payload["name"] == "design_from_parts"]
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


# --------------------------------------------------------------------------- reviewers (phase 3)


def _by_type(events: list[AgentEvent], kind: str) -> list[AgentEvent]:
    return [e for e in events if e.type == kind]


@pytest.mark.anyio
async def test_review_events_follow_candidates_and_feedback_is_injected():
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, reviews=True, dispersion=False)
    )
    events = await _collect(client, env=ENV, seed=1)
    types = [e.type for e in events]
    candidates = _by_type(events, "candidate")
    reviews = _by_type(events, "review")
    assert len(candidates) == 2 and len(reviews) == 2
    # one review per candidate, same source_id, emitted right after the candidate
    for cand, rev in zip(candidates, reviews, strict=True):
        assert rev.payload["source_id"] == cand.payload["source_id"]
        assert types.index("review", types.index("candidate")) > types.index("candidate")
    aspects = [v["aspect"] for v in reviews[0].payload["verdicts"]]
    assert aspects == ["stability", "recovery", "cost", "safety"]
    # demo script: first candidate gets a major cost finding, the second is all ok
    first = {v["aspect"]: v for v in reviews[0].payload["verdicts"]}
    assert first["cost"]["severity"] == "major"
    assert reviews[0].payload["max_severity"] == "major"
    assert reviews[0].payload["blocked"] is False
    assert reviews[0].payload["feedback"].startswith("Reviewer findings for candidate toolu_sim_2")
    assert all(v["severity"] == "ok" for v in reviews[1].payload["verdicts"])
    assert reviews[1].payload["feedback"] is None
    # the cited cost is the tool result's own number (no invented numbers survive)
    sim2 = next(e for e in events if e.type == "tool_result" and e.payload["id"] == "toolu_sim_2")
    cost2 = sim2.payload["result"]["sim"]["cost_jpy"]  # design_from_parts: the embedded sim
    assert f"cost_jpy {cost2:.0f}" in first["cost"]["findings"][0]
    # part-space candidates carry the parts and the bill for the UI and the reviewers
    assert candidates[0].payload["build"]["tier"] == "amateur"
    assert candidates[0].payload["bill"]["dry_mass_kg"] > 0
    assert reviews[0].payload["dropped"] == {}
    # 4 reviewer calls per candidate, each reviewed exactly once, on the reviewer model
    assert len(client.parse_calls) == 8
    assert {c["model"] for c in client.parse_calls} == {"claude-haiku-5-5"}
    assert all(c["output_config"] == {"effort": "low"} for c in client.parse_calls)
    # feedback goes into the NEXT user message: tool_result blocks first, then one text block
    last_user = client.calls[-1]["messages"][-1]["content"]
    kinds = [b["type"] for b in last_user]
    assert kinds == ["tool_result", "tool_result", "text"]
    assert last_user[-1]["text"].startswith("Reviewer findings for candidate toolu_sim_2")
    assert "[cost/major]" in last_user[-1]["text"]
    assert "re-simulating" in last_user[-1]["text"]
    # the demo still ends with passing designs (major is not a blocker)
    final = events[-1]
    assert final.type == "final"
    assert [d["passed"] for d in final.payload["result"]["designs"]] == [True, True]
    assert final.payload["result"].get("rejected_by_review", []) == []
    assert final.payload["review_blocked_ids"] == []
    assert final.payload["provenance_violations"] == []


@pytest.mark.anyio
async def test_blocker_moves_design_out_of_passing_list():
    blocker = {
        "aspect": "safety",
        "severity": "blocker",
        "findings": ["the payload description matches an out-of-scope item"],
        "suggested_changes": ["replace the payload with an inert mass"],
    }
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, dispersion=False),
        reviews=[{"safety": blocker}],
    )
    events = await _collect(client, env=ENV, seed=1)
    reviews = _by_type(events, "review")
    assert (
        reviews[0].payload["blocked"] is True and reviews[0].payload["source_id"] == "toolu_sim_2"
    )
    assert reviews[1].payload["blocked"] is False
    warnings = _by_type(events, "warning")
    assert len(warnings) == 1 and warnings[0].payload["kind"] == "review_gate"
    assert warnings[0].payload["rejected_ids"] == ["toolu_sim_2"]
    final = events[-1]
    assert final.type == "final"
    result = final.payload["result"]
    assert final.payload["review_blocked_ids"] == ["toolu_sim_2"]
    assert [d["sources"]["cost_jpy"] for d in result["designs"]] == ["toolu_sim_3"]
    assert all(d["passed"] for d in result["designs"])
    rejected = result["rejected_by_review"]
    assert len(rejected) == 1
    assert rejected[0]["sources"]["cost_jpy"] == "toolu_sim_2"
    assert rejected[0]["passed"] is False
    assert rejected[0]["review_blocked"] is True
    assert "out-of-scope" in rejected[0]["review_findings"][0]


@pytest.mark.anyio
async def test_reviewer_findings_with_invented_numbers_are_dropped_before_feedback():
    invented = {
        "aspect": "stability",
        "severity": "major",
        "findings": [
            "stability_margin_cal should be at least 2.75 cal but the margin looks thin",
            "fin span is small for this body length",
        ],
        "suggested_changes": ["increase fin span to 0.123 m"],
    }
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, dispersion=False),
        reviews=[{"stability": invented}],
    )
    events = await _collect(client, env=ENV, seed=1)
    review = _by_type(events, "review")[0]
    stability = next(v for v in review.payload["verdicts"] if v["aspect"] == "stability")
    assert stability["severity"] == "major"
    assert stability["findings"] == [
        "fin span is small for this body length",
        "[1 finding dropped: it cited numbers absent from the tool results]",
    ]
    assert stability["suggested_changes"] == []
    assert review.payload["dropped"] == {
        "stability": [
            "stability_margin_cal should be at least 2.75 cal but the margin looks thin",
            "increase fin span to 0.123 m",
        ]
    }
    injected = client.calls[-1]["messages"][-1]["content"][-1]
    assert injected["type"] == "text"
    assert "2.75" not in injected["text"] and "0.123" not in injected["text"]
    assert "fin span is small" in injected["text"]


@pytest.mark.anyio
async def test_reviewers_can_be_disabled_and_never_run_on_failed_attempts():
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, reviews=True, dispersion=False)
    )
    cfg = AgentConfig.load().model_copy(update={"reviewers": ReviewerConfig(enabled=False)})
    events = await _collect(client, env=ENV, seed=1, config=cfg)
    assert not _by_type(events, "review")
    assert client.parse_calls == []
    assert all(b["type"] == "tool_result" for b in client.calls[-1]["messages"][-1]["content"])
    assert events[-1].type == "final"

    # enabled: the failing first attempt (toolu_sim_1) is never reviewed
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, reviews=True, dispersion=False)
    )
    events = await _collect(client, env=ENV, seed=1)
    assert {e.payload["source_id"] for e in _by_type(events, "review")} == {
        "toolu_sim_2",
        "toolu_sim_3",
    }


def test_config_loads_reviewer_block():
    cfg = AgentConfig.load()
    assert cfg.reviewers_enabled is True
    assert cfg.reviewers.model == "claude-haiku-5-5"
    assert cfg.reviewers.effort == "low"
    assert cfg.reviewers.max_rounds_per_candidate == 1
    assert cfg.reviewers.max_tokens == 4096


def test_apply_review_gate_is_pure_and_keeps_order():
    result = {
        "designs": [
            {"design": {}, "passed": True, "sources": {"apogee_m": "a"}},
            {"design": {}, "passed": True, "sources": {"apogee_m": "b"}},
            {"design": {}, "passed": True, "sources": {"apogee_m": "c"}},
        ],
        "summary": "s",
    }
    gated, moved = _apply_review_gate(result, {"b": ["bad"]})
    assert moved == ["b"]
    assert [d["sources"]["apogee_m"] for d in gated["designs"]] == ["a", "c"]
    assert gated["rejected_by_review"][0]["review_findings"] == ["bad"]
    assert result["designs"][1]["passed"] is True  # input untouched
    assert _apply_review_gate(result, {}) == (result, [])


# --------------------------------------------------------------------------- reference seed


def _bottle_reference_result(success: bool) -> dict:
    return {
        "references": [{"id": "apte_2l_800ml_40psi", "name": "Apte 2 L"}],
        "seed": {
            "reference_id": "apte_2l_800ml_40psi",
            "design": {
                "tier": "bottle",
                "bottle_volume_m3": 0.002,
                "water_fill_frac": 0.4,
                "initial_gauge_pressure_pa": 376000,
                "nozzle_diameter_m": 0.0222,
                "dry_mass_kg": 0.1,
                "payload_mass_kg": 0.06,
                "has_fins": True,
                "has_parachute": True,
                "parachute_diameter_m": 0.31,
            },
            "notes": ["seeded from Apte 2 L"],
            "env": {},
            "sim": {
                "success": success,
                "failure_reasons": [] if success else ["apogee 12 m not within +/-10%"],
                "metrics": {"apogee_m": 32.2, "descent_speed_mps": 4.8},
                "cost_jpy": 2300.0,
                "trace": [{"t_s": 0.0, "altitude_m": 0.0}],
                "warnings": [],
            },
        },
        "source_id": "toolu_ref",
    }


@pytest.mark.anyio
@pytest.mark.parametrize("seed_passes", [True, False])
async def test_passing_reference_seed_is_emitted_as_a_free_candidate(monkeypatch, seed_passes):
    from rocketwright.agent import loop as loop_module

    def fake_execute(name, tool_input, tool_use_id):
        assert name == "find_reference_designs"
        return _bottle_reference_result(seed_passes)

    monkeypatch.setattr(loop_module, "execute_tool", fake_execute)
    script = [
        make_message(
            [
                tool_use_block(
                    "toolu_ref",
                    "find_reference_designs",
                    {"requirement": {}, "tier": "bottle", "seed": True},
                )
            ],
            stop_reason="tool_use",
        ),
        make_message([text_block('{"designs": [], "summary": "s", "open_questions": []}')]),
    ]
    client = FakeAnthropicClient(script)
    events = await _collect(client, text="30 m まで上げたい")
    candidates = _by_type(events, "candidate")
    if seed_passes:
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.attempt == 0  # the seed is free: it does not count as an attempt
        assert cand.payload["source_id"] == "toolu_ref"
        assert cand.payload["seeded_from"] == "apte_2l_800ml_40psi"
        assert cand.payload["design"]["tier"] == "bottle"
        assert cand.payload["metrics"]["apogee_m"] == 32.2
        assert cand.payload["cost_jpy"] == 2300.0
    else:
        assert candidates == []
    assert not _by_type(events, "review")  # the seed is never reviewed
    assert events[-1].type == "final" and events[-1].payload["attempts"] == 0
    # the seed sim's trace is stripped from what the model sees (like simulate_design)
    sent = client.calls[-1]["messages"][2]["content"][0]["content"]
    assert "trace" not in json.loads(sent)["seed"]["sim"]
    assert json.loads(sent)["seed"]["sim"]["trace_point_count"] == 1
