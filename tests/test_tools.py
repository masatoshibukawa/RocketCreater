"""Tests for the agent tool definitions and their implementations (real physics for every tier:
multistage for commercial/heavy, solid for amateur, water for bottle; run_dispersion is the
real Monte Carlo of rocketwright.dispersion over the same judged simulate)."""

import json

import pytest

from rocketwright.agent.tools import (
    DISPERSION_DEFAULT_N,
    DISPERSION_MAX_N,
    PASS_CRITERIA,
    TOOL_NAMES,
    TOOL_REGISTRY,
    execute_tool,
    get_tool_definitions,
)
from rocketwright.cost import estimate_cost_jpy
from rocketwright.physics import multistage as ms
from rocketwright.physics import solid, water
from rocketwright.schema import DesignAdapter, DispersionResult, Env, SimResult

AMATEUR_DESIGN = {
    "tier": "amateur",
    "body_diameter_m": 0.054,
    "body_length_m": 0.9,
    "nose_shape": "ogive",
    "nose_length_m": 0.15,
    "fins": {"count": 4, "root_chord_m": 0.1, "tip_chord_m": 0.05, "span_m": 0.06},
    "motor_id": "dummy_G80",
    "dry_mass_kg": 0.5,
    "payload_mass_kg": 1.0,
    "parachute_diameter_m": 0.6,
    "deploy_delay_s": 1.0,
}

# Electron-class vehicle with catalog engine ids; with the coast-and-circularize insertion it
# reaches 400 km x ~760 km from this pitch program (numbers from scripts/tune_demo_design.py).
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


def test_derive_requirements_tool_classifies_when_tier_is_null():
    inp = {"requirement": REQ_ORBIT, "tier": None, "launch_latitude_deg": 28.5}
    out = execute_tool("derive_requirements", inp, "toolu_d1")
    assert "error" not in out
    assert out["source_id"] == "toolu_d1"
    assert out["tier"] == "commercial" and out["tier_from"] == "classify_requirement"
    assert out["goal_kind"] == "orbit"
    q = {x["key"]: x for x in out["quantities"]}
    assert abs(q["circular_speed_mps"]["value"] - 7670.0) < 10.0
    assert abs(q["rotation_credit_mps"]["value"] - 408.0) < 2.0
    assert q["required_dv_mps"]["provisional"] is True
    for x in out["quantities"]:
        assert x["formula"] and x["inputs"]
    assert out["summary"]
    json.dumps(out)


def test_derive_requirements_tool_honours_tier_and_default_latitude():
    inp = {"requirement": REQ_AMATEUR, "tier": "amateur", "launch_latitude_deg": None}
    out = execute_tool("derive_requirements", inp, "toolu_d2")
    assert "error" not in out
    assert out["tier"] == "amateur" and out["tier_from"] == "input"
    q = {x["key"]: x for x in out["quantities"]}
    assert abs(q["burnout_speed_vacuum_mps"]["value"] - 198.0) < 0.5
    assert q["motor_class_impulse_min_ns"]["annotation"]
    assert set(out["candidates"]["motor_ids"]) <= set(solid.list_motor_ids())
    # orbit tier on an altitude goal is a ValueError, reported not raised
    bad = execute_tool(
        "derive_requirements",
        {"requirement": REQ_AMATEUR, "tier": "commercial", "launch_latitude_deg": None},
        "toolu_d3",
    )
    assert "error" in bad and bad["source_id"] == "toolu_d3"


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


