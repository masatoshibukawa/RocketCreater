import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/design_trace.py"
spec = importlib.util.spec_from_file_location("design_trace", SCRIPT)
design_trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design_trace)


def event(kind, **payload):
    return {"type": kind, "payload": payload}


def test_table_shows_what_changed_between_simulations_and_why_one_failed():
    first = {"bottle_volume_m3": 0.0005, "water_fill_frac": 0.3}
    second = {"bottle_volume_m3": 0.0015, "water_fill_frac": 0.3}
    table = design_trace.trace_table(
        [
            event("tool_call", id="a", name="simulate_design", input={"design": first}),
            event(
                "tool_result",
                id="a",
                name="simulate_design",
                result={"metrics": {"apogee_m": 12.0}, "failure_reasons": ["apogee low"]},
            ),
            event("tool_call", id="b", name="simulate_design", input={"design": second}),
            event(
                "tool_result",
                id="b",
                name="simulate_design",
                result={"metrics": {"apogee_m": 20.0}, "failure_reasons": []},
            ),
        ]
    )
    lines = table.splitlines()
    assert "apogee low" in lines[2]
    assert "bottle_volume_m3: 0.0005 → 0.0015" in lines[3]
    assert "water_fill_frac" not in lines[3]
    assert lines[3].endswith("| 合格 |")


def test_stage_rows_count_candidates_instead_of_claiming_a_pass():
    table = design_trace.trace_table(
        [
            event("tool_call", id="a", name="design_stage", input={}),
            event(
                "tool_result",
                id="a",
                name="design_stage",
                result={"stage": "nozzle", "enumerated": 6, "simulated": 4, "passed": 2},
            ),
        ]
    )
    row = table.splitlines()[2]
    assert "design_stage: nozzle" in row
    assert "enumerated 6, simulated 4, passed 2" in row
    assert "合格" not in row
