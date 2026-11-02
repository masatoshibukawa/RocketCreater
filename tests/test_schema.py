"""Round-trip and invariant tests for rocketwright.schema."""

import pytest
from pydantic import ValidationError

from rocketwright.schema import (
    MAX_TRACE_POINTS,
    AmateurDesign,
    Booster,
    BottleDesign,
    DesignAdapter,
    DispersionResult,
    Ellipse95,
    Env,
    FinSet,
    GoalKind,
    LandingScatter,
    MultistageDesign,
    OrbitInsertionStats,
    Quantiles,
    Requirement,
    SimResult,
    Stage,
    Tier,
    TracePoint,
)


def bottle() -> BottleDesign:
    return BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=500_000,
        nozzle_diameter_m=0.022,
        dry_mass_kg=0.12,
        payload_mass_kg=0.06,
        has_parachute=True,
        parachute_diameter_m=0.4,
    )


def amateur() -> AmateurDesign:
    return AmateurDesign(
        body_diameter_m=0.054,
        body_length_m=0.9,
        nose_length_m=0.15,
        fins=FinSet(count=4, root_chord_m=0.1, tip_chord_m=0.05, span_m=0.06),
        motor_id="dummy-F32",
        dry_mass_kg=0.5,
        payload_mass_kg=0.2,
        parachute_diameter_m=0.6,
        deploy_delay_s=4.0,
    )


def commercial() -> MultistageDesign:
    return MultistageDesign(
        tier="commercial",
        stages=[
            Stage(
                propellant_mass_kg=20_000,
                structural_fraction=0.08,
                engine_id="eng-a",
                engine_count=1,
            ),
            Stage(propellant_mass_kg=4_000, structural_fraction=0.1, engine_id="eng-b"),
        ],
        fairing_mass_kg=150,
        payload_mass_kg=200,
        pitch_start_s=10,
        initial_pitch_deg=5,
    )


def heavy() -> MultistageDesign:
    return MultistageDesign(
        tier="heavy",
        stages=[
            Stage(
                propellant_mass_kg=400_000,
                structural_fraction=0.06,
                engine_id="eng-a",
                engine_count=9,
            ),
            Stage(propellant_mass_kg=90_000, structural_fraction=0.08, engine_id="eng-b"),
            Stage(propellant_mass_kg=10_000, structural_fraction=0.1, engine_id="eng-c"),
        ],
        boosters=[Booster(booster_id="srb-x", count=2)],
        fairing_mass_kg=2_000,
        payload_mass_kg=5_000,
        pitch_start_s=12,
        initial_pitch_deg=4,
    )


@pytest.mark.parametrize("make", [bottle, amateur, commercial, heavy])
def test_design_roundtrip(make):
    design = make()
    via_adapter = DesignAdapter.validate_json(DesignAdapter.dump_json(design))
    assert via_adapter == design
    assert type(via_adapter) is type(design)
    via_class = type(design).model_validate_json(design.model_dump_json())
    assert via_class == design


def test_discriminator_picks_class():
    parsed = DesignAdapter.validate_python(heavy().model_dump())
    assert isinstance(parsed, MultistageDesign)
    assert parsed.tier == "heavy"
    assert parsed.tier == Tier.HEAVY


def test_discriminator_rejects_wrong_tier():
    data = bottle().model_dump()
    data["tier"] = "amateur"  # fields do not match AmateurDesign
    with pytest.raises(ValidationError):
        DesignAdapter.validate_python(data)
    data["tier"] = "plane"
    with pytest.raises(ValidationError, match="tier"):
        DesignAdapter.validate_python(data)


def test_commercial_rejects_boosters():
    data = commercial().model_dump()
    data["boosters"] = [{"booster_id": "srb-x", "count": 2}]
    with pytest.raises(ValidationError, match="boosters"):
        MultistageDesign.model_validate(data)


def test_bottle_parachute_requires_diameter():
    with pytest.raises(ValidationError, match="parachute_diameter_m"):
        BottleDesign(
            bottle_volume_m3=0.0015,
            water_fill_frac=0.4,
            initial_gauge_pressure_pa=500_000,
            nozzle_diameter_m=0.022,
            dry_mass_kg=0.12,
            has_parachute=True,
        )