@pytest.mark.parametrize(
    ("design", "req", "model"),
    [(AMATEUR_DESIGN, REQ_AMATEUR, solid), (BOTTLE_DESIGN, None, water)],
)
def test_simulate_design_suborbital_uses_real_physics(design, req, model):
    a = _sim(design, req, tool_id="toolu_a")
    b = _sim(design, req, tool_id="toolu_b")
    assert "error" not in a
    sim = SimResult.model_validate(a)
    assert sim.tier == design["tier"]
    assert not any("DUMMY" in w for w in sim.warnings)
    assert a["source_id"] == "toolu_a"
    a.pop("source_id")
    b.pop("source_id")
    assert a == b
    # the nominal models are deterministic and ignore the seed
    c = _sim(design, req, seed=8, tool_id="toolu_c")
    c.pop("source_id")
    assert c == a
    assert len(sim.trace) > 2
    assert sim.cost_jpy > 0
    # the metrics are the physics module's, judged against the requirement's altitude target
    parsed = DesignAdapter.validate_python(design)
    target = req["target_altitude_m"] if req else None
    ref = model.simulate(parsed, Env.model_validate(ENV), target_apogee_m=target)
    assert sim.metrics == ref.metrics
    assert set(ref.failure_reasons) <= set(sim.failure_reasons)


def test_amateur_altitude_target_comes_from_requirement():
    out = _sim(AMATEUR_DESIGN, REQ_AMATEUR)  # a G80 cannot reach 2 km with 1.5 kg
    assert out["success"] is False
    assert any("apogee" in r and "2000 m" in r for r in out["failure_reasons"])
    out2 = _sim(AMATEUR_DESIGN, None)
    assert not any("2000 m" in r for r in out2["failure_reasons"])


def test_judge_payload_and_recovery_rules():
    light = {**REQ_AMATEUR, "payload_mass_kg": 2.0}  # design carries only 1 kg
    out = _sim(AMATEUR_DESIGN, light)
    assert any("payload" in r for r in out["failure_reasons"])
    no_chute = {**BOTTLE_DESIGN, "has_parachute": False, "parachute_diameter_m": None}
    req = {"goal_kind": "altitude", "target_altitude_m": 30, "recovery_required": True}
    out = _sim(no_chute, req)
    assert any("recovery" in r and "parachute" in r for r in out["failure_reasons"])
    out = _sim(no_chute, {**req, "recovery_required": False})
    assert not any("recovery" in r for r in out["failure_reasons"])


def test_unknown_motor_id_is_an_error_not_a_crash():
    out = _sim({**AMATEUR_DESIGN, "motor_id": "no_such_motor"}, REQ_AMATEUR, tool_id="toolu_m")
    assert "error" in out
    assert "no_such_motor" in out["error"] and "dummy_G80" in out["error"]
    assert out["source_id"] == "toolu_m"


def test_simulate_design_multistage_uses_real_physics():
    a = _sim(COMMERCIAL_DESIGN, REQ_ORBIT, tool_id="toolu_a")
    assert "error" not in a
    sim = SimResult.model_validate(a)
    assert sim.tier == "commercial"
    assert not any("DUMMY" in w for w in sim.warnings)
    # the metrics are the multistage model's, judged against the requirement's orbit
    design = DesignAdapter.validate_python(COMMERCIAL_DESIGN)
    # orbit goals are flown with Earth rotation on (eastward launch assumed, see _simulate_dispatch)
    ref = ms.simulate(
        design, Env.model_validate({**ENV, "earth_rotation": True}), target_perigee_m=400_000
    )
    assert sim.metrics == ref.metrics
    assert any("earth rotation enabled" in w for w in sim.warnings)
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
            {**COMMERCIAL_DESIGN["stages"][1], "propellant_mass_kg": 1500},
        ],
        "pitch_start_s": 12,
        "initial_pitch_deg": 4,
    }
    out = _sim(under_fuelled, REQ_ORBIT)
    assert "error" not in out
    assert out["success"] is False
    assert any("perigee" in r and "400 km" in r for r in out["failure_reasons"])
    # without a requirement there is no insertion target and only the multistage default
    # minimum perigee (150 km) applies: the 400 km rule really came from the requirement
    out2 = _sim(under_fuelled, None)
    assert not any("400 km" in r for r in out2["failure_reasons"])


