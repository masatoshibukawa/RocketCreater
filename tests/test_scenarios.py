"""Regression tests: every scenarios/*.yaml runs end to end with the scripted fake client.

These are the demo scripts (CLAUDE.md section 10: the scenarios working is the top priority).
Every scenario must exercise its REAL physics model (bottle: water, amateur: solid, commercial:
multistage) and show at least one failing attempt before the passing ones.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import FakeAnthropicClient, build_demo_script
from rocketwright.agent.loop import AgentConfig, run_design_loop
from rocketwright.agent.tools import DUMMY_WARNING

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("*.yaml"))
MAX_RUN_S = 15.0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"  # trio is not installed


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


async def _run(scenario: dict[str, Any]) -> list[AgentEvent]:
    text = scenario["request_text"]
    env = scenario.get("env") or {}
    seed = scenario.get("seed")
    tier = scenario["expected"]["tier"]
    client = FakeAnthropicClient(build_demo_script(tier, text, env, seed))
    cfg = AgentConfig.load()
    return [ev async for ev in run_design_loop(text, client=client, config=cfg, env=env, seed=seed)]


def _sim_results(events: list[AgentEvent]) -> dict[str, dict[str, Any]]:
    """tool_use id -> simulate_design result, in call order."""
    return {
        e.payload["id"]: e.payload["result"]
        for e in events
        if e.type == "tool_result" and e.payload["name"] == "simulate_design"
    }


def test_scenario_files_exist() -> None:
    assert SCENARIOS, f"no scenarios in {SCENARIO_DIR}"
    assert {p.stem for p in SCENARIOS} >= {"demo_amateur", "demo_bottle", "demo_commercial"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
async def test_scenario_runs_end_to_end_with_fake_client(path: Path) -> None:
    scenario = _load(path)
    expected_tier = scenario["expected"]["tier"]

    t0 = time.monotonic()
    events = await _run(scenario)
    elapsed = time.monotonic() - t0
    assert elapsed < MAX_RUN_S, f"{path.stem} took {elapsed:.1f} s"

    # classified tier matches the scenario expectation
    classify = next(
        e for e in events if e.type == "tool_result" and e.payload["name"] == "classify_requirement"
    )
    assert classify.payload["is_error"] is False
    assert classify.payload["result"]["tier"] == expected_tier

    # no tool error anywhere in the demo
    assert all(not e.payload.get("is_error") for e in events if e.type == "tool_result")

    # a final event with at least one passing design and clean provenance
    final = events[-1]
    assert final.type == "final", final.payload
    result = final.payload["result"]
    assert isinstance(result, dict)
    passing = [d for d in result["designs"] if d["passed"]]
    assert passing
    assert final.payload["provenance_violations"] == []

    # every source id maps to a real simulate_design tool_use id of this run
    sims = _sim_results(events)
    for d in result["designs"]:
        assert d["sources"], d
        assert set(d["sources"].values()) <= set(sims), d["sources"]
        sim = sims[d["sources"]["cost_jpy"]]
        assert d["cost_jpy"] == sim["cost_jpy"]
        assert d["metrics"] == sim["metrics"]
        assert d["passed"] == sim["success"]

    # the demo's point: a failing attempt whose reason is read and fixed, then passes
    ordered = list(sims.values())
    assert ordered[0]["success"] is False, "the first attempt must fail"
    assert ordered[0]["failure_reasons"]
    assert ordered[-1]["success"] is True

    # real physics for every tier: no dummy placeholder in any simulate result
    for sim in ordered:
        assert DUMMY_WARNING not in sim["warnings"]
        assert not any("DUMMY" in w for w in sim["warnings"])
        assert sim["cost_jpy"] > 0

    if expected_tier == "commercial":
        assert any("perigee" in r for r in ordered[0]["failure_reasons"])
        for d in passing:
            assert d["metrics"]["perigee_m"] >= 360_000
            assert d["cost_jpy"] <= 2.0e9  # scenario budget
    elif expected_tier == "amateur":
        assert any("descent speed" in r for r in ordered[0]["failure_reasons"])
        for d in passing:
            assert 1_800 <= d["metrics"]["apogee_m"] <= 2_200  # +-10 % of the 2 km target
            assert d["metrics"]["stability_margin_cal"] >= 1.5
            assert d["metrics"]["descent_speed_mps"] <= 6.0
            assert d["cost_jpy"] <= 50_000
    else:
        assert any("parachute" in r for r in ordered[0]["failure_reasons"])
        for d in passing:
            assert 27 <= d["metrics"]["apogee_m"] <= 33  # +-10 % of the 30 m target
            assert d["metrics"]["descent_speed_mps"] <= 6.0  # the egg
            assert d["cost_jpy"] <= 3_000


@pytest.mark.anyio
async def test_commercial_designs_use_catalog_engine_ids() -> None:
    scenario = _load(SCENARIO_DIR / "demo_commercial.yaml")
    events = await _run(scenario)
    calls = [e for e in events if e.type == "tool_call" and e.payload["name"] == "simulate_design"]
    assert calls
    search = next(
        e for e in events if e.type == "tool_result" and e.payload["name"] == "search_catalog"
    )
    catalog_ids = {eng["id"] for eng in search.payload["result"]["engines"]}
    assert catalog_ids
    for call in calls:
        design = call.payload["input"]["design"]
        for stage in design["stages"]:
            assert stage["engine_id"] in catalog_ids, stage["engine_id"]
        assert call.payload["input"]["tune_pitch"] is False  # demo uses pre-tuned numbers
