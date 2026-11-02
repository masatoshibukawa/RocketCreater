"""Parachute descent and wind drift shared by the bottle and amateur tiers (CLAUDE.md section 7).

Every approximation is marked with `# SIMPLIFICATION:`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rocketwright.physics import atmosphere as atm
from rocketwright.schema import Env, TracePoint

__all__ = ["DEFAULT_PARACHUTE_CD", "DescentResult", "descend", "descent_trace", "wind_vector_mps"]

G0_MPS2 = 9.80665
# SIMPLIFICATION: flat-sheet / hemispherical hobby parachute; a cross-type chute is ~0.8.
DEFAULT_PARACHUTE_CD = 1.5


@dataclass(frozen=True)
class DescentResult:
    descent_speed_mps: float
    landing_east_m: float
    landing_north_m: float
    descent_time_s: float


def wind_vector_mps(env: Env) -> tuple[float, float]:
    """(east, north) velocity of the air. `wind_direction_deg` is where the wind blows FROM
    (meteorological convention, 0 = north, 90 = east), so the air moves the opposite way."""
    theta = math.radians(env.wind_direction_deg)
    return -env.wind_speed_mps * math.sin(theta), -env.wind_speed_mps * math.cos(theta)


def descend(
    mass_kg: float,
    parachute_diameter_m: float,
    env: Env,
    start_altitude_m: float,
    start_east_m: float = 0.0,
    start_north_m: float = 0.0,
    cd: float = DEFAULT_PARACHUTE_CD,
) -> DescentResult:
    """Steady parachute descent from `start_altitude_m` (above the pad) to the ground.

    SIMPLIFICATION: the descent is at the terminal speed computed with the air density at the
    mid-point of the descent (pad altitude + half the start altitude); opening transients and
    the density change along the way are ignored. The rocket drifts with the full wind vector
    for the whole descent (wind constant with altitude, as in the flight models).
    """
    if mass_kg <= 0.0:
        raise ValueError("mass_kg must be positive")
    if parachute_diameter_m <= 0.0:
        raise ValueError("parachute_diameter_m must be positive")
    if start_altitude_m < 0.0:
        raise ValueError("start_altitude_m must be >= 0")
    if cd <= 0.0:
        raise ValueError("cd must be positive")
    area_m2 = math.pi * (parachute_diameter_m / 2.0) ** 2
    rho = float(atm.density_kgpm3(env.launch_altitude_m + start_altitude_m / 2.0))
    speed = math.sqrt(2.0 * mass_kg * G0_MPS2 / (rho * cd * area_m2))
    time_s = start_altitude_m / speed
    wind_east, wind_north = wind_vector_mps(env)
    return DescentResult(
        descent_speed_mps=speed,
        landing_east_m=start_east_m + wind_east * time_s,
        landing_north_m=start_north_m + wind_north * time_s,
        descent_time_s=time_s,
    )


def descent_trace(
    descent: DescentResult,
    *,
    start_time_s: float,
    start_altitude_m: float,
    start_east_m: float,
    start_north_m: float,
    mass_kg: float,
    n_points: int = 40,
) -> list[TracePoint]:
    """Straight-line trace samples for the steady descent (excluding the start point)."""
    points: list[TracePoint] = []
    if descent.descent_time_s <= 0.0:
        return points
    for k in range(1, n_points + 1):
        frac = k / n_points
        east = start_east_m + (descent.landing_east_m - start_east_m) * frac
        north = start_north_m + (descent.landing_north_m - start_north_m) * frac
        points.append(
            TracePoint(
                t_s=start_time_s + descent.descent_time_s * frac,
                altitude_m=start_altitude_m * (1.0 - frac),
                downrange_m=math.hypot(east, north),
                east_m=east,
                north_m=north,
                speed_mps=descent.descent_speed_mps,
                mass_kg=mass_kg,
            )
        )
    return points
