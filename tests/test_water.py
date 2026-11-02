"""Tests for the bottle-tier water-rocket model (CLAUDE.md section 7, "water")."""

from __future__ import annotations

import math
import time

import pytest

from rocketwright.physics import water
from rocketwright.schema import MAX_TRACE_POINTS, BottleDesign, Env, Tier


def design(**overrides: object) -> BottleDesign:
    base: dict[str, object] = {
        "bottle_volume_m3": 0.0015,
        "water_fill_frac": 0.4,
        "initial_gauge_pressure_pa": 500_000.0,
        "nozzle_diameter_m": 0.022,
        "dry_mass_kg": 0.10,
        "payload_mass_kg": 0.0,
        "has_fins": True,
        "has_parachute": False,
    }
    base.update(overrides)
    return BottleDesign(**base)  # type: ignore[arg-type]


def calm_env() -> Env:
    return Env(launch_altitude_m=10.0, rail_length_m=1.0)


def test_published_ballpark_1p5l_40pct_500kpa() -> None:
    """1.5 L bottle, 40 % water, 500 kPa gauge, ~100 g airframe. Water-rocket calculators and
    club reports put this configuration at a few tens of metres (PROVISIONAL ballpark: the
    expected range below is not yet tied to a cited measurement; see README "Values to
    confirm")."""
    res = water.simulate(design(), calm_env())
    assert 20.0 < res.metrics["apogee_m"] < 80.0, res.metrics


def test_more_pressure_flies_higher_and_faster() -> None:
    low = water.simulate(design(initial_gauge_pressure_pa=300_000.0), calm_env())
    high = water.simulate(design(initial_gauge_pressure_pa=600_000.0), calm_env())
    assert high.metrics["apogee_m"] > low.metrics["apogee_m"]
    assert high.metrics["max_speed_mps"] > low.metrics["max_speed_mps"]
    assert high.metrics["peak_thrust_n"] > low.metrics["peak_thrust_n"]


def test_determinism_and_seed_is_ignored() -> None:
    env = Env(launch_altitude_m=10.0, wind_speed_mps=2.0, wind_direction_deg=90.0)
    a = water.simulate(design(), env, seed=1)
    b = water.simulate(design(), env, seed=99)
    assert a.model_dump() == b.model_dump()


def test_peak_thrust_is_bernoulli_two_delta_p_times_nozzle_area() -> None:
    d = design()
    res = water.simulate(d, calm_env())
    area = math.pi * (d.nozzle_diameter_m / 2.0) ** 2
    assert res.metrics["peak_thrust_n"] == pytest.approx(
        2.0 * d.initial_gauge_pressure_pa * area, rel=1e-6
    )
    assert 0.0 < res.metrics["thrust_phase_duration_s"] < 0.5
    assert res.metrics["water_exhausted_speed_mps"] > 0.0
    assert res.metrics["max_accel_mps2"] > 50.0


def test_no_fins_warns_and_flies_lower() -> None:
    finned = water.simulate(design(has_fins=True), calm_env())
    finless = water.simulate(design(has_fins=False), calm_env())
    assert any("fins" in w for w in finless.warnings)
    assert not any("fins" in w for w in finned.warnings)
    assert finless.metrics["apogee_m"] < finned.metrics["apogee_m"]


def test_parachute_slows_descent_and_drifts_downwind() -> None:
    env = Env(launch_altitude_m=10.0, wind_speed_mps=3.0, wind_direction_deg=270.0)
    ballistic = water.simulate(design(payload_mass_kg=0.06), env)
    chuted = water.simulate(
        design(payload_mass_kg=0.06, has_parachute=True, parachute_diameter_m=0.5), env
    )
    assert chuted.metrics["descent_speed_mps"] < ballistic.metrics["descent_speed_mps"]
    assert chuted.metrics["flight_time_s"] > ballistic.metrics["flight_time_s"]
    assert chuted.metrics["landing_east_m"] > 0.0  # wind from the west
    assert chuted.metrics["landing_distance_m"] == pytest.approx(
        math.hypot(chuted.metrics["landing_east_m"], chuted.metrics["landing_north_m"])
    )
    # the egg (payload) needs <= 6 m/s: ballistic fails, the parachute passes that rule
    assert any("descent speed" in r for r in ballistic.failure_reasons)
    assert not any("descent speed" in r for r in chuted.failure_reasons)


def test_pass_thresholds_apogee_and_pressure() -> None:
    env = calm_env()
    nominal = water.simulate(design(), env)
    on_target = water.simulate(design(), env, target_apogee_m=nominal.metrics["apogee_m"])
    assert not any("apogee" in r for r in on_target.failure_reasons)
    off_target = water.simulate(design(), env, target_apogee_m=nominal.metrics["apogee_m"] * 2.0)
    assert any("apogee" in r for r in off_target.failure_reasons)
    too_hot = water.simulate(design(initial_gauge_pressure_pa=1_500_000.0), env)
    assert any("pressure" in r for r in too_hot.failure_reasons)
    assert too_hot.success is False


def test_trace_and_result_shape() -> None:
    res = water.simulate(design(), calm_env())
    assert res.tier is Tier.BOTTLE
    assert 0 < len(res.trace) <= MAX_TRACE_POINTS
    assert res.trace[0].t_s == 0.0 and res.trace[0].altitude_m == pytest.approx(0.0)
    assert max(p.altitude_m for p in res.trace) == pytest.approx(res.metrics["apogee_m"], rel=0.02)
    assert res.trace[-1].altitude_m == pytest.approx(0.0, abs=0.5)
    assert res.trace[-1].t_s == pytest.approx(res.metrics["flight_time_s"])
    assert res.cost_jpy == 0.0
    assert not any("DUMMY" in w for w in res.warnings)


def test_one_flight_runs_under_50_ms() -> None:
    d = design()
    env = Env(launch_altitude_m=10.0, wind_speed_mps=2.0, wind_direction_deg=90.0)
    water.simulate(d, env)
    best = math.inf
    for _ in range(5):
        t0 = time.perf_counter()
        water.simulate(d, env)
        best = min(best, time.perf_counter() - t0)
    assert best < 0.050, f"one flight took {best * 1e3:.1f} ms"


def test_rejects_other_tiers() -> None:
    from rocketwright.schema import AmateurDesign, FinSet

    amateur = AmateurDesign(
        body_diameter_m=0.054,
        body_length_m=0.9,
        nose_length_m=0.15,
        fins=FinSet(count=4, root_chord_m=0.1, tip_chord_m=0.05, span_m=0.06),
        motor_id="dummy_G80",
        dry_mass_kg=0.5,
        parachute_diameter_m=0.6,
    )
    with pytest.raises(ValueError, match="bottle"):
        water.simulate(amateur, calm_env())
