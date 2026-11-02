"""Regression tests: every scenarios/*.yaml runs end to end with the scripted fake client.

These are the demo scripts (CLAUDE.md section 10: the scenarios working is the top priority).
Every scenario must exercise its REAL physics model (bottle: water, amateur: solid, commercial:
multistage), derive its targets by formula, seed the design from the reference catalog, and
show at least one failing attempt whose reason is read and fixed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import (
    DEMO_ATTEMPT_TOOL,
    FakeAnthropicClient,
    attempt_outcome,
    build_demo_script,
)
from rocketwright.agent.loop import AgentConfig, run_design_loop
from rocketwright.references import load_references

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


def _tool_results(events: list[AgentEvent], name: str) -> dict[str, dict[str, Any]]:
    """tool_use id -> result of the named tool, in call order."""
    return {
        e.payload["id"]: e.payload["result"]
        for e in events
        if e.type == "tool_result" and e.payload["name"] == name
    }


def _sim_results(events: list[AgentEvent], tier: str) -> dict[str, dict[str, Any]]:
    """tool_use id -> sim result of every attempt (simulate_design result, or the `sim` of a
    design_from_parts result; a build stopped by a buildability error gives a failed, empty
    sim whose failure_reasons are the error issues)."""
    out: dict[str, dict[str, Any]] = {}
    for tid, result in _tool_results(events, DEMO_ATTEMPT_TOOL[tier]).items():
        sim, _ = attempt_outcome(tier, result)
        if not sim:
            errors = [i["message"] for i in result["issues"] if i["severity"] == "error"]
            sim = {
                "success": False,
                "failure_reasons": errors,
                "metrics": {},
                "warnings": [],
                "cost_jpy": (result.get("bill") or {}).get("cost_jpy"),  # the bill still exists
            }
        out[tid] = sim
    return out


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

    # the targets were derived by formula and the final cites that tool call
    derives = _tool_results(events, "derive_requirements")
    assert len(derives) == 1
    derive_id, derive = next(iter(derives.items()))
    assert derive["tier"] == expected_tier and derive["quantities"]
    assert result["derived_targets"] == derive_id

    # the design was seeded from a catalog reference of this tier and the final cites it
    refs = _tool_results(events, "find_reference_designs")
    assert len(refs) == 1
    ref_id, ref = next(iter(refs.items()))
    catalog = {entry.id: entry for entry in load_references()}
    assert result["reference_id"] in catalog
    assert catalog[result["reference_id"]].tier.value == expected_tier
    seed = ref["seed"]
    assert seed["reference_id"] == result["reference_id"]
    assert seed["notes"] and "trace" not in seed["sim"]
    assert seed["design"]["tier"] == expected_tier
    # the first attempt is based on the seed (same tier and propulsion / bottle); the part-space
    # tiers adopt the seed BUILD with design_from_parts, the others the seed design
    attempt_tool = DEMO_ATTEMPT_TOOL[expected_tier]
    first_call = next(
        e for e in events if e.type == "tool_call" and e.payload["name"] == attempt_tool
    )
    if attempt_tool == "design_from_parts":
        assert seed["build"] is not None and first_call.payload["input"]["build"] == seed["build"]
    else:
        first_design = first_call.payload["input"]["design"]
        for key in ("motor_id", "nozzle_diameter_m", "boosters"):
            if key in seed["design"]:
                assert first_design[key] == seed["design"][key]
    # a passing seed is shown as a free candidate (attempt 0) citing the reference tool call
    seed_candidates = [
        e for e in events if e.type == "candidate" and e.payload["source_id"] == ref_id
    ]
    if seed["sim"]["success"]:
        assert len(seed_candidates) == 1
        assert seed_candidates[0].attempt == 0
        assert seed_candidates[0].payload["seeded_from"] == result["reference_id"]
        assert seed_candidates[0].payload["metrics"] == seed["sim"]["metrics"]
    else:
        assert seed_candidates == []

    # every source id maps to a real attempt / run_dispersion tool_use id of this run
    sims = _sim_results(events, expected_tier)
    disps = _tool_results(events, "run_dispersion")
    for d in result["designs"]:
        assert d["sources"], d
        assert set(d["sources"].values()) <= set(sims) | set(disps), d["sources"]
        sim = sims[d["sources"]["cost_jpy"]]
        assert d["cost_jpy"] == sim["cost_jpy"]
        assert d["metrics"] == sim["metrics"]
        assert d["passed"] == sim["success"]
        assert d["design"]["tier"] == expected_tier
        if attempt_tool == "design_from_parts":
            # the final cites the parts: the build's ids and the bill rows
            assert d["build"]["tier"] == expected_tier
            assert d["bill"] and all(r["part_id"] for r in d["bill"])
            assert "parts:" in d["explanation"]

    # the demo runs the Monte-Carlo dispersion on the first passing design and reports its
    # success rate (real rocketwright.dispersion, n=100, same seed as the scenario)
    assert len(disps) == 1
    disp = next(iter(disps.values()))
    assert disp["n"] == 100 and disp["seed"] == scenario.get("seed")
    assert 0.0 <= disp["success_rate"] <= 1.0
    assert disp["quantiles"] and "nominal" in disp
    assert not any("DUMMY" in w for w in disp["warnings"])
    with_rate = [d for d in result["designs"] if d["success_rate"] is not None]
    assert with_rate, "the final answer must carry the dispersion success rate"
    for d in with_rate:
        assert d["success_rate"] == disp["success_rate"]
        assert d["sources"]["success_rate"] in disps
    if expected_tier in ("bottle", "amateur"):
        assert disp["landing"] is not None and len(disp["landing"]["points"]) == 100
        assert disp["orbit_insertion"] is None
    else:
        assert disp["orbit_insertion"] is not None and disp["landing"] is None

    # the demo's point: a failing attempt whose reason is read and fixed, then passes
    ordered = list(sims.values())
    failed = [s for s in ordered if not s["success"]]
    assert failed, "the demo must show at least one failing attempt"
    assert all(s["failure_reasons"] for s in failed)
    assert ordered[-1]["success"] is True

    # real physics for every tier: no dummy placeholder in any simulate result
    for sim in ordered:
        assert not any("DUMMY" in w for w in sim["warnings"])
        assert sim["cost_jpy"] > 0

    if expected_tier == "commercial":
        # seeded from Electron: the tuned seed passes, the cheaper first-stage cut fails on
        # perigee, the upper-stage cut passes cheaper
        assert result["reference_id"] == "electron"
        assert [s["success"] for s in ordered] == [True, False, True]
        assert any("perigee" in r for r in ordered[1]["failure_reasons"])
        assert ordered[2]["cost_jpy"] < ordered[0]["cost_jpy"]
        for d in passing:
            assert d["metrics"]["perigee_m"] >= 360_000
            assert d["cost_jpy"] <= 2.0e9  # scenario budget
    elif expected_tier == "amateur":
        # seeded from an Estes kit scaled into a 54 mm minimum-diameter airframe: the seed
        # build cannot be built (fins do not fit the balsa sheet) and its own sim overshoots;
        # the 66 mm BT-80 airframe with plywood / G-10 fins fixes both
        assert result["reference_id"].startswith("estes_")
        assert [s["success"] for s in ordered] == [False, True, True]
        assert any("fin" in r and "sheet" in r for r in ordered[0]["failure_reasons"])
        assert seed["sim"]["metrics"]["apogee_m"] > 2_200 and not seed["sim"]["success"]
        for d in passing:
            assert 1_800 <= d["metrics"]["apogee_m"] <= 2_200  # +-10 % of the 2 km target
            assert d["metrics"]["stability_margin_cal"] >= 1.5
            assert d["metrics"]["descent_speed_mps"] <= 6.0
            assert d["cost_jpy"] <= 50_000
            assert d["build"]["body_tube_id"] == "estes_bt80_tube"
            assert d["build"]["motor_id"] == seed["build"]["motor_id"]
    else:
        # seeded from the Apte 2 L kit: the seed build is over budget (the launcher), the
        # user's 1.5 L bottle without the launcher passes, with more pressure and chute too
        assert result["reference_id"].startswith("apte_")
        assert [s["success"] for s in ordered] == [False, True, True]
        assert any("cost" in r for r in ordered[0]["failure_reasons"])
        for d in passing:
            assert d["build"]["bottle_id"] == "pet_bottle_1p5l"  # the bottle the user has
            assert d["design"]["bottle_volume_m3"] == 0.0015
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
        assert call.payload["input"]["tune_pitch"] is False  # the seed was tuned once
    ref = next(
        e for e in events if e.type == "tool_call" and e.payload["name"] == "find_reference_designs"
    )
    assert ref.payload["input"]["seed"] is True and ref.payload["input"]["tune"] is True
