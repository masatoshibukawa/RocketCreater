"""Solid-motor flight model for the amateur tier (CLAUDE.md section 7, "solid").

A hobby rocket on a commercial motor: 1-D along the launch rail until the rail is cleared, then
a 3-D point mass (x east, y north, z up, metres above the pad) with gravity, thrust along the
body axis, constant-Cd drag and a constant wind. Static stability comes from
rocketwright.physics.stability (Barrowman), the parachute descent from
rocketwright.physics.recovery. Every approximation is marked with `# SIMPLIFICATION:`.

Public entry points:

* `simulate(design, env, seed=None, *, target_apogee_m=None)` -- the common physics interface.
* `simulate_with_options(...)` -- same, with `gravity` / `drag` switches for verification tests.
* `run_flight(design, env, options)` -- the raw trajectory and flight events.
* `load_motor(motor_id)` / `list_motor_ids()` -- RASP `.eng` thrust curves from catalog/motors.
"""

from __future__ import annotations

import functools
import math
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from rocketwright.physics import atmosphere as atm
from rocketwright.physics import recovery, stability
from rocketwright.schema import (
    MAX_TRACE_POINTS,
    AmateurDesign,
    Design,
    DispersionResult,
    Env,
    SimResult,
    Tier,
    TracePoint,
    decimate_trace,
)

__all__ = [
    "DEFAULT_CD",
    "MOTOR_DIR",
    "PASS_THRESHOLDS",
    "Flight",
    "FlightOptions",
    "Motor",
    "dispersion",
    "list_motor_ids",
    "load_motor",
    "run_flight",
    "simulate",
    "simulate_with_options",
]

# --------------------------------------------------------------------------- constants

G0_MPS2 = 9.80665
# SIMPLIFICATION: one constant drag coefficient on the body frontal area for a slender finned
# hobby rocket at zero angle of attack (OpenRocket typically gives 0.4-0.6 subsonic).
DEFAULT_CD = 0.5
MOTOR_DIR = Path(__file__).resolve().parents[1] / "catalog" / "motors"

# Single place for the pass/fail rules (CLAUDE.md section 6). `max_*_warn` entries only warn.
PASS_THRESHOLDS: dict[str, float] = {
    "min_rail_exit_speed_mps": 15.0,  # common club guideline for a stable departure
    "min_stability_margin_cal": 1.5,
    "max_stability_margin_cal": 4.0,  # above this the rocket is overstable: warning only
    "max_descent_speed_mps": 6.0,
    "apogee_tolerance_frac": 0.10,  # |apogee - target| <= target * tol when a target is given
    "max_deploy_speed_mps": 40.0,  # parachute opening speed: warning only (provisional)
}

# Integration controls: fine steps while the motor burns (thrust-curve resolution), coarser
# while coasting. max_step bounds the trace resolution.
_MAX_STEP_BURN_S = 0.02
_MAX_STEP_COAST_S = 0.25
_RTOL = 1e-6
_ATOL = 1e-6
_MAX_FLIGHT_S = 600.0
_TRACE_DESCENT_POINTS = 40


# --------------------------------------------------------------------------- motor catalog


