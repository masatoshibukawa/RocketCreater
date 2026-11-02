"""Tests for the Monte-Carlo dispersion runner (CLAUDE.md section 7, "多数回試行")."""

from __future__ import annotations

import math
import pickle
import time

import numpy as np
import pytest

from rocketwright import dispersion as mc
from rocketwright.physics import multistage, solid, water
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    DesignAdapter,
    DispersionResult,
    Env,
    FinSet,
    LandingPoint,
    MultistageDesign,
    SimResult,
    Stage,
    Tier,
)

G0 = 9.80665


def amateur_design() -> AmateurDesign:
    return AmateurDesign(
        body_diameter_m=0.054,
        body_length_m=0.9,
        nose_length_m=0.15,
        fins=FinSet(count=4, root_chord_m=0.10, tip_chord_m=0.05, span_m=0.035, sweep_m=0.03),
        motor_id="dummy_J420",
        dry_mass_kg=1.8,
        payload_mass_kg=1.0,
        parachute_diameter_m=1.2,
        deploy_delay_s=1.0,
    )


def bottle_design() -> BottleDesign:
    return BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=300_000.0,
        nozzle_diameter_m=0.022,
        dry_mass_kg=0.12,
        payload_mass_kg=0.06,
        has_parachute=True,
        parachute_diameter_m=0.5,
    )


def commercial_design() -> MultistageDesign:
    return MultistageDesign(
        tier="commercial",
        stages=[
            Stage(
                propellant_mass_kg=9250,
                structural_fraction=0.08,
                engine_id="rutherford",
                engine_count=10,
            ),
            Stage(
                propellant_mass_kg=3500,
                structural_fraction=0.10,
                engine_id="rutherford",
                engine_count=1,
            ),
        ],
        fairing_mass_kg=50,
        payload_mass_kg=150,
        pitch_start_s=25.5,
        initial_pitch_deg=7.95,
    )


def windy_env() -> Env:
    return Env(
        launch_latitude_deg=36.0,
        launch_altitude_m=300.0,
        wind_speed_mps=3.0,
        wind_direction_deg=270.0,
    )


# --------------------------------------------------------------------------- helpers


def test_normalize_reason_buckets_numbers_but_keeps_catalog_ids() -> None:
    a = mc.normalize_reason("perigee 289.9 km below target 400 km (tolerance -10 %)")
    b = mc.normalize_reason("perigee 301.25 km  below target 400 km (tolerance -10 %)")
    assert a == b == "perigee N km below target N km (tolerance N %)"
    assert mc.normalize_reason("motor dummy_G80 cannot lift: 80 N <= 90 N") == (
        "motor dummy_G80 cannot lift: N N <= N N"
    )
    assert mc.normalize_reason("cost 1,234,567 JPY exceeds budget 2e9 JPY") == (
        "cost N JPY exceeds budget N JPY"
    )


def test_spec_covers_every_tier_and_is_provisional() -> None:
    assert set(mc.DISPERSION_SPEC) == set(Tier)
    assert mc.DISPERSION_SPEC_PROVISIONAL is True
    assert {"pressure_frac", "wind_speed_mps", "wind_direction_deg"} <= set(
        mc.DISPERSION_SPEC[Tier.BOTTLE]
    )
    assert {
        "thrust_frac",
        "dry_mass_frac",
        "wind_speed_mps",
        "wind_direction_deg",
        "deploy_delay_s",
    } <= set(mc.DISPERSION_SPEC[Tier.AMATEUR])
    for t in (Tier.COMMERCIAL, Tier.HEAVY):
        assert {"isp_frac", "thrust_frac", "structural_fraction_frac"} <= set(mc.DISPERSION_SPEC[t])


def test_metric_quantiles_are_nan_safe_and_ordered() -> None:
    def sim(**metrics: float) -> SimResult:
        return SimResult(tier=Tier.AMATEUR, success=True, metrics=metrics, cost_jpy=0.0)

    samples = [sim(apogee_m=float(v), extra_m=math.nan) for v in range(1, 101)]
    samples.append(sim(apogee_m=math.inf, only_once_m=3.0))
    q = mc.metric_quantiles(samples)
    assert "extra_m" not in q  # all NaN -> skipped
    assert q["only_once_m"].p05 == q["only_once_m"].p95 == 3.0
    a = q["apogee_m"]
    assert a.p05 <= a.p50 <= a.p95
    assert a.p50 == pytest.approx(50.5)
    assert a.p95 < 101  # inf dropped


