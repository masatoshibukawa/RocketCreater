"""Reference vehicles: real rockets with a published requirement, design and performance.

Entries live in `rocketwright/catalog/references/<tier>.yaml`. Every entry must cite at least one
public source; numbers not confirmed by a human are `provisional: true`. Two uses:

1. Precision: `reproduce()` flies the published design through our own physics and reports the
   error against the published performance (`scripts/check_references.py`, tests).
2. Design seeds: `find_nearest()` picks the closest references to a Requirement so the agent can
   start from a real vehicle instead of a blank sheet, and `seed_design()` scales that vehicle
   to the requirement with a few plain, provisional rules (every one a `# SIMPLIFICATION:`)
   and returns the notes that explain each step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rocketwright.physics import atmosphere as atm
from rocketwright.physics import multistage, recovery, solid, water
from rocketwright.schema import (
    UNIT_SUFFIXES,
    AmateurDesign,
    BottleDesign,
    Design,
    DesignAdapter,
    Env,
    GoalKind,
    MultistageDesign,
    Requirement,
    SimResult,
    Stage,
    Tier,
)

REFERENCES_DIR = Path(__file__).resolve().parent / "catalog" / "references"
DEFAULT_TOLERANCE_FRAC = 0.30  # reproduction error allowed unless the entry says otherwise

# Published-performance keys the reproduction knows how to compare, per goal kind.
_SUBORBITAL_KEYS = ("apogee_m",)
_ORBITAL_KEYS = ("payload_to_orbit_kg", "orbit_altitude_m")


class ReferenceEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    tier: Tier
    name: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    provisional: bool = True
    requirement: Requirement
    design: Design
    published: dict[str, float]
    env: Env = Env()
    tolerance_frac: float = Field(default=DEFAULT_TOLERANCE_FRAC, gt=0)
    notes: str = ""

    @field_validator("sources")
    @classmethod
    def _sources_are_urls(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if not s.startswith(("http://", "https://"))]
        if bad:
            raise ValueError(f"sources must be public URLs: {bad}")
        return v

    @field_validator("published")
    @classmethod
    def _published_keys_have_units(cls, v: dict[str, float]) -> dict[str, float]:
        bad = [k for k in v if not k.endswith(UNIT_SUFFIXES)]
        if bad:
            raise ValueError(f"published keys must end with a unit suffix {UNIT_SUFFIXES}: {bad}")
        return v

    @property
    def is_orbital(self) -> bool:
        return self.requirement.goal_kind is GoalKind.ORBIT


def _check_consistency(entry: ReferenceEntry) -> None:
    design_tier = entry.design.tier
    if design_tier != entry.tier.value:
        raise ValueError(f"{entry.id}: design.tier {design_tier!r} != tier {entry.tier.value!r}")
    needed = _ORBITAL_KEYS if entry.is_orbital else _SUBORBITAL_KEYS
    missing = [k for k in needed if k not in entry.published]
    if missing:
        raise ValueError(f"{entry.id}: published is missing {missing}")
    if entry.is_orbital and not isinstance(entry.design, MultistageDesign):
        raise ValueError(f"{entry.id}: orbit goals need a MultistageDesign")


def load_references_from(directory: Path) -> list[ReferenceEntry]:
    entries: list[ReferenceEntry] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for raw in data.get("references", []) or []:
            entry = ReferenceEntry.model_validate(raw)
            _check_consistency(entry)
            if entry.id in seen:
                raise ValueError(f"duplicate reference id {entry.id!r} in {path.name}")
            seen.add(entry.id)
            entries.append(entry)
    return entries


@lru_cache(maxsize=1)
def load_references() -> tuple[ReferenceEntry, ...]:
    return tuple(load_references_from(REFERENCES_DIR))


def get_reference(entry_id: str) -> ReferenceEntry:
    for entry in load_references():
        if entry.id == entry_id:
            return entry
    raise KeyError(
        f"unknown reference id {entry_id!r}; available: {[e.id for e in load_references()]}"
    )


# --------------------------------------------------------------------------- nearest


def _log_ratio(a: float, b: float, floor: float) -> float:
    return abs(math.log(max(a, floor) / max(b, floor)))


def requirement_distance(req: Requirement, entry: ReferenceEntry) -> float:
    """Log-scale distance over target altitude and payload mass. Orbit vs altitude goals never
    match (infinite distance): a sounding rocket is not a seed for an orbital mission."""
    ref = entry.requirement
    if ref.goal_kind is not req.goal_kind:
        return math.inf
    d_alt = _log_ratio(req.target_altitude_m, ref.target_altitude_m, floor=1.0)
    d_pay = _log_ratio(req.payload_mass_kg, ref.payload_mass_kg, floor=0.01)
    return math.hypot(d_alt, d_pay)


def find_nearest(
    req: Requirement, tier: Tier, k: int = 3, entries: tuple[ReferenceEntry, ...] | None = None
) -> list[tuple[float, ReferenceEntry]]:
    pool = entries if entries is not None else load_references()
    ranked = sorted(
        ((requirement_distance(req, e), e) for e in pool if e.tier is tier),
        key=lambda pair: pair[0],
    )
    return [pair for pair in ranked if math.isfinite(pair[0])][:k]


# --------------------------------------------------------------------------- reproduction


@dataclass(frozen=True)
class Reproduction:
    entry_id: str
    tier: Tier
    published: dict[str, float]
    simulated: dict[str, float]
    errors_frac: dict[str, float]  # per compared key: (simulated - published) / published
    success: bool
    failure_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    tolerance_frac: float

    @property
    def within_tolerance(self) -> bool:
        return all(abs(e) <= self.tolerance_frac for e in self.errors_frac.values())


def _reproduce_orbital(entry: ReferenceEntry, *, tune: bool) -> tuple[SimResult, dict[str, float]]:
    design = entry.design
    assert isinstance(design, MultistageDesign)
    payload = entry.published["payload_to_orbit_kg"]
    target = entry.published["orbit_altitude_m"]
    design = design.model_copy(update={"payload_mass_kg": payload})
    if tune:
        design = multistage.tune_pitch_program(design, entry.env, target_perigee_m=target)
    result = multistage.simulate(design, entry.env, None, target_perigee_m=target)
    # A launcher reproduces its published capability when the published payload reaches the
    # published orbit with margin to spare; the comparable quantity is the payload the model
    # would lift (published + margin).
    margin = result.metrics.get("payload_margin_kg", 0.0)
    simulated = {
        "payload_to_orbit_kg": payload + margin,
        "orbit_altitude_m": result.metrics.get("perigee_m", 0.0),
    }
    return result, simulated


def _reproduce_suborbital(entry: ReferenceEntry) -> tuple[SimResult, dict[str, float]]:
    target = entry.published["apogee_m"]
    if entry.tier is Tier.AMATEUR:
        result = solid.simulate(entry.design, entry.env, None, target_apogee_m=target)
    else:
        result = water.simulate(entry.design, entry.env, None, target_apogee_m=target)
    return result, {"apogee_m": result.metrics["apogee_m"]}


def reproduce(entry: ReferenceEntry, *, tune: bool = True) -> Reproduction:
    """Fly the reference design through our physics and compare with its published numbers."""
    if entry.is_orbital:
        result, simulated = _reproduce_orbital(entry, tune=tune)
    else:
        result, simulated = _reproduce_suborbital(entry)
    errors = {
        k: (simulated[k] - entry.published[k]) / entry.published[k]
        for k in simulated
        if entry.published.get(k)
    }
    return Reproduction(
        entry_id=entry.id,
        tier=entry.tier,
        published=dict(entry.published),
        simulated=simulated,
        errors_frac=errors,
        success=result.success,
        failure_reasons=tuple(result.failure_reasons),
        warnings=tuple(result.warnings),
        tolerance_frac=entry.tolerance_frac,
    )


# --------------------------------------------------------------------------- design seeds

G0_MPS2 = recovery.G0_MPS2
# Liftoff thrust-to-weight the multistage seed is held to (the physics module only warns
# between 1.1 and 1.2; the seed stays above the warning line).
SEED_MIN_LIFTOFF_TWR = multistage.PASS_THRESHOLDS["warn_liftoff_twr_ratio"]
# SIMPLIFICATION: payload ratios are taken with a 1 kg floor so a zero-payload reference or
# requirement still gives a finite scale, and clamped so a wild ratio cannot produce a
# nonsensical vehicle (the agent is told when the clamp bites).
_PAYLOAD_FLOOR_KG = 1.0
_SCALE_BOUNDS = (0.02, 50.0)
# SIMPLIFICATION (amateur): the body tube must be this much wider than the motor (wall, liner
# and centering rings) and at least this many motor lengths long (the mount is at most
# two-thirds of the tube).
_MOTOR_CLEARANCE_M = 0.006
_BODY_LENGTH_PER_MOTOR_LENGTH = 1.5
_MOTOR_PICK_ITERATIONS = 6
# SIMPLIFICATION (bottle): a parachute added by the seed is sized for this fraction of the
# descent-speed limit in water.PASS_THRESHOLDS, at the pad's air density, with the hobby-chute
# drag coefficient in physics.recovery.
_PARACHUTE_SPEED_MARGIN = 0.8


def _liftoff_mass_and_thrust(design: MultistageDesign) -> tuple[float, float]:
    """Liftoff mass and sea-level thrust the way physics.multistage builds the vehicle (engine
    mass is inside the structural fraction; boosters add their gross mass and thrust)."""
    mass = design.fairing_mass_kg + design.payload_mass_kg
    for stage in design.stages:
        mass += stage.propellant_mass_kg + multistage.structural_mass_kg(
            stage.propellant_mass_kg, stage.structural_fraction
        )
    first = design.stages[0]
    thrust = multistage.get_engine(first.engine_id, kind="engine").thrust_sl_n * first.engine_count
    for booster in design.boosters:
        spec = multistage.get_engine(booster.booster_id, kind="booster")
        mass += (spec.mass_kg + spec.propellant_mass_kg) * booster.count
        thrust += spec.thrust_sl_n * booster.count
    return mass, thrust


def _payload_scale(req: Requirement, entry: ReferenceEntry, notes: list[str]) -> float:
    raw = max(req.payload_mass_kg, _PAYLOAD_FLOOR_KG) / max(
        entry.requirement.payload_mass_kg, _PAYLOAD_FLOOR_KG
    )
    s = min(max(raw, _SCALE_BOUNDS[0]), _SCALE_BOUNDS[1])
    if s != raw:
        notes.append(
            f"payload ratio {raw:.3g} clamped to {s:.3g} (seed scale bounds {_SCALE_BOUNDS}); "
            "a vehicle this far from the reference needs its own design"
        )
    return s


def _seed_multistage(
    entry: ReferenceEntry, req: Requirement, env: Env, *, tune: bool
) -> tuple[MultistageDesign, list[str]]:
    ref = entry.design
    assert isinstance(ref, MultistageDesign)
    notes: list[str] = []
    s = _payload_scale(req, entry, notes)
    # SIMPLIFICATION: every stage's propellant is scaled by the payload ratio (linear), so the
    # stage mass ratios and structural fractions, hence the ideal delta-v, are the reference's.
    # Drag and gravity losses do not scale exactly, which is why the seed is then simulated.
    stages = [
        Stage(
            propellant_mass_kg=st.propellant_mass_kg * s,
            structural_fraction=st.structural_fraction,
            engine_id=st.engine_id,
            # SIMPLIFICATION: engine counts follow the same ratio, rounded to the nearest whole
            # engine with a tie going to fewer, so each stage keeps about the reference's
            # thrust-to-weight. A smaller vehicle has more drag per tonne (area ~ mass^(2/3)),
            # so the lower side is the safe one for max-Q (a half-Electron on 5 Rutherfords
            # hits 69 kPa, on 4 it is 30 kPa); the liftoff T/W floor below catches the other
            # side. Engines are never resized.
            engine_count=max(1, math.ceil(st.engine_count * s - 0.5)),
        )
        for st in ref.stages
    ]
    notes.append(
        f"payload {entry.requirement.payload_mass_kg:g} kg -> {req.payload_mass_kg:g} kg: every "
        f"stage's propellant scaled by {s:.3g} (linear in payload, SIMPLIFICATION); structural "
        f"fractions and engine types kept; engine counts "
        f"{[st.engine_count for st in ref.stages]} -> {[st.engine_count for st in stages]} "
        "(same ratio, nearest whole engine, a tie goes to fewer: less thrust is the safe side "
        "for max-Q on a smaller vehicle)"
    )
    # SIMPLIFICATION: the fairing is a shell, so its mass scales with (volume ratio)^(2/3).
    fairing = ref.fairing_mass_kg * s ** (2.0 / 3.0)
    if ref.boosters:
        notes.append(
            f"strap-on boosters kept as the reference's ({[b.count for b in ref.boosters]} x "
            f"{[b.booster_id for b in ref.boosters]}); they are catalog items and cannot be "
            "scaled, so the booster share of the liftoff thrust changes with the core"
        )
    design = ref.model_copy(
        update={
            "stages": stages,
            "fairing_mass_kg": fairing,
            "payload_mass_kg": req.payload_mass_kg,
        }
    )
    mass, thrust = _liftoff_mass_and_thrust(design)
    twr = thrust / (mass * G0_MPS2)
    added = 0
    first_spec = multistage.get_engine(stages[0].engine_id, kind="engine")
    while twr < SEED_MIN_LIFTOFF_TWR and added < 1000:
        added += 1
        stages[0] = stages[0].model_copy(update={"engine_count": stages[0].engine_count + 1})
        design = design.model_copy(update={"stages": stages})
        mass, thrust = _liftoff_mass_and_thrust(design)
        twr = thrust / (mass * G0_MPS2)
    if added:
        notes.append(
            f"first stage given {added} more {first_spec.id} engine(s) ({stages[0].engine_count} "
            f"total) so the liftoff thrust-to-weight reaches {twr:.2f} >= {SEED_MIN_LIFTOFF_TWR}"
        )
    notes.append(
        f"liftoff mass {mass:,.0f} kg, sea-level thrust {thrust / 1e3:,.0f} kN, "
        f"thrust-to-weight {twr:.2f} (catalog thrust_sl_n; fairing {fairing:.0f} kg from "
        "the reference's x payload ratio^(2/3), SIMPLIFICATION)"
    )
    target = req.target_altitude_m
    ref_target = entry.requirement.target_altitude_m
    if tune:
        design = multistage.tune_pitch_program(
            design,
            env,
            target_perigee_m=target,
            target_apogee_m=req.target_apogee_m,
        )
        notes.append(
            f"pitch program re-tuned for a {target / 1e3:.0f} km perigee: kick at "
            f"{design.pitch_start_s:.1f} s / {design.initial_pitch_deg:.2f} deg (the reference "
            f"flew {ref.pitch_start_s:.1f} s / {ref.initial_pitch_deg:.2f} deg to "
            f"{ref_target / 1e3:.0f} km)"
        )
    else:
        notes.append(
            f"pitch program is the reference's ({ref.pitch_start_s:.1f} s / "
            f"{ref.initial_pitch_deg:.2f} deg, tuned for {ref_target / 1e3:.0f} km); "
            + (
                f"the target perigee is {target / 1e3:.0f} km, so re-tune it "
                "(tune=true here or simulate_design with tune_pitch=true) before judging"
                if target != ref_target
                else "re-tune it after any further mass change"
            )
        )
    return design, notes


def _pick_motor(required_ns: float, notes: list[str]) -> solid.Motor:
    motors = sorted(
        (solid.load_motor(m) for m in solid.list_motor_ids()), key=lambda m: m.total_impulse_ns
    )
    for motor in motors:
        if motor.total_impulse_ns >= required_ns:
            return motor
    largest = motors[-1]
    notes.append(
        f"no bundled motor reaches the required {required_ns:,.0f} Ns; using the largest, "
        f"{largest.id} ({largest.total_impulse_ns:,.0f} Ns): expect a shortfall"
    )
    return largest


def _seed_amateur(
    entry: ReferenceEntry, req: Requirement, env: Env
) -> tuple[AmateurDesign, list[str]]:
    del env  # the amateur seed uses no site data
    ref = entry.design
    assert isinstance(ref, AmateurDesign)
    notes: list[str] = []
    ref_motor = solid.load_motor(ref.motor_id)
    ref_liftoff = ref.dry_mass_kg + ref.payload_mass_kg + ref_motor.total_mass_kg
    ref_alt = max(entry.requirement.target_altitude_m, 1.0)
    alt_ratio = max(req.target_altitude_m, 1.0) / ref_alt
    ref_len = ref.nose_length_m + ref.body_length_m

    def airframe(motor: solid.Motor) -> tuple[float, float, float, float]:
        """(body diameter, body length, nose length, dry mass) once `motor` must fit."""
        # SIMPLIFICATION: the airframe is scaled geometrically by the diameter ratio needed to
        # house the motor (so the Barrowman margin in calibers is roughly kept), the tube is
        # lengthened if the motor still does not fit, and the dry mass follows the tube's
        # surface area (diameter x length: same wall, same materials).
        diameter = max(ref.body_diameter_m, motor.diameter_m + _MOTOR_CLEARANCE_M)
        g = diameter / ref.body_diameter_m
        body_len = max(ref.body_length_m * g, motor.length_m * _BODY_LENGTH_PER_MOTOR_LENGTH)
        nose_len = ref.nose_length_m * g
        dry = ref.dry_mass_kg * g * (nose_len + body_len) / ref_len
        return diameter, body_len, nose_len, dry

    # SIMPLIFICATION: a drag-free ballistic estimate: apogee ~ (impulse / liftoff mass)^2, so
    # the impulse needed scales with (liftoff mass ratio) x sqrt(altitude ratio). The motor's
    # own mass changes the liftoff mass, so the pick is iterated to a fixed point.
    motor = ref_motor
    required_ns = ref_motor.total_impulse_ns
    for _ in range(_MOTOR_PICK_ITERATIONS):
        _, _, _, dry = airframe(motor)
        liftoff = dry + req.payload_mass_kg + motor.total_mass_kg
        required_ns = ref_motor.total_impulse_ns * (liftoff / ref_liftoff) * math.sqrt(alt_ratio)
        trial: list[str] = []
        candidate = _pick_motor(required_ns, trial)
        if candidate.id == motor.id:
            notes.extend(trial)
            break
        motor = candidate
    else:
        notes.extend(trial)
    diameter, body_len, nose_len, dry = airframe(motor)
    liftoff = dry + req.payload_mass_kg + motor.total_mass_kg
    notes.append(
        f"motor {ref_motor.id} ({ref_motor.total_impulse_ns:,.0f} Ns) -> {motor.id} "
        f"({motor.total_impulse_ns:,.0f} Ns): required impulse {required_ns:,.0f} Ns = reference "
        f"x liftoff-mass ratio {liftoff / ref_liftoff:.2f} x sqrt(altitude ratio {alt_ratio:.2f}) "
        "(drag-free ballistic rule, SIMPLIFICATION); smallest bundled motor at or above it"
    )
    g = diameter / ref.body_diameter_m
    fins = ref.fins.model_copy(
        update={
            "root_chord_m": ref.fins.root_chord_m * g,
            "tip_chord_m": ref.fins.tip_chord_m * g,
            "span_m": ref.fins.span_m * g,
            "sweep_m": ref.fins.sweep_m * g,
            "thickness_m": ref.fins.thickness_m * g,
        }
    )
    if g != 1.0 or body_len != ref.body_length_m:
        notes.append(
            f"airframe scaled x{g:.2f} to house the {motor.diameter_m * 1e3:.0f} mm motor: body "
            f"{diameter * 1e3:.0f} mm x {body_len:.2f} m, nose {nose_len:.2f} m, same fin and "
            f"nose shapes; dry mass {ref.dry_mass_kg * 1e3:.0f} g -> {dry * 1e3:.0f} g "
            "(tube surface area, SIMPLIFICATION)"
        )
    # Parachute: same descent speed as the reference -> area proportional to landing mass.
    ref_landing = (
        ref.dry_mass_kg
        + ref.payload_mass_kg
        + (ref_motor.total_mass_kg - ref_motor.propellant_mass_kg)
    )
    landing = dry + req.payload_mass_kg + (motor.total_mass_kg - motor.propellant_mass_kg)
    chute = ref.parachute_diameter_m * math.sqrt(landing / ref_landing)
    notes.append(
        f"parachute {ref.parachute_diameter_m:.2f} m -> {chute:.2f} m (diameter x sqrt of the "
        f"landing-mass ratio {landing / ref_landing:.2f}) to keep the reference's descent speed"
    )
    design = ref.model_copy(
        update={
            "body_diameter_m": diameter,
            "body_length_m": body_len,
            "nose_length_m": nose_len,
            "fins": fins,
            "motor_id": motor.id,
            "dry_mass_kg": dry,
            "payload_mass_kg": req.payload_mass_kg,
            "parachute_diameter_m": chute,
        }
    )
    return design, notes


def _seed_bottle(
    entry: ReferenceEntry, req: Requirement, env: Env
) -> tuple[BottleDesign, list[str]]:
    ref = entry.design
    assert isinstance(ref, BottleDesign)
    notes: list[str] = []
    th = water.PASS_THRESHOLDS
    ref_alt = max(entry.requirement.target_altitude_m, 1.0)
    # SIMPLIFICATION: apogee taken as proportional to the initial gauge pressure (the stored
    # air energy), bottle, water fill and nozzle kept; the payload adds mass that this rule
    # ignores, so the seed is simulated right after.
    wanted = ref.initial_gauge_pressure_pa * max(req.target_altitude_m, 1.0) / ref_alt
    pressure = min(wanted, th["max_gauge_pressure_pa"])
    notes.append(
        f"bottle ({ref.bottle_volume_m3 * 1e3:.1f} L, {ref.water_fill_frac:.0%} water, "
        f"{ref.nozzle_diameter_m * 1e3:.1f} mm nozzle) kept; gauge pressure "
        f"{ref.initial_gauge_pressure_pa / 1e3:.0f} kPa -> {pressure / 1e3:.0f} kPa, linear in "
        f"the apogee ratio {req.target_altitude_m / ref_alt:.2f} (SIMPLIFICATION)"
    )
    if pressure < wanted:
        notes.append(
            f"the {wanted / 1e3:.0f} kPa this rule asks for is above the "
            f"{th['max_gauge_pressure_pa'] / 1e3:.0f} kPa bottle safety cap "
            "(water.PASS_THRESHOLDS, provisional): clipped at the cap; expect a shortfall "
            "unless the bottle, water fill or nozzle change"
        )
    update: dict[str, object] = {
        "initial_gauge_pressure_pa": pressure,
        "payload_mass_kg": req.payload_mass_kg,
    }
    landing = ref.dry_mass_kg + req.payload_mass_kg
    if ref.has_parachute and ref.parachute_diameter_m is not None:
        ref_landing = ref.dry_mass_kg + ref.payload_mass_kg
        chute = ref.parachute_diameter_m * math.sqrt(landing / ref_landing)
        update["parachute_diameter_m"] = chute
        notes.append(
            f"parachute {ref.parachute_diameter_m:.2f} m -> {chute:.2f} m (sqrt of the "
            f"landing-mass ratio) to keep the reference's descent speed"
        )
    elif req.recovery_required or req.payload_mass_kg > 0.0:
        limit = (
            th["max_descent_speed_with_payload_mps"]
            if req.payload_mass_kg > 0.0
            else th["max_descent_speed_mps"]
        )
        speed = _PARACHUTE_SPEED_MARGIN * limit
        rho = float(atm.density_kgpm3(env.launch_altitude_m))
        area = 2.0 * landing * G0_MPS2 / (rho * recovery.DEFAULT_PARACHUTE_CD * speed**2)
        chute = math.sqrt(4.0 * area / math.pi)
        update["has_parachute"] = True
        update["parachute_diameter_m"] = chute
        notes.append(
            f"parachute added ({chute:.2f} m): the reference flew ballistic, but "
            + ("recovery is required" if req.recovery_required else "there is a payload")
            + f"; sized for a {speed:.1f} m/s terminal speed ({_PARACHUTE_SPEED_MARGIN:.0%} of "
            f"the {limit:.0f} m/s limit) with {landing * 1e3:.0f} g landing, Cd "
            f"{recovery.DEFAULT_PARACHUTE_CD} (physics.recovery) and the pad's air density"
        )
    return ref.model_copy(update=update), notes


def seed_design(
    entry: ReferenceEntry,
    req: Requirement,
    *,
    env: Env | None = None,
    tune: bool = False,
) -> tuple[Design, list[str]]:
    """A scaled copy of the reference design that targets `req`, plus the notes explaining
    each scaling step (plain language, every rule provisional). `env` defaults to the
    reference's launch site; it is used for pitch tuning (multistage, only when `tune` is
    true: a few seconds) and for the parachute sizing (bottle). The result validates as a
    Design but is a starting point, not a judged design: simulate it."""
    site = env if env is not None else entry.env
    if isinstance(entry.design, MultistageDesign):
        if req.goal_kind is not GoalKind.ORBIT:
            raise ValueError(
                f"reference {entry.id!r} is an orbital launcher; altitude goals cannot be seeded "
                "from it"
            )
        design, notes = _seed_multistage(entry, req, site, tune=tune)
    elif isinstance(entry.design, AmateurDesign):
        design, notes = _seed_amateur(entry, req, site)
    else:
        design, notes = _seed_bottle(entry, req, site)
    notes.insert(
        0,
        f"seeded from {entry.name} ({entry.id}; "
        f"{'provisional' if entry.provisional else 'checked'} catalog entry): "
        f"{entry.requirement.payload_mass_kg:g} kg to "
        f"{entry.requirement.target_altitude_m:g} m -> requirement {req.payload_mass_kg:g} kg "
        f"to {req.target_altitude_m:g} m",
    )
    validated = DesignAdapter.validate_python(design.model_dump())
    return validated, notes


def find_reference_designs(req: Requirement, tier: Tier, k: int = 3) -> list[dict[str, Any]]:
    """The `k` nearest references for the agent: id, name, sources, distance, published
    performance, the reference's own requirement and site, provisional flag and the first
    300 characters of the notes. No design and no trace (seed_design gives the design)."""
    rows: list[dict[str, Any]] = []
    for distance, entry in find_nearest(req, tier, k=k):
        rows.append(
            {
                "id": entry.id,
                "name": entry.name,
                "sources": list(entry.sources),
                "distance": round(distance, 4),
                "published": dict(entry.published),
                "requirement": entry.requirement.model_dump(mode="json"),
                "env": entry.env.model_dump(mode="json"),
                "provisional": entry.provisional,
                "tolerance_frac": entry.tolerance_frac,
                "notes": entry.notes[:300],
            }
        )
    return rows
