"""Tests for rocketwright.derive: natural-language requirement -> quantitative targets by closed
formulas (no simulation, no LLM, no network). Hand-computed values are checked per tier."""

from __future__ import annotations

import json
import math

import pytest

from rocketwright.derive import (
    DERIVE_CONSTANTS,
    DerivedQuantity,
    DerivedRequirements,
    derive,
    motor_class_letter,
    parachute_diameter_m,
)
from rocketwright.physics import multistage as ms
from rocketwright.physics import recovery, solid, water
from rocketwright.schema import UNIT_SUFFIXES, GoalKind, Requirement, Tier

G0 = 9.80665


def _by_key(res: DerivedRequirements) -> dict[str, DerivedQuantity]:
    return {q.key: q for q in res.quantities}


def _check_common(res: DerivedRequirements, tier: Tier) -> None:
    assert res.tier is tier
    assert res.quantities, "no quantities derived"
    for q in res.quantities:
        assert q.key.endswith(UNIT_SUFFIXES), q.key
        assert q.formula.strip(), q.key
        assert q.inputs, q.key
        assert math.isfinite(q.value), q.key
        assert isinstance(q.assumptions, list)
    assert res.summary.strip()
    d = res.as_dict()
    json.dumps(d)  # must be JSON-serialisable
    assert d["tier"] == tier.value
    assert [q["key"] for q in d["quantities"]] == [q.key for q in res.quantities]


# --------------------------------------------------------------------------- constants


def test_every_constant_has_a_source_or_is_provisional():
    for name, entry in DERIVE_CONSTANTS.items():
        assert "value" in entry, name
        assert entry.get("provisional") is True or entry.get("source"), name
        assert entry.get("note"), name


# --------------------------------------------------------------------------- orbit


def test_orbit_circular_speed_rotation_credit_and_losses():
    req = Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=400_000, payload_mass_kg=150)
    res = derive(req, Tier.COMMERCIAL, launch_latitude_deg=28.5)
    _check_common(res, Tier.COMMERCIAL)
    q = _by_key(res)
    v_circ = math.sqrt(ms.MU_EARTH_M3PS2 / (ms.R_EARTH_M + 400_000.0))
    assert q["circular_speed_mps"].value == pytest.approx(v_circ, rel=1e-9)
    assert abs(q["circular_speed_mps"].value - 7670.0) < 10.0  # textbook ~7,669 m/s
    assert q["circular_speed_mps"].provisional is False
    assert "sqrt" in q["circular_speed_mps"].formula
    credit = ms.OMEGA_EARTH_RADPS * ms.R_EARTH_M * math.cos(math.radians(28.5))
    assert q["rotation_credit_mps"].value == pytest.approx(credit, rel=1e-9)
    assert abs(q["rotation_credit_mps"].value - 408.0) < 2.0
    loss = DERIVE_CONSTANTS["orbit_loss_allowance_mps"]["value"]
    assert q["loss_allowance_mps"].value == loss
    assert q["loss_allowance_mps"].provisional is True
    assert q["apogee_raise_dv_mps"].value == 0.0
    assert q["required_dv_mps"].value == pytest.approx(v_circ - credit + loss, rel=1e-9)
    assert q["required_dv_mps"].provisional is True  # inherits the loss allowance


def test_orbit_elliptical_target_adds_hohmann_raise():
    circ = Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=200_000, payload_mass_kg=1000)
    ell = Requirement(
        goal_kind=GoalKind.ORBIT,
        target_altitude_m=200_000,
        target_apogee_m=35_786_000,
        payload_mass_kg=1000,
    )
    q_c = _by_key(derive(circ, Tier.HEAVY, launch_latitude_deg=0.0))
    q_e = _by_key(derive(ell, Tier.HEAVY, launch_latitude_deg=0.0))
    r1 = ms.R_EARTH_M + 200_000.0
    r2 = ms.R_EARTH_M + 35_786_000.0
    raise_dv = math.sqrt(ms.MU_EARTH_M3PS2 / r1) * (math.sqrt(2.0 * r2 / (r1 + r2)) - 1.0)
    assert q_e["apogee_raise_dv_mps"].value == pytest.approx(raise_dv, rel=1e-9)
    assert 2300.0 < raise_dv < 2500.0  # LEO -> GTO is ~2.4 km/s
    assert q_e["required_dv_mps"].value == pytest.approx(
        q_c["required_dv_mps"].value + raise_dv, rel=1e-9
    )


