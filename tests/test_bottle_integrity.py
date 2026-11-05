import numpy as np
import pytest

from rocketwright.physics.bottle_integrity.contact import contact_force, response
from rocketwright.physics.bottle_integrity.loads import gas_nozzle, propulsion
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.schema import BottleDesign


@pytest.fixture
def design():
    return BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.25,
        initial_gauge_pressure_pa=400000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.1527873,
        payload_mass_kg=0.06,
        has_parachute=True,
        parachute_diameter_m=0.595071,
    )


def test_nozzle_is_continuous_at_choking_and_stops_at_ambient():
    cfg = AnalysisConfig().loads
    critical = (2 / (cfg.gamma + 1)) ** (cfg.gamma / (cfg.gamma - 1))
    p = cfg.ambient_pa / critical
    a = gas_nozzle(p * (1 - 1e-7), 293.15, 1e-4, cfg)
    b = gas_nozzle(p * (1 + 1e-7), 293.15, 1e-4, cfg)
    assert np.allclose(a[:2], b[:2], rtol=1e-5)
    assert gas_nozzle(cfg.ambient_pa, 293.15, 1e-4, cfg)[0] == 0


def test_adiabatic_liquid_phase_and_closed_energy_balance(design):
    cfg = AnalysisConfig().loads.model_copy(update={"gas_wall_h": 0.0, "outside_h": 0.0})
    r = propulsion(design, cfg)
    assert r["completed"] and r["air_duration_s"] > 0
    liquid = r["liquid_end"]
    ratio = 1 - design.water_fill_frac
    assert liquid["temperature_k"] == pytest.approx(
        cfg.initial_k * ratio ** (cfg.gamma - 1), rel=2e-5
    )
    assert liquid["pressure_pa"] == pytest.approx(
        (cfg.ambient_pa + design.initial_gauge_pressure_pa) * ratio**cfg.gamma, rel=2e-5
    )
    assert r["energy_balance_relative"] < 1e-6
    assert r["mass_balance_relative"] < 1e-6


def test_contact_never_pulls_and_dissipates():
    p = AnalysisConfig().contact
    for x in [-0.012, -0.008, 0, 0.008, 0.012]:
        for v in [-10.0, 0.0, 10.0]:
            f, elastic, dissipated = contact_force(x, v, p)
            assert f * x >= 0 and dissipated >= -1e-12
            if abs(x) <= p.gap_m:
                assert f == elastic == dissipated == 0


def test_nonlinear_contact_accounts_for_work_and_limits_penetration():
    p = AnalysisConfig().contact
    t = np.linspace(0, 0.3, 1501)
    acceleration = np.where(t < 0.02, 200 * np.sin(np.pi * t / 0.02), 0)
    r = response(t, acceleration, 0.06, p, initial_proper=0)
    assert r["contact_occurred"]
    assert 0 < r["peak_penetration_mm"] < 8
    assert r["work_balance_relative"] < 5e-4
    assert r["peak_contact_force_n"] > 0
