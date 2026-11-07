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
from rocketwright.agent.prompts import SYSTEM_PROMPT
from rocketwright.schema import Tier

AMATEUR_TEXT = "1 kg の荷物を高度 2 km まで上げてパラシュートで回収したい。予算 5 万円。"
# the demo_amateur scenario env: the seeded first attempt is about a tenth too high there
ENV = {"launch_latitude_deg": 36.0, "launch_altitude_m": 300, "wind_speed_mps": 3.0}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"  # trio is not installed


def _all_tiers(**update) -> AgentConfig:
    """These tests drive the loop itself; the amateur script is the fullest one it has."""
    return AgentConfig.load().model_copy(update={"allowed_tiers": tuple(Tier), **update})


async def _collect(client, text=AMATEUR_TEXT, **kwargs) -> list[AgentEvent]:
    kwargs.setdefault("config", _all_tiers())
    return [ev async for ev in run_design_loop(text, client=client, **kwargs)]


def test_config_loads_from_yaml():
    cfg = AgentConfig.load()
    assert cfg.allowed_tiers == (Tier.BOTTLE,)
    assert cfg.design_model == "claude-haiku-5-5"
    assert cfg.light_model == "claude-haiku-5-5"
    assert cfg.effort == "low"
    assert cfg.max_attempts == 8
    assert cfg.max_turns == 24
    assert cfg.max_tokens == 16000


