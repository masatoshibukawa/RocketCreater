"""Tests for the amateur-tier solid-motor flight model (CLAUDE.md section 7, "solid")."""

from __future__ import annotations

import math
import re
import time
from pathlib import Path

import pytest
import yaml

from rocketwright.physics import solid
from rocketwright.schema import MAX_TRACE_POINTS, AmateurDesign, Env, FinSet, Tier

G0 = 9.80665
REFERENCE_DIR = Path(__file__).parent / "reference"
OPENROCKET_FILES = sorted(REFERENCE_DIR.glob("openrocket_*.yaml"))


def design(**overrides: object) -> AmateurDesign:
    base: dict[str, object] = {
        "body_diameter_m": 0.054,
        "body_length_m": 0.90,
        "nose_shape": "ogive",
        "nose_length_m": 0.15,
        "fins": FinSet(count=4, root_chord_m=0.12, tip_chord_m=0.06, span_m=0.07, sweep_m=0.03),
        "motor_id": "dummy_G80",
        "dry_mass_kg": 0.5,
        "payload_mass_kg": 0.2,
        "parachute_diameter_m": 0.9,
        "deploy_delay_s": 1.0,
    }
    base.update(overrides)
    return AmateurDesign(**base)  # type: ignore[arg-type]


def calm_env() -> Env:
    return Env(launch_latitude_deg=36.0, launch_altitude_m=300.0, rail_length_m=1.5)


# --------------------------------------------------------------------------- motor catalog


def _class_bounds_ns(letter: str) -> tuple[float, float]:
    """NAR/Tripoli total-impulse class: A = 1.26-2.5 Ns, each letter doubles."""
    k = ord(letter.upper()) - ord("A")
    upper = 2.5 * 2.0**k
    return upper / 2.0, upper


@pytest.mark.parametrize("motor_id", solid.list_motor_ids())
def test_bundled_motor_total_impulse_matches_class_letter(motor_id: str) -> None:
    motor = solid.load_motor(motor_id)
    m = re.search(r"([A-O])(\d+)", motor.name)
    assert m, f"motor name {motor.name!r} has no class designation"
    lo, hi = _class_bounds_ns(m.group(1))
    assert lo < motor.total_impulse_ns <= hi, (motor_id, motor.total_impulse_ns)
    # the number after the letter is the average thrust in N (within 30 %)
    assert motor.average_thrust_n == pytest.approx(float(m.group(2)), rel=0.30)
    assert motor.thrust_curve[0][0] == 0.0
    assert motor.thrust_curve[-1][1] == 0.0
    assert all(
        t1 > t0
        for (t0, _), (t1, _) in zip(motor.thrust_curve, motor.thrust_curve[1:], strict=False)
    )
    assert 0.0 < motor.propellant_mass_kg < motor.total_mass_kg
    assert motor.diameter_m > 0.0 and motor.length_m > 0.0


@pytest.mark.parametrize("motor_id", solid.list_motor_ids())
def test_bundled_motor_metadata_is_sourced_or_provisional(motor_id: str) -> None:
    motor = solid.load_motor(motor_id)
    assert motor.provisional or (motor.source and motor.license), motor_id
    if motor_id.startswith("dummy_"):
        assert motor.provisional is True


def test_motor_thrust_interpolates_and_is_zero_outside_burn() -> None:
    motor = solid.load_motor("dummy_G80")
    t_mid = motor.burn_time_s / 2.0
    assert motor.thrust_n(t_mid) > 0.0
    assert motor.thrust_n(-1.0) == 0.0
    assert motor.thrust_n(motor.burn_time_s + 1.0) == 0.0
    assert motor.peak_thrust_n >= motor.average_thrust_n


def test_unknown_motor_lists_available_ids() -> None:
    with pytest.raises(KeyError, match="dummy_G80"):
        solid.load_motor("no_such_motor")


# --------------------------------------------------------------------------- verification


