"""Multistage ascent model for the commercial and heavy tiers (CLAUDE.md section 7).

Concept-level model: a point mass moving in a vertical plane around a spherical Earth with
central gravity, USSA76 drag, altitude-corrected specific impulse and an open-loop gravity
turn (vertical rise, instantaneous pitch kick, then zero angle of attack). Lower stages burn
back to back; strap-on boosters burn in parallel with stage 0. Every approximation is marked
with `# SIMPLIFICATION:`.

Orbit insertion (when a target perigee is given) has two modes:

* `"coast_circularize"` (default): the last stage burns until the osculating apogee reaches
  the target apogee, coasts to that apogee and then burns until the osculating perigee reaches
  the target perigee; leftover propellant is the margin. The cutoffs are integration events on
  the state (engine cutoff at a target apogee is standard concept-design practice), not
  feedback steering: thrust stays along the velocity vector, so this remains an open-loop
  ascent in the sense of CLAUDE.md section 4 (no guidance software).
* `"direct"`: the historical single burn to depletion; the orbit is whatever results.

Public entry points:

* `simulate(design, env, seed=None, *, target_perigee_m=None, target_apogee_m=None,
  insertion="coast_circularize")` -- the common physics interface returning a `SimResult`.
* `simulate_with_options(...)` -- same, with `gravity` / `drag` / `atmosphere` switches so
  verification tests can isolate the rocket equation.
* `run_ascent(design, env, options)` -- the raw trajectory (arrays, staging events, losses,
  insertion bookkeeping). The targets and the insertion mode live in `AscentOptions`.
* `tune_pitch_program(design, env, target_perigee_m, target_apogee_m=None)` -- searches
  `pitch_start_s` and `initial_pitch_deg` with scipy.optimize to hit a target orbit.
* `get_engine(engine_id)` / `load_engine_catalog()` -- cached access to catalog/engines.yaml.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize

from rocketwright import dispersion as mc
from rocketwright.physics import atmosphere as atm
from rocketwright.schema import (
    MAX_TRACE_POINTS,
    Design,
    DispersionResult,
    Env,
    MultistageDesign,
    SimResult,
    Tier,
    TracePoint,
    decimate_trace,
)

__all__ = [
    "PASS_THRESHOLDS",
    "INSERTION_MODES",
    "MU_EARTH_M3PS2",
    "R_EARTH_M",
    "FAIRING_JETTISON_ALTITUDE_M",
    "EngineSpec",
    "AscentOptions",
    "MassEvent",
    "Ascent",
    "load_engine_catalog",
    "get_engine",
    "run_ascent",
    "simulate",
    "simulate_with_options",
    "tune_pitch_program",
    "dispersion",
]

# --------------------------------------------------------------------------- constants

G0_MPS2 = 9.80665
MU_EARTH_M3PS2 = 3.986004418e14  # WGS84 gravitational parameter
R_EARTH_M = 6_371_000.0  # SIMPLIFICATION: mean radius, spherical Earth
OMEGA_EARTH_RADPS = 7.2921159e-5
SEA_LEVEL_PRESSURE_PA = atm.SEA_LEVEL_PRESSURE_PA

# SIMPLIFICATION: fairing jettison at a fixed altitude instead of a free-molecular-heating limit.
FAIRING_JETTISON_ALTITUDE_M = 110_000.0

# SIMPLIFICATION: vehicle diameter is estimated from the total propellant mass with
# d = 0.05 m * (m_prop / 1 kg)^(1/3)  (Falcon 9: ~520 t -> 4.0 m; Electron: ~10 t -> 1.1 m).
DIAMETER_PER_CUBE_ROOT_KG = 0.05

# SIMPLIFICATION: drag coefficient of a slender launch vehicle as a small Mach table
# (subsonic ~0.3, transonic rise to ~0.6, decaying to ~0.25 hypersonic). Not vehicle-specific.
_CD_MACH = (0.0, 0.8, 1.0, 1.2, 2.0, 3.0, 5.0, 10.0)
_CD_VALUE = (0.30, 0.32, 0.55, 0.60, 0.45, 0.35, 0.28, 0.25)

# Reported apogee for escape (hyperbolic) trajectories, so metrics stay finite floats.
ESCAPE_APOGEE_SENTINEL_M = 1.0e9

# Integration controls. max_step bounds the trace resolution and the max-Q sampling; the
# unpowered coast to apogee uses a coarser step (nothing to resolve but the orbit).
_MAX_STEP_S = 2.0
_COAST_MAX_STEP_S = 10.0
_RTOL = 1e-8
_ATOL = 1e-6
# Propellant below which a stage counts as empty (snapped to zero).
_EMPTY_PROPELLANT_KG = 1e-6

INSERTION_MODES = ("coast_circularize", "direct")
# SIMPLIFICATION: osculating perigee altitude the first insertion burn must have reached before
# the apogee cutoff fires. A lofted lower stage can show a ballistic peak above the target while
# the perigee is still thousands of km below ground; cutting off there would leave a
# circularization burn of several km/s, during which the zero-angle-of-attack burn at apogee
# falls back into the atmosphere. -1000 km keeps that burn at a few hundred m/s.
CUTOFF_MIN_PERIGEE_M = -1_000_000.0

# Single place for the pass/fail rules (CLAUDE.md section 6).
PASS_THRESHOLDS: dict[str, float] = {
    "min_perigee_m": 150_000.0,  # used when the caller gives no target
    "perigee_tolerance_frac": 0.10,  # perigee >= target * (1 - tol) when a target is given
    "apogee_tolerance_frac": 0.10,  # |apogee - target| <= target * tol when a target is given
    "min_liftoff_twr_ratio": 1.1,  # Atlas V 401 lifts off at ~1.17; below 1.2 is only warned
    "warn_liftoff_twr_ratio": 1.2,
    "max_q_pa": 60_000.0,
}

CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalog" / "engines.yaml"


# --------------------------------------------------------------------------- engine catalog


@dataclass(frozen=True)
class EngineSpec:
    """One catalog entry. `kind` is "engine" or "booster"; boosters carry their own propellant."""

    id: str
    name: str
    kind: str
    thrust_sl_n: float
    thrust_vac_n: float
    isp_sl_s: float
    isp_vac_s: float
    mass_kg: float  # dry engine mass, or booster structural mass
    propellant_mass_kg: float = 0.0  # boosters only
    provisional: bool = False
    source: str | None = None

    @property
    def mdot_kgps(self) -> float:
        """Constant mass flow derived from vacuum thrust and vacuum Isp."""
        return self.thrust_vac_n / (G0_MPS2 * self.isp_vac_s)

    def isp_s(self, ambient_pressure_pa: float) -> float:
        """Specific impulse interpolated linearly in ambient pressure between SL and vacuum."""
        frac = min(max(ambient_pressure_pa / SEA_LEVEL_PRESSURE_PA, 0.0), 1.0)
        return self.isp_vac_s - (self.isp_vac_s - self.isp_sl_s) * frac


def _parse_entry(raw: dict[str, Any], kind: str) -> EngineSpec:
    required = ("id", "name", "thrust_sl_n", "thrust_vac_n", "isp_sl_s", "isp_vac_s", "mass_kg")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"engines.yaml entry {raw.get('id')!r} is missing fields {missing}")
    if kind == "booster" and "propellant_mass_kg" not in raw:
        raise ValueError(f"booster {raw['id']!r} needs propellant_mass_kg")
    provisional = bool(raw.get("provisional", False))
    source = raw.get("source")
    if not provisional and not source:
        raise ValueError(f"catalog entry {raw['id']!r} needs a source URL or provisional: true")
    return EngineSpec(
        id=str(raw["id"]),
        name=str(raw["name"]),
        kind=kind,
        thrust_sl_n=float(raw["thrust_sl_n"]),
        thrust_vac_n=float(raw["thrust_vac_n"]),
        isp_sl_s=float(raw["isp_sl_s"]),
        isp_vac_s=float(raw["isp_vac_s"]),
        mass_kg=float(raw["mass_kg"]),
        propellant_mass_kg=float(raw.get("propellant_mass_kg", 0.0)),
        provisional=provisional,
        source=str(source) if source else None,
    )


@functools.lru_cache(maxsize=4)
def load_engine_catalog(path: Path = CATALOG_PATH) -> dict[str, EngineSpec]:
    """Read and cache engines.yaml. Engines and boosters share one id namespace."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    catalog: dict[str, EngineSpec] = {}
    for kind, key in (("engine", "engines"), ("booster", "boosters")):
        for raw in data.get(key) or []:
            spec = _parse_entry(raw, kind)
            if spec.id in catalog:
                raise ValueError(f"duplicate catalog id {spec.id!r}")
            catalog[spec.id] = spec
    return catalog


