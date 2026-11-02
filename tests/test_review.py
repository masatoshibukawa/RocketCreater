"""Tests for the per-aspect reviewers (rocketwright.agent.review) with the fake client."""

from __future__ import annotations

import httpx
import pytest

from rocketwright.agent.fake_client import FakeAnthropicClient
from rocketwright.agent.loop import AgentConfig
from rocketwright.agent.prompts import REVIEWER_PROMPTS
from rocketwright.agent.review import (
    ASPECTS,
    ReviewVerdict,
    review_candidate,
    review_feedback_message,
    sanitize_verdict,
)

SIM = {
    "success": True,
    "failure_reasons": [],
    "metrics": {"apogee_m": 2050.0, "descent_speed_mps": 4.8, "stability_margin_cal": 1.9},
    "cost_jpy": 47000.0,
    "warnings": [],
    "source_id": "toolu_sim_2",
}
CANDIDATE = {
    "source_id": "toolu_sim_2",
    "design": {"tier": "amateur", "parachute_diameter_m": 1.2},
    "metrics": SIM["metrics"],
    "cost_jpy": SIM["cost_jpy"],
}
REQ = "1 kg to 2 km, recover by parachute, budget 50000 JPY"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _api_error() -> Exception:
    import anthropic

    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.invalid"))


def test_reviewer_prompts_cover_all_aspects_and_forbid_new_numbers():
    assert tuple(REVIEWER_PROMPTS) == ASPECTS == ("stability", "recovery", "cost", "safety")
    for aspect, prompt in REVIEWER_PROMPTS.items():
        assert aspect in prompt
        assert "do not" in prompt.lower() or "never" in prompt.lower()
    assert "propellant" in REVIEWER_PROMPTS["safety"].lower()


@pytest.mark.anyio
async def test_review_candidate_runs_four_reviewers_in_order_on_light_model():
    client = FakeAnthropicClient([])
    cfg = AgentConfig.load()
    verdicts = await review_candidate(client, cfg, CANDIDATE, SIM, REQ)
    assert [v.aspect for v in verdicts] == list(ASPECTS)
    assert all(v.severity == "ok" for v in verdicts)  # unscripted fake answers "ok"
    assert len(client.parse_calls) == 4
    for call in client.parse_calls:
        assert call["model"] == "claude-haiku-5-5"
        assert call["max_tokens"] == 4096
        assert call["output_config"] == {"effort": "low"}
        assert call["output_format"] is ReviewVerdict
        assert "tool_choice" not in call and "tools" not in call
        assert "budget_tokens" not in str(call.get("thinking", ""))
        user = call["messages"][0]
        assert user["role"] == "user"
        assert "toolu_sim_2" in user["content"]
        assert REQ in user["content"]
    systems = [c["system"] for c in client.parse_calls]
    assert systems == list(REVIEWER_PROMPTS.values())


@pytest.mark.anyio
async def test_scripted_verdicts_and_api_error_fallback():
    reviews = [
        {
            "cost": {
                "aspect": "cost",
                "severity": "major",
                "findings": ["cost_jpy 47000 leaves little margin under budget"],
                "suggested_changes": ["choose a cheaper motor"],
            },
            "recovery": _api_error(),
            "stability": ReviewVerdict(
                aspect="stability", severity="ok", findings=[], suggested_changes=[]
            ),
        }
    ]
    client = FakeAnthropicClient([], reviews=reviews)
    verdicts = await review_candidate(client, AgentConfig.load(), CANDIDATE, SIM, REQ)
    by_aspect = {v.aspect: v for v in verdicts}
    assert by_aspect["cost"].severity == "major"
    assert by_aspect["recovery"].severity == "minor"
    assert by_aspect["recovery"].findings[0].startswith("reviewer unavailable: ")
    assert "APIConnectionError" in by_aspect["recovery"].findings[0]
    assert by_aspect["stability"].severity == "ok"
    assert by_aspect["safety"].severity == "ok"


def test_sanitize_drops_findings_with_unsourced_numbers():
    v = ReviewVerdict(
        aspect="stability",
        severity="major",
        findings=[
            "stability_margin_cal 1.9 is above the 1.5 cal minimum",  # 1.5 not in results
            "apogee_m 2050 is fine",
            "margin may drop with a heavier payload",
        ],
        suggested_changes=["use a 2.5 m chute"],  # unsourced too
    )
    clean, dropped = sanitize_verdict(v, [SIM, CANDIDATE["design"]])
    assert clean.findings == [
        "apogee_m 2050 is fine",
        "margin may drop with a heavier payload",
        "[1 finding dropped: it cited numbers absent from the tool results]",
    ]
    assert dropped == ["stability_margin_cal 1.9 is above the 1.5 cal minimum", "use a 2.5 m chute"]
    assert clean.suggested_changes == []
    assert clean.severity == "major"


def test_feedback_message_lists_only_non_ok_verdicts():
    verdicts = [
        ReviewVerdict(aspect="stability", severity="ok", findings=[], suggested_changes=[]),
        ReviewVerdict(
            aspect="cost",
            severity="major",
            findings=["cost leaves little margin"],
            suggested_changes=["cheaper motor"],
        ),
        ReviewVerdict(
            aspect="safety",
            severity="blocker",
            findings=["payload not in scope"],
            suggested_changes=[],
        ),
    ]
    msg = review_feedback_message(verdicts, source_id="toolu_sim_2")
    assert msg.startswith("Reviewer findings for candidate toolu_sim_2:")
    assert "[cost/major] cost leaves little margin; suggested: cheaper motor" in msg
    assert "[safety/blocker] payload not in scope" in msg
    assert "stability" not in msg
    assert "re-designing" in msg.lower() and "re-simulating" in msg.lower()
    assert "explain" in msg.lower()
    # nothing to say when everything is ok
    assert review_feedback_message([verdicts[0]], source_id="x") == ""