def test_vacuum_no_gravity_matches_rocket_equation() -> None:
    """With dm/dt = -m_p * F(t) / I_total the model is exactly Tsiolkovsky with
    v_e = I_total / m_p, whatever the curve shape; the integration error must stay below 0.2 %."""
    d = design()
    motor = solid.load_motor(d.motor_id)
    res = solid.simulate_with_options(d, calm_env(), gravity=False, drag=False)
    m0 = d.dry_mass_kg + d.payload_mass_kg + motor.total_mass_kg
    mf = m0 - motor.propellant_mass_kg
    v_e = motor.total_impulse_ns / motor.propellant_mass_kg
    expected = v_e * math.log(m0 / mf)
    assert res.metrics["burnout_speed_mps"] == pytest.approx(expected, rel=2e-3)
    assert res.metrics["max_speed_mps"] == pytest.approx(expected, rel=2e-3)
    assert res.metrics["liftoff_mass_kg"] == pytest.approx(m0)
    assert res.metrics["total_impulse_ns"] == pytest.approx(motor.total_impulse_ns)
    assert any("verification" in w for w in res.warnings)


def test_apogee_without_drag_matches_v2_over_2g_from_burnout() -> None:
    d = design()
    res = solid.simulate_with_options(d, calm_env(), gravity=True, drag=False)
    z_b = res.metrics["burnout_altitude_m"]
    v_b = res.metrics["burnout_speed_mps"]  # vertical launch, no wind -> speed is vertical
    assert res.metrics["apogee_m"] == pytest.approx(z_b + v_b**2 / (2.0 * G0), rel=5e-3)


def test_determinism_and_seed_is_ignored() -> None:
    d = design()
    env = Env(launch_altitude_m=300.0, wind_speed_mps=3.0, wind_direction_deg=270.0)
    a = solid.simulate(d, env, seed=1)
    b = solid.simulate(d, env, seed=2)
    assert a.model_dump() == b.model_dump()


def test_rail_exit_speed_increases_with_thrust() -> None:
    weak = solid.simulate(design(motor_id="dummy_F32"), calm_env())
    strong = solid.simulate(design(motor_id="dummy_G80"), calm_env())
    assert strong.metrics["rail_exit_speed_mps"] > weak.metrics["rail_exit_speed_mps"]
    assert strong.metrics["apogee_m"] > weak.metrics["apogee_m"]


def test_one_flight_runs_under_50_ms() -> None:
    d = design()
    env = Env(launch_altitude_m=300.0, wind_speed_mps=3.0, wind_direction_deg=270.0)
    solid.simulate(d, env)  # warm up caches
    best = math.inf
    for _ in range(5):
        t0 = time.perf_counter()
        solid.simulate(d, env)
        best = min(best, time.perf_counter() - t0)
    assert best < 0.050, f"one flight took {best * 1e3:.1f} ms"


# --------------------------------------------------------------------------- results


def test_metrics_trace_and_landing_are_consistent() -> None:
    d = design()
    env = Env(launch_altitude_m=300.0, wind_speed_mps=3.0, wind_direction_deg=270.0)
    res = solid.simulate(d, env)
    assert res.tier is Tier.AMATEUR
    for key in (
        "apogee_m",
        "max_speed_mps",
        "rail_exit_speed_mps",
        "burnout_altitude_m",
        "stability_margin_cal",
        "descent_speed_mps",
        "landing_east_m",
        "landing_north_m",
        "landing_distance_m",
        "flight_time_s",
        "max_accel_mps2",
        "total_impulse_ns",
        "liftoff_mass_kg",
    ):
        assert key in res.metrics, key
    m = res.metrics
    assert m["landing_distance_m"] == pytest.approx(
        math.hypot(m["landing_east_m"], m["landing_north_m"])
    )
    # wind from the west: the long parachute descent drifts the rocket east of the pad
    assert m["landing_east_m"] > 0.0
    assert m["max_accel_mps2"] > G0
    assert 0 < len(res.trace) <= MAX_TRACE_POINTS
    assert res.trace[0].altitude_m == pytest.approx(0.0)
    assert res.trace[0].t_s == 0.0
    assert max(p.altitude_m for p in res.trace) == pytest.approx(m["apogee_m"], rel=0.02)
    assert res.trace[-1].altitude_m == pytest.approx(0.0, abs=1.0)
    assert res.trace[-1].t_s == pytest.approx(m["flight_time_s"])
    assert all(p.mass_kg is not None for p in res.trace)
    assert res.trace[-1].east_m == pytest.approx(m["landing_east_m"])
    assert res.cost_jpy == 0.0  # cost.py owns the estimate