def test_budget_rule_is_shared_by_all_tiers():
    tight_orbit = {**REQ_ORBIT, "budget_jpy": 1000.0}
    out = _sim(COMMERCIAL_DESIGN, tight_orbit)
    assert out["success"] is False
    assert any("budget" in r for r in out["failure_reasons"])
    tight_amateur = {**REQ_AMATEUR, "budget_jpy": 1.0}
    out = _sim(AMATEUR_DESIGN, tight_amateur)
    assert out["success"] is False
    assert any("budget" in r for r in out["failure_reasons"])


def test_pass_criteria_hold_only_requirement_level_rules():
    assert set(PASS_CRITERIA) == {"payload_shortfall_tolerance_kg"}
    # flight rules live in the physics modules, one PASS_THRESHOLDS dict each
    assert "perigee_tolerance_frac" in ms.PASS_THRESHOLDS
    assert {"min_rail_exit_speed_mps", "min_stability_margin_cal"} <= set(solid.PASS_THRESHOLDS)
    assert {"max_gauge_pressure_pa", "apogee_tolerance_frac"} <= set(water.PASS_THRESHOLDS)


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


def test_orbit_goal_enables_earth_rotation_with_a_warning():
    from rocketwright.agent.tools import _simulate_dispatch
    from rocketwright.schema import Requirement

    design = DesignAdapter.validate_python(COMMERCIAL_DESIGN)
    req = Requirement.model_validate(REQ_ORBIT)
    still = Env.model_validate(ENV)
    assert still.earth_rotation is False
    out = _simulate_dispatch(design, still, 1, req)
    assert any("earth rotation enabled for orbit goal" in w for w in out.warnings)
    rotating = ms.simulate(
        design, still.model_copy(update={"earth_rotation": True}), target_perigee_m=400_000
    )
    assert out.metrics == rotating.metrics
    # an explicit earth_rotation=True gets no warning; no requirement -> left alone
    out2 = _simulate_dispatch(design, still.model_copy(update={"earth_rotation": True}), 1, req)
    assert not any("earth rotation enabled" in w for w in out2.warnings)
    out3 = _simulate_dispatch(design, still, 1, None)
    assert not any("earth rotation enabled" in w for w in out3.warnings)
    assert out3.metrics == ms.simulate(design, still).metrics


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


def _disp(design, req, n=50, seed=3, tool_id="toolu_d"):
    return execute_tool(
        "run_dispersion",
        {"design": design, "env": ENV, "n": n, "seed": seed, "requirement": req},
        tool_id,
    )


@pytest.mark.parametrize("design", [AMATEUR_DESIGN, COMMERCIAL_DESIGN, BOTTLE_DESIGN])
def test_run_dispersion_is_real_monte_carlo(design):
    out = _disp(design, None)
    assert "error" not in out, out
    assert out["source_id"] == "toolu_d"
    disp = DispersionResult.model_validate({k: v for k, v in out.items() if k != "nominal"})
    assert disp.n == 50 and disp.seed == 3
    assert 0 <= disp.success_rate <= 1
    assert not any("DUMMY" in w for w in disp.warnings)
    # the nominal (unperturbed) run is the simulate_design result, echoed under `nominal`
    real = _sim(design, None)
    assert out["nominal"]["metrics"] == real["metrics"]
    assert out["nominal"]["success"] == real["success"]
    assert out["nominal"]["failure_reasons"] == real["failure_reasons"]
    # quantiles bracket the nominal of the main metric (the spread is real but modest)
    key = "perigee_m" if design["tier"] in ("commercial", "heavy") else "apogee_m"
    q = disp.quantiles[key]
    assert q.p05 < q.p95
    if design["tier"] in ("commercial", "heavy"):
        assert disp.orbit_insertion is not None and disp.landing is None
        assert len(disp.orbit_insertion.samples) == 50
    else:
        assert disp.landing is not None and disp.orbit_insertion is None
        assert len(disp.landing.points) == 50
        assert disp.landing.ellipse_95.semi_major_m >= disp.landing.ellipse_95.semi_minor_m
    # deterministic: same input + seed -> identical result
    again = _disp(design, None, tool_id="toolu_d2")
    again.pop("source_id")
    out.pop("source_id")
    assert again == out


