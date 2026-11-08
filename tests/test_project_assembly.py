import pytest

from rocketwright.agent.project_assembly import Observation, assembly_assessment
from tests.test_project_equipment import spec


def test_missing_operator_dimensions_and_force_are_not_passing():
    result = assembly_assessment(spec())
    assert all(row["status"] == "not_evaluated" for row in result["checks"])
    assert result["physical_qualification"] is False
    assert all(row["retreat_mm"] == list(reversed(row["approach_mm"])) for row in result["paths"])


def test_slot_and_access_reject_oversized_tool_without_inventing_hand_measurements():
    s = spec()
    s.equipment.strap_width_mm = 5
    s.equipment.tool_radius_mm = 100
    rows = {r["id"]: r for r in assembly_assessment(s)["checks"]}
    assert rows["strap_width"]["status"] == "interference"
    assert rows["tool_access"]["status"] == "interference"
    assert rows["hand_access"]["status"] == "not_evaluated"
    s.geometry = s.geometry.model_copy(update={"fin_slot_width_mm": 6})
    assert assembly_assessment(s)["checks"][0]["status"] == "screen_pass"


def test_observation_requires_attribution_and_finite_measured_values():
    with pytest.raises(ValueError):
        Observation(step="nose_fit", status="observed")
    with pytest.raises(ValueError):
        Observation(step="measure", measured_values={"mass_g": float("nan")})
    assert Observation(step="nose_fit").status == "unconfirmed"
