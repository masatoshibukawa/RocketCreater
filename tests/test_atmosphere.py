"""Checkpoint tests for the US Standard Atmosphere 1976 implementation.

Reference values (table rows at geometric altitude) are taken from
NASA-TM-X-74335 "U.S. Standard Atmosphere, 1976":
https://ntrs.nasa.gov/citations/19770009539
"""

import numpy as np
import pytest

from rocketwright.physics import atmosphere as atm

# (geopotential_height_m, temperature_k, pressure_pa, density_kgpm3)
# Layer-base values from table 4 / the main tables of the USSA76 document. The document tabulates
# the layer bases (11 km, 20 km, 47 km, ...) in GEOPOTENTIAL height; the functions under test take
# geometric altitude, so the test converts with z = r0 * H / (r0 - H), r0 = 6 356 766 m (eq. 18).
# 84 852 m geopotential is the 86 km geometric top of the layer model (molecular-scale T 186.946 K).
CHECKPOINTS = [
    (0.0, 288.15, 101325.0, 1.225),
    (11_000.0, 216.65, 22632.0, 0.3639),
    (20_000.0, 216.65, 5474.9, 0.08803),
    (47_000.0, 270.65, 110.91, 0.001428),
    (84_852.0, 186.946, 0.3734, 6.958e-6),
]
R0_M = 6_356_766.0


def geometric_m(h_geopotential_m: float) -> float:
    return R0_M * h_geopotential_m / (R0_M - h_geopotential_m)


@pytest.mark.parametrize(("h_m", "t_k", "p_pa", "rho"), CHECKPOINTS)
def test_ussa76_checkpoints(h_m: float, t_k: float, p_pa: float, rho: float) -> None:
    z_m = geometric_m(h_m)
    assert atm.temperature_k(z_m) == pytest.approx(t_k, abs=0.5)
    assert atm.pressure_pa(z_m) == pytest.approx(p_pa, rel=5e-3)
    assert atm.density_kgpm3(z_m) == pytest.approx(rho, rel=5e-3)


def test_pressure_monotonically_decreases() -> None:
    z = np.linspace(0.0, 300_000.0, 3001)
    p = atm.pressure_pa(z)
    assert np.all(np.diff(p) < 0.0)
    assert np.all(p > 0.0)


def test_density_monotonically_decreases() -> None:
    z = np.linspace(0.0, 300_000.0, 3001)
    rho = atm.density_kgpm3(z)
    assert np.all(np.diff(rho) < 0.0)


def test_continuity_at_86km_boundary() -> None:
    below, above = 86_000.0 - 1e-3, 86_000.0 + 1e-3
    assert atm.pressure_pa(below) == pytest.approx(atm.pressure_pa(above), rel=1e-4)
    assert atm.density_kgpm3(below) == pytest.approx(atm.density_kgpm3(above), rel=1e-4)
    assert atm.temperature_k(below) == pytest.approx(atm.temperature_k(above), abs=0.1)


def test_speed_of_sound_at_sea_level() -> None:
    assert atm.speed_of_sound_mps(0.0) == pytest.approx(340.3, abs=0.2)


def test_scalar_and_array_inputs_agree() -> None:
    z = np.array([0.0, 5_000.0, 50_000.0, 120_000.0])
    vec = atm.density_kgpm3(z)
    assert vec.shape == z.shape
    for zi, vi in zip(z, vec, strict=True):
        assert atm.density_kgpm3(float(zi)) == pytest.approx(vi)
    assert isinstance(atm.pressure_pa(1000.0), float)