def get_engine(engine_id: str, kind: str | None = None) -> EngineSpec:
    """Look up a catalog entry by id; `kind` restricts to "engine" or "booster"."""
    catalog = load_engine_catalog()
    spec = catalog.get(engine_id)
    if spec is None or (kind is not None and spec.kind != kind):
        available = sorted(k for k, v in catalog.items() if kind is None or v.kind == kind)
        label = kind or "engine/booster"
        raise KeyError(f"unknown {label} id {engine_id!r}; available ids: {available}")
    return spec


# --------------------------------------------------------------------------- vehicle set-up


@dataclass(frozen=True)
class _Thruster:
    """A group of identical engines draining one propellant store at constant mass flow."""

    mdot_kgps: float
    isp_sl_s: float
    isp_vac_s: float

    @property
    def thrust_vac_n(self) -> float:
        return self.mdot_kgps * G0_MPS2 * self.isp_vac_s


@dataclass(frozen=True)
class _Phase:
    """A constant-configuration burn: which thrusters fire, for how long, what is dropped after."""

    label: str  # mass event label recorded at the end of the phase
    thrusters: tuple[_Thruster, ...]
    duration_s: float
    propellant_kg: float  # consumed during the phase
    drop_after_kg: float  # jettisoned at the end of the phase

    @property
    def mdot_kgps(self) -> float:
        return sum(t.mdot_kgps for t in self.thrusters)

    @property
    def thrust_vac_n(self) -> float:
        return sum(t.thrust_vac_n for t in self.thrusters)

    @property
    def isp_vac_effective_s(self) -> float:
        """Mixture Isp = total vacuum thrust / (g0 * total mass flow)."""
        return self.thrust_vac_n / (G0_MPS2 * self.mdot_kgps)


@dataclass(frozen=True)
class _Vehicle:
    phases: tuple[_Phase, ...]
    liftoff_mass_kg: float
    liftoff_thrust_sl_n: float
    fairing_mass_kg: float
    reference_area_m2: float
    stage_wet_kg: tuple[float, ...]
    stage_dry_kg: tuple[float, ...]
    warnings: tuple[str, ...]


def structural_mass_kg(propellant_mass_kg: float, structural_fraction: float) -> float:
    """structure = propellant * f / (1 - f) with f = structure / (structure + propellant)."""
    return propellant_mass_kg * structural_fraction / (1.0 - structural_fraction)


