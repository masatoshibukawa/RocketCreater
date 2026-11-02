"""US Standard Atmosphere 1976 up to 86 km, exponential extrapolation above.

Reference: NASA-TM-X-74335, "U.S. Standard Atmosphere, 1976",
https://ntrs.nasa.gov/citations/19770009539

The seven-layer model below 86 km is evaluated in geopotential height with the standard
constants of the document. Above 86 km the atmosphere is extrapolated as an isothermal
exponential whose scale height is the hydrostatic scale height at the 86 km boundary, so
pressure, density and temperature are continuous there.

All functions accept a scalar `float` (returning `float`) or a numpy array (returning an array
of the same shape).
"""

from __future__ import annotations

import math
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "G0_MPS2",
    "R_SPECIFIC_AIR_JPKGK",
    "GAMMA_AIR",
    "SEA_LEVEL_PRESSURE_PA",
    "SEA_LEVEL_TEMPERATURE_K",
    "SEA_LEVEL_DENSITY_KGPM3",
    "temperature_k",
    "pressure_pa",
    "density_kgpm3",
    "speed_of_sound_mps",
    "state_scalar",
]

# Constants of the USSA76 document (section 1.2 / table 2).
G0_MPS2 = 9.80665
R_STAR_JPMOLK = 8.31432  # universal gas constant used by the document
M0_KGPMOL = 0.0289644  # mean molar mass of air at sea level
R_SPECIFIC_AIR_JPKGK = R_STAR_JPMOLK / M0_KGPMOL  # 287.053 J/(kg K)
GAMMA_AIR = 1.4
EARTH_RADIUS_GEOPOTENTIAL_M = 6_356_766.0  # r0 of the document (geopotential conversion)
SEA_LEVEL_PRESSURE_PA = 101_325.0
SEA_LEVEL_TEMPERATURE_K = 288.15
SEA_LEVEL_DENSITY_KGPM3 = SEA_LEVEL_PRESSURE_PA / (R_SPECIFIC_AIR_JPKGK * SEA_LEVEL_TEMPERATURE_K)

# Layer bases in geopotential height (m), base temperature (K) and lapse rate (K/m).
# Table 4 of the document. The last base (84 852 m geopotential = 86 km geometric) closes the
# seventh layer.
_LAYER_BASE_H_M = np.array([0.0, 11_000.0, 20_000.0, 32_000.0, 47_000.0, 51_000.0, 71_000.0])
_LAYER_LAPSE_KPM = np.array([-6.5e-3, 0.0, 1.0e-3, 2.8e-3, 0.0, -2.8e-3, -2.0e-3])
_LAYER_BASE_T_K = np.array([288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65])
TOP_GEOMETRIC_ALTITUDE_M = 86_000.0


def _geopotential_m(z_m: NDArray[np.float64]) -> NDArray[np.float64]:
    """Geometric altitude -> geopotential height (document eq. 18)."""
    return EARTH_RADIUS_GEOPOTENTIAL_M * z_m / (EARTH_RADIUS_GEOPOTENTIAL_M + z_m)


def _layer_base_pressures() -> NDArray[np.float64]:
    """Pressure at each layer base, integrated from sea level so the layers chain exactly."""
    p = np.empty(len(_LAYER_BASE_H_M))
    p[0] = SEA_LEVEL_PRESSURE_PA
    for i in range(1, len(p)):
        dh = _LAYER_BASE_H_M[i] - _LAYER_BASE_H_M[i - 1]
        lapse = _LAYER_LAPSE_KPM[i - 1]
        t_base = _LAYER_BASE_T_K[i - 1]
        if lapse == 0.0:
            p[i] = p[i - 1] * np.exp(-G0_MPS2 * dh / (R_SPECIFIC_AIR_JPKGK * t_base))
        else:
            p[i] = p[i - 1] * (t_base / (t_base + lapse * dh)) ** (
                G0_MPS2 / (R_SPECIFIC_AIR_JPKGK * lapse)
            )
    return p


_LAYER_BASE_P_PA = _layer_base_pressures()