def test_orbit_mass_ratio_and_liftoff_mass_scale():
    req = Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=400_000, payload_mass_kg=150)
    res = derive(req, Tier.COMMERCIAL, launch_latitude_deg=28.5)
    q = _by_key(res)
    isp = DERIVE_CONSTANTS["representative_isp_s"]["value"]["commercial"]
    dv = q["required_dv_mps"].value
    assert q["mass_ratio_total_ratio"].value == pytest.approx(math.exp(dv / (isp * G0)), rel=1e-9)
    assert q["stage_mass_ratio_ratio"].value == pytest.approx(
        math.exp(dv / 2.0 / (isp * G0)), rel=1e-9
    )
    assert q["mass_ratio_total_ratio"].provisional is True
    assert 0.0 < q["payload_fraction_frac"].value < 0.1
    assert 0.8 < q["propellant_mass_fraction_frac"].value < 1.0
    assert q["liftoff_mass_kg"].value == pytest.approx(150.0 / q["payload_fraction_frac"].value)
    typical = DERIVE_CONSTANTS["typical_payload_fraction_frac"]["value"]
    assert q["liftoff_mass_typical_kg"].value == pytest.approx(150.0 / typical)
    # Electron class: 300 kg -> ~13 t; here 150 kg lands in the same decade.
    assert 2_000.0 < q["liftoff_mass_kg"].value < 30_000.0


def test_orbit_default_latitude_is_a_provisional_constant():
    req = Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=500_000)
    res = derive(req, Tier.COMMERCIAL)
    q = _by_key(res)
    lat = DERIVE_CONSTANTS["default_launch_latitude_deg"]["value"]
    assert q["rotation_credit_mps"].inputs["launch_latitude_deg"] == lat
    assert q["rotation_credit_mps"].provisional is True
    res2 = derive(req, Tier.COMMERCIAL, launch_latitude_deg=0.0)
    assert _by_key(res2)["rotation_credit_mps"].provisional is False


def test_orbit_tier_with_altitude_goal_is_rejected():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=100_000)
    with pytest.raises(ValueError, match="orbit"):
        derive(req, Tier.COMMERCIAL)
    with pytest.raises(ValueError, match="altitude"):
        derive(Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=400_000), Tier.AMATEUR)


# --------------------------------------------------------------------------- amateur


def test_amateur_burnout_speed_impulse_and_motor_class():
    req = Requirement(
        goal_kind=GoalKind.ALTITUDE,
        target_altitude_m=2000,
        payload_mass_kg=1.0,
        recovery_required=True,
    )
    res = derive(req, Tier.AMATEUR)
    _check_common(res, Tier.AMATEUR)
    q = _by_key(res)
    assert q["burnout_speed_vacuum_mps"].value == pytest.approx(math.sqrt(2 * G0 * 2000), rel=1e-9)
    assert abs(q["burnout_speed_vacuum_mps"].value - 198.0) < 0.5
    assert q["burnout_speed_vacuum_mps"].provisional is False
    # drag raises the needed burnout speed; the factor is derived from solid.DEFAULT_CD
    assert q["burnout_speed_mps"].value > q["burnout_speed_vacuum_mps"].value
    assert q["drag_allowance_ratio"].value == pytest.approx(
        q["burnout_speed_mps"].value / q["burnout_speed_vacuum_mps"].value
    )
    assert q["drag_allowance_ratio"].inputs["cd"] == solid.DEFAULT_CD
    assert q["drag_allowance_ratio"].provisional is True
    airframe = DERIVE_CONSTANTS["amateur_airframe_mass_kg"]["value"]
    slope = DERIVE_CONSTANTS["amateur_airframe_mass_per_payload_frac"]["value"]
    m = airframe + slope * 1.0 + 1.0
    assert q["liftoff_mass_kg"].value == pytest.approx(m)
    t_burn = DERIVE_CONSTANTS["amateur_burn_time_s"]["value"]
    assert q["total_impulse_ns"].value == pytest.approx(
        m * (q["burnout_speed_mps"].value + G0 * t_burn)
    )
    assert q["total_impulse_ns"].provisional is True
    letter = motor_class_letter(q["total_impulse_ns"].value)
    assert q["motor_class_impulse_min_ns"].annotation == letter
    assert q["motor_class_impulse_min_ns"].value < q["total_impulse_ns"].value
    assert q["total_impulse_ns"].value <= q["motor_class_impulse_max_ns"].value
    # candidate motors: in the class or one above, from the bundled catalog
    ids = res.candidates["motor_ids"]
    assert set(ids) <= set(solid.list_motor_ids())
    lo = q["motor_class_impulse_min_ns"].value
    hi = 4.0 * lo  # class + one above spans two doublings
    for mid in ids:
        assert lo < solid.load_motor(mid).total_impulse_ns <= hi
    for mid in solid.list_motor_ids():
        if lo < solid.load_motor(mid).total_impulse_ns <= hi:
            assert mid in ids
    assert any("1.5 cal" in n for n in res.notes)


