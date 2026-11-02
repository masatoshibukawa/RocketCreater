"""Tests for parachute descent and wind drift (rocketwright.physics.recovery)."""

from __future__ import annotations

import math

import pytest

from rocketwright.physics import atmosphere as atm
from rocketwright.physics import recovery
from rocketwright.schema import Env

G0 = 9.80665


def test_terminal_speed_formula_at_mid_altitude_density() -> None:
    env = Env(launch_altitude_m=100.0)
    mass, diameter, cd = 2.0, 1.2, 1.5
    res = recovery.descend(mass, diameter, env, start_altitude_m=1000.0, cd=cd)
    rho = atm.density_kgpm3(100.0 + 500.0)  # SIMPLIFICATION: density at mid-descent altitude
    area = math.pi * (diameter / 2.0) ** 2
    expected = math.sqrt(2.0 * mass * G0 / (rho * cd * area))
    assert res.descent_speed_mps == pytest.approx(expected, rel=1e-9)
    assert res.descent_time_s == pytest.approx(1000.0 / expected, rel=1e-9)


def test_wind_from_west_drifts_east() -> None:
    env = Env(wind_speed_mps=4.0, wind_direction_deg=270.0)  # wind blows FROM the west
    res = recovery.descend(1.0, 1.0, env, start_altitude_m=500.0)
    assert res.landing_east_m > 0.0
    assert res.landing_north_m == pytest.approx(0.0, abs=1e-6)
    assert res.landing_east_m == pytest.approx(4.0 * res.descent_time_s)


def test_wind_from_north_drifts_south_and_start_offset_is_kept() -> None:
    env = Env(wind_speed_mps=2.0, wind_direction_deg=0.0)
    res = recovery.descend(
        1.0, 1.0, env, start_altitude_m=200.0, start_east_m=10.0, start_north_m=5.0
    )
    assert res.landing_east_m == pytest.approx(10.0, abs=1e-6)
    assert res.landing_north_m < 5.0
    assert res.landing_north_m == pytest.approx(5.0 - 2.0 * res.descent_time_s)


def test_bigger_parachute_descends_slower() -> None:
    env = Env()
    small = recovery.descend(1.5, 0.6, env, start_altitude_m=300.0)
    large = recovery.descend(1.5, 1.2, env, start_altitude_m=300.0)
    assert large.descent_speed_mps < small.descent_speed_mps
    assert large.descent_time_s > small.descent_time_s


def test_rejects_non_positive_inputs() -> None:
    with pytest.raises(ValueError):
        recovery.descend(0.0, 1.0, Env(), start_altitude_m=100.0)
    with pytest.raises(ValueError):
        recovery.descend(1.0, 0.0, Env(), start_altitude_m=100.0)
    with pytest.raises(ValueError):
        recovery.descend(1.0, 1.0, Env(), start_altitude_m=-1.0)