def _build_vehicle(
    design: MultistageDesign, *, isp_scale: float = 1.0, thrust_scale: float = 1.0
) -> _Vehicle:
    """Assemble the burn phases. `isp_scale` multiplies every Isp and `thrust_scale` every
    thrust (so the mass flow scales with thrust_scale / isp_scale); both default to 1.0 and are
    what the Monte-Carlo dispersion perturbs."""
    if isp_scale <= 0.0 or thrust_scale <= 0.0:
        raise ValueError("isp_scale and thrust_scale must be > 0")
    mdot_scale = thrust_scale / isp_scale
    warnings: list[str] = []
    stage_wet: list[float] = []
    stage_dry: list[float] = []
    stage_thrusters: list[_Thruster] = []
    for i, stage in enumerate(design.stages):
        spec = get_engine(stage.engine_id, kind="engine")
        if spec.provisional:
            warnings.append(
                f"engine {spec.id!r} ({spec.name}) has provisional catalog data "
                "awaiting confirmation"
            )
        dry = structural_mass_kg(stage.propellant_mass_kg, stage.structural_fraction)
        # SIMPLIFICATION: engine mass is assumed to be part of the structural fraction, so it is
        # not added on top; warn when the fraction cannot even cover the engines.
        if spec.mass_kg * stage.engine_count > dry:
            warnings.append(
                f"stage {i + 1}: structural mass {dry:.0f} kg is below the engine mass "
                f"{spec.mass_kg * stage.engine_count:.0f} kg ({stage.engine_count} x {spec.id})"
            )
        stage_dry.append(dry)
        stage_wet.append(dry + stage.propellant_mass_kg)
        stage_thrusters.append(
            _Thruster(
                spec.mdot_kgps * stage.engine_count * mdot_scale,
                spec.isp_sl_s * isp_scale,
                spec.isp_vac_s * isp_scale,
            )
        )

    booster_thrusters: list[_Thruster] = []
    booster_prop_kg = 0.0
    booster_dry_kg = 0.0
    booster_burn_s = math.inf
    booster_thrust_sl_n = 0.0
    for booster in design.boosters:
        spec = get_engine(booster.booster_id, kind="booster")
        if spec.provisional:
            warnings.append(
                f"booster {spec.id!r} ({spec.name}) has provisional catalog data "
                "awaiting confirmation"
            )
        booster_thrusters.append(
            _Thruster(
                spec.mdot_kgps * booster.count * mdot_scale,
                spec.isp_sl_s * isp_scale,
                spec.isp_vac_s * isp_scale,
            )
        )
        booster_prop_kg += spec.propellant_mass_kg * booster.count
        booster_dry_kg += spec.mass_kg * booster.count
        booster_burn_s = min(
            booster_burn_s, spec.propellant_mass_kg / (spec.mdot_kgps * mdot_scale)
        )
        booster_thrust_sl_n += spec.thrust_sl_n * booster.count * thrust_scale

    phases: list[_Phase] = []
    stage0 = design.stages[0]
    t0 = stage0.propellant_mass_kg / stage_thrusters[0].mdot_kgps
    if booster_thrusters:
        # SIMPLIFICATION: all boosters are jettisoned together when the shortest-burning one is
        # empty; any propellant left in the others is dropped with them.
        if booster_burn_s < t0:
            booster_mdot = sum(t.mdot_kgps for t in booster_thrusters)
            burnt = booster_mdot * booster_burn_s
            phases.append(
                _Phase(
                    label="booster_separation",
                    thrusters=(stage_thrusters[0], *booster_thrusters),
                    duration_s=booster_burn_s,
                    propellant_kg=burnt + stage_thrusters[0].mdot_kgps * booster_burn_s,
                    drop_after_kg=booster_dry_kg + (booster_prop_kg - burnt),
                )
            )
            phases.append(
                _Phase(
                    label="stage1_separation",
                    thrusters=(stage_thrusters[0],),
                    duration_s=t0 - booster_burn_s,
                    propellant_kg=stage_thrusters[0].mdot_kgps * (t0 - booster_burn_s),
                    drop_after_kg=stage_dry[0],
                )
            )
        else:
            # SIMPLIFICATION: boosters that outlast stage 0 are jettisoned with it.
            warnings.append(
                "boosters burn longer than stage 1; leftover booster propellant is dropped"
            )
            booster_mdot = sum(t.mdot_kgps for t in booster_thrusters)
            burnt = booster_mdot * t0
            phases.append(
                _Phase(
                    label="stage1_separation",
                    thrusters=(stage_thrusters[0], *booster_thrusters),
                    duration_s=t0,
                    propellant_kg=burnt + stage0.propellant_mass_kg,
                    drop_after_kg=stage_dry[0] + booster_dry_kg + (booster_prop_kg - burnt),
                )
            )
    else:
        phases.append(
            _Phase(
                label="stage1_separation",
                thrusters=(stage_thrusters[0],),
                duration_s=t0,
                propellant_kg=stage0.propellant_mass_kg,
                drop_after_kg=stage_dry[0],
            )
        )
    for i in range(1, len(design.stages)):
        # SIMPLIFICATION: upper stages ignite immediately at separation (no coast, no ullage).
        stage = design.stages[i]
        phases.append(
            _Phase(
                label=f"stage{i + 1}_separation",
                thrusters=(stage_thrusters[i],),
                duration_s=stage.propellant_mass_kg / stage_thrusters[i].mdot_kgps,
                propellant_kg=stage.propellant_mass_kg,
                drop_after_kg=stage_dry[i],
            )
        )

    liftoff_mass = (
        sum(stage_wet)
        + booster_prop_kg
        + booster_dry_kg
        + design.fairing_mass_kg
        + design.payload_mass_kg
    )
    stage0_spec = get_engine(stage0.engine_id, kind="engine")
    liftoff_thrust_sl = (
        stage0_spec.thrust_sl_n * stage0.engine_count * thrust_scale + booster_thrust_sl_n
    )
    total_prop = sum(s.propellant_mass_kg for s in design.stages) + booster_prop_kg
    diameter_m = DIAMETER_PER_CUBE_ROOT_KG * total_prop ** (1.0 / 3.0)
    return _Vehicle(
        phases=tuple(phases),
        liftoff_mass_kg=liftoff_mass,
        liftoff_thrust_sl_n=liftoff_thrust_sl,
        fairing_mass_kg=design.fairing_mass_kg,
        reference_area_m2=math.pi * diameter_m**2 / 4.0,
        stage_wet_kg=tuple(stage_wet),
        stage_dry_kg=tuple(stage_dry),
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- trajectory


@dataclass(frozen=True)
class AscentOptions:
    """Physics switches (all on for real runs, off individually for verification tests) and
    the orbit-insertion targets. With `target_perigee_m` and `insertion="coast_circularize"`
    the last stage is flown as burn-to-apogee / coast / circularize (see the module docstring);
    `"direct"` keeps the single burn to depletion."""

    gravity: bool = True
    drag: bool = True
    atmosphere: bool = True  # off -> vacuum Isp everywhere and no drag
    target_perigee_m: float | None = None
    target_apogee_m: float | None = None
    insertion: str = "coast_circularize"
    # The burn-to-apogee cutoff is armed only once the osculating perigee is above this
    # altitude (see CUTOFF_MIN_PERIGEE_M).
    cutoff_min_perigee_m: float = CUTOFF_MIN_PERIGEE_M

    def __post_init__(self) -> None:
        if self.insertion not in INSERTION_MODES:
            raise ValueError(f"insertion must be one of {INSERTION_MODES}, got {self.insertion!r}")

    @property
    def circularize(self) -> bool:
        return self.insertion == "coast_circularize" and self.target_perigee_m is not None

    @property
    def apogee_target_m(self) -> float | None:
        if self.target_apogee_m is not None:
            return self.target_apogee_m
        return self.target_perigee_m


@dataclass(frozen=True)
class MassEvent:
    t_s: float
    label: str  # "stage1_separation", "booster_separation", "fairing_jettison", ...
    mass_before_kg: float
    mass_after_kg: float


@dataclass
class Ascent:
    """Raw integration output. Arrays are sampled at the integrator steps (<= 2 s apart while
    thrusting, <= 10 s during the coast)."""

    t_s: NDArray[np.float64]
    x_m: NDArray[np.float64]
    y_m: NDArray[np.float64]
    vx_mps: NDArray[np.float64]
    vy_mps: NDArray[np.float64]
    mass_kg: NDArray[np.float64]
    dynamic_pressure_pa: NDArray[np.float64]
    events: list[MassEvent]
    liftoff_mass_kg: float
    liftoff_thrust_sl_n: float
    reference_area_m2: float
    stage_wet_kg: tuple[float, ...]
    stage_dry_kg: tuple[float, ...]
    dv_ideal_mps: float
    dv_gravity_loss_mps: float
    dv_drag_loss_mps: float
    dv_pressure_loss_mps: float
    initial_speed_mps: float  # eastward surface speed when Earth rotation is on
    impacted: bool
    burnout_index: int  # sample index of the final engine cutoff (end of the last burn)
    insertion: str  # "direct" | "coast_circularize"
    apogee_reached: bool  # coast_circularize: the burn-to-apogee cutoff fired before depletion
    perigee_reached: bool  # coast_circularize: the circularization cutoff fired before depletion
    coast_time_s: float
    circularization_dv_mps: float  # ideal delta-v spent in the circularization burn
    propellant_margin_kg: float  # leftover propellant in the last stage after insertion
    propellant_margin_dv_mps: float  # its ideal delta-v at the final mass
    aborted: bool = False  # integrator event root-finding failed; trajectory is truncated
    warnings: list[str] = field(default_factory=list)

    @property
    def altitude_m(self) -> NDArray[np.float64]:
        return np.hypot(self.x_m, self.y_m) - R_EARTH_M

    @property
    def speed_mps(self) -> NDArray[np.float64]:
        return np.hypot(self.vx_mps, self.vy_mps)

    @property
    def downrange_m(self) -> NDArray[np.float64]:
        """Ground track from the pad along the great circle (launch is on the +y axis)."""
        return R_EARTH_M * np.arctan2(self.x_m, self.y_m)

    @property
    def final_state(self) -> tuple[float, float, float, float]:
        return (
            float(self.x_m[-1]),
            float(self.y_m[-1]),
            float(self.vx_mps[-1]),
            float(self.vy_mps[-1]),
        )


class _Dynamics:
    """Right-hand side of the equations of motion, parameterised per phase.

    State: [x, y, vx, vy, m, L_gravity, L_drag, L_pressure]; the last three accumulate the
    delta-v losses so the budget closes: v_burnout = dv_ideal - losses (+ initial speed).
    """

    def __init__(self, vehicle: _Vehicle, env: Env, options: AscentOptions) -> None:
        self.vehicle = vehicle
        self.options = options
        self.temperature_offset_k = env.temperature_offset_k
        # SIMPLIFICATION: with Earth rotation on, the in-plane component of the co-rotating
        # atmosphere is omega * cos(latitude), as if the trajectory plane were the equator.
        self.omega_radps = (
            OMEGA_EARTH_RADPS * math.cos(math.radians(env.launch_latitude_deg))
            if env.earth_rotation
            else 0.0
        )
        self.kicked = False
        self.kick_dir: tuple[float, float] = (0.0, 1.0)
        self.phase: _Phase = vehicle.phases[0]

    def air_velocity(self, x: float, y: float) -> tuple[float, float]:
        return self.omega_radps * y, -self.omega_radps * x

    def thrust_direction(
        self, rhat: tuple[float, float], vrel: tuple[float, float], speed_rel: float
    ) -> tuple[float, float]:
        if not self.kicked:
            return rhat  # vertical rise
        if speed_rel < 1e-3:
            return self.kick_dir
        return vrel[0] / speed_rel, vrel[1] / speed_rel  # zero angle of attack

    def dynamic_pressure_pa(self, state: NDArray[np.float64]) -> float:
        x, y, vx, vy = (float(v) for v in state[:4])
        if not (self.options.atmosphere and self.options.drag):
            return 0.0
        alt = math.hypot(x, y) - R_EARTH_M
        _, _, rho = atm.state_scalar(alt, self.temperature_offset_k)
        ax, ay = self.air_velocity(x, y)
        return 0.5 * rho * ((vx - ax) ** 2 + (vy - ay) ** 2)

    def __call__(self, t: float, state: NDArray[np.float64]) -> list[float]:
        x, y, vx, vy, m = (float(v) for v in state[:5])
        r = math.hypot(x, y)
        rhat = (x / r, y / r)
        alt = r - R_EARTH_M
        ax, ay = self.air_velocity(x, y)
        vrel = (vx - ax, vy - ay)
        speed_rel = math.hypot(*vrel)
        u = self.thrust_direction(rhat, vrel, speed_rel)

        if self.options.atmosphere:
            _, p, rho = atm.state_scalar(alt, self.temperature_offset_k)
            # SIMPLIFICATION: no hypersonic speed-of-sound subtleties; T from the same model.
            t_k = atm.state_scalar(alt, 0.0)[0]
            sound = math.sqrt(atm.GAMMA_AIR * atm.R_SPECIFIC_AIR_JPKGK * t_k)
        else:
            p, rho, sound = 0.0, 0.0, 1.0

        phase = self.phase
        thrust = sum(th.mdot_kgps * G0_MPS2 * _isp(th, p) for th in phase.thrusters)
        thrust_vac = phase.thrust_vac_n

        drag = 0.0
        if self.options.drag and rho > 0.0 and speed_rel > 0.0:
            cd = float(np.interp(speed_rel / sound, _CD_MACH, _CD_VALUE))
            drag = 0.5 * rho * speed_rel**2 * cd * self.vehicle.reference_area_m2
        g = MU_EARTH_M3PS2 / (r * r) if self.options.gravity else 0.0

        a_t = thrust / m
        a_d = drag / m
        dvx = a_t * u[0] - g * rhat[0]
        dvy = a_t * u[1] - g * rhat[1]
        if a_d > 0.0:
            dvx -= a_d * vrel[0] / speed_rel
            dvy -= a_d * vrel[1] / speed_rel
        # Gravity loss only accrues while thrusting (a coast has no delta-v budget to lose).
        g_loss = g * (u[0] * rhat[0] + u[1] * rhat[1]) if thrust > 0.0 else 0.0
        return [
            vx,
            vy,
            dvx,
            dvy,
            -phase.mdot_kgps,
            g_loss,
            a_d,
            (thrust_vac - thrust) / m,
        ]


def _isp(th: _Thruster, p_pa: float) -> float:
    frac = min(max(p_pa / SEA_LEVEL_PRESSURE_PA, 0.0), 1.0)
    return th.isp_vac_s - (th.isp_vac_s - th.isp_sl_s) * frac


def _rotate_clockwise(vx: float, vy: float, angle_rad: float) -> tuple[float, float]:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return vx * c + vy * s, -vx * s + vy * c


def _radial_speed_mps(s: NDArray[np.float64]) -> float:
    x, y, vx, vy = (float(v) for v in s[:4])
    return (x * vx + y * vy) / math.hypot(x, y)


def _half_period_s(x: float, y: float, vx: float, vy: float) -> float | None:
    """Half the osculating orbital period (an upper bound on the time to apogee), or None when
    the state is not elliptic."""
    r = math.hypot(x, y)
    energy = 0.5 * (vx * vx + vy * vy) - MU_EARTH_M3PS2 / r
    if energy >= 0.0:
        return None
    a = -MU_EARTH_M3PS2 / (2.0 * energy)
    return math.pi * math.sqrt(a**3 / MU_EARTH_M3PS2)


def _apsis_speed_mps(r_m: float, r_other_m: float) -> float:
    """Speed at radius `r_m` on the ellipse whose other apsis is `r_other_m` (vis-viva)."""
    return math.sqrt(2.0 * MU_EARTH_M3PS2 * r_other_m / (r_m * (r_m + r_other_m)))


def run_ascent(
    design: MultistageDesign,
    env: Env,
    options: AscentOptions,
    *,
    isp_scale: float = 1.0,
    thrust_scale: float = 1.0,
) -> Ascent:
    """Integrate the ascent through all burn phases and return the raw trajectory.

    Lower stages (and boosters) burn to depletion back to back. The last stage depends on
    `options`: in `"direct"` mode (or without a target) it also burns to depletion; in
    `"coast_circularize"` mode it burns until the osculating apogee reaches the target apogee,
    coasts to apogee and burns again until the osculating perigee reaches the target perigee
    (or the propellant runs out, in which case the achieved orbit is reported and
    `perigee_reached` is False). If the apogee target is out of reach the stage burns out, the
    vehicle still coasts to its apogee and `apogee_reached` is False.

    SIMPLIFICATION: the three cutoffs are integration events on the osculating orbit (apogee
    altitude with the perigee above `options.cutoff_min_perigee_m`, radial speed crossing
    zero, perigee altitude), not a guidance law: thrust stays
    along the velocity vector (zero angle of attack) throughout, including during the
    circularization burn, so a long low-thrust burn at apogee loses altitude. Engine cutoff at
    a target apogee followed by a coast is how concept-level ascent budgets are usually drawn
    up, and it keeps the ascent open-loop in the sense of CLAUDE.md section 4.
    """
    vehicle = _build_vehicle(design, isp_scale=isp_scale, thrust_scale=thrust_scale)
    dyn = _Dynamics(vehicle, env, options)
    circularize = options.circularize
    target_perigee_m = options.target_perigee_m
    target_apogee_m = options.apogee_target_m

    r0 = R_EARTH_M + env.launch_altitude_m
    x0, y0 = 0.0, r0
    vx0, vy0 = dyn.air_velocity(x0, y0)  # vehicle at rest on the (possibly rotating) pad
    initial_speed = math.hypot(vx0, vy0)
    state = np.array([x0, y0, vx0, vy0, vehicle.liftoff_mass_kg, 0.0, 0.0, 0.0])

    t = 0.0
    fairing_pending = vehicle.fairing_mass_kg > 0.0
    impacted = False
    aborted = False
    events: list[MassEvent] = []
    warnings: list[str] = list(vehicle.warnings)
    ts: list[NDArray[np.float64]] = []
    ys: list[NDArray[np.float64]] = []

    def sample_count() -> int:
        return sum(len(a) for a in ts)

    # ---- integration events (terminal; `direction` makes them one-sided)
    def impact(_t: float, s: NDArray[np.float64]) -> float:
        # Trigger 1 m below the pad so the t=0 sample never fires it.
        return math.hypot(s[0], s[1]) - r0 + 1.0

    impact.terminal = True  # type: ignore[attr-defined]
    impact.direction = -1  # type: ignore[attr-defined]

    def fairing(_t: float, s: NDArray[np.float64]) -> float:
        return math.hypot(s[0], s[1]) - R_EARTH_M - FAIRING_JETTISON_ALTITUDE_M

    fairing.terminal = True  # type: ignore[attr-defined]
    fairing.direction = 1  # type: ignore[attr-defined]

    # Mass the current burn ends at (propellant empty); lowered further if the fairing goes
    # mid-burn. A one-element list so the burnout event closure sees updates. The span end is
    # the authoritative burnout time (mass is linear in time); the event is only a safety net
    # 1 g past empty, which also keeps solve_ivp's root finder away from the exact-zero value
    # at the span end that used to raise "f(a) and f(b) must have different signs".
    m_phase_end = [0.0]

    def burnout(_t: float, s: NDArray[np.float64]) -> float:
        return s[4] - m_phase_end[0] + 1e-3

    burnout.terminal = True  # type: ignore[attr-defined]
    burnout.direction = -1  # type: ignore[attr-defined]

    def apogee_reached(_t: float, s: NDArray[np.float64]) -> float:
        # Fires when the osculating apogee has reached the target AND the orbit is closed
        # (perigee above `cutoff_min_perigee_m`); min() keeps the event continuous.
        rp, ra, _ = _orbit_elements(*(float(v) for v in s[:4]))
        return min(ra - float(target_apogee_m or 0.0), rp - options.cutoff_min_perigee_m)

    apogee_reached.terminal = True  # type: ignore[attr-defined]
    apogee_reached.direction = 1  # type: ignore[attr-defined]

    def apogee_passed(_t: float, s: NDArray[np.float64]) -> float:
        return _radial_speed_mps(s)

    apogee_passed.terminal = True  # type: ignore[attr-defined]
    apogee_passed.direction = -1  # type: ignore[attr-defined]

    def perigee_reached(_t: float, s: NDArray[np.float64]) -> float:
        # Fires when the osculating perigee reaches the target, OR when the horizontal speed
        # passes the local circular speed: from then on the current point is the perigee and
        # burning on would only raise the apogee (the apsides swap once the speed passes
        # circular, so "perigee >= target" alone is not monotonic). max() keeps the event
        # continuous; both terms rise monotonically during a prograde burn.
        x, y, vx, vy = (float(v) for v in s[:4])
        rp, _, _ = _orbit_elements(x, y, vx, vy)
        r_now = math.hypot(x, y)
        v_h = abs(x * vy - y * vx) / r_now  # |h| / r: the gravity turn runs clockwise
        return max(
            rp - float(target_perigee_m or 0.0),
            v_h - math.sqrt(MU_EARTH_M3PS2 / r_now),
        )

    perigee_reached.terminal = True  # type: ignore[attr-defined]
    perigee_reached.direction = 1  # type: ignore[attr-defined]

    def apply_kick() -> None:
        ax, ay = dyn.air_velocity(float(state[0]), float(state[1]))
        vrx, vry = float(state[2]) - ax, float(state[3]) - ay
        r = math.hypot(float(state[0]), float(state[1]))
        rhat = (float(state[0]) / r, float(state[1]) / r)
        angle = math.radians(design.initial_pitch_deg)
        dyn.kick_dir = _rotate_clockwise(rhat[0], rhat[1], angle)
        # SIMPLIFICATION: instantaneous pitch kick rotates the air-relative velocity vector.
        nvx, nvy = _rotate_clockwise(vrx, vry, angle)
        state[2], state[3] = nvx + ax, nvy + ay
        dyn.kicked = True

    def integrate(t_end: float, extra: list[Any], max_step: float) -> str:
        """Advance to `t_end` handling the pitch kick, the fairing and impact; returns "end",
        "impact", "aborted" or the name of the `extra` event that fired."""
        nonlocal t, state, impacted, aborted, fairing_pending
        while t < t_end - 1e-9:
            if not dyn.kicked and design.pitch_start_s <= t + 1e-9:
                apply_kick()
            t_stop = t_end
            if not dyn.kicked and design.pitch_start_s < t_stop:
                t_stop = design.pitch_start_s
            with_fairing = fairing_pending
            event_fns = [impact] + ([fairing] if with_fairing else []) + extra
            try:
                sol = solve_ivp(
                    dyn,
                    (t, t_stop),
                    state,
                    method="RK45",
                    events=event_fns,
                    max_step=max_step,
                    rtol=_RTOL,
                    atol=_ATOL,
                )
            except ValueError as exc:
                # solve_ivp's event root-finding can fail on a grazing crossing; treat the
                # ascent as failed rather than crashing the caller (tuner, dispersion).
                aborted = True
                warnings.append(
                    f"ascent integration aborted at t = {t:.1f} s (event root-finding: {exc})"
                )
                return "aborted"
            if not sol.success:
                raise RuntimeError(f"multistage integration failed: {sol.message}")
            ts.append(sol.t)
            ys.append(sol.y)
            t = float(sol.t[-1])
            state = sol.y[:, -1].copy()
            if sol.t_events[0].size:  # impact
                impacted = True
                return "impact"
            if with_fairing and sol.t_events[1].size:
                fairing_pending = False
                before = float(state[4])
                state[4] = before - vehicle.fairing_mass_kg
                m_phase_end[0] -= vehicle.fairing_mass_kg
                events.append(MassEvent(t, "fairing_jettison", before, float(state[4])))
                continue
            offset = 2 if with_fairing else 1
            for k, fn in enumerate(extra):
                if sol.t_events[offset + k].size:
                    return str(fn.__name__)
        return "end"

    def burn(phase: _Phase, propellant_kg: float, extra: list[Any]) -> str:
        """Burn `propellant_kg` through `phase`'s thrusters (or until an `extra` event)."""
        dyn.phase = phase
        m_phase_end[0] = float(state[4]) - propellant_kg
        t_end = t + propellant_kg / phase.mdot_kgps
        outcome = integrate(t_end, [burnout, *extra], _MAX_STEP_S)
        if outcome in ("end", "burnout"):
            # Depletion (span end or the 1 g safety net): snap the propellant to exactly empty.
            state[4] = m_phase_end[0]
            return "depleted"
        return outcome

    last = len(vehicle.phases) - 1
    apogee_hit = not circularize
    perigee_hit = not circularize
    for i, phase in enumerate(vehicle.phases):
        if i == last and circularize:
            break
        outcome = burn(phase, phase.propellant_kg, [])
        if outcome != "depleted":
            break
        # End of phase: drop the spent hardware.
        before = float(state[4])
        state[4] = before - phase.drop_after_kg
        events.append(MassEvent(t, phase.label, before, float(state[4])))

    coast_time_s = 0.0
    circ_dv_mps = 0.0
    propellant_left_kg = 0.0
    burnout_index = max(sample_count() - 1, 0)
    if circularize and not impacted and not aborted:
        phase = vehicle.phases[last]
        # --- burn 1: raise the osculating apogee to the target (zero-length if already above)
        if apogee_reached(t, state) >= 0.0:
            dyn.phase = phase
            m_phase_end[0] = float(state[4]) - phase.propellant_kg
            outcome = "apogee_reached"
        else:
            outcome = burn(phase, phase.propellant_kg, [apogee_reached])
        apogee_hit = outcome == "apogee_reached"
        propellant_left_kg = max(float(state[4]) - m_phase_end[0], 0.0)
        if propellant_left_kg < _EMPTY_PROPELLANT_KG:
            propellant_left_kg = 0.0
        if outcome in ("depleted", "apogee_reached"):
            burnout_index = max(sample_count() - 1, 0)
            m_now = float(state[4])
            events.append(MassEvent(t, "coast_start", m_now, m_now))
            # --- coast to apogee (unpowered; drag stays on and fades with the atmosphere)
            half_period = _half_period_s(*(float(v) for v in state[:4]))
            if half_period is not None and _radial_speed_mps(state) > 0.0:
                t_coast_start = t
                coast = _Phase("coast", (), half_period, 0.0, 0.0)
                dyn.phase = coast
                outcome = integrate(t + 1.05 * half_period, [apogee_passed], _COAST_MAX_STEP_S)
                coast_time_s = t - t_coast_start
            else:
                outcome = "end"  # descending or not elliptic: nothing to coast to
            # --- burn 2: raise the osculating perigee to the target with what is left
            if outcome in ("end", "apogee_passed"):
                rp_now, _, _ = _orbit_elements(*(float(v) for v in state[:4]))
                if propellant_left_kg > 0.0 and rp_now < float(target_perigee_m or 0.0):
                    m_before = float(state[4])
                    events.append(MassEvent(t, "circularization_ignition", m_before, m_before))
                    outcome = burn(phase, propellant_left_kg, [perigee_reached])
                    perigee_hit = outcome == "perigee_reached"
                    m_after = float(state[4])
                    circ_dv_mps = phase.isp_vac_effective_s * G0_MPS2 * math.log(m_before / m_after)
                    propellant_left_kg = max(m_after - m_phase_end[0], 0.0)
                    if propellant_left_kg < _EMPTY_PROPELLANT_KG:
                        propellant_left_kg = 0.0
                        state[4] = m_phase_end[0]
                    if outcome in ("depleted", "perigee_reached"):
                        burnout_index = max(sample_count() - 1, 0)
                        events.append(MassEvent(t, "circularization_cutoff", m_after, m_after))
                else:
                    perigee_hit = rp_now >= float(target_perigee_m or 0.0)
            if not impacted and not aborted:
                before = float(state[4])
                state[4] = before - phase.drop_after_kg - propellant_left_kg
                events.append(MassEvent(t, phase.label, before, float(state[4])))

    if not ts:  # aborted before the first step: keep the initial state as the only sample
        ts.append(np.array([t]))
        ys.append(state.reshape(-1, 1).copy())
    t_all = np.concatenate(ts)
    y_all = np.concatenate(ys, axis=1)
    burnout_index = min(burnout_index, len(t_all) - 1)
    # Keep mass continuous with the events: samples are pre-drop, which is what we want.
    q = np.array([dyn.dynamic_pressure_pa(y_all[:, i]) for i in range(y_all.shape[1])])

    m_final = float(y_all[4, -1])
    margin_dv = 0.0
    if propellant_left_kg > 0.0 and m_final > propellant_left_kg:
        margin_dv = (
            vehicle.phases[last].isp_vac_effective_s
            * G0_MPS2
            * math.log(m_final / (m_final - propellant_left_kg))
        )
    dv_ideal = _ideal_dv_mps(vehicle, 0.0)
    return Ascent(
        t_s=t_all,
        x_m=y_all[0],
        y_m=y_all[1],
        vx_mps=y_all[2],
        vy_mps=y_all[3],
        mass_kg=y_all[4],
        dynamic_pressure_pa=q,
        events=events,
        liftoff_mass_kg=vehicle.liftoff_mass_kg,
        liftoff_thrust_sl_n=vehicle.liftoff_thrust_sl_n,
        reference_area_m2=vehicle.reference_area_m2,
        stage_wet_kg=vehicle.stage_wet_kg,
        stage_dry_kg=vehicle.stage_dry_kg,
        dv_ideal_mps=dv_ideal,
        dv_gravity_loss_mps=float(y_all[5, -1]),
        dv_drag_loss_mps=float(y_all[6, -1]),
        dv_pressure_loss_mps=float(y_all[7, -1]),
        initial_speed_mps=initial_speed,
        impacted=impacted,
        burnout_index=burnout_index,
        insertion=options.insertion if circularize else "direct",
        apogee_reached=apogee_hit,
        perigee_reached=perigee_hit,
        coast_time_s=coast_time_s,
        circularization_dv_mps=circ_dv_mps,
        propellant_margin_kg=propellant_left_kg,
        propellant_margin_dv_mps=margin_dv,
        aborted=aborted,
        warnings=warnings,
    )


def _ideal_dv_mps(vehicle: _Vehicle, extra_payload_kg: float) -> float:
    """Rocket-equation delta-v (vacuum Isp) over the phase sequence with extra payload added."""
    m = vehicle.liftoff_mass_kg + extra_payload_kg
    fairing_dropped = False
    total = 0.0
    for phase in vehicle.phases:
        m_end = m - phase.propellant_kg
        total += phase.isp_vac_effective_s * G0_MPS2 * math.log(m / m_end)
        m = m_end - phase.drop_after_kg
        # SIMPLIFICATION: for the ideal budget the fairing is dropped after the first phase.
        if not fairing_dropped:
            m -= vehicle.fairing_mass_kg
            fairing_dropped = True
    return total


# --------------------------------------------------------------------------- orbit + metrics


def _orbit_elements(x: float, y: float, vx: float, vy: float) -> tuple[float, float, bool]:
    """(perigee_altitude_m, apogee_altitude_m, is_escape) from the 2-D state."""
    r = math.hypot(x, y)
    v2 = vx * vx + vy * vy
    h = x * vy - y * vx
    energy = 0.5 * v2 - MU_EARTH_M3PS2 / r
    e = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h * h / MU_EARTH_M3PS2**2))
    rp = h * h / (MU_EARTH_M3PS2 * (1.0 + e))
    if energy >= 0.0:
        return rp - R_EARTH_M, ESCAPE_APOGEE_SENTINEL_M, True
    a = -MU_EARTH_M3PS2 / (2.0 * energy)
    return rp - R_EARTH_M, a * (1.0 + e) - R_EARTH_M, False


