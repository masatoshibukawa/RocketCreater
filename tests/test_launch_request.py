import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocketwright.launch_request import (
    DEFAULT_ENV,
    LaunchRequest,
    load_launch_request,
    size_launcher,
    to_requirement,
)
from rocketwright.schema import GoalKind

EXAMPLE = Path(__file__).resolve().parents[1] / "scenarios/opt_cube/launch_request.json"


def request(**changes):
    return LaunchRequest.model_validate({**json.loads(EXAMPLE.read_text()), **changes})


def test_example_becomes_an_orbit_requirement_with_the_satellite_mass():
    req = to_requirement(load_launch_request(EXAMPLE))
    assert req.goal_kind is GoalKind.ORBIT
    assert req.payload_mass_kg == pytest.approx(3.985)
    assert req.target_altitude_m == pytest.approx(400_000)
    assert req.target_apogee_m == pytest.approx(400_000)
    assert "OPT-CUBE" in req.text


@pytest.mark.parametrize(
    "changes",
    [{"schema_version": 2}, {"payload_mass_kg": 0}, {"target_apogee_m": 1.0}, {"extra": 1}],
)
def test_rejects_requests_the_rocket_side_cannot_trust(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def fake_simulate(passes_from):
    calls = []

    def simulate(design, env, requirement):
        count = design["stages"][0]["engine_count"]
        calls.append(count)
        return {
            "success": count >= passes_from,
            "failure_reasons": [] if count >= passes_from else ["too small"],
            "metrics": {"payload_margin_kg": 10.0 * count},
            "cost_jpy": 1.0,
            "tuned_design": design,
        }

    return simulate, calls


def fake_dispersion(design, env, requirement, n, seed):
    return {"success_rate": 0.9, "n": n, "seed": seed}


def test_sizing_stops_at_the_smallest_vehicle_that_passes():
    simulate, calls = fake_simulate(passes_from=3)
    result = size_launcher(request(), simulate=simulate, dispersion=fake_dispersion)
    assert calls == [1, 2, 3]
    assert result.engine_count == 3
    assert result.reference_id == "electron"
    assert result.success_rate == pytest.approx(0.9)
    assert result.design["payload_mass_kg"] == pytest.approx(3.985)


def test_sizing_scales_propellant_with_the_engine_count():
    simulate, _ = fake_simulate(passes_from=3)
    result = size_launcher(request(), simulate=simulate, dispersion=fake_dispersion)
    assert result.design["stages"][0]["propellant_mass_kg"] == pytest.approx(9250.0 * 3 / 9)
    assert result.design["stages"][1]["engine_count"] == 1


def test_sizing_reports_when_nothing_passes():
    simulate, calls = fake_simulate(passes_from=99)
    with pytest.raises(ValueError, match="no size"):
        size_launcher(request(), simulate=simulate, dispersion=fake_dispersion)
    assert calls == list(range(1, 10))


def test_sizing_falls_back_to_the_most_robust_size_with_a_warning():
    simulate, calls = fake_simulate(passes_from=1)

    def dispersion(design, env, requirement, n, seed):
        return {"success_rate": 0.8 if design["stages"][0]["engine_count"] == 7 else 0.3}

    result = size_launcher(request(), simulate=simulate, dispersion=dispersion)
    assert calls == list(range(1, 10))
    assert result.engine_count == 7
    assert any("no size reaches" in w for w in result.warnings)


def test_warnings_carry_the_limits_of_the_handoff():
    simulate, _ = fake_simulate(passes_from=1)
    result = size_launcher(request(), simulate=simulate, dispersion=fake_dispersion)
    text = " ".join(result.warnings)
    assert "provisional" in text
    assert "inclination" in text
    assert "envelope" in text


def test_inclination_below_the_launch_latitude_is_flagged():
    simulate, _ = fake_simulate(passes_from=1)
    env = DEFAULT_ENV.model_copy(update={"launch_latitude_deg": 60.0})
    result = size_launcher(request(), env=env, simulate=simulate, dispersion=fake_dispersion)
    assert any("below the launch latitude" in w for w in result.warnings)


def test_real_physics_sizes_a_small_launcher_for_opt_cube():
    result = size_launcher(load_launch_request(EXAMPLE), dispersion=fake_dispersion)
    assert result.engine_count == 1  # fake_dispersion always clears the bar
    assert result.metrics["payload_margin_kg"] > 0
    assert result.metrics["perigee_m"] >= 360_000