def test_ellipse_95_matches_known_covariance() -> None:
    rng = np.random.default_rng(0)
    # anisotropic cloud rotated by 30 deg: sigma 10 along the major axis, 3 across
    theta = math.radians(30.0)
    raw = rng.normal(size=(20_000, 2)) * np.array([10.0, 3.0])
    rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    xy = raw @ rot.T + np.array([100.0, -50.0])
    ell = mc.ellipse_95([LandingPoint(east_m=x, north_m=y) for x, y in xy])
    assert ell.center_east_m == pytest.approx(100.0, abs=0.5)
    assert ell.center_north_m == pytest.approx(-50.0, abs=0.5)
    assert ell.semi_major_m == pytest.approx(math.sqrt(mc.CHI2_2DOF_95) * 10.0, rel=0.03)
    assert ell.semi_minor_m == pytest.approx(math.sqrt(mc.CHI2_2DOF_95) * 3.0, rel=0.03)
    assert ell.angle_deg == pytest.approx(30.0, abs=1.5)
    # containment: about 95 % of the points fall inside
    c, s = math.cos(math.radians(ell.angle_deg)), math.sin(math.radians(ell.angle_deg))
    dx, dy = xy[:, 0] - ell.center_east_m, xy[:, 1] - ell.center_north_m
    u, v = dx * c + dy * s, -dx * s + dy * c
    inside = (u / ell.semi_major_m) ** 2 + (v / ell.semi_minor_m) ** 2 <= 1.0
    assert inside.mean() == pytest.approx(0.95, abs=0.01)
    # degenerate inputs do not crash
    assert mc.ellipse_95([]).semi_major_m == 0.0
    one = mc.ellipse_95([LandingPoint(east_m=1.0, north_m=2.0)])
    assert (one.center_east_m, one.center_north_m, one.semi_major_m) == (1.0, 2.0, 0.0)


# --------------------------------------------------------------------------- perturbations


def test_perturbations_are_deterministic_and_within_spec() -> None:
    env = windy_env()
    for perturb, design in (
        (mc.perturb_bottle, bottle_design()),
        (mc.perturb_amateur, amateur_design()),
        (mc.perturb_multistage, commercial_design()),
    ):
        a = perturb(design, env, np.random.default_rng([7, 3]))
        b = perturb(design, env, np.random.default_rng([7, 3]))
        assert a == b
        d, e, scales = a
        assert d.tier == design.tier
        assert e.wind_speed_mps >= 0.0 and 0.0 <= e.wind_direction_deg < 360.0
        for v in scales.values():
            assert 0.5 <= v <= 1.5
    # amateur: thrust goes through the keyword, mass/delay through the design, wind via env
    d, e, scales = mc.perturb_amateur(amateur_design(), env, np.random.default_rng([1, 1]))
    assert set(scales) == {"thrust_scale"}
    assert d.deploy_delay_s >= 0.0 and d.dry_mass_kg > 0.0
    assert d.motor_id == "dummy_J420"
    # multistage: isp/thrust keywords, structural fraction stays in (0, 1), env untouched
    d2, e2, scales2 = mc.perturb_multistage(commercial_design(), env, np.random.default_rng([1, 1]))
    assert set(scales2) == {"isp_scale", "thrust_scale"}
    assert all(0.0 < s.structural_fraction < 1.0 for s in d2.stages)
    assert e2 == env
    with pytest.raises(ValueError):
        mc.perturb_bottle(amateur_design(), env, np.random.default_rng(0))


def test_perturbed_designs_are_valid_models() -> None:
    """model_copy skips validation, so re-validate what the perturbations produce."""
    env = windy_env()
    for i in range(50):
        rng = np.random.default_rng([99, i])
        for perturb, design in (
            (mc.perturb_bottle, bottle_design()),
            (mc.perturb_amateur, amateur_design()),
            (mc.perturb_multistage, commercial_design()),
        ):
            d, e, _ = perturb(design, env, rng)
            DesignAdapter.validate_python(d.model_dump())
            Env.model_validate(e.model_dump())


# --------------------------------------------------------------------------- physics keywords


def test_solid_thrust_scale_scales_the_rocket_equation() -> None:
    d = amateur_design()
    motor = solid.load_motor(d.motor_id)
    calm = Env(launch_altitude_m=300.0)
    for scale in (0.9, 1.1):
        res = solid.simulate_with_options(d, calm, gravity=False, drag=False, thrust_scale=scale)
        m0 = d.dry_mass_kg + d.payload_mass_kg + motor.total_mass_kg
        mf = m0 - motor.propellant_mass_kg
        v_e = scale * motor.total_impulse_ns / motor.propellant_mass_kg
        assert res.metrics["burnout_speed_mps"] == pytest.approx(v_e * math.log(m0 / mf), rel=2e-3)
        assert res.metrics["total_impulse_ns"] == pytest.approx(scale * motor.total_impulse_ns)
    assert solid.load_motor(d.motor_id).scaled(1.0) is motor
    with pytest.raises(ValueError):
        motor.scaled(0.0)