def _dv_to_reference_orbit_mps(
    perigee_m: float, apogee_m: float, reference_perigee_m: float
) -> float:
    """Impulsive delta-v still needed to lift the osculating (perigee, apogee) orbit's perigee to
    the reference altitude: a burn at apogee, plus a circularization at the reference altitude
    when the apogee itself is below it. Zero once the perigee is at or above the reference."""
    r_ref = R_EARTH_M + reference_perigee_m
    rp = max(R_EARTH_M + perigee_m, 0.0)
    ra = R_EARTH_M + apogee_m
    if rp >= r_ref or not math.isfinite(ra) or ra >= ESCAPE_APOGEE_SENTINEL_M:
        return 0.0
    dv = _apsis_speed_mps(ra, r_ref) - _apsis_speed_mps(ra, rp)
    if ra < r_ref:
        dv += math.sqrt(MU_EARTH_M3PS2 / r_ref) - _apsis_speed_mps(r_ref, ra)
    return max(dv, 0.0)


def _required_dv_mps(ascent: Ascent, reference_perigee_m: float) -> float:
    """Ideal delta-v the vehicle must deliver to put the flown payload on the reference orbit.

    coast_circularize: the propellant actually burnt (ideal budget minus the leftover's
    delta-v) plus the impulsive delta-v still missing from the final osculating orbit
    (`_dv_to_reference_orbit_mps`; zero when the perigee target was reached).
    direct (single burn): the circular-orbit energy at the reference altitude charged from
    the burnout radius, v_req^2 = v_circ(r_ref)^2 + 2 mu (1 / r_burnout - 1 / r_ref), minus the
    pad speed, plus the simulated losses held fixed.
    SIMPLIFICATION: losses are those of the flown trajectory and are not re-flown for the
    changed payload.
    """
    xf, yf, vxf, vyf = ascent.final_state
    r_final = math.hypot(xf, yf)
    r_ref = R_EARTH_M + reference_perigee_m
    if ascent.insertion == "coast_circularize":
        rp, ra, _ = _orbit_elements(xf, yf, vxf, vyf)
        return (
            ascent.dv_ideal_mps
            - ascent.propellant_margin_dv_mps
            + _dv_to_reference_orbit_mps(rp, ra, reference_perigee_m)
        )
    v_req_sq = MU_EARTH_M3PS2 / r_ref + 2.0 * MU_EARTH_M3PS2 * (1.0 / r_final - 1.0 / r_ref)
    v_req = math.sqrt(max(v_req_sq, 0.0))
    return (
        v_req
        - ascent.initial_speed_mps
        + ascent.dv_gravity_loss_mps
        + ascent.dv_drag_loss_mps
        + ascent.dv_pressure_loss_mps
    )