@pytest.mark.parametrize(
    ("impulse", "letter"),
    [
        (0.5, "1/4A"),
        (1.0, "1/2A"),
        (1.26, "A"),
        (2.5, "A"),
        (2.51, "B"),
        (10.0, "C"),
        (19.9, "D"),
        (112.7, "G"),
        (160.0, "G"),
        (160.1, "H"),
        (469.9, "I"),
        (937.8, "J"),
        (1280.0, "J"),
        (1281.0, "K"),
        (2560.0, "K"),
        (40_960.0, "O"),
        (50_000.0, "P"),
    ],
)
def test_motor_class_letter(impulse, letter):
    assert motor_class_letter(impulse) == letter


def test_parachute_diameter_for_1kg_at_6mps():
    d = parachute_diameter_m(1.0, 6.0)
    rho = 1.225
    expected = math.sqrt(8.0 * 1.0 * G0 / (math.pi * rho * recovery.DEFAULT_PARACHUTE_CD * 36.0))
    assert d == pytest.approx(expected, rel=1e-3)
    assert abs(d - 0.614) < 0.005
    # round trip through recovery.descend: the terminal speed comes back as 6 m/s
    from rocketwright.schema import Env

    res = recovery.descend(1.0, d, Env(), start_altitude_m=0.0)
    assert res.descent_speed_mps == pytest.approx(6.0, rel=1e-3)


def test_amateur_parachute_quantity_matches_helper():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=800, payload_mass_kg=0.5)
    q = _by_key(derive(req, Tier.AMATEUR))
    limit = solid.PASS_THRESHOLDS["max_descent_speed_mps"]
    assert q["parachute_diameter_m"].value == pytest.approx(
        parachute_diameter_m(q["liftoff_mass_kg"].value, limit)
    )
    assert q["parachute_diameter_m"].inputs["descent_speed_mps"] == limit


# --------------------------------------------------------------------------- bottle


def test_bottle_pressure_water_mass_and_parachute():
    req = Requirement(
        goal_kind=GoalKind.ALTITUDE,
        target_altitude_m=30,
        payload_mass_kg=0.06,
        recovery_required=True,
    )
    res = derive(req, Tier.BOTTLE)
    _check_common(res, Tier.BOTTLE)
    q = _by_key(res)
    V = DERIVE_CONSTANTS["bottle_volume_m3"]["value"]
    f = DERIVE_CONSTANTS["bottle_water_fill_frac"]["value"]
    eff = DERIVE_CONSTANTS["bottle_energy_efficiency_frac"]["value"]
    m = DERIVE_CONSTANTS["bottle_airframe_mass_kg"]["value"] + 0.06
    gam = water.GAMMA_AIR
    v0 = (1.0 - f) * V
    work_per_pa = v0 / (gam - 1.0) * (1.0 - (v0 / V) ** (gam - 1.0))
    p_abs = m * G0 * 30.0 / (eff * work_per_pa)
    p_gauge = p_abs - 101_325.0
    assert q["gauge_pressure_pa"].value == pytest.approx(p_gauge, rel=1e-9)
    assert 300_000.0 < p_gauge < 1_000_000.0
    assert q["gauge_pressure_pa"].provisional is True
    assert q["water_mass_kg"].value == pytest.approx(f * V * water.WATER_DENSITY_KGPM3)
    assert q["gauge_pressure_unclipped_pa"].inputs["expansion_work_j"] == pytest.approx(
        p_abs * work_per_pa, rel=1e-9
    )
    assert q["parachute_needed_count"].value == 1.0
    assert q["parachute_diameter_m"].value == pytest.approx(
        parachute_diameter_m(m, water.PASS_THRESHOLDS["max_descent_speed_with_payload_mps"])
    )
    assert not res.warnings


def test_bottle_pressure_is_clipped_with_a_warning():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=95, payload_mass_kg=0.2)
    res = derive(req, Tier.BOTTLE)
    q = _by_key(res)
    cap = water.PASS_THRESHOLDS["max_gauge_pressure_pa"]
    assert q["gauge_pressure_pa"].value == cap
    assert q["gauge_pressure_unclipped_pa"].value > cap
    assert any("clip" in w.lower() or "cap" in w.lower() for w in res.warnings)
    assert q["parachute_needed_count"].value == 1.0  # payload > 0


def test_bottle_without_payload_or_recovery_needs_no_parachute():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=20)
    res = derive(req, Tier.BOTTLE)
    q = _by_key(res)
    assert q["parachute_needed_count"].value == 0.0
    assert "parachute_diameter_m" not in q


# --------------------------------------------------------------------------- determinism


def test_derive_is_deterministic():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=1500, payload_mass_kg=0.8)
    a = derive(req, Tier.AMATEUR).as_dict()
    b = derive(req, Tier.AMATEUR).as_dict()
    assert a == b