def test_run_dispersion_samples_are_judged_against_the_requirement():
    # a G80 cannot reach 2 km with 1.5 kg: every sample fails the requirement's apogee rule
    out = _disp(AMATEUR_DESIGN, REQ_AMATEUR, n=20)
    assert "error" not in out
    assert out["success_rate"] == 0.0
    assert any("apogee" in k for k in out["failure_counts"])
    assert sum(out["failure_counts"].values()) >= 20
    # the bucket keys carry no sample-specific numbers
    for k in out["failure_counts"]:
        assert "2000" not in k
    # the budget rule of _finalize applies to every sample too
    tight = {**REQ_ORBIT, "budget_jpy": 1000.0}
    out = _disp(COMMERCIAL_DESIGN, tight, n=4)
    assert out["success_rate"] == 0.0
    assert any("budget" in k for k in out["failure_counts"])


def test_run_dispersion_n_default_and_cap():
    out = _disp(BOTTLE_DESIGN, None, n=None)
    assert "error" not in out and out["n"] == DISPERSION_DEFAULT_N
    out = _disp(BOTTLE_DESIGN, None, n=DISPERSION_MAX_N + 1)
    assert "error" in out and str(DISPERSION_MAX_N) in out["error"]
    out = _disp(BOTTLE_DESIGN, None, n=0)
    assert "error" in out
    defs = {d["name"]: d for d in get_tool_definitions()}
    assert "success_rate" in defs["run_dispersion"]["description"]


def test_estimate_cost_tool():
    out = execute_tool("estimate_cost", {"design": COMMERCIAL_DESIGN}, "toolu_e")
    assert out["cost_jpy"] > 0
    assert out["provisional"] is True


def test_render_drawing_stores_svg_artifact():
    from rocketwright.agent.store import DEFAULT_STORE

    out = execute_tool("render_drawing", {"design": AMATEUR_DESIGN}, "toolu_f")
    assert "error" not in out
    assert out["source_id"] == "toolu_f"
    assert out["tier"] == "amateur"
    assert out["svg_chars"] > 0
    assert "svg" not in out  # the SVG text is not sent back to the model
    assert out["download"]["svg"] == f"/artifacts/{out['id']}.svg"
    art = DEFAULT_STORE.get(f"{out['id']}.svg")
    assert art is not None and art.content.startswith("<svg")


def test_export_report_from_result_json():
    from rocketwright.agent.store import DEFAULT_STORE

    # A simulate_design result as the model sees it: SimResult fields plus loop extras
    # (`trace_point_count` replaces the trace); the extras must be ignored.
    sim = {
        "tier": "amateur",
        "success": True,
        "failure_reasons": [],
        "metrics": {"apogee_m": 812.0, "max_speed_mps": 120.5, "descent_speed_mps": 5.1},
        "cost_jpy": 40_000.0,
        "warnings": [],
        "source_id": "toolu_sim",
        "trace_point_count": 60,
    }
    out = execute_tool(
        "export_report",
        {
            "design": AMATEUR_DESIGN,
            "result_json": json.dumps(sim),
            "requirement": None,
            "dispersion_json": None,
        },
        "toolu_g",
    )
    assert "error" not in out, out
    assert out["source_id"] == "toolu_g"
    assert out["markdown_chars"] > 0 and out["bom_rows"] >= 3
    d = out["download"]
    assert d["report"] == f"/artifacts/{out['id']}.md"
    assert d["bom"] == f"/artifacts/{out['id']}.csv"
    assert d["json"] == f"/artifacts/{out['id']}.json"
    md = DEFAULT_STORE.get(f"{out['id']}.md").content
    assert "toolu_sim" in md  # provenance id of every metric
    assert "Checklist" in md


def test_export_report_rejects_bad_result_json():
    out = execute_tool(
        "export_report",
        {
            "design": AMATEUR_DESIGN,
            "result_json": "not json",
            "requirement": None,
            "dispersion_json": None,
        },
        "toolu_h",
    )
    assert "error" in out and "result_json" in out["error"]