@pytest.mark.anyio
async def test_scripted_amateur_run_event_sequence():
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, dispersion=False)
    )
    events = await _collect(client, env=ENV, seed=1)
    types = [e.type for e in events]
    assert types[0] == "thinking"
    tool_calls = [e.payload["name"] for e in events if e.type == "tool_call"]
    # classify; derive + the nearest real kit in one turn; the auto_design baseline; two
    # design_stage revisions (mount, then fins: upstream first); the final build confirmed
    assert tool_calls == [
        "classify_requirement",
        "derive_requirements",
        "find_reference_designs",
        "auto_design",
        "design_stage",
        "design_stage",
        "design_from_parts",
    ]
    stages = [
        e.payload["input"]["stage"]
        for e in events
        if e.type == "tool_call" and e.payload["name"] == "design_stage"
    ]
    assert stages == ["mount", "fins"]
    assert types.count("tool_result") == 7
    assert types[-1] == "final"
    assert types.count("final") == 1
    assert types.count("candidate") == 2  # auto_design and design_from_parts

    # attempts = auto_design + design_from_parts (design_stage is exploration)
    final = events[-1]
    assert final.attempt == 2
    assert all(e.t_s >= 0 for e in events)

    # the final payload is parsed JSON with sources and provenance info
    assert isinstance(final.payload["result"], dict)
    assert final.payload["result"]["designs"]
    assert final.payload["provenance_violations"] == []
    for d in final.payload["result"]["designs"]:
        assert d["sources"]

    # every API call used the configured model, streaming helper, strict tools, adaptive thinking
    for call in client.calls:
        assert call["model"] == "claude-haiku-5-5"
        assert call["max_tokens"] == 16000
        assert call["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert call["output_config"] == {"effort": "low"}
        assert "tool_choice" not in call
        assert all("strict" not in t for t in call["tools"])  # API limit on nullable params
        assert "budget_tokens" not in json.dumps(call["thinking"])

    # both tool results of the derive turn went back in ONE user message; the model never
    # sees a simulation trace
    last_messages = client.calls[-1]["messages"]
    assert last_messages[0]["role"] == "user"
    roles = [m["role"] for m in last_messages]
    assert roles == ["user", "assistant"] * 6 + ["user"]
    derive_turn = last_messages[4]["content"]
    results = [b for b in derive_turn if b["type"] == "tool_result"]
    assert {r["tool_use_id"] for r in results} == {"toolu_derive", "toolu_ref"}
    sent = {
        b["tool_use_id"]: json.loads(b["content"])
        for m in last_messages
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b["type"] == "tool_result"
    }
    for tid in ("toolu_auto", "toolu_parts"):
        assert "trace" not in sent[tid]["sim"] and "apogee_m" in sent[tid]["sim"]["metrics"]
    assert [t["stage"] for t in sent["toolu_auto"]["trace"]][0] == "motor"


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
    cfg = _all_tiers(max_attempts=1)
    events = await _collect(client, env=ENV, seed=1, config=cfg)
    results = [e for e in events if e.type == "tool_result"]
    attempts = [e for e in results if e.payload["name"] in ("auto_design", "design_from_parts")]
    assert [e.payload["name"] for e in attempts] == ["auto_design", "design_from_parts"]
    assert attempts[0].payload["is_error"] is False
    assert attempts[1].payload["is_error"] is True
    assert "attempt" in attempts[1].payload["result"]["error"]
    # design_stage is exploration: it still runs after the budget is spent
    stage_results = [e for e in results if e.payload["name"] == "design_stage"]
    assert stage_results and not any(e.payload["is_error"] for e in stage_results)
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
    auto_turn = next(
        content
        for content in user_turns
        if isinstance(content, list) and any(b.get("tool_use_id") == "toolu_auto" for b in content)
    )
    assert told[0] in auto_turn  # sent with the first attempt's result
    assert events[-1].type == "final"
    assert events[-1].attempt == 1
    # the final still reports the baseline that passed
    designs = events[-1].payload["result"]["designs"]
    assert [d["sources"]["cost_jpy"] for d in designs] == ["toolu_auto"]


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


def _user_turn_after(client, tool_use_id: str) -> list[dict]:
    """The user message that carries the tool_result of `tool_use_id`."""
    for m in client.calls[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            if any(b.get("tool_use_id") == tool_use_id for b in m["content"]):
                return m["content"]
    raise AssertionError(f"no user turn answers {tool_use_id}")


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
    assert [c.payload["source_id"] for c in candidates] == ["toolu_auto", "toolu_parts"]
    aspects = [v["aspect"] for v in reviews[0].payload["verdicts"]]
    assert aspects == ["stability", "recovery", "cost", "safety"]
    # demo script: first candidate gets a major cost finding, the second is all ok
    first = {v["aspect"]: v for v in reviews[0].payload["verdicts"]}
    assert first["cost"]["severity"] == "major"
    assert reviews[0].payload["max_severity"] == "major"
    assert reviews[0].payload["blocked"] is False
    assert reviews[0].payload["feedback"].startswith("Reviewer findings for candidate toolu_auto")
    assert all(v["severity"] == "ok" for v in reviews[1].payload["verdicts"])
    assert reviews[1].payload["feedback"] is None
    # the cited cost is the tool result's own number (no invented numbers survive)
    auto = next(e for e in events if e.type == "tool_result" and e.payload["id"] == "toolu_auto")
    cost = auto.payload["result"]["sim"]["cost_jpy"]  # auto_design: the embedded sim
    assert f"cost_jpy {cost:.0f}" in first["cost"]["findings"][0]
    # part-space candidates carry the parts and the bill for the UI and the reviewers
    assert candidates[0].payload["build"]["tier"] == "amateur"
    assert candidates[0].payload["bill"]["dry_mass_kg"] > 0
    assert reviews[0].payload["dropped"] == {}
    # 4 reviewer calls per candidate, each reviewed exactly once, on the reviewer model
    assert len(client.parse_calls) == 8
    assert {c["model"] for c in client.parse_calls} == {"claude-haiku-5-5"}
    assert all(c["output_config"] == {"effort": "low"} for c in client.parse_calls)
    # feedback goes into the NEXT user message: tool_result block first, then one text block
    auto_turn = _user_turn_after(client, "toolu_auto")
    assert [b["type"] for b in auto_turn] == ["tool_result", "text"]
    assert auto_turn[-1]["text"].startswith("Reviewer findings for candidate toolu_auto")
    assert "[cost/major]" in auto_turn[-1]["text"]
    assert "re-simulating" in auto_turn[-1]["text"]
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
    assert reviews[0].payload["blocked"] is True and reviews[0].payload["source_id"] == "toolu_auto"
    assert reviews[1].payload["blocked"] is False
    warnings = _by_type(events, "warning")
    assert len(warnings) == 1 and warnings[0].payload["kind"] == "review_gate"
    assert warnings[0].payload["rejected_ids"] == ["toolu_auto"]
    final = events[-1]
    assert final.type == "final"
    result = final.payload["result"]
    assert final.payload["review_blocked_ids"] == ["toolu_auto"]
    assert [d["sources"]["cost_jpy"] for d in result["designs"]] == ["toolu_parts"]
    assert all(d["passed"] for d in result["designs"])
    rejected = result["rejected_by_review"]
    assert len(rejected) == 1
    assert rejected[0]["sources"]["cost_jpy"] == "toolu_auto"
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
    injected = _user_turn_after(client, "toolu_auto")[-1]
    assert injected["type"] == "text"
    assert "2.75" not in injected["text"] and "0.123" not in injected["text"]
    assert "fin span is small" in injected["text"]


@pytest.mark.anyio
async def test_reviewers_can_be_disabled_and_never_run_on_failed_attempts():
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, reviews=True, dispersion=False)
    )
    cfg = _all_tiers(reviewers=ReviewerConfig(enabled=False))
    events = await _collect(client, env=ENV, seed=1, config=cfg)
    assert not _by_type(events, "review")
    assert client.parse_calls == []
    assert all(b["type"] == "tool_result" for b in client.calls[-1]["messages"][-1]["content"])
    assert events[-1].type == "final"

    # enabled: only the attempts are reviewed, never the design_stage exploration
    client = FakeAnthropicClient(
        build_demo_script("amateur", AMATEUR_TEXT, ENV, seed=1, reviews=True, dispersion=False)
    )
    events = await _collect(client, env=ENV, seed=1)
    assert {e.payload["source_id"] for e in _by_type(events, "review")} == {
        "toolu_auto",
        "toolu_parts",
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


# --------------------------------------------------------------------------- design chain tools


def _chain_result(name: str, tool_use_id: str) -> dict:
    sim = {
        "tier": "amateur",
        "success": True,
        "failure_reasons": [],
        "metrics": {"apogee_m": 1870.6, "stability_margin_cal": 5.49},
        "cost_jpy": 33930.0,
        "trace": [{"t_s": 0.0, "altitude_m": 0.0}, {"t_s": 1.0, "altitude_m": 50.0}],
        "warnings": [],
    }
    build = {"tier": "amateur", "motor_id": "aerotech_J435WS"}
    bill = {"parts": [], "dry_mass_kg": 1.2, "cost_jpy": 33930.0}
    if name == "design_stage":
        return {
            "stage": "fins",
            "candidates": [{"option": "fin_plywood_3mm", "passed": True, "build": build}],
            "source_id": tool_use_id,
        }
    return {
        "tier": "amateur",
        "build": build,
        "design": {"tier": "amateur", "motor_id": "aerotech_J435WS"},
        "bill": bill,
        "issues": [],
        "sim": sim,
        "trace": [{"stage": "motor", "chosen": "aerotech_J435WS"}]
        if name == "auto_design"
        else None,
        "source_id": tool_use_id,
    }


@pytest.mark.anyio
async def test_auto_design_is_an_attempt_and_design_stage_is_exploration(monkeypatch):
    from rocketwright.agent import loop as loop_module

    monkeypatch.setattr(loop_module, "execute_tool", lambda n, i, t: _chain_result(n, t))
    script = [
        make_message(
            [tool_use_block("toolu_auto", "auto_design", {"tier": "amateur"})],
            stop_reason="tool_use",
        ),
        make_message(
            [tool_use_block("toolu_stage", "design_stage", {"tier": "amateur", "stage": "fins"})],
            stop_reason="tool_use",
        ),
        make_message(
            [tool_use_block("toolu_parts", "design_from_parts", {"build": {}})],
            stop_reason="tool_use",
        ),
        make_message([text_block('{"designs": [], "summary": "s", "open_questions": []}')]),
    ]
    client = FakeAnthropicClient(script)
    events = await _collect(client, text="1 kg を 2 km まで")
    candidates = _by_type(events, "candidate")
    assert [c.payload["source_id"] for c in candidates] == ["toolu_auto", "toolu_parts"]
    auto, parts = candidates
    assert auto.attempt == 1 and parts.attempt == 2  # design_stage is not an attempt
    assert auto.payload["origin"] == "auto_design"
    assert parts.payload["origin"] == "design_from_parts"
    for cand in candidates:
        assert cand.payload["build"]["motor_id"] == "aerotech_J435WS"
        assert cand.payload["bill"]["cost_jpy"] == 33930.0
        assert cand.payload["metrics"]["apogee_m"] == 1870.6
    # both part-space candidates are reviewed; the design_stage exploration is not
    assert [r.payload["source_id"] for r in _by_type(events, "review")] == [
        "toolu_auto",
        "toolu_parts",
    ]
    assert events[-1].type == "final" and events[-1].payload["attempts"] == 2
    # the UI still gets the full sim (trace included) through the tool_result event
    auto_result = next(
        e for e in events if e.type == "tool_result" and e.payload["id"] == "toolu_auto"
    )
    assert len(auto_result.payload["result"]["sim"]["trace"]) == 2
    # ...but the model never sees a sim trace: auto_design / design_from_parts are stripped
    sent = {
        b["tool_use_id"]: json.loads(b["content"])
        for m in client.calls[-1]["messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b["type"] == "tool_result"
    }
    for tid in ("toolu_auto", "toolu_parts"):
        assert "trace" not in sent[tid]["sim"] and sent[tid]["sim"]["trace_point_count"] == 2
    assert sent["toolu_auto"]["trace"] == [{"stage": "motor", "chosen": "aerotech_J435WS"}]
    assert sent["toolu_stage"]["candidates"][0]["option"] == "fin_plywood_3mm"


def test_for_model_strips_nested_sim_traces():
    from rocketwright.agent.loop import _for_model

    result = {
        "sim": {"trace": [{"t_s": 0.0}], "metrics": {}},
        "candidates": [{"option": "a", "sim": {"trace": [{}, {}], "metrics": {}}}],
        "feasibility": {"cheapest_passing": {"sim": {"trace": [{}], "metrics": {}}}},
    }
    slim = _for_model(result)
    assert slim["sim"] == {"metrics": {}, "trace_point_count": 1}
    assert slim["candidates"][0]["sim"] == {"metrics": {}, "trace_point_count": 2}
    assert slim["feasibility"]["cheapest_passing"]["sim"]["trace_point_count"] == 1
    assert result["sim"]["trace"] == [{"t_s": 0.0}]  # input untouched


def test_system_prompt_describes_the_staged_chain_workflow():
    from rocketwright.design_chain import AMATEUR_STAGES, BOTTLE_STAGES

    text = " ".join(SYSTEM_PROMPT.split())
    # bottle / amateur: auto_design baseline, then design_stage from the most upstream stage
    for word in ("auto_design", "design_stage", "design_from_parts", "run_dispersion"):
        assert word in text
    assert "MOST UPSTREAM" in text and "funnel" in text and "`why`" in text
    assert " -> ".join(AMATEUR_STAGES) in text and " -> ".join(BOTTLE_STAGES) in text
    # honest budget, certification and coupler warnings, the reference as context only
    assert "feasibility" in text and "cheapest passing" in text
    assert "Level 1" in text and "Level 2" in text and "coupler" in text
    assert "closest to" in text
    # the orbital tiers keep the reference-seeded workflow
    assert "tune=true" in text and "simulate_design" in text


@pytest.mark.parametrize(
    "text",
    [
        "予算はいくらですか？",
        "What is the budget?",
        "目標の高度を教えてください。",
        "回収は必要でしょうか",
    ],
)
def test_a_reply_that_asks_for_something_is_a_question(text):
    from rocketwright.agent.loop import _looks_like_question

    assert _looks_like_question(text)


def test_a_plain_statement_is_not_a_question():
    from rocketwright.agent.loop import _looks_like_question

    assert not _looks_like_question("設計が完了しました。合格案は 2 件です。")


# --- bottle only -----------------------------------------------------------------------

BOTTLE_TEXT = "卵を割らずに 30 m まで上げて回収したい"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    [
        "150 kg の小型衛星を高度 400 km の軌道に投入したい。予算 20 億円",
        "1 kg の荷物を 2 km まで上げて回収したい",
        "企業級のロケットを設計して",
    ],
)
async def test_a_request_past_the_bottle_range_is_refused_before_any_api_call(text):
    client = FakeAnthropicClient([])

    events = [ev async for ev in run_design_loop(text, client=client)]

    assert [e.type for e in events] == ["error"]
    assert events[0].payload["kind"] == "out_of_scope"
    assert events[0].payload["category"] == "tier_limit"
    assert events[0].payload["reason"].startswith("できません")
    assert client.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("altitude_m", "payload_kg", "named"),
    [(2000.0, 0.06, "2 km"), (60.0, 0.06, "60 m"), (20.0, 1.0, "1 kg")],
)
async def test_classify_stops_what_the_text_screen_could_not_read(altitude_m, payload_kg, named):
    requirement = {
        "goal_kind": "altitude",
        "target_altitude_m": altitude_m,
        "target_apogee_m": None,
        "payload_mass_kg": payload_kg,
        "budget_jpy": None,
        "recovery_required": True,
        "tier_override": None,
        "text": "",
    }
    client = FakeAnthropicClient(
        [
            make_message(
                [tool_use_block("toolu_c", "classify_requirement", {"requirement": requirement})],
                stop_reason="tool_use",
            )
        ]
    )

    events = [ev async for ev in run_design_loop("もっと高く飛ばしたい", client=client)]

    assert events[-1].type == "error"
    assert events[-1].payload["category"] == "tier_limit"
    assert named in events[-1].payload["reason"]
    assert len(client.calls) == 1