def test_failure_reasons_come_from_thresholds() -> None:
    env = calm_env()
    tiny_fins = design(fins=FinSet(count=3, root_chord_m=0.03, tip_chord_m=0.01, span_m=0.01))
    res = solid.simulate(tiny_fins, env)
    assert res.success is False
    assert any("stability margin" in r for r in res.failure_reasons)

    small_chute = design(parachute_diameter_m=0.2)
    res = solid.simulate(small_chute, env)
    assert any("descent speed" in r for r in res.failure_reasons)

    ok = solid.simulate(design(), env)
    off_target = solid.simulate(design(), env, target_apogee_m=ok.metrics["apogee_m"] * 3.0)
    assert any("apogee" in r for r in off_target.failure_reasons)
    on_target = solid.simulate(design(), env, target_apogee_m=ok.metrics["apogee_m"])
    assert not any("apogee" in r for r in on_target.failure_reasons)


def test_underpowered_motor_fails_rail_exit_speed() -> None:
    heavy = design(motor_id="dummy_F32", dry_mass_kg=1.5, payload_mass_kg=1.0)
    res = solid.simulate(heavy, calm_env())
    assert res.success is False
    assert any("rail exit speed" in r for r in res.failure_reasons)


def test_motor_that_cannot_lift_the_rocket_fails_cleanly() -> None:
    brick = design(motor_id="dummy_F32", dry_mass_kg=5.0, payload_mass_kg=5.0)
    res = solid.simulate(brick, calm_env())
    assert res.success is False
    assert any("lift" in r for r in res.failure_reasons)


def test_overstable_design_only_warns() -> None:
    d = design(fins=FinSet(count=4, root_chord_m=0.20, tip_chord_m=0.10, span_m=0.18))
    res = solid.simulate(d, calm_env())
    assert res.metrics["stability_margin_cal"] > solid.PASS_THRESHOLDS["max_stability_margin_cal"]
    assert any("overstable" in w for w in res.warnings)
    assert not any("stability margin" in r for r in res.failure_reasons)


def test_rejects_other_tiers() -> None:
    from rocketwright.schema import BottleDesign

    bottle = BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=5e5,
        nozzle_diameter_m=0.022,
        dry_mass_kg=0.1,
    )
    with pytest.raises(ValueError, match="amateur"):
        solid.simulate(bottle, calm_env())


# --------------------------------------------------------------------------- OpenRocket


@pytest.mark.parametrize(
    "path",
    OPENROCKET_FILES or [None],
    ids=[p.stem for p in OPENROCKET_FILES] or ["no-openrocket-reference"],
)
def test_openrocket_reference_flight(path: Path | None) -> None:
    """Compare against an OpenRocket run of the same vehicle (tests/reference/README.md)."""
    if path is None:
        pytest.skip("no tests/reference/openrocket_*.yaml; a human must export one from OpenRocket")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data.get("source"), f"{path.name} needs a source URL / OpenRocket version note"
    d = AmateurDesign.model_validate(data["design"])
    env = Env.model_validate(data.get("env") or {})
    res = solid.simulate(d, env)
    tol = float(data.get("tolerance_frac", 0.15))
    for key, expected in data["expected"].items():
        assert res.metrics[key] == pytest.approx(float(expected), rel=tol), key