def test_requirement_env_roundtrip():
    req = Requirement(
        goal_kind=GoalKind.ORBIT,
        target_altitude_m=400_000,
        target_apogee_m=400_000,
        payload_mass_kg=150,
        budget_jpy=2e9,
        tier_override=Tier.HEAVY,
        text="put 150 kg into a 400 km orbit",
    )
    assert Requirement.model_validate_json(req.model_dump_json()) == req
    env = Env(
        launch_latitude_deg=31.25, launch_altitude_m=20, wind_speed_mps=5, wind_direction_deg=270
    )
    assert Env.model_validate_json(env.model_dump_json()) == env


def test_requirement_rejects_apogee_for_altitude_goal():
    with pytest.raises(ValidationError, match="target_apogee_m"):
        Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=1000, target_apogee_m=2000)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        Env(launch_latitude_deg=0, wind_speed_kph=10)


def test_trace_is_capped():
    points = [TracePoint(t_s=float(i), altitude_m=float(i), speed_mps=1.0) for i in range(2000)]
    result = SimResult(tier=Tier.AMATEUR, success=True, cost_jpy=0, trace=points)
    assert len(result.trace) == MAX_TRACE_POINTS
    assert result.trace[0].t_s == 0
    assert result.trace[-1].t_s == 1999
    exact = SimResult(tier=Tier.AMATEUR, success=True, cost_jpy=0, trace=points[:MAX_TRACE_POINTS])
    assert exact.trace == points[:MAX_TRACE_POINTS]


def test_metric_keys_require_unit_suffix():
    with pytest.raises(ValidationError, match="unit suffix"):
        SimResult(tier=Tier.BOTTLE, success=True, cost_jpy=0, metrics={"apogee": 1.0})
    ok = SimResult(tier=Tier.BOTTLE, success=True, cost_jpy=0, metrics={"apogee_m": 1.0})
    assert ok.metrics == {"apogee_m": 1.0}


def test_failed_result_needs_reason():
    with pytest.raises(ValidationError, match="failure reason"):
        SimResult(tier=Tier.BOTTLE, success=False, cost_jpy=0)
    SimResult(tier=Tier.BOTTLE, success=False, cost_jpy=0, failure_reasons=["apogee below target"])


def _landing() -> LandingScatter:
    return LandingScatter(
        points=[{"east_m": 1.0, "north_m": 2.0}],
        ellipse_95=Ellipse95(
            center_east_m=1, center_north_m=2, semi_major_m=3, semi_minor_m=2, angle_deg=10
        ),
    )


def _orbit() -> OrbitInsertionStats:
    q = Quantiles(p05=-1000, p50=0, p95=1000)
    return OrbitInsertionStats(
        perigee_error_m=q, apogee_error_m=q, payload_margin_kg=Quantiles(p05=1, p50=2, p95=3)
    )


def test_dispersion_tier_block():
    sub = DispersionResult(tier=Tier.BOTTLE, n=10, seed=1, success_rate=0.9, landing=_landing())
    assert DispersionResult.model_validate_json(sub.model_dump_json()) == sub
    with pytest.raises(ValidationError, match="landing"):
        DispersionResult(tier=Tier.BOTTLE, n=10, seed=1, success_rate=0.9, orbit_insertion=_orbit())
    orb = DispersionResult(
        tier=Tier.COMMERCIAL, n=10, seed=1, success_rate=0.5, orbit_insertion=_orbit()
    )
    assert DispersionResult.model_validate_json(orb.model_dump_json()) == orb
    with pytest.raises(ValidationError, match="orbit_insertion"):
        DispersionResult(tier=Tier.HEAVY, n=10, seed=1, success_rate=0.5, landing=_landing())


def test_quantiles_must_be_ordered():
    with pytest.raises(ValidationError, match="p05 <= p50 <= p95"):
        Quantiles(p05=3, p50=2, p95=1)


def test_models_are_frozen():
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=100)
    with pytest.raises(ValidationError):
        req.payload_mass_kg = 1.0  # type: ignore[misc]
