"""Regression tests: every scenarios/*.yaml runs end to end with the scripted fake client.

These are the demo scripts (CLAUDE.md section 10: the scenarios working is the top priority).
Every scenario must exercise its REAL physics model (bottle: water, amateur: solid, commercial:
multistage) and derive its targets by formula. The orbital story seeds the design from the
reference catalog and shows a failing attempt whose reason is read and fixed; the bottle /
amateur stories run the staged design chain: auto_design baseline -> design_stage revisions,
each starting at the most upstream stage that changes (a failing candidate is read and the
cause fixed upstream first) -> design_from_parts -> run_dispersion.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from rocketwright.agent.events import AgentEvent
from rocketwright.agent.fake_client import (
    CHAIN_TIERS,
    FakeAnthropicClient,
    attempt_outcome,
    build_demo_script,
)
from rocketwright.agent.loop import ATTEMPT_TOOLS, AgentConfig, run_design_loop
from rocketwright.design_chain import STAGES
from rocketwright.references import load_references
from rocketwright.schema import Tier

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
    client = FakeAnthropicClient(
        build_demo_script(tier, text, env, seed, story=scenario.get("story"))
    )
    cfg = AgentConfig.load().model_copy(update={"allowed_tiers": tuple(Tier)})
    return [ev async for ev in run_design_loop(text, client=client, config=cfg, env=env, seed=seed)]


def _tool_results(events: list[AgentEvent], name: str) -> dict[str, dict[str, Any]]:
    """tool_use id -> result of the named tool, in call order."""
    return {
        e.payload["id"]: e.payload["result"]
        for e in events
        if e.type == "tool_result" and e.payload["name"] == name
    }


def _tool_inputs(events: list[AgentEvent], name: str) -> dict[str, dict[str, Any]]:
    return {
        e.payload["id"]: e.payload["input"]
        for e in events
        if e.type == "tool_call" and e.payload["name"] == name
    }


def _sim_results(events: list[AgentEvent]) -> dict[str, dict[str, Any]]:
    """tool_use id -> sim result of every attempt (simulate_design result, or the `sim` of a
    design_from_parts / auto_design result; a build stopped by a buildability error gives a
    failed, empty sim whose failure_reasons are the error issues), in call order."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.type != "tool_result" or e.payload["name"] not in ATTEMPT_TOOLS:
            continue
        result = e.payload["result"]
        sim, _ = attempt_outcome(e.payload["name"], result)
        if not sim:
            errors = [i["message"] for i in result["issues"] if i["severity"] == "error"]
            sim = {
                "success": False,
                "failure_reasons": errors,
                "metrics": {},
                "warnings": [],
                "cost_jpy": (result.get("bill") or {}).get("cost_jpy"),
            }
        out[e.payload["id"]] = sim
    return out


# build field -> design-chain stage (bottle and amateur)
_STAGE_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "amateur": {
        "motor": ("motor_id",),
        "mount": ("motor_mount_id",),
        "body_tube": ("body_tube_id",),
        "nose_cone": ("nose_cone_id",),
        "body_length": ("body_length_m",),
        "fins": ("fin_material_id", "fins"),
        "parachute": ("parachute_id",),
        "deploy_delay": ("deploy_delay_s",),
    },
    "bottle": {
        "bottle": ("bottle_id",),
        "nozzle": ("nozzle_id",),
        "water_fill": ("water_fill_frac",),
        "pressure": ("initial_gauge_pressure_pa",),
        "fins": ("fin_set_id",),
        "parachute": ("parachute_id",),
    },
}


