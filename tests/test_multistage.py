"""Tests for the multistage ascent model (CLAUDE.md section 7, prompt 1A)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from rocketwright.physics import multistage as ms
from rocketwright.schema import (
    MAX_TRACE_POINTS,
    Booster,
    Env,
    MultistageDesign,
    Stage,
    Tier,
)

G0 = 9.80665
REFERENCE_DIR = Path(__file__).parent / "reference"


def single_stage() -> MultistageDesign:
    return MultistageDesign(
        tier="commercial",
        stages=[
            Stage(
                propellant_mass_kg=20_000.0,
                structural_fraction=0.08,
                engine_id="merlin_1d",
                engine_count=1,
            )
        ],
        payload_mass_kg=500.0,
        pitch_start_s=10.0,
        initial_pitch_deg=5.0,
    )


def two_stage(pitch_start_s: float = 23.0, initial_pitch_deg: float = 5.0) -> MultistageDesign:
    """A Falcon-9-class two-stage vehicle (round numbers, not a reproduction).

    The default pitch program puts 15 t into a ~300 x 2600 km orbit in this model."""
    return MultistageDesign(
        tier="commercial",
        stages=[
            Stage(
                propellant_mass_kg=400_000.0,
                structural_fraction=0.055,
                engine_id="merlin_1d",
                engine_count=9,
            ),
            Stage(
                propellant_mass_kg=100_000.0,
                structural_fraction=0.045,
                engine_id="merlin_1d_vacuum",
                engine_count=1,
            ),
        ],
        fairing_mass_kg=1_900.0,
        payload_mass_kg=15_000.0,
        pitch_start_s=pitch_start_s,
        initial_pitch_deg=initial_pitch_deg,
    )


def env() -> Env:
    return Env(launch_latitude_deg=28.5, launch_altitude_m=0.0)


# --------------------------------------------------------------------------- catalog


def test_engine_lookup_lists_available_ids_on_miss() -> None:
    with pytest.raises(KeyError, match="merlin_1d"):
        ms.get_engine("no_such_engine")


def test_engine_entries_have_required_fields() -> None:
    engine = ms.get_engine("merlin_1d")
    assert engine.isp_vac_s > engine.isp_sl_s > 0
    assert engine.thrust_vac_n > engine.thrust_sl_n > 0
    assert engine.mass_kg > 0


# --------------------------------------------------------------------------- physics


def test_single_stage_matches_tsiolkovsky_without_gravity_and_drag() -> None:
    design = single_stage()
    engine = ms.get_engine(design.stages[0].engine_id)
    stage = design.stages[0]
    structural_kg = (
        stage.propellant_mass_kg * stage.structural_fraction / (1.0 - stage.structural_fraction)
    )
    m0 = stage.propellant_mass_kg + structural_kg + design.payload_mass_kg
    mf = m0 - stage.propellant_mass_kg
    expected_mps = engine.isp_vac_s * G0 * math.log(m0 / mf)

    result = ms.simulate_with_options(design, env(), gravity=False, drag=False, atmosphere=False)

    assert result.metrics["burnout_speed_mps"] == pytest.approx(expected_mps, rel=1e-3)
    assert result.metrics["dv_ideal_mps"] == pytest.approx(expected_mps, rel=1e-6)
    assert result.metrics["dv_gravity_loss_mps"] == pytest.approx(0.0, abs=1e-6)
    assert result.metrics["dv_drag_loss_mps"] == pytest.approx(0.0, abs=1e-6)


def test_two_stage_mass_drops_by_structural_mass_at_staging() -> None:
    design = two_stage()
    ascent = ms.run_ascent(design, env(), ms.AscentOptions())
    stage0 = design.stages[0]
    structural0_kg = (
        stage0.propellant_mass_kg * stage0.structural_fraction / (1.0 - stage0.structural_fraction)
    )
    liftoff_kg = ascent.liftoff_mass_kg

    separations = [e for e in ascent.events if e.label == "stage1_separation"]
    assert len(separations) == 1
    sep = separations[0]
    # Propellant fully consumed before separation ...
    assert sep.mass_before_kg == pytest.approx(liftoff_kg - stage0.propellant_mass_kg, rel=1e-9)
    # ... and exactly the structural mass is dropped.
    assert sep.mass_before_kg - sep.mass_after_kg == pytest.approx(structural0_kg, rel=1e-9)

    result = ms.simulate(design, env())
    assert result.metrics["stage1_dry_mass_kg"] == pytest.approx(structural0_kg)
    assert result.metrics["stage1_wet_mass_kg"] == pytest.approx(
        structural0_kg + stage0.propellant_mass_kg
    )
    assert result.metrics["total_liftoff_mass_kg"] == pytest.approx(liftoff_kg)


def test_determinism() -> None:
    a = ms.simulate(two_stage(), env(), seed=42)
    b = ms.simulate(two_stage(), env(), seed=42)
    assert a.model_dump() == b.model_dump()


def test_rejects_non_multistage_tiers() -> None:
    from rocketwright.schema import BottleDesign

    bottle = BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=500_000,
        nozzle_diameter_m=0.022,
        dry_mass_kg=0.12,
    )
    with pytest.raises(ValueError, match="tier"):
        ms.simulate(bottle, env())


def test_full_model_two_stage_reaches_orbit() -> None:
    result = ms.simulate(two_stage(), env(), target_perigee_m=200_000.0)
    m = result.metrics
    for key in (
        "perigee_m",
        "apogee_m",
        "burnout_speed_mps",
        "burnout_altitude_m",
        "dv_ideal_mps",
        "dv_gravity_loss_mps",
        "dv_drag_loss_mps",
        "max_q_pa",
        "max_q_altitude_m",
        "payload_margin_kg",
        "stage1_wet_mass_kg",
        "stage1_dry_mass_kg",
        "stage2_wet_mass_kg",
        "stage2_dry_mass_kg",
        "total_liftoff_mass_kg",
        "flight_time_s",
    ):
        assert key in m, key
    assert result.tier is Tier.COMMERCIAL
    assert len(result.trace) <= MAX_TRACE_POINTS
    assert result.trace[0].t_s == 0.0
    assert result.trace[-1].t_s == pytest.approx(m["flight_time_s"])
    assert m["perigee_m"] > 0.0
    assert 0.0 < m["max_q_pa"] < 1e6
    assert m["dv_gravity_loss_mps"] > 0.0
    assert m["dv_drag_loss_mps"] > 0.0
    assert result.success, result.failure_reasons


def test_failure_reasons_come_from_thresholds() -> None:
    # A single-stage vehicle with a tiny pitch kick cannot reach orbit.
    result = ms.simulate(single_stage(), env(), target_perigee_m=200_000.0)
    assert not result.success
    assert any("perigee" in r for r in result.failure_reasons)
    assert "min_perigee_m" in ms.PASS_THRESHOLDS
    assert "min_liftoff_twr_ratio" in ms.PASS_THRESHOLDS
    assert "max_q_pa" in ms.PASS_THRESHOLDS


def test_heavy_with_boosters_runs_and_separates_boosters() -> None:
    design = MultistageDesign(
        tier="heavy",
        stages=[
            Stage(
                propellant_mass_kg=280_000.0,
                structural_fraction=0.07,
                engine_id="rd_180",
                engine_count=1,
            ),
            Stage(
                propellant_mass_kg=25_000.0,
                structural_fraction=0.09,
                engine_id="rl10",
                engine_count=1,
            ),
        ],
        boosters=[Booster(booster_id="gem_63", count=4)],
        fairing_mass_kg=2_500.0,
        payload_mass_kg=10_000.0,
        pitch_start_s=12.0,
        initial_pitch_deg=5.0,
    )
    ascent = ms.run_ascent(design, env(), ms.AscentOptions())
    labels = [e.label for e in ascent.events]
    assert "booster_separation" in labels
    result = ms.simulate(design, env())
    assert result.metrics["total_liftoff_mass_kg"] > 400_000.0
    assert any("provisional" in w for w in result.warnings)


def test_earth_rotation_adds_eastward_speed() -> None:
    design = two_stage()
    still = ms.simulate(design, env())
    rotating = ms.simulate(design, Env(launch_latitude_deg=28.5, earth_rotation=True))
    assert rotating.trace[0].speed_mps > still.trace[0].speed_mps


def test_tune_pitch_program_returns_new_design_closer_to_target() -> None:
    start = two_stage(pitch_start_s=8.0, initial_pitch_deg=12.0)
    target_m = 250_000.0
    before = ms.simulate(start, env(), target_perigee_m=target_m).metrics["perigee_m"]
    tuned = ms.tune_pitch_program(start, env(), target_perigee_m=target_m)
    assert isinstance(tuned, MultistageDesign)
    assert tuned.stages == start.stages
    result = ms.simulate(tuned, env(), target_perigee_m=target_m)
    after = result.metrics["perigee_m"]
    assert abs(after - target_m) < abs(before - target_m)
    assert result.success, result.failure_reasons


# --------------------------------------------------------------------------- orbit insertion


def test_coast_circularize_is_default_with_a_target_and_hits_it() -> None:
    target_m = 400_000.0
    design = two_stage(pitch_start_s=21.5, initial_pitch_deg=4.5)  # tune_pitch_program output
    result = ms.simulate(design, env(), target_perigee_m=target_m)
    m = result.metrics
    assert result.success, result.failure_reasons
    assert m["perigee_m"] == pytest.approx(target_m, rel=0.05)
    assert m["apogee_m"] == pytest.approx(target_m, rel=0.10)
    assert m["coast_time_s"] > 0.0
    assert m["circularization_dv_mps"] > 0.0
    assert m["propellant_margin_kg"] > 0.0
    assert m["payload_margin_kg"] > 0.0
    assert "max_q_pa" in m
    # the trace shows the coast: mass is constant while the altitude keeps climbing
    masses = [p.mass_kg for p in result.trace]
    assert any(abs(a - b) < 1e-6 for a, b in zip(masses, masses[1:], strict=False))
    # burn 1 cutoff -> coast -> circularization burn; "burnout" is the final engine cutoff
    assert m["coast_start_time_s"] < m["circularization_ignition_time_s"]
    assert m["circularization_cutoff_time_s"] > m["circularization_ignition_time_s"]
    assert m["burnout_time_s"] == pytest.approx(m["circularization_cutoff_time_s"])
    assert result.trace[-1].t_s == pytest.approx(m["flight_time_s"])
    assert m["coast_time_s"] == pytest.approx(
        m["circularization_ignition_time_s"] - m["coast_start_time_s"]
    )


def test_direct_insertion_keeps_the_single_burn_behaviour() -> None:
    design = two_stage()
    direct = ms.simulate(design, env(), target_perigee_m=400_000.0, insertion="direct")
    plain = ms.simulate(design, env())
    assert direct.metrics["perigee_m"] == pytest.approx(plain.metrics["perigee_m"])
    assert direct.metrics["coast_time_s"] == 0.0
    assert direct.metrics["circularization_dv_mps"] == 0.0
    assert direct.metrics["propellant_margin_kg"] == 0.0
    # no target -> no insertion manoeuvre either
    assert plain.metrics["coast_time_s"] == 0.0


def test_coast_circularize_falls_through_when_apogee_is_out_of_reach() -> None:
    # Single stage with a tiny kick: the osculating apogee never reaches 400 km.
    result = ms.simulate(single_stage(), env(), target_perigee_m=400_000.0)
    assert not result.success
    assert any("apogee" in r for r in result.failure_reasons)
    assert result.metrics["propellant_margin_kg"] == 0.0
    assert result.metrics["payload_margin_kg"] < 0.0


def test_direct_payload_margin_charges_the_climb_to_the_reference_altitude() -> None:
    """At a 600 km reference the single-burn trajectory burns out far lower; the margin must
    charge the climb, so the implied capability stays well under the old +80 % optimism."""
    design = two_stage()
    low = ms.simulate(design, env(), target_perigee_m=200_000.0, insertion="direct").metrics
    high = ms.simulate(design, env(), target_perigee_m=600_000.0, insertion="direct").metrics
    assert high["payload_margin_kg"] < low["payload_margin_kg"]
    # Energy of a 600 km circular orbit charged from the burnout radius (see _required_dv_mps)
    r_b = ms.R_EARTH_M + high["burnout_altitude_m"]
    r_ref = ms.R_EARTH_M + 600_000.0
    v_req = math.sqrt(
        ms.MU_EARTH_M3PS2 / r_ref + 2.0 * ms.MU_EARTH_M3PS2 * (1.0 / r_b - 1.0 / r_ref)
    )
    assert v_req > math.sqrt(ms.MU_EARTH_M3PS2 / r_ref)
    assert high["payload_margin_kg"] < 0.5 * design.payload_mass_kg


def test_run_ascent_survives_event_root_finding_edge_case() -> None:
    """Regression: firefly_alpha with a 200 kg fairing, rotation on and a 16 s / 3 deg kick
    used to raise `ValueError: f(a) and f(b) must have different signs` from solve_ivp."""
    from rocketwright.references import get_reference

    entry = get_reference("firefly_alpha")
    design = entry.design.model_copy(
        update={
            "pitch_start_s": 16.0,
            "initial_pitch_deg": 3.0,
            "fairing_mass_kg": 200.0,
            "payload_mass_kg": 1030.0,
        }
    )
    ascent = ms.run_ascent(design, entry.env, ms.AscentOptions())
    assert ascent.t_s[-1] > 0.0
    result = ms.simulate(design, entry.env, target_perigee_m=300_000.0)
    assert math.isfinite(result.metrics["perigee_m"])


def test_liftoff_twr_threshold_is_1_1_with_a_warning_below_1_2() -> None:
    assert ms.PASS_THRESHOLDS["min_liftoff_twr_ratio"] == pytest.approx(1.1)
    design = two_stage()
    # 9 Merlins on 400 t is ~1.4; scale the propellant up so the T/W lands between 1.1 and 1.2
    heavy = design.model_copy(
        update={
            "stages": [
                design.stages[0].model_copy(update={"propellant_mass_kg": 520_000.0}),
                design.stages[1],
            ]
        }
    )
    result = ms.simulate(heavy, env())
    twr = result.metrics["liftoff_twr_ratio"]
    assert 1.1 <= twr < 1.2, twr
    assert not any("thrust-to-weight" in r for r in result.failure_reasons)
    assert any("thrust-to-weight" in w for w in result.warnings)


# --------------------------------------------------------------------------- reference vehicles


def _reference_files() -> list[Path]:
    return sorted(REFERENCE_DIR.glob("*.yaml")) + sorted(REFERENCE_DIR.glob("*.yml"))


@pytest.mark.parametrize("path", _reference_files() or [None])
def test_reference_vehicle_payload_order_of_magnitude(path: Path | None) -> None:
    if path is None:
        pytest.skip(
            "no reference vehicle data in tests/reference/ (see tests/reference/README.md); "
            "a human must add a YAML file with a public source URL"
        )
    ref = yaml.safe_load(path.read_text())
    design = MultistageDesign.model_validate(ref["design"])
    design = design.model_copy(update={"payload_mass_kg": float(ref["payload_to_leo_kg"])})
    target_m = float(ref["orbit_altitude_m"])
    tuned = ms.tune_pitch_program(design, env(), target_perigee_m=target_m)
    result = ms.simulate(tuned, env(), target_perigee_m=target_m)
    # Order-of-magnitude check: the stated payload reaches a positive perigee, and the payload
    # margin estimate is within a factor of two of the stated capability.
    assert result.metrics["perigee_m"] > 0.0, result.failure_reasons
    assert abs(result.metrics["payload_margin_kg"]) < float(ref["payload_to_leo_kg"])