def test_multistage_isp_and_thrust_scales() -> None:
    design = MultistageDesign(
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
    engine = multistage.get_engine("merlin_1d")
    stage = design.stages[0]
    m0 = stage.propellant_mass_kg / (1.0 - stage.structural_fraction) + design.payload_mass_kg
    mf = m0 - stage.propellant_mass_kg
    env = Env(launch_latitude_deg=28.5)
    base = multistage.simulate_with_options(
        design, env, gravity=False, drag=False, atmosphere=False
    )
    # Isp scale multiplies the Tsiolkovsky delta-v; thrust scale leaves it unchanged but
    # shortens the burn in proportion.
    isp = multistage.simulate_with_options(
        design, env, gravity=False, drag=False, atmosphere=False, isp_scale=1.05
    )
    expected = 1.05 * engine.isp_vac_s * G0 * math.log(m0 / mf)
    assert isp.metrics["burnout_speed_mps"] == pytest.approx(expected, rel=1e-3)
    assert isp.metrics["dv_ideal_mps"] == pytest.approx(expected, rel=1e-6)
    thr = multistage.simulate_with_options(
        design, env, gravity=False, drag=False, atmosphere=False, thrust_scale=1.25
    )
    assert thr.metrics["dv_ideal_mps"] == pytest.approx(base.metrics["dv_ideal_mps"], rel=1e-9)
    assert thr.metrics["burnout_speed_mps"] == pytest.approx(
        base.metrics["burnout_speed_mps"], rel=1e-3
    )
    assert thr.metrics["stage1_separation_time_s"] == pytest.approx(
        base.metrics["stage1_separation_time_s"] / 1.25, rel=1e-6
    )
    assert thr.metrics["liftoff_thrust_n"] == pytest.approx(1.25 * base.metrics["liftoff_thrust_n"])
    with pytest.raises(ValueError):
        multistage.simulate(design, env, thrust_scale=0.0)


# --------------------------------------------------------------------------- runner


def _failing_simulate(design, env, seed=None, **scales) -> SimResult:  # noqa: ANN001
    """Module-level so it pickles: fails when the perturbed pressure is above the nominal."""
    high = design.initial_gauge_pressure_pa > 300_000.0
    return SimResult(
        tier=Tier.BOTTLE,
        success=not high,
        failure_reasons=[f"pressure {design.initial_gauge_pressure_pa:.0f} Pa too high"]
        if high
        else [],
        metrics={
            "apogee_m": design.initial_gauge_pressure_pa / 10_000.0,
            "landing_east_m": env.wind_speed_mps,
            "landing_north_m": env.wind_direction_deg,
        },
        cost_jpy=0.0,
        warnings=["w1"] if high else ["w2"],
    )


def test_runner_collects_rate_quantiles_failures_and_warnings() -> None:
    run = mc.run_dispersion_detailed(
        bottle_design(),
        windy_env(),
        40,
        5,
        perturb=mc.perturb_bottle,
        simulate=_failing_simulate,
        tier=Tier.BOTTLE,
        summarize=mc.summarize_landing,
    )
    res = run.result
    assert isinstance(res, DispersionResult)
    assert res.n == 40 and res.seed == 5 and len(run.samples) == 40
    assert run.nominal.success  # the nominal run is unperturbed (300 kPa exactly)
    n_fail = sum(1 for s in run.samples if not s.success)
    assert 5 < n_fail < 35  # about half the draws are above the nominal
    assert res.success_rate == pytest.approx(1.0 - n_fail / 40)
    assert res.failure_counts == {"pressure N Pa too high": n_fail}
    assert sorted(res.warnings) == ["w1", "w2"]  # unique, aggregated
    assert res.quantiles["apogee_m"].p05 < 30.0 < res.quantiles["apogee_m"].p95
    assert res.landing is not None and len(res.landing.points) == 40
    assert res.orbit_insertion is None
    DispersionResult.model_validate_json(res.model_dump_json())


def test_runner_is_deterministic_and_order_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs = dict(
        perturb=mc.perturb_bottle,
        simulate=_failing_simulate,
        tier=Tier.BOTTLE,
        summarize=mc.summarize_landing,
    )
    monkeypatch.setenv("ROCKETWRIGHT_DISPERSION_WORKERS", "0")
    inline = mc.run_dispersion(bottle_design(), windy_env(), 48, 11, **kwargs)
    monkeypatch.setenv("ROCKETWRIGHT_DISPERSION_WORKERS", "3")
    pooled = mc.run_dispersion(bottle_design(), windy_env(), 48, 11, **kwargs)
    assert inline == pooled
    assert mc.run_dispersion(bottle_design(), windy_env(), 48, 12, **kwargs) != inline
    # sample i depends on (seed, i) only: the first 10 of n=48 equal n=10
    monkeypatch.setenv("ROCKETWRIGHT_DISPERSION_WORKERS", "0")
    small = mc.run_dispersion(bottle_design(), windy_env(), 10, 11, **kwargs)
    assert small.landing is not None and inline.landing is not None
    assert small.landing.points == inline.landing.points[:10]


def test_worker_arguments_pickle() -> None:
    import functools

    args = (
        bottle_design(),
        windy_env(),
        1,
        0,
        Tier.BOTTLE,
        mc.perturb_bottle,
        functools.partial(_failing_simulate),
    )
    assert pickle.loads(pickle.dumps(args))[0] == bottle_design()


def test_sample_exception_becomes_a_failed_sample() -> None:
    def boom(design, env, seed=None, **scales):  # noqa: ANN001
        if scales:
            raise RuntimeError("integration failed")
        return SimResult(tier=Tier.AMATEUR, success=True, cost_jpy=0.0)

    run = mc.run_dispersion_detailed(
        amateur_design(),
        windy_env(),
        4,
        1,
        perturb=mc.perturb_amateur,
        simulate=boom,
        tier=Tier.AMATEUR,
        summarize=mc.summarize_landing,
    )
    assert run.result.success_rate == 0.0
    assert run.result.failure_counts == {"simulation error: RuntimeError: integration failed": 4}
    with pytest.raises(ValueError):
        mc.run_dispersion(
            amateur_design(),
            windy_env(),
            0,
            1,
            perturb=mc.perturb_amateur,
            simulate=boom,
            tier=Tier.AMATEUR,
            summarize=mc.summarize_landing,
        )


# --------------------------------------------------------------------------- per model


def test_amateur_dispersion_n100_under_10_s() -> None:
    t0 = time.perf_counter()
    res = solid.dispersion(amateur_design(), windy_env(), 100, 42)
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"amateur n=100 took {elapsed:.1f} s"
    assert res.tier is Tier.AMATEUR and res.n == 100
    assert res.landing is not None and len(res.landing.points) == 100
    assert res.landing.ellipse_95.semi_major_m > 0.0
    assert res.success_rate > 0.5  # the demo design passes nominally
    assert "apogee_m" in res.quantiles and "descent_speed_mps" in res.quantiles
    q = res.quantiles["apogee_m"]
    assert q.p05 < q.p95  # the perturbations really move the apogee
    assert solid.dispersion(amateur_design(), windy_env(), 100, 42) == res


def test_bottle_dispersion_scatters_downwind() -> None:
    res = water.dispersion(bottle_design(), windy_env(), 40, 1)
    assert res.tier is Tier.BOTTLE and res.landing is not None
    assert len(res.landing.points) == 40
    # wind from 270 deg (west) blows the parachute east
    assert res.landing.ellipse_95.center_east_m > 0.0
    assert res.orbit_insertion is None


def test_commercial_dispersion_reports_orbit_errors_about_the_nominal() -> None:
    design = commercial_design()
    env = Env(launch_latitude_deg=31.25, launch_altitude_m=20.0)
    run = mc.run_dispersion_detailed(
        design,
        env,
        40,
        3,
        perturb=mc.perturb_multistage,
        simulate=multistage.simulate,
        tier=Tier.COMMERCIAL,
        summarize=mc.summarize_orbit,
    )
    res = run.result
    assert res.landing is None and res.orbit_insertion is not None
    orbit = res.orbit_insertion
    assert len(orbit.samples) == 40
    nominal = multistage.simulate(design, env)
    assert run.nominal.metrics == nominal.metrics
    errors = sorted(s.perigee_m - nominal.metrics["perigee_m"] for s in orbit.samples)
    assert orbit.perigee_error_m.p50 == pytest.approx(float(np.percentile(errors, 50)))
    assert orbit.perigee_error_m.p05 < orbit.perigee_error_m.p95
    assert multistage.dispersion(design, env, 40, 3) == res
    with pytest.raises(ValueError):
        multistage.dispersion(amateur_design(), env, 4, 1)
    with pytest.raises(ValueError):
        solid.dispersion(bottle_design(), env, 4, 1)
    with pytest.raises(ValueError):
        water.dispersion(design, env, 4, 1)