def _changed_stages(tier: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return [
        stage
        for stage, fields in _STAGE_FIELDS[tier].items()
        if any(before.get(f) != after.get(f) for f in fields)
    ]


def test_scenario_files_exist() -> None:
    assert SCENARIOS, f"no scenarios in {SCENARIO_DIR}"
    assert {p.stem for p in SCENARIOS} >= {
        "demo_amateur",
        "demo_bottle",
        "demo_commercial",
        "demo_model_rocket",
    }


def _check_common(path: Path, scenario: dict[str, Any], events: list[AgentEvent]) -> None:
    expected_tier = scenario["expected"]["tier"]
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
    assert [d for d in result["designs"] if d["passed"]]
    assert final.payload["provenance_violations"] == []

    # the targets were derived by formula and the final cites that tool call
    derives = _tool_results(events, "derive_requirements")
    assert len(derives) == 1
    derive_id, derive = next(iter(derives.items()))
    assert derive["tier"] == expected_tier and derive["quantities"]
    assert result["derived_targets"] == derive_id

    # the final cites a catalog reference of this tier
    catalog = {entry.id: entry for entry in load_references()}
    assert result["reference_id"] in catalog
    assert catalog[result["reference_id"]].tier.value == expected_tier

    # every source id maps to a real attempt / run_dispersion tool_use id of this run
    sims = _sim_results(events)
    disps = _tool_results(events, "run_dispersion")
    for d in result["designs"]:
        assert d["sources"], d
        assert set(d["sources"].values()) <= set(sims) | set(disps), d["sources"]
        sim = sims[d["sources"]["cost_jpy"]]
        assert d["cost_jpy"] == sim["cost_jpy"]
        assert d["metrics"] == sim["metrics"]
        assert d["passed"] == sim["success"]
        assert d["design"]["tier"] == expected_tier

    # the Monte-Carlo dispersion on a passing design, its success rate in the final answer
    # (real rocketwright.dispersion, n=100, same seed as the scenario)
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

    # real physics for every tier: no dummy placeholder in any attempt result
    for sim in sims.values():
        assert not any("DUMMY" in w for w in sim["warnings"])
        assert sim["cost_jpy"] > 0


def _check_chain_story(scenario: dict[str, Any], events: list[AgentEvent]) -> dict[str, Any]:
    """The staged-chain story of a bottle / amateur scenario; returns what the per-scenario
    checks need."""
    tier = scenario["expected"]["tier"]
    order = STAGES[tier]
    result = events[-1].payload["result"]
    calls = [e.payload["name"] for e in events if e.type == "tool_call"]
    # classify -> derive (+ nearest real kit as context) -> auto_design -> design_stage* ->
    # design_from_parts -> run_dispersion
    assert calls[:4] == [
        "classify_requirement",
        "derive_requirements",
        "find_reference_designs",
        "auto_design",
    ]
    tail = calls[4:]
    n_stage = tail.count("design_stage")
    assert tail == ["design_stage"] * n_stage + ["design_from_parts", "run_dispersion"]
    assert n_stage >= 1
    # the reference is context only (no seed), and the final cites the nearest one
    ref_id, ref = next(iter(_tool_results(events, "find_reference_designs").items()))
    assert _tool_inputs(events, "find_reference_designs")[ref_id]["seed"] is False
    assert ref["seed"] is None and result["reference_id"] == ref["references"][0]["id"]
    assert ref_id in result["summary"]

    # auto_design: attempt 1, a candidate with its build / bill, its trace quoted
    auto_id, auto = next(iter(_tool_results(events, "auto_design").items()))
    assert [t["stage"] for t in auto["trace"]] == list(order)
    assert auto["sim"]["success"] is True and "trace" not in auto["sim"]
    cands = {e.payload["source_id"]: e for e in events if e.type == "candidate"}
    assert cands[auto_id].attempt == 1
    assert cands[auto_id].payload["origin"] == "auto_design"
    assert cands[auto_id].payload["build"] == auto["build"]
    first = auto["trace"][0]
    funnel = first["funnel"]
    assert (
        f"{funnel['enumerated']} enumerated, {funnel['simulated']} simulated, "
        f"{funnel['passed']} passed" in result["summary"]
    )

    # design_stage calls: exploration (no candidate, no attempt), each starting at or upstream
    # of every stage it changes: `chosen` only holds stages above `stage`, each one the option
    # in effect (auto_design's choice or a candidate adopted from an earlier design_stage call)
    stage_inputs = _tool_inputs(events, "design_stage")
    stage_results = _tool_results(events, "design_stage")
    in_effect: dict[str, set[str]] = {t["stage"]: {str(t["chosen"])} for t in auto["trace"]}
    for sid, inp in stage_inputs.items():
        assert sid not in cands
        stage = inp["stage"]
        for pair in inp["chosen"]:
            assert order.index(pair["stage"]) < order.index(stage), (stage, pair)
            assert pair["value"] in in_effect.get(pair["stage"], set()), (stage, pair)
        res = stage_results[sid]
        assert res["stage"] == stage and res["candidates"]
        assert res["enumerated"] >= res["compatible"] >= res["simulated"] >= res["passed"]
        in_effect.setdefault(stage, set()).update(c["option"] for c in res["candidates"])
        # the candidates' why are quoted in the final summary (funnel and the reason)
        assert f"design_stage({stage})" in result["summary"]
    # the final build is one of the last design_stage call's candidates (or the baseline),
    # and it differs from the baseline only at / below the first revised stage
    parts_id, parts = next(iter(_tool_results(events, "design_from_parts").items()))
    last = stage_results[list(stage_inputs)[-1]]
    assert parts["build"] == auto["build"] or parts["build"] in [
        c["build"] for c in last["candidates"]
    ]
    changed = _changed_stages(tier, auto["build"], parts["build"])
    min_index = min(order.index(inp["stage"]) for inp in stage_inputs.values())
    assert all(order.index(s) >= min_index for s in changed), (changed, min_index)
    assert cands[parts_id].attempt == 2
    assert cands[parts_id].payload["origin"] == "design_from_parts"
    assert events[-1].payload["attempts"] == 2
    # the dispersion ran on the final build, judged on its parts bill
    disp_input = next(iter(_tool_inputs(events, "run_dispersion").values()))
    assert disp_input["design"] == parts["design"]
    assert disp_input["cost_jpy"] == parts["bill"]["cost_jpy"]
    # a failing candidate was read on the way (the "fix the cause" beat), and the part-space
    # rows of the final carry the parts and the bill
    failing = [c for r in stage_results.values() for c in r["candidates"] if not c["passed"]]
    assert failing and all(c["failure_reasons"] or c["issues"] for c in failing)
    for d in result["designs"]:
        assert d["build"]["tier"] == tier
        assert d["bill"] and all(r["part_id"] for r in d["bill"])
        assert "parts:" in d["explanation"]
    return {
        "auto": auto,
        "parts": parts,
        "stage_inputs": list(stage_inputs.values()),
        "stage_results": list(stage_results.values()),
        "changed": changed,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
async def test_scenario_runs_end_to_end_with_fake_client(path: Path) -> None:
    scenario = _load(path)
    expected_tier = scenario["expected"]["tier"]

    t0 = time.monotonic()
    events = await _run(scenario)
    elapsed = time.monotonic() - t0
    assert elapsed < MAX_RUN_S, f"{path.stem} took {elapsed:.1f} s"
    _check_common(path, scenario, events)
    result = events[-1].payload["result"]
    passing = [d for d in result["designs"] if d["passed"]]

    if expected_tier in CHAIN_TIERS:
        story = _check_chain_story(scenario, events)
        auto, parts = story["auto"], story["parts"]
        stages = [inp["stage"] for inp in story["stage_inputs"]]
        if path.stem == "demo_amateur":
            # baseline: a certified J motor in the 54 mm LOC tube, 2 tubes + coupler, over-
            # stable, Level 2; avoid the coupler from the mount stage (the 98 mm single tube
            # fails), then ease the margin from the fins stage
            assert auto["build"]["motor_id"] == "aerotech_J435WS"
            assert auto["build"]["body_tube_id"] == "loc_tube_54mm"
            codes = {i["code"] for i in auto["issues"]}
            assert {"high_power_motor", "body_length_stock", "static_margin_high"} <= codes
            assert "Level 2" in result["summary"]
            assert stages == ["mount", "fins"]
            mount = story["stage_results"][0]
            single = [
                c for c in mount["candidates"] if c["build"]["body_tube_id"] == "loc_tube_98mm"
            ]
            assert single and not single[0]["passed"]
            assert story["changed"] == ["fins"]
            assert (
                parts["sim"]["metrics"]["stability_margin_cal"]
                < auto["sim"]["metrics"]["stability_margin_cal"]
            )
            for d in passing:
                assert 1_800 <= d["metrics"]["apogee_m"] <= 2_200  # +-10 % of the 2 km target
                assert d["metrics"]["descent_speed_mps"] <= 6.0
                assert d["cost_jpy"] <= 50_000
        elif path.stem == "demo_model_rocket":
            # no certification: a low-power motor (no high_power_motor warning) in an Estes
            # BT-60; the single-tube BT-80 fails, so the baseline is confirmed
            assert scenario["story"] == "model_rocket"
            assert auto["build"]["motor_id"] == "aerotech_F32T"
            assert auto["build"]["body_tube_id"] == "estes_bt60_tube"
            for build_issues in (auto["issues"], parts["issues"]):
                assert "high_power_motor" not in {i["code"] for i in build_issues}
            assert stages == ["body_tube"]
            assert parts["build"] == auto["build"]
            assert len(result["designs"]) == 1  # the confirmed baseline, not listed twice
            for d in passing:
                assert 450 <= d["metrics"]["apogee_m"] <= 550
                assert d["cost_jpy"] <= 20_000
        else:
            # the loop keeps the user's 1.5 L bottle from the baseline on, so only the pressure
            # is revisited: the lowest passing one, for headroom below the cap
            assert auto["build"]["bottle_id"] == "pet_bottle_1p5l"
            assert stages == ["pressure"]
            assert story["stage_inputs"][0]["chosen"][0] == {
                "stage": "bottle",
                "value": "pet_bottle_1p5l",
            }
            assert parts["build"]["bottle_id"] == "pet_bottle_1p5l"
            pressures = [
                float(c["option"]) for c in story["stage_results"][0]["candidates"] if c["passed"]
            ]
            assert parts["build"]["initial_gauge_pressure_pa"] == min(pressures)
            assert (
                parts["build"]["initial_gauge_pressure_pa"]
                < auto["build"]["initial_gauge_pressure_pa"]
            )
            for d in passing:
                assert 27 <= d["metrics"]["apogee_m"] <= 33  # +-10 % of the 30 m target
                assert d["metrics"]["descent_speed_mps"] <= 6.0  # the egg
                assert d["cost_jpy"] <= 3_000
        return

    # orbital story: seeded from a catalog reference, a failing attempt read and fixed
    ref_id, ref = next(iter(_tool_results(events, "find_reference_designs").items()))
    seed = ref["seed"]
    assert seed["reference_id"] == result["reference_id"]
    assert seed["notes"] and "trace" not in seed["sim"]
    assert seed["design"]["tier"] == expected_tier
    first_call = next(
        e for e in events if e.type == "tool_call" and e.payload["name"] == "simulate_design"
    )
    first_design = first_call.payload["input"]["design"]
    assert first_design["boosters"] == seed["design"]["boosters"]
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
    ordered = list(_sim_results(events).values())
    failed = [s for s in ordered if not s["success"]]
    assert failed, "the demo must show at least one failing attempt"
    assert all(s["failure_reasons"] for s in failed)
    assert ordered[-1]["success"] is True
    # seeded from Electron: the tuned seed passes, the cheaper first-stage cut fails on
    # perigee, the upper-stage cut passes cheaper
    assert result["reference_id"] == "electron"
    assert [s["success"] for s in ordered] == [True, False, True]
    assert any("perigee" in r for r in ordered[1]["failure_reasons"])
    assert ordered[2]["cost_jpy"] < ordered[0]["cost_jpy"]
    for d in passing:
        assert d["metrics"]["perigee_m"] >= 360_000
        assert d["cost_jpy"] <= 2.0e9  # scenario budget


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
