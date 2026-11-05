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


def test_heat_equilibrium_and_sealed_pressure(design):
    from rocketwright.physics.bottle_integrity.thermal import wait

    cfg = AnalysisConfig(solar_w_m2=0)
    equilibrium = wait(design, cfg, ambient_c=25, initial_c=25, sealed=True)
    assert list(equilibrium["final_c"].values()) == pytest.approx([25] * 5)
    heated = wait(design, AnalysisConfig(), sealed=True)
    assert heated["energy_balance_relative"] < 1e-8
    assert (
        heated["peak_absolute_pressure_pa"]
        > cfg.loads.ambient_pa + design.initial_gauge_pressure_pa
    )


def test_quaternion_and_lyapunov_conventions():
    from rocketwright.physics.bottle_integrity.flight import qrate, rotation
    from rocketwright.physics.bottle_integrity.stability import lyapunov_matrix

    q = np.array([np.cos(0.3), 0, np.sin(0.3), 0])
    assert rotation(q)[:, 2] == pytest.approx([np.sin(0.6), 0, np.cos(0.6)])
    assert np.dot(q, qrate(q, [1, 2, 3])) == pytest.approx(0, abs=1e-12)
    assert rotation(q).T @ rotation(q) == pytest.approx(np.eye(3), abs=1e-12)
    stable = lyapunov_matrix([[0, 1], [-4, -0.8]])
    assert stable["min_P_eigenvalue"] > 0 and stable["residual"] < 1e-12
    assert not lyapunov_matrix([[0, 1], [4, -0.8]])["hurwitz"]


def test_evidence_rejects_synthetic_and_path_escape(tmp_path):
    from rocketwright.physics.bottle_integrity.evidence import audit, fit_curve

    record = dict(
        id="example",
        article="sample",
        component="material",
        method="tension",
        source_file="../outside.csv",
        source_sha256="0" * 64,
        measured=False,
        temperature_c=20,
        specimen_count=1,
        orientation="XY",
        manufacturing="example",
        reviewed_by=None,
        applicable_min=0,
        applicable_max=1,
    )
    result = audit([record], tmp_path)
    assert not result["records"] and "material" in result["missing"]
    assert "source_outside_evidence_directory" in result["rejected"][0]["reasons"]
    fitted = fit_curve([0, 1, 2, 3], [0, 10, 20, 30], holdout=[[0.5, 5], [1.5, 15]])
    assert fitted["holdout_rmse"] < 1e-10 and not fitted["validated"]


def test_invalid_anisotropy_and_missing_solver_are_not_passes(tmp_path):
    from rocketwright.physics.bottle_integrity.fem import run_deck
    from rocketwright.physics.bottle_integrity.schema import Material

    with pytest.raises(ValueError):
        Material(engineering_constants=(2e9, 2e9, 2e9, 0.99, 0.99, 0.99, 1e9, 1e9, 1e9))
    with pytest.raises(FileNotFoundError):
        run_deck(tmp_path / "absent.exe", tmp_path / "run", "missing", [])


def make_harness(tmp_path):
    from rocketwright.bottle_assembly import Workshop
    from rocketwright.bottle_search import Action, Search

    search = Search("references", Workshop())
    action = Action("component", "D02", 9, 400, 25, "carton_wide")
    return search.integrity(action, tmp_path / "integrity")


def test_harness_rejects_unavailable_methods_and_propagates_failure(tmp_path):
    h = make_harness(tmp_path)
    assert list(h.options()) == ["evidence"]
    with pytest.raises(ValueError):
        h.step("flight", "Skip the missing dependencies")
    h.step("evidence", "Audit actual records before analysis")
    assert list(h.options()) == ["thermal"]

    def fail():
        raise RuntimeError("Deliberate unavailable input")

    h._thermal = fail
    h.step("thermal", "Evaluate temperatures")
    assert h.results["flight"]["execution_status"] == "blocked"
    assert not h.results["verdict"]["qualified"]
    assert not h.options()


def test_axially_symmetric_flight_preserves_zero_rotation(tmp_path):
    from rocketwright.physics.bottle_integrity.flight import run

    h = make_harness(tmp_path)
    cfg = h.config.flight.model_copy(
        update={"wind_mps": 0, "gust_mps": 0, "initial_tilt_deg": 0, "cant_deg": 0}
    )
    result = run(h.design, h.assembly, propulsion(h.design, h.config.loads), cfg)
    assert result["completed"]
    assert np.max(abs(np.array(result["trace"]["omega_rad_s"]))) < 1e-12
    assert np.max(abs(np.array(result["trace"]["position_m"])[:, :2])) < 1e-12