@pytest.mark.anyio
async def test_a_bottle_only_run_offers_claude_the_bottle_tier_only():
    client = FakeAnthropicClient([make_message([text_block("どこまで上げますか？")])])

    [ev async for ev in run_design_loop(BOTTLE_TEXT, client=client)]

    call = client.calls[0]
    tools = {tool["name"]: tool for tool in call["tools"]}
    schema = json.dumps(tools["simulate_design"]["input_schema"])
    assert "stages" not in schema and "motor_id" not in schema
    assert tools["auto_design"]["input_schema"]["properties"]["tier"]["enum"] == ["bottle"]
    assert call["system"][0]["text"].startswith(SYSTEM_PROMPT)
    assert "できません" in call["system"][0]["text"]


@pytest.mark.anyio
async def test_a_plain_refusal_from_claude_reads_as_a_refusal():
    client = FakeAnthropicClient([make_message([text_block("できません。軌道には届きません。")])])

    events = [ev async for ev in run_design_loop(BOTTLE_TEXT, client=client)]

    assert [e.type for e in events] == ["text", "error"]
    assert events[-1].payload["kind"] == "out_of_scope"
    assert events[-1].payload["reason"] == "できません。軌道には届きません。"


# --- the check of the final answer ------------------------------------------------------

CLASSIFY_INPUT = {
    "requirement": {
        "goal_kind": "altitude",
        "target_altitude_m": 30.0,
        "target_apogee_m": None,
        "payload_mass_kg": 0.06,
        "budget_jpy": None,
        "recovery_required": True,
        "tier_override": None,
        "text": "",
    }
}


