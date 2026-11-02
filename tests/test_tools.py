"""Tests for the agent tool definitions and their implementations (real multistage physics for
commercial/heavy, dummy placeholders for bottle/amateur until phase 3)."""

import json

import pytest

from rocketwright.agent.tools import (
    DUMMY_WARNING,
    PASS_CRITERIA,
    TOOL_NAMES,
    TOOL_REGISTRY,
    execute_tool,
    get_tool_definitions,
)
from rocketwright.cost import estimate_cost_jpy
from rocketwright.physics import multistage as ms
from rocketwright.schema import DesignAdapter, DispersionResult, Env, SimResult

AMATEUR_DESIGN = {
    "tier": "amateur",
    "body_diameter_m": 0.054,
    "body_length_m": 0.9,
    "nose_shape": "ogive",
    "nose_length_m": 0.15,
    "fins": {"count": 4, "root_chord_m": 0.1, "tip_chord_m": 0.05, "span_m": 0.06},
    "motor_id": "dummy-F32",
    "dry_mass_kg": 0.5,
    "payload_mass_kg": 1.0,
    "parachute_diameter_m": 0.6,
    "deploy_delay_s": 4.0,
}

# Electron-class vehicle with catalog engine ids; reaches ~475 x 670 km with this pitch program
# (numbers from scripts/tune_demo_design.py).
COMMERCIAL_DESIGN = {
    "tier": "commercial",
    "stages": [
        {
            "propellant_mass_kg": 9250,
            "structural_fraction": 0.08,
            "engine_id": "rutherford",
            "engine_count": 10,
        },
        {
            "propellant_mass_kg": 3500,
            "structural_fraction": 0.10,
            "engine_id": "rutherford",
            "engine_count": 1,
        },
    ],
    "fairing_mass_kg": 50,
    "payload_mass_kg": 150,
    "pitch_start_s": 25.5,
    "initial_pitch_deg": 7.95,
}

BOTTLE_DESIGN = {
    "tier": "bottle",
    "bottle_volume_m3": 0.0015,
    "water_fill_frac": 0.4,
    "initial_gauge_pressure_pa": 500000,
    "nozzle_diameter_m": 0.022,
    "dry_mass_kg": 0.12,
    "payload_mass_kg": 0.06,
    "has_parachute": True,
    "parachute_diameter_m": 0.4,
}

ENV = {"launch_latitude_deg": 31.25, "launch_altitude_m": 20, "wind_speed_mps": 5}
REQ_AMATEUR = {"goal_kind": "altitude", "target_altitude_m": 2000, "payload_mass_kg": 1.0}
REQ_ORBIT = {"goal_kind": "orbit", "target_altitude_m": 400000, "payload_mass_kg": 150}


def _sim(design, req, seed=7, tune_pitch=False, tool_id="toolu_a"):
    inp = {
        "design": design,
        "env": ENV,
        "seed": seed,
        "requirement": req,
        "tune_pitch": tune_pitch,
    }
    return execute_tool("simulate_design", inp, tool_id)


def _walk(schema: dict):
    yield schema
    for v in schema.get("properties", {}).values():
        yield from _walk(v)
    for key in ("anyOf", "oneOf"):
        for v in schema.get(key, []):
            yield from _walk(v)
    if "items" in schema:
        yield from _walk(schema["items"])


def test_definitions_cover_all_tools_and_are_strict():
    defs = get_tool_definitions()
    assert [d["name"] for d in defs] == list(TOOL_NAMES)
    assert set(TOOL_REGISTRY) == set(TOOL_NAMES)
    for d in defs:
        assert d["strict"] is True
        assert d["description"]
        schema = d["input_schema"]
        assert schema["type"] == "object"
        for node in _walk(schema):
            if node.get("type") == "object" or "properties" in node:
                assert node.get("additionalProperties") is False, (d["name"], node)
                assert sorted(node.get("required", [])) == sorted(node.get("properties", {})), (
                    d["name"],
                    node,
                )
            assert "$ref" not in node and "$defs" not in node, d["name"]
    json.dumps(defs)  # must be JSON-serialisable


def test_classify_tool():
    out = execute_tool("classify_requirement", {"requirement": REQ_ORBIT}, "toolu_1")
    assert out["tier"] == "commercial"
    assert out["source_id"] == "toolu_1"
    assert "error" not in out