@dataclass(frozen=True)
class Motor:
    """One RASP `.eng` motor. `thrust_curve` is (t_s, thrust_n) pairs starting at (0, 0)."""

    id: str
    name: str
    diameter_m: float
    length_m: float
    delays: tuple[str, ...]
    propellant_mass_kg: float
    total_mass_kg: float
    manufacturer: str
    thrust_curve: tuple[tuple[float, float], ...]
    source: str | None
    license: str | None
    provisional: bool
    _times: tuple[float, ...] = field(default=(), repr=False, compare=False)
    _thrusts: tuple[float, ...] = field(default=(), repr=False, compare=False)
    _cumulative_ns: tuple[float, ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        times = tuple(t for t, _ in self.thrust_curve)
        thrusts = tuple(f for _, f in self.thrust_curve)
        cumulative = [0.0]
        for i in range(1, len(times)):
            cumulative.append(
                cumulative[-1] + 0.5 * (thrusts[i - 1] + thrusts[i]) * (times[i] - times[i - 1])
            )
        object.__setattr__(self, "_times", times)
        object.__setattr__(self, "_thrusts", thrusts)
        object.__setattr__(self, "_cumulative_ns", tuple(cumulative))

    @property
    def burn_time_s(self) -> float:
        return self._times[-1]

    @property
    def total_impulse_ns(self) -> float:
        """Trapezoidal integral of the thrust curve."""
        return self._cumulative_ns[-1]

    @property
    def peak_thrust_n(self) -> float:
        return max(self._thrusts)

    @property
    def average_thrust_n(self) -> float:
        return self.total_impulse_ns / self.burn_time_s

    def thrust_n(self, t_s: float) -> float:
        """Linear interpolation of the curve; zero before ignition and after burnout."""
        if t_s <= 0.0 or t_s >= self.burn_time_s:
            return 0.0
        i = bisect_right(self._times, t_s)
        t0, t1 = self._times[i - 1], self._times[i]
        f0, f1 = self._thrusts[i - 1], self._thrusts[i]
        return f0 + (f1 - f0) * (t_s - t0) / (t1 - t0)

    def impulse_ns(self, t_s: float) -> float:
        """Impulse delivered up to `t_s` (used for the propellant-mass bookkeeping)."""
        if t_s <= 0.0:
            return 0.0
        if t_s >= self.burn_time_s:
            return self.total_impulse_ns
        i = bisect_right(self._times, t_s)
        t0 = self._times[i - 1]
        return self._cumulative_ns[i - 1] + 0.5 * (self._thrusts[i - 1] + self.thrust_n(t_s)) * (
            t_s - t0
        )


def list_motor_ids(motor_dir: Path = MOTOR_DIR) -> list[str]:
    return sorted(p.stem for p in motor_dir.glob("*.eng"))


def _parse_eng(motor_id: str, text: str) -> Motor:
    meta: dict[str, str] = {}
    header: list[str] | None = None
    curve: list[tuple[float, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            body = line.lstrip(";").strip()
            key, sep, value = body.partition(":")
            if sep and key.strip().lower() in ("source", "license", "provisional"):
                meta[key.strip().lower()] = value.strip()
            continue
        if header is None:
            header = line.split()
            if len(header) < 7:
                raise ValueError(f"motor {motor_id!r}: bad RASP header {line!r}")
            continue
        t_str, f_str = line.split()[:2]
        curve.append((float(t_str), float(f_str)))
    if header is None or not curve:
        raise ValueError(f"motor {motor_id!r}: no header / thrust samples")
    if curve[0][0] > 0.0:
        curve.insert(0, (0.0, 0.0))  # RASP files usually omit the ignition point
    for (t0, _), (t1, _) in zip(curve, curve[1:], strict=False):
        if t1 <= t0:
            raise ValueError(f"motor {motor_id!r}: thrust samples must have increasing times")
    provisional = meta.get("provisional", "false").lower() in ("true", "yes", "1")
    source = meta.get("source") or None
    license_ = meta.get("license") or None
    if not provisional and not (source and license_):
        raise ValueError(f"motor {motor_id!r} needs `; source:` and `; license:` or provisional")
    return Motor(
        id=motor_id,
        name=header[0],
        diameter_m=float(header[1]) / 1000.0,
        length_m=float(header[2]) / 1000.0,
        delays=tuple(header[3].split("-")),
        propellant_mass_kg=float(header[4]),
        total_mass_kg=float(header[5]),
        manufacturer=header[6],
        thrust_curve=tuple(curve),
        source=source,
        license=license_,
        provisional=provisional,
    )


@functools.lru_cache(maxsize=64)
def load_motor(motor_id: str, motor_dir: Path = MOTOR_DIR) -> Motor:
    """Read and cache catalog/motors/<motor_id>.eng. Unknown ids list the available ones."""
    path = motor_dir / f"{motor_id}.eng"
    if not path.is_file():
        raise KeyError(f"unknown motor id {motor_id!r}; available ids: {list_motor_ids(motor_dir)}")
    return _parse_eng(motor_id, path.read_text(encoding="utf-8", errors="replace"))


# --------------------------------------------------------------------------- flight


@dataclass(frozen=True)
class FlightOptions:
    gravity: bool = True
    drag: bool = True
    cd: float = DEFAULT_CD


@dataclass(frozen=True)
class Flight:
    """Raw trajectory from ignition to parachute deployment (or impact / burnout in
    verification mode), plus the flight events."""

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
    left_rail: bool
    rail_exit_time_s: float
    rail_exit_speed_mps: float
    burnout_time_s: float
    burnout_altitude_m: float
    burnout_speed_mps: float
    apogee_time_s: float
    apogee_m: float
    deploy_time_s: float
    deploy_altitude_m: float
    deploy_speed_mps: float
    deploy_east_m: float
    deploy_north_m: float
    impacted_before_deploy: bool


class _Dynamics:
    """ODE right-hand side; state = [x, y, z, vx, vy, vz, m]."""

    def __init__(
        self, design: AmateurDesign, motor: Motor, env: Env, options: FlightOptions
    ) -> None:
        self.motor = motor
        self.area_m2 = math.pi * (design.body_diameter_m / 2.0) ** 2
        self.cd = options.cd if options.drag else 0.0
        self.g = G0_MPS2 if options.gravity else 0.0  # SIMPLIFICATION: constant g
        self.wind_e, self.wind_n = recovery.wind_vector_mps(env)
        self.pad_altitude_m = env.launch_altitude_m
        self.temperature_offset_k = env.temperature_offset_k
        self.mdot_per_newton = motor.propellant_mass_kg / motor.total_impulse_ns
        self.on_rail = True
        self.thrust_on = True

    def forces(self, t: float, s: NDArray[np.float64]) -> tuple[float, float, float, float]:
        """(thrust_n, drag_n, air-relative speed, proper acceleration) at the state."""
        thrust = self.motor.thrust_n(t) if self.thrust_on else 0.0
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
        return thrust, drag, va, abs(thrust - drag) / float(s[6])

    def __call__(self, t: float, s: NDArray[np.float64]) -> list[float]:
        m = float(s[6])
        thrust, drag, va, _ = self.forces(t, s)
        dm = -self.mdot_per_newton * thrust if self.thrust_on else 0.0
        if self.on_rail:
            # SIMPLIFICATION: the rail is vertical (Env has no launch-angle field); the rocket
            # is held on the pad until the thrust exceeds the weight.
            vz = float(s[5])
            az = (thrust - math.copysign(drag, vz)) / m - self.g
            if vz <= 0.0 and az < 0.0:
                az = 0.0
            return [0.0, 0.0, max(vz, 0.0), 0.0, 0.0, az, dm]
        # SIMPLIFICATION: zero angle of attack -- the body axis follows the air-relative velocity
        # (instant weathercock into the wind at rail exit), so thrust and drag are collinear.
        vax, vay, vaz = float(s[3]) - self.wind_e, float(s[4]) - self.wind_n, float(s[5])
        if va > 1e-9:
            ux, uy, uz = vax / va, vay / va, vaz / va
        else:
            ux, uy, uz = 0.0, 0.0, 1.0
        f_axis = (thrust - drag) / m
        return [
            float(s[3]),
            float(s[4]),
            float(s[5]),
            f_axis * ux,
            f_axis * uy,
            f_axis * uz - self.g,
            dm,
        ]


def _event(fn: Callable[..., float], *, terminal: bool, direction: int) -> Callable[..., float]:
    fn.terminal = terminal
    fn.direction = direction
    return fn


def _check_design(design: Design) -> AmateurDesign:
    if not isinstance(design, AmateurDesign):
        raise ValueError(f"solid.simulate requires a design with tier amateur, got {design.tier!r}")
    return design


def run_flight(design: AmateurDesign, env: Env, options: FlightOptions | None = None) -> Flight:
    """Integrate ignition -> rail exit -> burnout -> apogee -> deploy_delay_s of free fall."""
    options = options or FlightOptions()
    motor = load_motor(design.motor_id)
    dyn = _Dynamics(design, motor, env, options)
    m0 = design.dry_mass_kg + design.payload_mass_kg + motor.total_mass_kg
    state = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, m0])
    ts: list[NDArray[np.float64]] = [np.array([0.0])]
    ys: list[NDArray[np.float64]] = [state.reshape(7, 1).copy()]
    t = 0.0

    def integrate(t_end: float, events: list[Callable[..., float]], max_step: float) -> Any:
        nonlocal t, state
        sol = solve_ivp(
            dyn,
            (t, t_end),
            state,
            method="RK45",
            events=events,
            max_step=max_step,
            rtol=_RTOL,
            atol=_ATOL,
        )
        if not sol.success:
            raise RuntimeError(f"solid integration failed: {sol.message}")
        ts.append(sol.t[1:])
        ys.append(sol.y[:, 1:])
        t = float(sol.t[-1])
        state = sol.y[:, -1].copy()
        return sol

    rail_exit = _event(lambda _t, s: s[2] - env.rail_length_m, terminal=True, direction=1)
    apogee = _event(lambda _t, s: s[5], terminal=True, direction=-1)
    impact = _event(lambda _t, s: s[2], terminal=True, direction=-1)

    # --- rail phase (1-D). The motor may burn out on the rail (then the rocket never leaves).
    left_rail = False
    if motor.peak_thrust_n > m0 * dyn.g:
        sol = integrate(motor.burn_time_s, [rail_exit], _MAX_STEP_BURN_S)
        left_rail = bool(sol.t_events[0].size)
    rail_exit_time = t
    rail_exit_speed = float(state[5])
    dyn.on_rail = False

    burnout_time = motor.burn_time_s
    apogee_time = t
    deploy_time = t
    impacted = False
    if left_rail:
        # --- powered 3-D flight to burnout
        if t < motor.burn_time_s:
            integrate(motor.burn_time_s, [impact], _MAX_STEP_BURN_S)
        state[6] = m0 - motor.propellant_mass_kg  # snap the propellant to exactly empty
        burnout_state = state.copy()
        dyn.thrust_on = False
        if options.gravity:
            # --- coast to apogee, then deploy_delay_s of free fall before the parachute opens
            # SIMPLIFICATION: the parachute opens at apogee + deploy_delay_s regardless of the
            # motor's ejection-charge timing.
            sol = integrate(t + _MAX_FLIGHT_S, [apogee, impact], _MAX_STEP_COAST_S)
            apogee_time = t
            impacted = bool(sol.t_events[1].size)
            if not impacted and design.deploy_delay_s > 0.0:
                sol = integrate(t + design.deploy_delay_s, [impact], _MAX_STEP_COAST_S)
                impacted = bool(sol.t_events[0].size)
            deploy_time = t
        else:
            burnout_state = state.copy()
            apogee_time = deploy_time = t
    else:
        burnout_state = state.copy()

    t_all = np.concatenate(ts)
    y_all = np.concatenate(ys, axis=1)
    thrust = np.array([motor.thrust_n(float(ti)) for ti in t_all])
    # Proper acceleration per sample; the rail/thrust flags only matter for the air speed.
    dyn.on_rail, dyn.thrust_on = True, True
    accel = np.empty(len(t_all))
    for i, ti in enumerate(t_all):
        dyn.on_rail = float(y_all[2, i]) < env.rail_length_m and ti <= rail_exit_time
        accel[i] = dyn.forces(float(ti), y_all[:, i])[3]
    i_apogee = int(np.argmax(y_all[2]))
    return Flight(
        t_s=t_all,
        x_m=y_all[0],
        y_m=y_all[1],
        z_m=y_all[2],
        vx_mps=y_all[3],
        vy_mps=y_all[4],
        vz_mps=y_all[5],
        mass_kg=y_all[6],
        thrust_n=thrust,
        accel_mps2=accel,
        liftoff_mass_kg=m0,
        left_rail=left_rail,
        rail_exit_time_s=rail_exit_time,
        rail_exit_speed_mps=rail_exit_speed,
        burnout_time_s=burnout_time,
        burnout_altitude_m=float(burnout_state[2]),
        burnout_speed_mps=float(math.hypot(burnout_state[3], burnout_state[4], burnout_state[5])),
        apogee_time_s=apogee_time,
        apogee_m=float(y_all[2, i_apogee]),
        deploy_time_s=deploy_time,
        deploy_altitude_m=max(float(state[2]), 0.0),
        deploy_speed_mps=float(math.hypot(state[3], state[4], state[5])),
        deploy_east_m=float(state[0]),
        deploy_north_m=float(state[1]),
        impacted_before_deploy=impacted,
    )


# --------------------------------------------------------------------------- results


def _build_trace(flight: Flight, descent: recovery.DescentResult | None) -> list[TracePoint]:
    points = [
        TracePoint(
            t_s=float(flight.t_s[i]),
            altitude_m=float(flight.z_m[i]),
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
            start_time_s=flight.deploy_time_s,
            start_altitude_m=flight.deploy_altitude_m,
            start_east_m=flight.deploy_east_m,
            start_north_m=flight.deploy_north_m,
            mass_kg=float(flight.mass_kg[-1]),
            n_points=_TRACE_DESCENT_POINTS,
        )
    return decimate_trace(points, MAX_TRACE_POINTS)


def simulate_with_options(
    design: Design,
    env: Env,
    *,
    gravity: bool = True,
    drag: bool = True,
    target_apogee_m: float | None = None,
) -> SimResult:
    """`simulate` with physics switches (tests use them to isolate the rocket equation)."""
    am_design = _check_design(design)
    motor = load_motor(am_design.motor_id)
    options = FlightOptions(gravity=gravity, drag=drag)
    flight = run_flight(am_design, env, options)
    th = PASS_THRESHOLDS
    failures: list[str] = []
    warnings: list[str] = []
    if motor.provisional:
        warnings.append(
            f"motor {motor.id!r} has a provisional (synthetic) thrust curve awaiting a licensed one"
        )

    margin = stability.static_margin_cal(
        am_design, motor.total_mass_kg, motor_length_m=motor.length_m
    )
    weight_n = flight.liftoff_mass_kg * G0_MPS2
    if motor.peak_thrust_n <= weight_n and gravity:
        failures.append(
            f"motor {motor.id} cannot lift the rocket: peak thrust {motor.peak_thrust_n:.0f} N "
            f"<= liftoff weight {weight_n:.0f} N"
        )
    elif not flight.left_rail:
        failures.append(
            f"rocket did not leave the {env.rail_length_m:g} m rail before burnout "
            f"(thrust-to-weight too low)"
        )
    elif flight.rail_exit_speed_mps < th["min_rail_exit_speed_mps"]:
        failures.append(
            f"rail exit speed {flight.rail_exit_speed_mps:.1f} m/s below "
            f"{th['min_rail_exit_speed_mps']:.0f} m/s (lengthen the rail, lighten the rocket "
            f"or pick a higher-thrust motor)"
        )
    if margin < th["min_stability_margin_cal"]:
        failures.append(
            f"stability margin {margin:.2f} cal below {th['min_stability_margin_cal']} cal "
            f"(larger fins, longer body or payload further forward)"
        )
    elif margin > th["max_stability_margin_cal"]:
        warnings.append(
            f"overstable: stability margin {margin:.2f} cal above {th['max_stability_margin_cal']} "
            f"cal (weathercocks strongly into the wind)"
        )

    descent_mass = flight.liftoff_mass_kg - motor.propellant_mass_kg
    descent: recovery.DescentResult | None = None
    if flight.left_rail and not flight.impacted_before_deploy:
        descent = recovery.descend(
            descent_mass,
            am_design.parachute_diameter_m,
            env,
            start_altitude_m=flight.deploy_altitude_m,
            start_east_m=flight.deploy_east_m,
            start_north_m=flight.deploy_north_m,
        )
        if descent.descent_speed_mps > th["max_descent_speed_mps"]:
            failures.append(
                f"descent speed {descent.descent_speed_mps:.2f} m/s above "
                f"{th['max_descent_speed_mps']:.0f} m/s (larger parachute)"
            )
        if flight.deploy_speed_mps > th["max_deploy_speed_mps"]:
            warnings.append(
                f"parachute opens at {flight.deploy_speed_mps:.0f} m/s "
                f"(> {th['max_deploy_speed_mps']:.0f} m/s): shorten deploy_delay_s"
            )
    elif flight.left_rail:
        failures.append(
            f"rocket hit the ground {flight.deploy_time_s - flight.apogee_time_s:.1f} s after "
            f"apogee before the parachute opened (deploy_delay_s {am_design.deploy_delay_s:g} s "
            f"too long)"
        )
    if target_apogee_m is not None:
        tol = target_apogee_m * th["apogee_tolerance_frac"]
        if abs(flight.apogee_m - target_apogee_m) > tol:
            failures.append(
                f"apogee {flight.apogee_m:.0f} m not within +/-{th['apogee_tolerance_frac']:.0%} "
                f"of target {target_apogee_m:.0f} m"
            )
    if not gravity or not drag:
        warnings.append("physics switches off (verification mode): not a flight prediction")

    landing_e = descent.landing_east_m if descent else flight.deploy_east_m
    landing_n = descent.landing_north_m if descent else flight.deploy_north_m
    flight_time = flight.deploy_time_s + (descent.descent_time_s if descent else 0.0)
    speed = np.hypot(np.hypot(flight.vx_mps, flight.vy_mps), flight.vz_mps)
    metrics: dict[str, float] = {
        "apogee_m": flight.apogee_m,
        "apogee_time_s": flight.apogee_time_s,
        "max_speed_mps": float(speed.max()),
        "max_accel_mps2": float(flight.accel_mps2.max()),
        "rail_exit_speed_mps": flight.rail_exit_speed_mps,
        "rail_exit_time_s": flight.rail_exit_time_s,
        "burnout_time_s": flight.burnout_time_s,
        "burnout_altitude_m": flight.burnout_altitude_m,
        "burnout_speed_mps": flight.burnout_speed_mps,
        "stability_margin_cal": margin,
        "deploy_altitude_m": flight.deploy_altitude_m,
        "deploy_speed_mps": flight.deploy_speed_mps,
        "descent_speed_mps": descent.descent_speed_mps if descent else flight.deploy_speed_mps,
        "descent_time_s": descent.descent_time_s if descent else 0.0,
        "landing_east_m": landing_e,
        "landing_north_m": landing_n,
        "landing_distance_m": math.hypot(landing_e, landing_n),
        "flight_time_s": flight_time,
        "total_impulse_ns": motor.total_impulse_ns,
        "liftoff_mass_kg": flight.liftoff_mass_kg,
        "motor_mass_kg": motor.total_mass_kg,
        "liftoff_twr_ratio": motor.average_thrust_n / weight_n if weight_n > 0 else math.inf,
    }
    return SimResult(
        tier=Tier.AMATEUR,
        success=not failures,
        failure_reasons=failures,
        metrics=metrics,
        cost_jpy=0.0,  # cost.py owns the estimate; the agent fills it in.
        trace=_build_trace(flight, descent),
        warnings=warnings,
    )


def simulate(
    design: Design, env: Env, seed: int | None = None, *, target_apogee_m: float | None = None
) -> SimResult:
    """Common physics interface (CLAUDE.md section 6). `seed` is accepted for interface
    compatibility; the nominal solid model is deterministic and ignores it."""
    del seed
    return simulate_with_options(design, env, target_apogee_m=target_apogee_m)


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    raise NotImplementedError("solid.dispersion: implemented in phase 3")