def _final_message(sources: dict, apogee_m: float = 30.0) -> object:
    row = {
        "design": {},
        "metrics": {"apogee_m": apogee_m},
        "passed": False,
        "cost_jpy": None,
        "success_rate": None,
        "sources": sources,
        "explanation": "",
    }
    return make_message([text_block(json.dumps({"designs": [row], "summary": "s"}))])


def _classify_message() -> object:
    return make_message(
        [tool_use_block("toolu_c", "classify_requirement", CLASSIFY_INPUT)], stop_reason="tool_use"
    )


@pytest.mark.anyio
async def test_a_final_that_fails_the_check_gets_one_correction():
    client = FakeAnthropicClient(
        [
            _classify_message(),
            _final_message({"apogee_m": "toolu_made_up"}),
            _final_message({"apogee_m": "toolu_c"}, apogee_m=1000.0),  # the tier's budget floor
        ]
    )

    events = [ev async for ev in run_design_loop(BOTTLE_TEXT, client=client)]

    sent = client.calls[-1]["messages"][-1]
    assert sent["role"] == "user"
    assert "toolu_made_up" in sent["content"]
    assert events[-1].type == "final"
    assert len(events[-1].payload["result"]["designs"]) == 1
    assert "rejected_by_check" not in events[-1].payload["result"]


@pytest.mark.anyio
async def test_a_final_that_fails_twice_loses_the_design():
    bad = {"apogee_m": "toolu_made_up"}
    client = FakeAnthropicClient([_classify_message(), _final_message(bad), _final_message(bad)])

    events = [ev async for ev in run_design_loop(BOTTLE_TEXT, client=client)]

    assert events[-2].type == "warning"
    assert events[-2].payload["kind"] == "final_check"
    result = events[-1].payload["result"]
    assert result["designs"] == []
    assert result["rejected_by_check"][0]["check_problems"]
