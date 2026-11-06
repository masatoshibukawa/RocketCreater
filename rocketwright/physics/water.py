"""Water-rocket model for the bottle tier (CLAUDE.md section 7, "water").

A PET bottle partly filled with water and pressurised with air. The air expands adiabatically
(gamma = 1.4) and pushes the water out of the nozzle; the water jet thrust is the Bernoulli
value `F = 2 (p - p_atm) A_nozzle` with mass flow `rho A sqrt(2 (p - p_atm) / rho)`. When the
water is gone the remaining compressed air is treated as one small impulse, then the empty
bottle flies a drag ballistic arc (x east, y north, z up, metres above the pad) with a constant
wind, and either descends on a parachute (rocketwright.physics.recovery) or falls to the
ground. Every approximation is marked with `# SIMPLIFICATION:`.

Public entry points:

* `simulate(design, env, seed=None, *, target_apogee_m=None)` -- the common physics interface.
* `run_flight(design, env)` -- the raw trajectory and flight events.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from rocketwright import dispersion as mc
from rocketwright.physics import atmosphere as atm
from rocketwright.physics import recovery
from rocketwright.schema import (
    MAX_TRACE_POINTS,
    BottleDesign,
    Design,
    DispersionResult,
    Env,
    SimResult,
    Tier,
    TracePoint,
    decimate_trace,
)

__all__ = [
    "AIR_IMPULSE_EFFICIENCY",
    "DEFAULT_CD",
    "GAMMA_AIR",
    "PASS_THRESHOLDS",
    "TUMBLING_DRAG_FACTOR",
    "WATER_DENSITY_KGPM3",
    "Flight",
    "bottle_diameter_m",
    "dispersion",
    "run_flight",
    "simulate",
]

# --------------------------------------------------------------------------- constants

G0_MPS2 = 9.80665
GAMMA_AIR = atm.GAMMA_AIR
R_AIR_JPKGK = atm.R_SPECIFIC_AIR_JPKGK
WATER_DENSITY_KGPM3 = 1000.0
# SIMPLIFICATION: one constant drag coefficient on the bottle cross-section for a finned bottle
# rocket flying nose first (provisional; blunt bottles are often quoted at 0.3-0.5).
DEFAULT_CD = 0.5
# SIMPLIFICATION: a bottle without fins tumbles; modelled as a doubled drag coefficient.
TUMBLING_DRAG_FACTOR = 2.0
# SIMPLIFICATION: the air-blowdown phase is one instantaneous impulse equal to this fraction
# of sqrt(2 m_air W_isentropic), i.e. of the impulse a uniform jet carrying the whole isentropic
# expansion work would give (provisional efficiency).
AIR_IMPULSE_EFFICIENCY = 0.5
# SIMPLIFICATION: the bottle diameter is estimated from the volume (a 1.5 L PET bottle is about
# 90 mm across); provisional.
_DIAMETER_1P5L_M = 0.09

# Single place for the pass/fail rules (CLAUDE.md section 6).
PASS_THRESHOLDS: dict[str, float] = {
    "apogee_tolerance_frac": 0.10,  # |apogee - target| <= target * tol when a target is given
    "max_descent_speed_with_payload_mps": 6.0,  # an egg must land gently
    "max_descent_speed_mps": 10.0,  # empty bottle
    "max_gauge_pressure_pa": 1_000_000.0,  # PET bottle safety cap (provisional)
}

_MAX_STEP_THRUST_S = 0.001
_MAX_STEP_COAST_S = 0.1
_RTOL = 1e-6
_ATOL = 1e-6
_MAX_FLIGHT_S = 300.0
_TRACE_DESCENT_POINTS = 40


def bottle_diameter_m(volume_m3: float) -> float:
    return _DIAMETER_1P5L_M * (volume_m3 / 1.5e-3) ** (1.0 / 3.0)


# --------------------------------------------------------------------------- flight


@dataclass(frozen=True)
class Flight:
    """Raw trajectory from launch to apogee (parachute) or impact (no parachute)."""

    t_s: NDArray[np.float64]
    x_m: NDArray[np.float64]
    y_m: NDArray[np.float64]
    z_m: NDArray[np.float64]
    vx_mps: NDArray[np.float64]
    vy_mps: NDArray[np.float64]
    vz_mps: NDArray[np.float64]
    mass_kg: NDArray[np.float64]
    thrust_n: NDArray[np.float64]
    accel_mps2: NDArray[np.float64]  # proper acceleration |thrust - drag| / m
    liftoff_mass_kg: float
    water_mass_kg: float
    peak_thrust_n: float
    left_rail: bool
    rail_exit_time_s: float
    rail_exit_speed_mps: float
    thrust_end_time_s: float
    water_exhausted_speed_mps: float
    water_impulse_ns: float
    air_impulse_ns: float
    apogee_time_s: float
    apogee_m: float
    apogee_east_m: float
    apogee_north_m: float
    impacted: bool
    impact_speed_mps: float


class _Dynamics:
    """ODE right-hand side; state = [x, y, z, vx, vy, vz, m_water]."""

    def __init__(self, design: BottleDesign, env: Env) -> None:
        self.p_atm = atm.state_scalar(env.launch_altitude_m, env.temperature_offset_k)[1]
        self.nozzle_area_m2 = math.pi * (design.nozzle_diameter_m / 2.0) ** 2
        self.area_m2 = math.pi * (bottle_diameter_m(design.bottle_volume_m3) / 2.0) ** 2
        self.cd = DEFAULT_CD * (1.0 if design.has_fins else TUMBLING_DRAG_FACTOR)
        self.volume_m3 = design.bottle_volume_m3
        self.air_volume0_m3 = design.bottle_volume_m3 * (1.0 - design.water_fill_frac)
        self.p0 = self.p_atm + design.initial_gauge_pressure_pa
        self.dry_mass_kg = design.dry_mass_kg + design.payload_mass_kg
        self.wind_e, self.wind_n = recovery.wind_vector_mps(env)
        self.pad_altitude_m = env.launch_altitude_m
        self.temperature_offset_k = env.temperature_offset_k
        self.on_rail = True
        self.water_on = True

    def pressure_pa(self, m_water: float) -> float:
        """Adiabatic air pressure for the water mass still in the bottle."""
        air_volume = self.volume_m3 - max(m_water, 0.0) / WATER_DENSITY_KGPM3
        return self.p0 * (self.air_volume0_m3 / air_volume) ** GAMMA_AIR

    def thrust(self, m_water: float) -> tuple[float, float]:
        """(thrust_n, water mass flow kg/s) from the Bernoulli jet."""
        if not self.water_on or m_water <= 0.0:
            return 0.0, 0.0
        dp = self.pressure_pa(m_water) - self.p_atm
        if dp <= 0.0:
            return 0.0, 0.0
        u = math.sqrt(2.0 * dp / WATER_DENSITY_KGPM3)
        return 2.0 * dp * self.nozzle_area_m2, WATER_DENSITY_KGPM3 * self.nozzle_area_m2 * u

    def forces(self, s: NDArray[np.float64]) -> tuple[float, float, float, float]:
        """(thrust_n, drag_n, air-relative speed, proper acceleration) at the state."""
        thrust, _ = self.thrust(float(s[6]))
        if self.on_rail:
            # SIMPLIFICATION: on the rail only the along-rail (vertical) air speed counts.
            va = abs(float(s[5]))
        else:
            va = math.sqrt(
                (float(s[3]) - self.wind_e) ** 2
                + (float(s[4]) - self.wind_n) ** 2
                + float(s[5]) ** 2
            )
        rho = atm.state_scalar(self.pad_altitude_m + float(s[2]), self.temperature_offset_k)[2]
        drag = 0.5 * rho * va * va * self.cd * self.area_m2
        mass = self.dry_mass_kg + max(float(s[6]), 0.0)
        return thrust, drag, va, abs(thrust - drag) / mass

    def __call__(self, _t: float, s: NDArray[np.float64]) -> list[float]:
        m_water = float(s[6])
        mass = self.dry_mass_kg + max(m_water, 0.0)
        thrust, mdot = self.thrust(m_water)
        _, drag, va, _ = self.forces(s)
        if self.on_rail:
            # SIMPLIFICATION: the launcher is vertical (Env has no launch-angle field); the
            # rocket is held on the pad until the thrust exceeds the weight.
            vz = float(s[5])
            az = (thrust - math.copysign(drag, vz)) / mass - G0_MPS2
            if vz <= 0.0 and az < 0.0:
                az = 0.0
            return [0.0, 0.0, max(vz, 0.0), 0.0, 0.0, az, -mdot]
        # SIMPLIFICATION: zero angle of attack -- the body axis follows the air-relative
        # velocity (instant weathercock into the wind at rail exit); thrust and drag collinear.
        vax, vay, vaz = float(s[3]) - self.wind_e, float(s[4]) - self.wind_n, float(s[5])
        if va > 1e-9:
            ux, uy, uz = vax / va, vay / va, vaz / va
        else:
            ux, uy, uz = 0.0, 0.0, 1.0
        f_axis = (thrust - drag) / mass
        return [
            float(s[3]),
            float(s[4]),
            float(s[5]),
            f_axis * ux,
            f_axis * uy,
            f_axis * uz - G0_MPS2,
            -mdot,
        ]

    def body_axis(self, s: NDArray[np.float64]) -> tuple[float, float, float]:
        if self.on_rail:
            return 0.0, 0.0, 1.0
        vax, vay, vaz = float(s[3]) - self.wind_e, float(s[4]) - self.wind_n, float(s[5])
        va = math.sqrt(vax * vax + vay * vay + vaz * vaz)
        return (vax / va, vay / va, vaz / va) if va > 1e-9 else (0.0, 0.0, 1.0)

    def air_impulse_ns(self, env: Env) -> float:
        """Impulse of the residual-air blowdown once the water is gone (see module notes)."""
        p_end = self.p0 * (self.air_volume0_m3 / self.volume_m3) ** GAMMA_AIR
        if p_end <= self.p_atm:
            return 0.0
        # SIMPLIFICATION: the air is at ambient temperature before launch.
        t0_k = atm.state_scalar(env.launch_altitude_m, env.temperature_offset_k)[0]
        m_air = self.p0 * self.air_volume0_m3 / (R_AIR_JPKGK * t0_k)
        work_j = (
            p_end
            * self.volume_m3
            / (GAMMA_AIR - 1.0)
            * (1.0 - (self.p_atm / p_end) ** ((GAMMA_AIR - 1.0) / GAMMA_AIR))
        )
        return AIR_IMPULSE_EFFICIENCY * math.sqrt(2.0 * m_air * work_j)


def _event(fn: Callable[..., float], *, terminal: bool, direction: int) -> Callable[..., float]:
    fn.terminal = terminal  # type: ignore[attr-defined]
    fn.direction = direction  # type: ignore[attr-defined]
    return fn


def _check_design(design: Design) -> BottleDesign:
    if not isinstance(design, BottleDesign):
        raise ValueError(f"water.simulate requires a design with tier bottle, got {design.tier!r}")
    return design


def run_flight(design: BottleDesign, env: Env) -> Flight:
    """Integrate launch -> rail exit -> water exhausted (+ air impulse) -> apogee, and on to
    the ground when there is no parachute."""
    dyn = _Dynamics(design, env)
    water_mass = design.bottle_volume_m3 * design.water_fill_frac * WATER_DENSITY_KGPM3
    m0 = dyn.dry_mass_kg + water_mass
    state = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, water_mass])
    ts: list[NDArray[np.float64]] = [np.array([0.0])]
    ys: list[NDArray[np.float64]] = [state.reshape(7, 1).copy()]
    t = 0.0

    def integrate(events: list[Callable[..., float]], max_step: float) -> Any:
        nonlocal t, state
        sol = solve_ivp(
            dyn,
            (t, t + _MAX_FLIGHT_S),
            state,
            method="RK45",
            events=events,
            max_step=max_step,
            rtol=_RTOL,
            atol=_ATOL,
        )
        if not sol.success:
            raise RuntimeError(f"water integration failed: {sol.message}")
        ts.append(sol.t[1:])
        ys.append(sol.y[:, 1:])
        t = float(sol.t[-1])
        state = sol.y[:, -1].copy()
        return sol

    rail_exit = _event(lambda _t, s: s[2] - env.rail_length_m, terminal=True, direction=1)
    water_out = _event(lambda _t, s: s[6], terminal=True, direction=-1)
    pressure_out = _event(
        lambda _t, s: dyn.pressure_pa(float(s[6])) - dyn.p_atm, terminal=True, direction=-1
    )
    apogee = _event(lambda _t, s: s[5], terminal=True, direction=-1)
    impact = _event(lambda _t, s: s[2], terminal=True, direction=-1)

    peak_thrust = 2.0 * design.initial_gauge_pressure_pa * dyn.nozzle_area_m2
    left_rail = False
    rail_exit_time = rail_exit_speed = 0.0
    thrust_end_time = 0.0
    water_exhausted_speed = 0.0
    air_impulse = 0.0
    apogee_time = 0.0
    impacted = False
    reached_apogee = False
    if peak_thrust > m0 * G0_MPS2:
        for _ in range(8):  # at most: rail exit, water out, apogee, impact (+ margin)
            events: list[Callable[..., float]] = [impact, apogee]
            if dyn.on_rail:
                events.append(rail_exit)
            if dyn.water_on:
                events += [water_out, pressure_out]
            sol = integrate(events, _MAX_STEP_THRUST_S if dyn.water_on else _MAX_STEP_COAST_S)
            fired = {ev: bool(sol.t_events[i].size) for i, ev in enumerate(events)}
            if fired[impact]:
                impacted = True
                break
            if fired[apogee]:
                reached_apogee = True
                apogee_time = t
                break
            if dyn.on_rail and fired[rail_exit]:
                left_rail = True
                rail_exit_time, rail_exit_speed = t, float(state[5])
                dyn.on_rail = False
            if dyn.water_on and (fired[water_out] or fired[pressure_out]):
                thrust_end_time = t
                water_exhausted_speed = float(math.hypot(state[3], state[4], state[5]))
                if fired[water_out]:
                    state[6] = 0.0
                    # SIMPLIFICATION: residual-air blowdown applied as one impulse along the
                    # body axis (see AIR_IMPULSE_EFFICIENCY); leftover water when the pressure
                    # reaches ambient first is carried as dead mass.
                    air_impulse = dyn.air_impulse_ns(env)
                    ux, uy, uz = dyn.body_axis(state)
                    dv = air_impulse / dyn.dry_mass_kg
                    state[3] += dv * ux
                    state[4] += dv * uy
                    state[5] += dv * uz
                dyn.water_on = False
        if reached_apogee and not design.has_parachute:
            dyn.water_on = False
            sol = integrate([impact], _MAX_STEP_COAST_S)
            impacted = bool(sol.t_events[0].size)

    t_all = np.concatenate(ts)
    y_all = np.concatenate(ys, axis=1)
    i_apogee = int(np.argmax(y_all[2]))
    thrust = np.empty(len(t_all))
    accel = np.empty(len(t_all))
    dyn.water_on = True
    for i, ti in enumerate(t_all):
        dyn.on_rail = (not left_rail) or float(ti) <= rail_exit_time
        dyn.water_on = thrust_end_time == 0.0 or float(ti) <= thrust_end_time
        f, _, _, a = dyn.forces(y_all[:, i])
        thrust[i], accel[i] = f, a
    water_impulse = float(np.sum(0.5 * (thrust[1:] + thrust[:-1]) * np.diff(t_all)))
    return Flight(
        t_s=t_all,
        x_m=y_all[0],
        y_m=y_all[1],
        z_m=y_all[2],
        vx_mps=y_all[3],
        vy_mps=y_all[4],
        vz_mps=y_all[5],
        mass_kg=dyn.dry_mass_kg + np.maximum(y_all[6], 0.0),
        thrust_n=thrust,
        accel_mps2=accel,
        liftoff_mass_kg=m0,
        water_mass_kg=water_mass,
        peak_thrust_n=peak_thrust,
        left_rail=left_rail,
        rail_exit_time_s=rail_exit_time,
        rail_exit_speed_mps=rail_exit_speed,
        thrust_end_time_s=thrust_end_time,
        water_exhausted_speed_mps=water_exhausted_speed,
        water_impulse_ns=water_impulse,
        air_impulse_ns=air_impulse,
        apogee_time_s=apogee_time if reached_apogee else float(t_all[i_apogee]),
        apogee_m=float(y_all[2, i_apogee]),
        apogee_east_m=float(y_all[0, i_apogee]),
        apogee_north_m=float(y_all[1, i_apogee]),
        impacted=impacted,
        impact_speed_mps=float(math.hypot(state[3], state[4], state[5])) if impacted else 0.0,
    )


# --------------------------------------------------------------------------- results


def _build_trace(flight: Flight, descent: recovery.DescentResult | None) -> list[TracePoint]:
    points = [
        TracePoint(
            t_s=float(flight.t_s[i]),
            altitude_m=max(float(flight.z_m[i]), 0.0),
            downrange_m=float(math.hypot(flight.x_m[i], flight.y_m[i])),
            east_m=float(flight.x_m[i]),
            north_m=float(flight.y_m[i]),
            speed_mps=float(math.hypot(flight.vx_mps[i], flight.vy_mps[i], flight.vz_mps[i])),
            mass_kg=float(flight.mass_kg[i]),
            extra={"thrust_n": float(flight.thrust_n[i])},
        )
        for i in range(len(flight.t_s))
    ]
    if descent is not None:
        points += recovery.descent_trace(
            descent,
            start_time_s=flight.apogee_time_s,
            start_altitude_m=flight.apogee_m,
            start_east_m=flight.apogee_east_m,
            start_north_m=flight.apogee_north_m,
            mass_kg=float(flight.mass_kg[-1]),
            n_points=_TRACE_DESCENT_POINTS,
        )
    return decimate_trace(points, MAX_TRACE_POINTS)


def simulate(
    design: Design, env: Env, seed: int | None = None, *, target_apogee_m: float | None = None
) -> SimResult:
    """Common physics interface (CLAUDE.md section 6). `seed` is accepted for interface
    compatibility; the nominal water model is deterministic and ignores it."""
    del seed
    bd = _check_design(design)
    flight = run_flight(bd, env)
    th = PASS_THRESHOLDS
    failures: list[str] = []
    warnings: list[str] = []
    if not bd.has_fins:
        warnings.append(
            "no fins: the bottle is aerodynamically unstable and tumbles (drag doubled, "
            "provisional); add fins for a predictable flight"
        )
    if bd.initial_gauge_pressure_pa > th["max_gauge_pressure_pa"]:
        failures.append(
            f"initial gauge pressure {bd.initial_gauge_pressure_pa / 1e3:.0f} kPa above the "
            f"{th['max_gauge_pressure_pa'] / 1e3:.0f} kPa bottle safety cap (provisional)"
        )
    weight_n = flight.liftoff_mass_kg * G0_MPS2
    if flight.peak_thrust_n <= weight_n:
        failures.append(
            f"initial thrust {flight.peak_thrust_n:.1f} N <= liftoff weight {weight_n:.1f} N: "
            "more pressure, a larger nozzle or less water"
        )
    elif not flight.left_rail:
        failures.append(f"rocket did not leave the {env.rail_length_m:g} m launcher")

    descent: recovery.DescentResult | None = None
    descent_speed = flight.impact_speed_mps
    landing_e, landing_n = float(flight.x_m[-1]), float(flight.y_m[-1])
    flight_time = float(flight.t_s[-1])
    if flight.left_rail and bd.has_parachute and bd.parachute_diameter_m is not None:
        # SIMPLIFICATION: the parachute opens exactly at apogee.
        descent = recovery.descend(
            float(flight.mass_kg[-1]),
            bd.parachute_diameter_m,
            env,
            start_altitude_m=flight.apogee_m,
            start_east_m=flight.apogee_east_m,
            start_north_m=flight.apogee_north_m,
        )
        descent_speed = descent.descent_speed_mps
        landing_e, landing_n = descent.landing_east_m, descent.landing_north_m
        flight_time = flight.apogee_time_s + descent.descent_time_s
    limit = (
        th["max_descent_speed_with_payload_mps"]
        if bd.payload_mass_kg > 0.0
        else th["max_descent_speed_mps"]
    )
    descent_excess = max(0.0, descent_speed - limit)
    if flight.left_rail and descent_excess > 0:
        what = "the payload" if bd.payload_mass_kg > 0.0 else "the bottle"
        failures.append(
            f"descent speed {descent_speed:.1f} m/s above {limit:.0f} m/s for {what} "
            f"({'larger parachute' if bd.has_parachute else 'add a parachute'})"
        )
    scores: dict[str, float] = {}
    if flight.left_rail:
        scores["descent_speed_excess_mps"] = descent_excess
    if target_apogee_m is not None:
        tol = target_apogee_m * th["apogee_tolerance_frac"]
        excess = max(0.0, abs(flight.apogee_m - target_apogee_m) - tol)
        scores["apogee_band_excess_m"] = excess
        if excess > 0:
            failures.append(
                f"apogee {flight.apogee_m:.1f} m not within +/-{th['apogee_tolerance_frac']:.0%} "
                f"of target {target_apogee_m:.0f} m"
            )

    speed = np.hypot(np.hypot(flight.vx_mps, flight.vy_mps), flight.vz_mps)
    metrics: dict[str, float] = {
        "apogee_m": flight.apogee_m,
        "apogee_time_s": flight.apogee_time_s,
        "max_speed_mps": float(speed.max()),
        "max_accel_mps2": float(flight.accel_mps2.max()),
        "peak_thrust_n": flight.peak_thrust_n,
        "thrust_phase_duration_s": flight.thrust_end_time_s,
        "water_exhausted_speed_mps": flight.water_exhausted_speed_mps,
        "water_impulse_ns": flight.water_impulse_ns,
        "air_impulse_ns": flight.air_impulse_ns,
        "rail_exit_speed_mps": flight.rail_exit_speed_mps,
        "descent_speed_mps": descent_speed,
        "landing_east_m": landing_e,
        "landing_north_m": landing_n,
        "landing_distance_m": math.hypot(landing_e, landing_n),
        "flight_time_s": flight_time,
        "liftoff_mass_kg": flight.liftoff_mass_kg,
        "water_mass_kg": flight.water_mass_kg,
        **scores,
    }
    return SimResult(
        tier=Tier.BOTTLE,
        success=not failures,
        failure_reasons=failures,
        metrics=metrics,
        cost_jpy=0.0,  # cost.py owns the estimate; the agent fills it in.
        trace=_build_trace(flight, descent),
        warnings=warnings,
    )


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    """Monte-Carlo dispersion with the bottle spec (rocketwright.dispersion.DISPERSION_SPEC):
    initial pressure and wind speed/direction."""
    _check_design(design)
    return mc.run_dispersion(
        design,
        env,
        n,
        seed,
        perturb=mc.perturb_bottle,
        simulate=simulate,
        tier=Tier.BOTTLE,
        summarize=mc.summarize_landing,
    )