def _payload_margin_kg(
    vehicle: _Vehicle, ascent: Ascent, reference_perigee_m: float, payload_mass_kg: float
) -> float:
    """Extra payload (negative = shortfall) that still reaches the reference orbit: the ideal
    rocket equation is inverted for the payload at which the vehicle's ideal delta-v equals
    `_required_dv_mps` (leftover propellant thus becomes payload, a shortfall becomes a
    negative margin)."""
    dv_needed = _required_dv_mps(ascent, reference_perigee_m)

    def shortfall(extra_kg: float) -> float:
        return _ideal_dv_mps(vehicle, extra_kg) - dv_needed

    lo = -payload_mass_kg + 1e-6
    hi = 10.0 * vehicle.liftoff_mass_kg
    if shortfall(lo) <= 0.0:
        return -payload_mass_kg
    if shortfall(hi) >= 0.0:
        return hi
    return float(brentq(shortfall, lo, hi, xtol=1e-3))


def _build_trace(ascent: Ascent) -> list[TracePoint]:
    alt = ascent.altitude_m
    down = ascent.downrange_m
    speed = ascent.speed_mps
    points = [
        TracePoint(
            t_s=float(ascent.t_s[i]),
            altitude_m=float(alt[i]),
            downrange_m=float(down[i]),
            speed_mps=float(speed[i]),
            mass_kg=float(ascent.mass_kg[i]),
            extra={"dynamic_pressure_pa": float(ascent.dynamic_pressure_pa[i])},
        )
        for i in range(len(ascent.t_s))
    ]
    return decimate_trace(points, MAX_TRACE_POINTS)