def test_validation_error_is_reported_not_raised():
    out = execute_tool(
        "classify_requirement", {"requirement": {"goal_kind": "sideways"}}, "toolu_2"
    )
    assert "error" in out
    assert out["source_id"] == "toolu_2"
    out = execute_tool("no_such_tool", {}, "toolu_3")
    assert "error" in out


def test_search_catalog_returns_lists():
    out = execute_tool(
        "search_catalog", {"tier": "commercial", "query": None, "kind": "all"}, "toolu_4"
    )
    assert isinstance(out["engines"], list)
    assert isinstance(out["parts"], list)
    assert isinstance(out["motors"], list)
    assert out["source_id"] == "toolu_4"
    out2 = execute_tool(
        "search_catalog", {"tier": None, "query": "zzz-no-such-thing", "kind": "engines"}, "t"
    )
    assert out2["engines"] == []


def test_search_catalog_tells_the_model_which_ids_to_use():
    out = execute_tool(
        "search_catalog", {"tier": "commercial", "query": None, "kind": "engines"}, "toolu_5"
    )
    ids = {e["id"] for e in out["engines"]}
    assert "merlin_1d" in ids
    assert "engine_id" in out["note"] and "id" in out["note"]
    defs = {d["name"]: d for d in get_tool_definitions()}
    sim_schema = json.dumps(defs["simulate_design"]["input_schema"])
    assert "engines.yaml" in sim_schema and "merlin_1d" in sim_schema
    assert "tune_pitch" in defs["simulate_design"]["input_schema"]["properties"]
    assert "second" in defs["simulate_design"]["description"]


@pytest.mark.parametrize(("design", "req"), [(AMATEUR_DESIGN, REQ_AMATEUR), (BOTTLE_DESIGN, None)])
def test_simulate_design_dummy_suborbital_is_valid_and_deterministic(design, req):
    a = _sim(design, req, tool_id="toolu_a")
    b = _sim(design, req, tool_id="toolu_b")
    assert "error" not in a
    sim = SimResult.model_validate(a)
    assert sim.tier == design["tier"]
    assert DUMMY_WARNING in sim.warnings
    assert a["source_id"] == "toolu_a"
    a.pop("source_id")
    b.pop("source_id")
    assert a == b
    c = _sim(design, req, seed=8, tool_id="toolu_c")
    c.pop("source_id")
    assert c != a
    assert len(sim.trace) > 2
    assert sim.cost_jpy > 0


def test_simulate_design_multistage_uses_real_physics():
    a = _sim(COMMERCIAL_DESIGN, REQ_ORBIT, tool_id="toolu_a")
    assert "error" not in a
    sim = SimResult.model_validate(a)
    assert sim.tier == "commercial"
    assert not any("DUMMY" in w for w in sim.warnings)
    # the metrics are the multistage model's, judged against the requirement's orbit
    design = DesignAdapter.validate_python(COMMERCIAL_DESIGN)
    ref = ms.simulate(design, Env.model_validate(ENV), target_perigee_m=400_000)
    assert sim.metrics == ref.metrics
    assert sim.success is True, sim.failure_reasons
    assert sim.metrics["perigee_m"] >= 360_000
    # cost comes from cost.py (multistage returns 0.0)
    assert sim.cost_jpy == pytest.approx(estimate_cost_jpy(design))
    assert sim.cost_jpy > 0
    assert len(sim.trace) > 2
    # the nominal model is deterministic and ignores the seed
    b = _sim(COMMERCIAL_DESIGN, REQ_ORBIT, seed=8, tool_id="toolu_b")
    a.pop("source_id")
    b.pop("source_id")
    assert a == b


def test_simulate_design_multistage_target_from_requirement():
    under_fuelled = {
        **COMMERCIAL_DESIGN,
        "stages": [
            {**COMMERCIAL_DESIGN["stages"][0], "engine_count": 9},
            {**COMMERCIAL_DESIGN["stages"][1], "propellant_mass_kg": 2500},
        ],
        "pitch_start_s": 12,
        "initial_pitch_deg": 4,
    }
    out = _sim(under_fuelled, REQ_ORBIT)
    assert "error" not in out
    assert out["success"] is False
    assert any("perigee" in r and "400 km" in r for r in out["failure_reasons"])
    # without a requirement only the multistage default minimum (150 km) applies, which this
    # ~290 km perigee clears: the 400 km rule really came from the requirement
    out2 = _sim(under_fuelled, None)
    assert out2["success"] is True, out2["failure_reasons"]
    assert not any("400 km" in r for r in out2["failure_reasons"])


