"""Tests for the agent tool definitions and their (currently dummy) implementations."""

import json

import pytest

from rocketwright.agent.tools import (
    TOOL_NAMES,
    TOOL_REGISTRY,
    execute_tool,
    get_tool_definitions,
)
from rocketwright.schema import DispersionResult, SimResult

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

COMMERCIAL_DESIGN = {
    "tier": "commercial",
    "stages": [
        {"propellant_mass_kg": 20000, "structural_fraction": 0.08, "engine_id": "eng-a"},
        {"propellant_mass_kg": 4000, "structural_fraction": 0.1, "engine_id": "eng-b"},
    ],
    "fairing_mass_kg": 150,
    "payload_mass_kg": 150,
    "pitch_start_s": 10,
    "initial_pitch_deg": 5,
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


@pytest.mark.parametrize(
    ("design", "req"),
    [(AMATEUR_DESIGN, REQ_AMATEUR), (COMMERCIAL_DESIGN, REQ_ORBIT), (BOTTLE_DESIGN, None)],
)
def test_simulate_design_dummy_is_valid_and_deterministic(design, req):
    inp = {"design": design, "env": ENV, "seed": 7, "requirement": req}
    a = execute_tool("simulate_design", inp, "toolu_a")
    b = execute_tool("simulate_design", inp, "toolu_b")
    assert "error" not in a
    sim = SimResult.model_validate(a)
    assert sim.tier == design["tier"]
    assert any("DUMMY" in w for w in sim.warnings)
    assert a["source_id"] == "toolu_a"
    a.pop("source_id")
    b.pop("source_id")
    assert a == b
    c = execute_tool("simulate_design", {**inp, "seed": 8}, "toolu_c")
    c.pop("source_id")
    assert c != a
    assert len(sim.trace) > 2
    assert sim.cost_jpy > 0


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
    assert any("DUMMY" in w for w in disp.warnings)
    if design["tier"] == "amateur":
        assert disp.landing is not None and len(disp.landing.points) == 50
    else:
        assert disp.orbit_insertion is not None


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