def _check_design(design: Design) -> MultistageDesign:
    if not isinstance(design, MultistageDesign):
        raise ValueError(
            f"multistage.simulate requires a design with tier commercial/heavy, got {design.tier!r}"
        )
    return design


def simulate_with_options(
    design: Design,
    env: Env,
    *,
    gravity: bool = True,
    drag: bool = True,
    atmosphere: bool = True,
    target_perigee_m: float | None = None,
    target_apogee_m: float | None = None,
    insertion: str = "coast_circularize",
    isp_scale: float = 1.0,
    thrust_scale: float = 1.0,
) -> SimResult:
    """`simulate` with physics switches (tests use them to isolate the rocket equation)."""
    ms_design = _check_design(design)
    options = AscentOptions(
        gravity=gravity,
        drag=drag,
        atmosphere=atmosphere,
        target_perigee_m=target_perigee_m,
        target_apogee_m=target_apogee_m,
        insertion=insertion,
    )
    vehicle = _build_vehicle(ms_design, isp_scale=isp_scale, thrust_scale=thrust_scale)
    ascent = run_ascent(ms_design, env, options, isp_scale=isp_scale, thrust_scale=thrust_scale)

    perigee_m, apogee_m, escape = _orbit_elements(*ascent.final_state)
    alt = ascent.altitude_m
    i_b = ascent.burnout_index
    i_q = int(np.argmax(ascent.dynamic_pressure_pa))
    twr = ascent.liftoff_thrust_sl_n / (ascent.liftoff_mass_kg * G0_MPS2)
    reference_perigee_m = (
        target_perigee_m if target_perigee_m is not None else PASS_THRESHOLDS["min_perigee_m"]
    )
    margin_kg = _payload_margin_kg(vehicle, ascent, reference_perigee_m, ms_design.payload_mass_kg)

    metrics: dict[str, float] = {
        "perigee_m": perigee_m,
        "apogee_m": apogee_m,
        "burnout_speed_mps": float(ascent.speed_mps[i_b]),
        "burnout_altitude_m": float(alt[i_b]),
        "burnout_downrange_m": float(ascent.downrange_m[i_b]),
        "burnout_time_s": float(ascent.t_s[i_b]),
        "dv_ideal_mps": ascent.dv_ideal_mps,
        "dv_gravity_loss_mps": ascent.dv_gravity_loss_mps,
        "dv_drag_loss_mps": ascent.dv_drag_loss_mps,
        "dv_pressure_loss_mps": ascent.dv_pressure_loss_mps,
        "max_q_pa": float(ascent.dynamic_pressure_pa[i_q]),
        "max_q_altitude_m": float(alt[i_q]),
        "max_q_time_s": float(ascent.t_s[i_q]),
        "payload_margin_kg": margin_kg,
        "propellant_margin_kg": ascent.propellant_margin_kg,
        "coast_time_s": ascent.coast_time_s,
        "circularization_dv_mps": ascent.circularization_dv_mps,
        "total_liftoff_mass_kg": ascent.liftoff_mass_kg,
        "liftoff_thrust_n": ascent.liftoff_thrust_sl_n,
        "liftoff_twr_ratio": twr,
        "reference_area_m2": ascent.reference_area_m2,
        "flight_time_s": float(ascent.t_s[-1]),
    }
    for i, (wet, dry) in enumerate(zip(ascent.stage_wet_kg, ascent.stage_dry_kg, strict=True)):
        metrics[f"stage{i + 1}_wet_mass_kg"] = wet
        metrics[f"stage{i + 1}_dry_mass_kg"] = dry
    for ev in ascent.events:
        metrics[f"{ev.label}_time_s"] = ev.t_s

    failures: list[str] = []
    warnings = list(ascent.warnings)
    if ascent.aborted:
        failures.append("ascent integration aborted (see warnings); trajectory is truncated")
    if ascent.impacted:
        failures.append(f"vehicle impacted the ground at t = {ascent.t_s[-1]:.1f} s")
    if twr < PASS_THRESHOLDS["min_liftoff_twr_ratio"]:
        failures.append(
            f"liftoff thrust-to-weight {twr:.2f} < {PASS_THRESHOLDS['min_liftoff_twr_ratio']}"
        )
    elif twr < PASS_THRESHOLDS["warn_liftoff_twr_ratio"]:
        warnings.append(
            f"liftoff thrust-to-weight {twr:.2f} is below "
            f"{PASS_THRESHOLDS['warn_liftoff_twr_ratio']} (slow initial climb)"
        )
    if metrics["max_q_pa"] > PASS_THRESHOLDS["max_q_pa"]:
        failures.append(
            f"max dynamic pressure {metrics['max_q_pa'] / 1e3:.1f} kPa > "
            f"{PASS_THRESHOLDS['max_q_pa'] / 1e3:.0f} kPa"
        )
    if ascent.insertion == "coast_circularize" and not ascent.apogee_reached:
        rp_b, ra_b, _ = _orbit_elements(
            *(float(a[i_b]) for a in (ascent.x_m, ascent.y_m, ascent.vx_mps, ascent.vy_mps))
        )
        failures.append(
            f"upper stage burned out before the insertion cutoff (needs apogee >= "
            f"{(options.apogee_target_m or 0.0) / 1e3:.0f} km and perigee >= "
            f"{options.cutoff_min_perigee_m / 1e3:.0f} km; had apogee "
            f"{min(ra_b, ESCAPE_APOGEE_SENTINEL_M) / 1e3:.0f} km, perigee {rp_b / 1e3:.0f} km); "
            "no circularization"
        )
    if target_perigee_m is not None:
        floor = target_perigee_m * (1.0 - PASS_THRESHOLDS["perigee_tolerance_frac"])
        if perigee_m < floor:
            failures.append(
                f"perigee {perigee_m / 1e3:.1f} km below target {target_perigee_m / 1e3:.0f} km "
                f"(tolerance -{PASS_THRESHOLDS['perigee_tolerance_frac'] * 100:.0f} %)"
            )
    elif perigee_m < PASS_THRESHOLDS["min_perigee_m"]:
        failures.append(
            f"perigee {perigee_m / 1e3:.1f} km below minimum "
            f"{PASS_THRESHOLDS['min_perigee_m'] / 1e3:.0f} km"
        )
    if target_apogee_m is not None:
        tol = target_apogee_m * PASS_THRESHOLDS["apogee_tolerance_frac"]
        if abs(apogee_m - target_apogee_m) > tol:
            failures.append(
                f"apogee {apogee_m / 1e3:.1f} km not within +/-"
                f"{PASS_THRESHOLDS['apogee_tolerance_frac'] * 100:.0f} % of "
                f"{target_apogee_m / 1e3:.0f} km"
            )
    if escape:
        warnings.append("final state is hyperbolic (escape); apogee reported as sentinel")
    if not atmosphere or not drag or not gravity:
        warnings.append("physics switches off (verification mode): not a flight prediction")

    return SimResult(
        tier=Tier(ms_design.tier),
        success=not failures,
        failure_reasons=failures,
        metrics=metrics,
        cost_jpy=0.0,  # cost.py owns the estimate; the agent fills it in.
        trace=_build_trace(ascent),
        warnings=warnings,
    )