def test_budget_rule_is_shared_by_dummy_and_real_paths():
    tight_orbit = {**REQ_ORBIT, "budget_jpy": 1000.0}
    out = _sim(COMMERCIAL_DESIGN, tight_orbit)
    assert out["success"] is False
    assert any("budget" in r for r in out["failure_reasons"])
    tight_amateur = {**REQ_AMATEUR, "budget_jpy": 1.0}
    out = _sim(AMATEUR_DESIGN, tight_amateur)
    assert out["success"] is False
    assert any("budget" in r for r in out["failure_reasons"])


def test_pass_criteria_are_suborbital_only():
    assert set(PASS_CRITERIA) == {
        "altitude_tolerance_frac",
        "min_stability_margin_cal",
        "max_descent_speed_mps",
    }
    assert "perigee_tolerance_frac" in ms.PASS_THRESHOLDS


def test_unknown_engine_id_is_an_error_not_a_crash():
    bad = {
        **COMMERCIAL_DESIGN,
        "stages": [{**COMMERCIAL_DESIGN["stages"][0], "engine_id": "eng-a"}],
    }
    out = _sim(bad, REQ_ORBIT, tool_id="toolu_bad")
    assert "error" in out
    assert "eng-a" in out["error"]
    assert "merlin_1d" in out["error"]  # the available ids are listed
    assert out["source_id"] == "toolu_bad"


def test_tune_pitch_returns_tuned_design():
    detuned = {**COMMERCIAL_DESIGN, "pitch_start_s": 15.0, "initial_pitch_deg": 3.0}
    out = _sim(detuned, REQ_ORBIT, tune_pitch=True)
    assert "error" not in out
    tuned = out["tuned_design"]
    assert tuned["stages"] == detuned["stages"]
    assert (tuned["pitch_start_s"], tuned["initial_pitch_deg"]) != (15.0, 3.0)
    # the returned SimResult is for the tuned design
    ref = _sim(tuned, REQ_ORBIT, tool_id="toolu_ref")
    assert ref["metrics"] == out["metrics"]
    assert out["success"] is True, out["failure_reasons"]


def test_tune_pitch_needs_an_orbit_requirement():
    out = _sim(COMMERCIAL_DESIGN, None, tune_pitch=True)
    assert "error" in out
    out = _sim(AMATEUR_DESIGN, REQ_AMATEUR, tune_pitch=True)
    assert "error" in out


def test_simulate_design_rejects_bad_design():
    out = execute_tool(
        "simulate_design",
        {"design": {"tier": "amateur"}, "env": ENV, "seed": 1, "requirement": None},
        "toolu_x",
    )
    assert "error" in out


@pytest.mark.parametrize("design", [AMATEUR_DESIGN, COMMERCIAL_DESIGN])
def test_run_dispersion_dummy(design):
    out = execute_tool(
        "run_dispersion",
        {"design": design, "env": ENV, "n": 50, "seed": 3, "requirement": None},
        "toolu_d",
    )
    assert "error" not in out
    disp = DispersionResult.model_validate(out)
    assert disp.n == 50
    assert disp.seed == 3
    assert 0 <= disp.success_rate <= 1
    assert DUMMY_WARNING in disp.warnings
    if design["tier"] == "amateur":
        assert disp.landing is not None and len(disp.landing.points) == 50
    else:
        assert disp.orbit_insertion is not None
        # the p50 is the REAL simulate result so the numbers stay consistent
        real = _sim(design, None)
        assert disp.quantiles["perigee_m"].p50 == real["metrics"]["perigee_m"]


def test_estimate_cost_tool():
    out = execute_tool("estimate_cost", {"design": COMMERCIAL_DESIGN}, "toolu_e")
    assert out["cost_jpy"] > 0
    assert out["provisional"] is True


def test_stubs_report_not_implemented():
    out = execute_tool("render_drawing", {"design": AMATEUR_DESIGN}, "toolu_f")
    assert out["status"] == "not_implemented"
    out = execute_tool(
        "export_report", {"designs": [AMATEUR_DESIGN], "format": "markdown"}, "toolu_g"
    )
    assert out["status"] == "not_implemented"
