"""The three bottle shelves must resolve to actual catalog parts, inputs and tool results."""

import pytest

from rocketwright.agent.fake_client import DEMO_DESIGNS, DEMO_REQUIREMENTS
from rocketwright.agent.tools import execute_tool, get_tool_definitions
from rocketwright.schema import BottleDesign

DESIGN = DEMO_DESIGNS["bottle"][1]
REQ = DEMO_REQUIREMENTS["bottle"]


def catalog(tier="bottle", query=None):
    return execute_tool("search_catalog", {"tier": tier, "kind": "parts", "query": query}, "cat")


def test_full_pool_has_a_source_for_every_design_input_and_score():
    pool = catalog()
    groups = pool["variable_definitions"]
    fields = {k for group in groups.values() for k in group["design_inputs"]}
    assert fields == set(BottleDesign.model_fields) - {"tier"}
    for group in groups.values():
        if choice := group.get("catalog_choice"):
            parts = [p for p in pool["parts"] if p["kind"] == choice["filter"]["kind"]]
            assert parts
            for spec in group["design_inputs"].values():
                if spec.get("value_from", "").startswith("selected_part."):
                    assert all(spec["value_from"].split(".")[1] in p for p in parts)

    args = {"design": DESIGN, "requirement": REQ, "seed": 7, "env": {}, "tune_pitch": False}
    calls = {
        "simulate_design": args,
        "estimate_cost": {"design": DESIGN},
        "run_dispersion": {k: v for k, v in {**args, "n": 3}.items() if k != "tune_pitch"},
    }
    tools = {t["name"]: t["input_schema"] for t in get_tool_definitions()}
    outputs = {}
    assert set(calls) == set(pool["analysis_methods"])
    for name, method in pool["analysis_methods"].items():
        assert set(method["arguments"]) == set(tools[name]["properties"])
        assert set(method["sensitive_to"]) <= fields
        outputs[name] = execute_tool(name, calls[name], name)
        assert "error" not in outputs[name]
    for score in pool["evaluation_functions"].values():
        for method, path in score["sources"].items():
            value = outputs[method]
            for key in path.split("."):
                value = value[key]
            assert isinstance(value, (float, bool, int)), path


def test_filtered_catalog_keeps_only_relevant_methods_and_scores():
    nozzle = catalog(query="bottle_nozzle_9mm")
    assert set(nozzle["variable_definitions"]) == {"nozzle"}
    assert set(nozzle["analysis_methods"]) == {"simulate_design", "run_dispersion"}
    assert "minimize_cost" not in nozzle["evaluation_functions"]
    for other in [catalog(query="no-such-part"), catalog(tier="amateur")]:
        assert "analysis_methods" not in other and "evaluation_functions" not in other


def test_literature_candidates_are_discoverable_and_separate_from_executable_tools():
    pool = catalog()
    planned = pool["planned"]
    assert planned["analysis_methods"].keys().isdisjoint(t["name"] for t in get_tool_definitions())
    assert planned["evaluation_functions"].keys().isdisjoint(pool["evaluation_functions"])
    variables = {
        name
        for group in pool["variable_definitions"].values()
        for section in ("design_inputs", "environment_inputs", "reserved")
        for name in group.get(section, {})
    }
    for method in planned["analysis_methods"].values():
        assert set(method["variables"]) <= variables
        assert method["validation"] and method["context"]
        assert set(method["references"]) <= pool["references"].keys()
    for score in planned["evaluation_functions"].values():
        method = planned["analysis_methods"][score["method"]]
        assert set(score["uses"]) <= set(method["outputs"])
    for source in pool["references"].values():
        assert source["url"].startswith("https://") and source["locator"]

    nose = catalog(query="bottle_nose_cone_foam")
    assert "nose_profile" in nose["variable_definitions"]["nose_cone"]["reserved"]
    assert "aerodynamic_polars" in nose["planned"]["analysis_methods"]
    assert "transient_nozzle_flow" not in nose["planned"]["analysis_methods"]
    assert "R02" not in nose["references"]


def test_reference_pressure_convention_and_pairs():
    replay = catalog()["planned"]["analysis_methods"]["vertical_flight_replay"]["benchmark"]
    runs = {r["run"]: r for r in replay["observations"]}
    assert runs[3]["water_fill_frac"] == runs[4]["water_fill_frac"]
    assert runs[1]["absolute_pressure_pa"] == runs[2]["absolute_pressure_pa"]
    assert runs[3]["absolute_pressure_pa"] - replay["approx_ambient_pressure_pa"] == 200000
    assert runs[4]["apogee_m"] == 17.4


def test_requirement_residuals_and_final_verdict_are_independent_of_search_focus():
    req = {**REQ, "target_altitude_m": 100, "budget_jpy": 100, "bottle_volume_m3": 0.002}
    args = {"design": DESIGN, "requirement": req, "env": {}, "seed": 7}
    sim = execute_tool("simulate_design", args, "sim")
    m = sim["metrics"]
    assert m["apogee_band_excess_m"] == pytest.approx(90 - m["apogee_m"])
    assert m["budget_excess_jpy"] == sim["cost_jpy"] - 100
    assert m["descent_speed_excess_mps"] == 0
    assert sim["success"] is False
    assert any("bottle volume" in reason for reason in sim["failure_reasons"])
    assert execute_tool("run_dispersion", {**args, "n": 3}, "mc")["success_rate"] == 0
    free = execute_tool("simulate_design", {**args, "requirement": None}, "free")["metrics"]
    assert "apogee_band_excess_m" not in free and "budget_excess_jpy" not in free