def _lower_atmosphere(h_m: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Temperature and pressure for geopotential heights within the seven layers."""
    idx = np.clip(np.searchsorted(_LAYER_BASE_H_M, h_m, side="right") - 1, 0, 6)
    dh = h_m - _LAYER_BASE_H_M[idx]
    lapse = _LAYER_LAPSE_KPM[idx]
    t_base = _LAYER_BASE_T_K[idx]
    p_base = _LAYER_BASE_P_PA[idx]
    t = t_base + lapse * dh
    isothermal = lapse == 0.0
    safe_lapse = np.where(isothermal, 1.0, lapse)
    p_grad = p_base * (t_base / np.where(isothermal, 1.0, t)) ** (
        G0_MPS2 / (R_SPECIFIC_AIR_JPKGK * safe_lapse)
    )
    p_iso = p_base * np.exp(-G0_MPS2 * dh / (R_SPECIFIC_AIR_JPKGK * t_base))
    return t, np.where(isothermal, p_iso, p_grad)


# Boundary state at 86 km geometric, computed from the layer model so the splice is continuous.
_T86_K, _P86_PA = (
    float(v[0]) for v in _lower_atmosphere(_geopotential_m(np.array([TOP_GEOMETRIC_ALTITUDE_M])))
)
_G86_MPS2 = (
    G0_MPS2
    * (EARTH_RADIUS_GEOPOTENTIAL_M / (EARTH_RADIUS_GEOPOTENTIAL_M + TOP_GEOMETRIC_ALTITUDE_M)) ** 2
)
# SIMPLIFICATION: above 86 km the real USSA76 temperature rises to ~1000 K in the thermosphere.
# We instead hold T = T(86 km) and use the local hydrostatic scale height (~5.6 km), which keeps
# pressure/density continuous at the boundary and matches the table within ~10 % at 100 km but
# underestimates density above ~120 km (irrelevant for drag at those altitudes).
_SCALE_HEIGHT_ABOVE_86KM_M = R_SPECIFIC_AIR_JPKGK * _T86_K / _G86_MPS2

_F = TypeVar("_F", float, NDArray[np.float64])


def _t_and_p(altitude_m: _F) -> tuple[NDArray[np.float64], NDArray[np.float64], bool]:
    z = np.asarray(altitude_m, dtype=np.float64)
    scalar = z.ndim == 0
    z = np.atleast_1d(z)
    z_clipped = np.minimum(z, TOP_GEOMETRIC_ALTITUDE_M)
    t, p = _lower_atmosphere(_geopotential_m(z_clipped))
    above = z > TOP_GEOMETRIC_ALTITUDE_M
    if np.any(above):
        dz = z[above] - TOP_GEOMETRIC_ALTITUDE_M
        t = t.copy()
        p = p.copy()
        t[above] = _T86_K
        p[above] = _P86_PA * np.exp(-dz / _SCALE_HEIGHT_ABOVE_86KM_M)
    return t, p, scalar


def _ret(v: NDArray[np.float64], scalar: bool) -> float | NDArray[np.float64]:
    return float(v[0]) if scalar else v


def temperature_k(altitude_m: _F) -> _F:
    """Kinetic temperature (K) at geometric altitude `altitude_m`."""
    t, _, scalar = _t_and_p(altitude_m)
    return _ret(t, scalar)  # type: ignore[return-value]


def pressure_pa(altitude_m: _F) -> _F:
    """Static pressure (Pa) at geometric altitude `altitude_m`."""
    _, p, scalar = _t_and_p(altitude_m)
    return _ret(p, scalar)  # type: ignore[return-value]


def density_kgpm3(altitude_m: _F) -> _F:
    """Air density (kg/m^3) from the ideal gas law with the sea-level molar mass.

    SIMPLIFICATION: the molar mass is held at its sea-level value; USSA76 lets it drop
    slightly above 80 km, so density there is overestimated by < 1 %.
    """
    t, p, scalar = _t_and_p(altitude_m)
    return _ret(p / (R_SPECIFIC_AIR_JPKGK * t), scalar)  # type: ignore[return-value]


def speed_of_sound_mps(altitude_m: _F) -> _F:
    """Speed of sound (m/s), sqrt(gamma R T) with gamma = 1.4."""
    t, _, scalar = _t_and_p(altitude_m)
    return _ret(np.sqrt(GAMMA_AIR * R_SPECIFIC_AIR_JPKGK * t), scalar)  # type: ignore[return-value]


# Pure-Python copies of the tables for the scalar fast path (no numpy per-call overhead).
_BASES_H = [float(v) for v in _LAYER_BASE_H_M]
_BASES_T = [float(v) for v in _LAYER_BASE_T_K]
_BASES_P = [float(v) for v in _LAYER_BASE_P_PA]
_LAPSES = [float(v) for v in _LAYER_LAPSE_KPM]


def state_scalar(
    altitude_m: float, temperature_offset_k: float = 0.0
) -> tuple[float, float, float]:
    """Fast scalar (temperature_k, pressure_pa, density_kgpm3) for ODE right-hand sides.

    Same model as the array functions. `temperature_offset_k` shifts the temperature at
    constant pressure (Env.temperature_offset_k), which scales density by T / (T + offset).
    SIMPLIFICATION: the offset does not re-integrate the hydrostatic pressure profile.
    """
    z = float(altitude_m)
    if z >= TOP_GEOMETRIC_ALTITUDE_M:
        t = _T86_K
        p = _P86_PA * math.exp(-(z - TOP_GEOMETRIC_ALTITUDE_M) / _SCALE_HEIGHT_ABOVE_86KM_M)
    else:
        z = max(z, 0.0)
        h = EARTH_RADIUS_GEOPOTENTIAL_M * z / (EARTH_RADIUS_GEOPOTENTIAL_M + z)
        i = 6
        while i > 0 and h < _BASES_H[i]:
            i -= 1
        dh = h - _BASES_H[i]
        lapse = _LAPSES[i]
        t_base = _BASES_T[i]
        t = t_base + lapse * dh
        if lapse == 0.0:
            p = _BASES_P[i] * math.exp(-G0_MPS2 * dh / (R_SPECIFIC_AIR_JPKGK * t_base))
        else:
            p = _BASES_P[i] * (t_base / t) ** (G0_MPS2 / (R_SPECIFIC_AIR_JPKGK * lapse))
    t_eff = max(t + temperature_offset_k, 1.0)
    return t_eff, p, p / (R_SPECIFIC_AIR_JPKGK * t_eff)