def simulate(
    design: Design,
    env: Env,
    seed: int | None = None,
    *,
    target_perigee_m: float | None = None,
    target_apogee_m: float | None = None,
    insertion: str = "coast_circularize",
    isp_scale: float = 1.0,
    thrust_scale: float = 1.0,
) -> SimResult:
    """Common physics interface (CLAUDE.md section 6). `seed` is accepted for interface
    compatibility; the nominal multistage model is deterministic and ignores it. `insertion`
    selects the orbit-insertion mode used when `target_perigee_m` is given (module docstring).
    `isp_scale` / `thrust_scale` (default 1.0) multiply every engine's Isp / thrust: the
    dispersion perturbs them."""
    del seed
    return simulate_with_options(
        design,
        env,
        target_perigee_m=target_perigee_m,
        target_apogee_m=target_apogee_m,
        insertion=insertion,
        isp_scale=isp_scale,
        thrust_scale=thrust_scale,
    )


# --------------------------------------------------------------------------- pitch tuning

_PITCH_START_BOUNDS_S = (5.0, 120.0)
_PITCH_ANGLE_BOUNDS_DEG = (0.5, 60.0)
# Coarse seed grid (log-spaced, 6 x 8 = 48 ascents) covering the whole box.
_SEED_STARTS_S = (5.0, 10.0, 20.0, 40.0, 80.0, 120.0)
_SEED_ANGLES_DEG = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
_MARGIN_WEIGHT = 0.01  # objective credit for leftover propellant (fraction of the last stage)


def tune_pitch_program(
    design: Design,
    env: Env,
    target_perigee_m: float,
    target_apogee_m: float | None = None,
    *,
    max_evaluations: int = 80,
    insertion: str = "coast_circularize",
) -> MultistageDesign:
    """Search pitch_start_s and initial_pitch_deg to hit the target orbit.

    The objective is evaluated on the inserted orbit (coast-and-circularize by default): the
    squared relative perigee error (shortfall weighted 10x) plus the apogee error (symmetric
    against `target_apogee_m`, or against the perigee target when none is given; in direct
    mode an apogee above the circular target is only weakly discouraged) minus a small credit
    for leftover propellant, so among the kicks that reach the orbit the one with the most
    margin wins. Coarse-then-fine: a log-spaced 6 x 8 grid over 5-120 s x 0.5-60 deg seeds a
    Nelder-Mead refinement in log space; total ascents <= `max_evaluations`.
    """
    ms_design = _check_design(design)
    apogee_target = target_apogee_m if target_apogee_m is not None else target_perigee_m
    options = AscentOptions(
        target_perigee_m=target_perigee_m, target_apogee_m=target_apogee_m, insertion=insertion
    )
    last_prop_kg = ms_design.stages[-1].propellant_mass_kg
    evaluations = 0
    log_lo = np.log([_PITCH_START_BOUNDS_S[0], _PITCH_ANGLE_BOUNDS_DEG[0]])
    log_hi = np.log([_PITCH_START_BOUNDS_S[1], _PITCH_ANGLE_BOUNDS_DEG[1]])

    def clamp(z: NDArray[np.float64]) -> tuple[float, float]:
        zc = np.minimum(np.maximum(z, log_lo), log_hi)
        return float(math.exp(zc[0])), float(math.exp(zc[1]))

    def objective(z: NDArray[np.float64]) -> float:
        nonlocal evaluations
        evaluations += 1
        s, a = clamp(z)
        candidate = ms_design.model_copy(update={"pitch_start_s": s, "initial_pitch_deg": a})
        ascent = run_ascent(candidate, env, options)
        rp, ra, _ = _orbit_elements(*ascent.final_state)
        ra = min(ra, 10.0 * apogee_target)
        # Perigee is the pass criterion, so a shortfall costs 10x an overshoot.
        perigee_rel = (rp - target_perigee_m) / target_perigee_m
        err = (10.0 if rp < target_perigee_m else 1.0) * perigee_rel**2
        apogee_rel = (ra - apogee_target) / apogee_target
        if target_apogee_m is not None or options.circularize:
            err += apogee_rel**2
        elif ra > apogee_target:
            err += 0.1 * apogee_rel**2
        if options.circularize:
            err += _MARGIN_WEIGHT * (1.0 - ascent.propellant_margin_kg / last_prop_kg)
        if ascent.impacted or ascent.aborted:
            err += 1e4
        # Penalise leaving the box so the clamp does not create a flat plateau.
        err += float(np.sum((np.log([s, a]) - z) ** 2)) * 1e-3
        return err

    # Coarse grid seeded with the caller's guess (first), then the log-spaced box.
    guess = np.log([ms_design.pitch_start_s, ms_design.initial_pitch_deg])
    candidates = [np.minimum(np.maximum(guess, log_lo), log_hi)]
    candidates += [np.log([s, a]) for s in _SEED_STARTS_S for a in _SEED_ANGLES_DEG]
    best_z, best_f = candidates[0], math.inf
    for z in candidates[: max(1, max_evaluations - 20)]:
        f = objective(z)
        if f < best_f:
            best_z, best_f = z, f

    remaining = max_evaluations - evaluations
    if remaining >= 4:
        # Fine stage: a simplex about one grid cell wide around the best coarse point.
        simplex = np.array([best_z, best_z + [0.35, 0.0], best_z + [0.0, 0.35]])
        result = minimize(
            objective,
            best_z,
            method="Nelder-Mead",
            options={
                "maxiter": remaining,
                "maxfev": remaining,
                "xatol": 1e-3,
                "fatol": 1e-8,
                "initial_simplex": simplex,
            },
        )
        if result.fun < best_f:
            best_z = result.x
    s, a = clamp(best_z)
    return ms_design.model_copy(update={"pitch_start_s": s, "initial_pitch_deg": a})


# --------------------------------------------------------------------------- dispersion


def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult:
    """Monte-Carlo dispersion with the commercial/heavy spec
    (rocketwright.dispersion.DISPERSION_SPEC): Isp, thrust and structural fraction."""
    ms_design = _check_design(design)
    return mc.run_dispersion(
        design,
        env,
        n,
        seed,
        perturb=mc.perturb_multistage,
        simulate=simulate,
        tier=Tier(ms_design.tier),
        summarize=mc.summarize_orbit,
    )
