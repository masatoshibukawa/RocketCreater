"""Step 2 of the workflow: a classified Requirement -> quantitative targets by closed formulas.

`derive(req, tier)` turns "put 150 kg into a 400 km orbit" into the numbers the agent needs
before it can propose a first design: circular speed, rotation credit, required delta-v, mass
ratio, liftoff-mass scale (orbit tiers); burnout speed, total impulse, motor class, parachute
size (amateur); gauge pressure, water mass, parachute (bottle). Everything is a closed-form
estimate (no ODE, no LLM, no network) and deterministic. Each `DerivedQuantity` carries the
equation with the numbers substituted so the agent can quote it, the inputs it used, the
assumptions, and `provisional=True` whenever a rule-of-thumb constant from `DERIVE_CONSTANTS`
entered the calculation (CLAUDE.md section 2, principle 4).

The numbers here are a starting scale, not a verdict: the physics models (multistage / solid /
water) remain the only source of pass/fail.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from rocketwright.physics import atmosphere as atm
from rocketwright.physics import multistage as ms
from rocketwright.physics import recovery, solid, water
from rocketwright.schema import UNIT_SUFFIXES, GoalKind, Requirement, Tier

__all__ = [
    "DERIVE_CONSTANTS",
    "DerivedQuantity",
    "DerivedRequirements",
    "derive",
    "motor_class_letter",
    "parachute_diameter_m",
]

G0_MPS2 = ms.G0_MPS2

# Rule-of-thumb constants. Every entry is `provisional: true` with a `source` URL where one
# exists (the value is still a representative pick from a published range, so it stays
# provisional until a human confirms it) or `source: None` when it is a plain estimate.
DERIVE_CONSTANTS: dict[str, dict[str, Any]] = {
    # ---- orbit tiers (commercial / heavy)
    "orbit_loss_allowance_mps": {
        "value": 1800.0,
        "unit": "mps",
        "provisional": True,
        "source": "https://en.wikipedia.org/wiki/Delta-v_budget",
        "note": (
            "gravity + drag + steering losses for an ascent to LEO; the cited budget puts them "
            "at about 1,500-2,000 m/s. Mid-range pick. The open-loop gravity turn in "
            "physics.multistage shows ~2,800 m/s on the lofted Electron-class demo ascent, so "
            "treat this as optimistic."
        ),
    },
    "default_launch_latitude_deg": {
        "value": 31.25,
        "unit": "deg",
        "provisional": True,
        "source": "https://en.wikipedia.org/wiki/Uchinoura_Space_Center",
        "note": "used when the caller gives no launch latitude (Uchinoura Space Center, Japan).",
    },
    "representative_isp_s": {
        "value": {"commercial": 300.0, "heavy": 300.0},
        "unit": "s",
        "provisional": True,
        "source": "https://en.wikipedia.org/wiki/Merlin_(rocket_engine_family)",
        "note": (
            "stage-averaged effective Isp of a kerolox vehicle (Merlin 1D: 282 s sea level / "
            "311 s vacuum; Rutherford 311/343 s). One value for both tiers; heavy vehicles with "
            "solid boosters are a little lower, hydrolox upper stages higher."
        ),
    },
    "representative_structural_fraction": {
        "value": 0.08,
        "unit": "frac",
        "provisional": True,
        "source": None,
        "note": (
            "structure / (structure + propellant) per stage; the bundled references use "
            "0.036-0.109 (catalog/references/commercial.yaml, heavy.yaml)."
        ),
    },
    "typical_payload_fraction_frac": {
        "value": 0.02,
        "unit": "frac",
        "provisional": True,
        "source": "https://en.wikipedia.org/wiki/Payload_fraction",
        "note": (
            "payload / liftoff mass to LEO; the cited table lists about 1-4 % for expendable "
            "launchers (Electron ~2.4 %, Falcon 9 ~4 %). 2 % is a conservative mid pick."
        ),
    },
    # ---- amateur tier
    "amateur_airframe_mass_kg": {
        "value": 0.5,
        "unit": "kg",
        "provisional": True,
        "source": None,
        "note": "airframe (tube, nose, fins, chute, no motor) for an empty hobby rocket.",
    },
    "amateur_airframe_mass_per_payload_frac": {
        "value": 0.3,
        "unit": "frac",
        "provisional": True,
        "source": None,
        "note": "extra airframe mass per kg of payload (payload bay, bulkheads, bigger chute).",
    },
    "amateur_body_diameter_m": {
        "value": 0.054,
        "unit": "m",
        "provisional": True,
        "source": None,
        "note": "representative 54 mm airframe for the drag estimate (same as the demo design).",
    },
    "amateur_burn_time_s": {
        "value": 2.0,
        "unit": "s",
        "provisional": True,
        "source": None,
        "note": "typical burn of the bundled F-J motors (1.5-2.7 s, catalog/motors/*.eng).",
    },
    "motor_class_base_impulse_ns": {
        "value": 1.25,
        "unit": "ns",
        "provisional": False,
        "source": "https://en.wikipedia.org/wiki/Model_rocket_motor_classification",
        "note": (
            "NAR/NFPA letter classes double from 1/2A (0.63-1.25 Ns): A 1.26-2.50, B 2.51-5.00, "
            "..., H 160.01-320, I 320.01-640, J 640.01-1,280, K 1,280.01-2,560, ... O up to 40,960."
        ),
    },
    # ---- bottle tier
    "bottle_volume_m3": {
        "value": 1.5e-3,
        "unit": "m3",
        "provisional": True,
        "source": None,
        "note": "a standard 1.5 L PET soda bottle.",
    },
    "bottle_water_fill_frac": {
        "value": 0.4,
        "unit": "frac",
        "provisional": True,
        "source": "https://arxiv.org/abs/2001.08828",
        "note": (
            "water volume / bottle volume; 1/3-2/5 is the usual optimum and the reference "
            "flights (catalog/references/bottle.yaml) use 0.255-0.40."
        ),
    },
    "bottle_airframe_mass_kg": {
        "value": 0.12,
        "unit": "kg",
        "provisional": True,
        "source": "https://arxiv.org/abs/2001.08828",
        "note": (
            "empty bottle + fins + nose (Fischer et al. 1 L rocket: 143 g; 2 L estimate 100 g)."
        ),
    },
    "bottle_energy_efficiency_frac": {
        "value": 0.16,
        "unit": "frac",
        "provisional": True,
        "source": "catalog/references/bottle.yaml",
        "note": (
            "m g h / W_isentropic over the 5 reference flights: 0.10, 0.10, 0.16, 0.27, 0.32 "
            "(median 0.16, mean 0.19). Lumps nozzle losses, air-phase losses and drag; a single "
            "value cannot fit both the blunt Apte bottle and the streamlined Fischer rocket."
        ),
    },
}

_CLASS_LETTERS = "ABCDEFGHIJKLMNO"


# --------------------------------------------------------------------------- result types


@dataclass(frozen=True)
class DerivedQuantity:
    """One derived number. `key` is unit-suffixed (schema.UNIT_SUFFIXES); `formula` is the
    equation with the numbers substituted; `provisional` is True when any DERIVE_CONSTANTS
    entry marked provisional entered the value. `annotation` carries a categorical label that
    does not fit a float (e.g. the motor class letter)."""

    key: str
    value: float
    formula: str
    inputs: dict[str, float]
    assumptions: list[str] = field(default_factory=list)
    provisional: bool = False
    annotation: str = ""

    def __post_init__(self) -> None:
        if not self.key.endswith(UNIT_SUFFIXES):
            raise ValueError(f"key {self.key!r} must end with one of {UNIT_SUFFIXES}")
        if not self.formula.strip():
            raise ValueError(f"{self.key}: formula must not be empty")
        if not self.inputs:
            raise ValueError(f"{self.key}: inputs must not be empty")


@dataclass(frozen=True)
class DerivedRequirements:
    tier: Tier
    goal_kind: GoalKind
    quantities: list[DerivedQuantity]
    summary: str
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    candidates: dict[str, list[str]] = field(default_factory=dict)  # e.g. {"motor_ids": [...]}

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "goal_kind": self.goal_kind.value,
            "quantities": [asdict(q) for q in self.quantities],
            "summary": self.summary,
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "candidates": {k: list(v) for k, v in self.candidates.items()},
        }

    def get(self, key: str) -> DerivedQuantity:
        for q in self.quantities:
            if q.key == key:
                return q
        raise KeyError(key)


# --------------------------------------------------------------------------- helpers


def _c(name: str) -> Any:
    return DERIVE_CONSTANTS[name]["value"]


def _note(name: str) -> str:
    entry = DERIVE_CONSTANTS[name]
    src = entry.get("source") or "no source"
    return f"{name} = {entry['value']} ({entry['unit']}; provisional; {src})"


def _f(x: float) -> str:
    """Compact number formatting for formula strings."""
    if x == 0.0:
        return "0"
    ax = abs(x)
    if ax >= 1e6 or ax < 1e-3:
        return f"{x:.4g}"
    if ax >= 100.0:
        return f"{x:,.0f}"
    if ax >= 1.0:
        return f"{x:.4g}"
    return f"{x:.4g}"


def parachute_diameter_m(
    mass_kg: float, descent_speed_mps: float, cd: float | None = None
) -> float:
    """Parachute diameter whose terminal speed at sea level is `descent_speed_mps`: the inverse
    of physics.recovery.descend (v = sqrt(2 m g / (rho cd A)) with A = pi d^2 / 4)."""
    if mass_kg <= 0.0 or descent_speed_mps <= 0.0:
        raise ValueError("mass_kg and descent_speed_mps must be positive")
    cd = recovery.DEFAULT_PARACHUTE_CD if cd is None else cd
    rho = float(atm.density_kgpm3(0.0))
    return math.sqrt(8.0 * mass_kg * G0_MPS2 / (math.pi * rho * cd * descent_speed_mps**2))


def motor_class_letter(total_impulse_ns: float) -> str:
    """NAR letter class of a total impulse (each class doubles the previous one)."""
    base = _c("motor_class_base_impulse_ns")  # top of 1/2A
    if total_impulse_ns <= 0.0:
        raise ValueError("total_impulse_ns must be positive")
    if total_impulse_ns <= base / 2.0:
        return "1/4A"
    if total_impulse_ns <= base:
        return "1/2A"
    # class index n: base * 2^(n-1) < I <= base * 2^n  (A: n=1)
    n = math.ceil(math.log2(total_impulse_ns / base) - 1e-12)
    if n <= len(_CLASS_LETTERS):
        return _CLASS_LETTERS[n - 1]
    return chr(ord("A") + n - 1) if n <= 26 else f"class-{n}"


def _motor_class_bounds(letter: str) -> tuple[float, float]:
    base = _c("motor_class_base_impulse_ns")
    if letter == "1/4A":
        return 0.0, base / 2.0
    if letter == "1/2A":
        return base / 2.0, base
    n = ord(letter) - ord("A") + 1
    return base * 2.0 ** (n - 1), base * 2.0**n


def _parachute_quantity(mass_kg: float, limit_mps: float, mass_desc: str) -> DerivedQuantity:
    cd = recovery.DEFAULT_PARACHUTE_CD
    rho = float(atm.density_kgpm3(0.0))
    d = parachute_diameter_m(mass_kg, limit_mps, cd)
    return DerivedQuantity(
        key="parachute_diameter_m",
        value=d,
        formula=(
            f"d = sqrt(8 m g / (pi rho Cd v^2)) = sqrt(8 * {_f(mass_kg)} * {_f(G0_MPS2)} / "
            f"(pi * {_f(rho)} * {_f(cd)} * {_f(limit_mps)}^2)) = {_f(d)} m"
        ),
        inputs={
            "mass_kg": mass_kg,
            "descent_speed_mps": limit_mps,
            "parachute_cd": cd,
            "air_density_kgpm3": rho,
        },
        assumptions=[
            f"mass = {mass_desc}",
            "sea-level density, recovery.DEFAULT_PARACHUTE_CD (flat / hemispherical chute)",
            "terminal speed formula of physics.recovery.descend inverted",
        ],
        provisional=True,
    )


# --------------------------------------------------------------------------- orbit tiers


def _derive_orbit(
    req: Requirement, tier: Tier, launch_latitude_deg: float | None
) -> DerivedRequirements:
    if req.goal_kind is not GoalKind.ORBIT:
        raise ValueError(
            f"tier '{tier.value}' derives orbit goals only; got '{req.goal_kind.value}'"
        )
    quantities: list[DerivedQuantity] = []
    warnings: list[str] = []
    mu = ms.MU_EARTH_M3PS2
    r_earth = ms.R_EARTH_M
    omega = ms.OMEGA_EARTH_RADPS
    h_perigee = req.target_altitude_m
    r1 = r_earth + h_perigee

    v_circ = math.sqrt(mu / r1)
    quantities.append(
        DerivedQuantity(
            key="circular_speed_mps",
            value=v_circ,
            formula=(f"v_circ = sqrt(mu / (R + h)) = sqrt({mu:.4g} / {r1:.4g}) = {_f(v_circ)} m/s"),
            inputs={"mu_m3ps2": mu, "earth_radius_m": r_earth, "perigee_altitude_m": h_perigee},
            assumptions=["spherical Earth, circular orbit at the target perigee altitude"],
        )
    )

    lat_provisional = launch_latitude_deg is None
    lat = _c("default_launch_latitude_deg") if lat_provisional else launch_latitude_deg
    credit = omega * r_earth * math.cos(math.radians(lat))
    quantities.append(
        DerivedQuantity(
            key="rotation_credit_mps",
            value=credit,
            formula=(
                f"v_rot = omega R cos(phi) = {omega:.4g} * {r_earth:.4g} * cos({_f(lat)} deg) = "
                f"{_f(credit)} m/s"
            ),
            inputs={"omega_radps": omega, "earth_radius_m": r_earth, "launch_latitude_deg": lat},
            assumptions=["eastward (due-east) launch; full pad speed counted"]
            + ([_note("default_launch_latitude_deg")] if lat_provisional else []),
            provisional=lat_provisional,
        )
    )

    loss = _c("orbit_loss_allowance_mps")
    quantities.append(
        DerivedQuantity(
            key="loss_allowance_mps",
            value=loss,
            formula=f"dv_loss = {_f(loss)} m/s (gravity + drag + steering allowance)",
            inputs={"loss_allowance_mps": loss},
            assumptions=[_note("orbit_loss_allowance_mps")],
            provisional=True,
        )
    )

    raise_dv = 0.0
    if req.target_apogee_m is not None and req.target_apogee_m > h_perigee:
        r2 = r_earth + req.target_apogee_m
        raise_dv = math.sqrt(mu / r1) * (math.sqrt(2.0 * r2 / (r1 + r2)) - 1.0)
        formula = (
            f"dv_raise = sqrt(mu / r1) (sqrt(2 r2 / (r1 + r2)) - 1) = {_f(v_circ)} * "
            f"(sqrt(2 * {r2:.4g} / ({r1:.4g} + {r2:.4g})) - 1) = {_f(raise_dv)} m/s"
        )
        inputs = {"perigee_radius_m": r1, "apogee_radius_m": r2, "mu_m3ps2": mu}
        assumptions = [
            "Hohmann first burn at perigee: circular -> elliptical with the target apogee"
        ]
    else:
        formula = "dv_raise = 0 m/s (circular target: apogee = perigee)"
        inputs = {"perigee_altitude_m": h_perigee}
        assumptions = ["no apogee raise needed"]
    quantities.append(
        DerivedQuantity(
            key="apogee_raise_dv_mps",
            value=raise_dv,
            formula=formula,
            inputs=inputs,
            assumptions=assumptions,
        )
    )

    dv = v_circ - credit + loss + raise_dv
    quantities.append(
        DerivedQuantity(
            key="required_dv_mps",
            value=dv,
            formula=(
                f"dv = v_circ - v_rot + dv_loss + dv_raise = {_f(v_circ)} - {_f(credit)} + "
                f"{_f(loss)} + {_f(raise_dv)} = {_f(dv)} m/s"
            ),
            inputs={
                "circular_speed_mps": v_circ,
                "rotation_credit_mps": credit,
                "loss_allowance_mps": loss,
                "apogee_raise_dv_mps": raise_dv,
            },
            assumptions=["ideal delta-v the propulsion must deliver (Tsiolkovsky sense)"],
            provisional=True,
        )
    )

    isp = float(_c("representative_isp_s")[tier.value])
    ve = isp * G0_MPS2
    mr_total = math.exp(dv / ve)
    quantities.append(
        DerivedQuantity(
            key="mass_ratio_total_ratio",
            value=mr_total,
            formula=(
                f"m0/mf = exp(dv / (Isp g0)) = exp({_f(dv)} / ({_f(isp)} * {_f(G0_MPS2)})) = "
                f"{_f(mr_total)}"
            ),
            inputs={"required_dv_mps": dv, "isp_s": isp, "g0_mps2": G0_MPS2},
            assumptions=[_note("representative_isp_s"), "single-Isp Tsiolkovsky equation"],
            provisional=True,
        )
    )
    mr_stage = math.exp(dv / 2.0 / ve)
    quantities.append(
        DerivedQuantity(
            key="stage_mass_ratio_ratio",
            value=mr_stage,
            formula=(
                f"MR_stage = exp(dv / 2 / (Isp g0)) = exp({_f(dv / 2.0)} / {_f(ve)}) = "
                f"{_f(mr_stage)}"
            ),
            inputs={"stage_dv_mps": dv / 2.0, "isp_s": isp, "g0_mps2": G0_MPS2},
            assumptions=["2 stages, equal delta-v split, same Isp"],
            provisional=True,
        )
    )

    # Per stage with structural fraction s: payload-side mass of the stage = M (1/MR) - m_struct,
    # m_struct = s/(1-s) * m_prop, m_prop = M (1 - 1/MR)  ->  M_next = M / lambda with
    # lambda = 1 / (1/MR - (1 - 1/MR) s/(1-s)). Two stages: m0 = payload * lambda^2.
    s = _c("representative_structural_fraction")
    inv = 1.0 / mr_stage
    denom = inv - (1.0 - inv) * s / (1.0 - s)
    if denom <= 0.0:
        warnings.append(
            f"stage mass ratio {mr_stage:.2f} with structural fraction {s} cannot close: "
            "no positive payload fraction (needs more stages, higher Isp or lower losses)"
        )
        payload_frac = 0.0
        prop_frac = 1.0
        m0 = float("inf")
    else:
        lam = 1.0 / denom
        payload_frac = 1.0 / (lam * lam)
        m0 = req.payload_mass_kg / payload_frac if req.payload_mass_kg > 0 else 0.0
        # propellant of both stages per unit liftoff mass
        m2 = 1.0 / lam  # stage-2 initial mass per unit liftoff mass
        prop_frac = (1.0 - inv) * 1.0 + (1.0 - inv) * m2
    quantities.append(
        DerivedQuantity(
            key="payload_fraction_frac",
            value=payload_frac,
            formula=(
                f"lambda = 1 / (1/MR - (1 - 1/MR) s/(1-s)) = 1 / ({_f(inv)} - "
                f"{_f(1.0 - inv)} * {_f(s)}/{_f(1.0 - s)}); payload/m0 = 1/lambda^2 = "
                f"{_f(payload_frac)}"
            ),
            inputs={"stage_mass_ratio_ratio": mr_stage, "structural_fraction": s},
            assumptions=[
                _note("representative_structural_fraction"),
                "2 equal-dv stages, fairing ignored, structure dropped at staging",
            ],
            provisional=True,
        )
    )
    quantities.append(
        DerivedQuantity(
            key="propellant_mass_fraction_frac",
            value=prop_frac,
            formula=(
                f"m_prop/m0 = (1 - 1/MR) (1 + 1/lambda) = {_f(1.0 - inv)} * "
                f"(1 + {_f(1.0 / lam if denom > 0 else 0.0)}) = {_f(prop_frac)}"
            ),
            inputs={"stage_mass_ratio_ratio": mr_stage, "structural_fraction": s},
            assumptions=["same staging model as payload_fraction_frac"],
            provisional=True,
        )
    )
    if math.isfinite(m0):
        quantities.append(
            DerivedQuantity(
                key="liftoff_mass_kg",
                value=m0,
                formula=(
                    f"m0 = payload / (payload/m0) = {_f(req.payload_mass_kg)} / "
                    f"{_f(payload_frac)} = {_f(m0)} kg"
                ),
                inputs={
                    "payload_mass_kg": req.payload_mass_kg,
                    "payload_fraction_frac": payload_frac,
                },
                assumptions=["from the staging model above; 0 when the payload is 0"],
                provisional=True,
            )
        )
    typical = _c("typical_payload_fraction_frac")
    m0_typ = req.payload_mass_kg / typical
    quantities.append(
        DerivedQuantity(
            key="liftoff_mass_typical_kg",
            value=m0_typ,
            formula=(
                f"m0 ~ payload / f_typical = {_f(req.payload_mass_kg)} / {_f(typical)} = "
                f"{_f(m0_typ)} kg"
            ),
            inputs={
                "payload_mass_kg": req.payload_mass_kg,
                "typical_payload_fraction_frac": typical,
            },
            assumptions=[_note("typical_payload_fraction_frac")],
            provisional=True,
        )
    )

    summary = (
        f"{tier.value}: {req.payload_mass_kg:g} kg to a {h_perigee / 1000:.0f} km perigee "
        f"needs about {dv:,.0f} m/s of delta-v (v_circ {v_circ:,.0f} - rotation {credit:,.0f} + "
        f"losses {loss:,.0f} + raise {raise_dv:,.0f}); with Isp {isp:.0f} s that is a total mass "
        f"ratio of {mr_total:.1f} ({mr_stage:.2f} per stage for 2 equal stages), a propellant "
        f"fraction of {prop_frac:.2f} and a liftoff mass of roughly "
        f"{(m0 if math.isfinite(m0) else m0_typ):,.0f} kg (typical-fraction check: "
        f"{m0_typ:,.0f} kg). "
        "All loss/Isp/structure constants are provisional; confirm with simulate_design."
    )
    return DerivedRequirements(
        tier=tier,
        goal_kind=req.goal_kind,
        quantities=quantities,
        summary=summary,
        warnings=warnings,
        notes=["pass/fail is decided by physics.multistage, not by these estimates"],
    )


# --------------------------------------------------------------------------- amateur


def _burnout_speed_with_drag(
    h_m: float, mass_kg: float, area_m2: float, cd: float
) -> tuple[float, float]:
    """Coast-to-apogee with constant drag: h = ln(1 + k v^2 / g) / (2 k), k = rho Cd A / (2 m),
    inverted for v. Returns (v, rho). SIMPLIFICATION: density frozen at the mid-coast altitude."""
    rho = float(atm.density_kgpm3(h_m / 2.0))
    k = rho * cd * area_m2 / (2.0 * mass_kg)
    v = math.sqrt(G0_MPS2 * (math.exp(2.0 * k * h_m) - 1.0) / k)
    return v, rho


def _derive_amateur(req: Requirement) -> DerivedRequirements:
    if req.goal_kind is not GoalKind.ALTITUDE:
        raise ValueError("tier 'amateur' derives altitude goals only")
    quantities: list[DerivedQuantity] = []
    h = req.target_altitude_m
    v_vac = math.sqrt(2.0 * G0_MPS2 * h)
    quantities.append(
        DerivedQuantity(
            key="burnout_speed_vacuum_mps",
            value=v_vac,
            formula=f"v = sqrt(2 g h) = sqrt(2 * {_f(G0_MPS2)} * {_f(h)}) = {_f(v_vac)} m/s",
            inputs={"target_altitude_m": h, "g0_mps2": G0_MPS2},
            assumptions=["impulsive burn at the pad, no drag"],
        )
    )

    airframe = _c("amateur_airframe_mass_kg")
    slope = _c("amateur_airframe_mass_per_payload_frac")
    m = airframe + slope * req.payload_mass_kg + req.payload_mass_kg
    quantities.append(
        DerivedQuantity(
            key="liftoff_mass_kg",
            value=m,
            formula=(
                f"m = m_airframe + k_payload * m_payload + m_payload = {_f(airframe)} + "
                f"{_f(slope)} * {_f(req.payload_mass_kg)} + {_f(req.payload_mass_kg)} = {_f(m)} kg"
            ),
            inputs={
                "airframe_mass_kg": airframe,
                "airframe_mass_per_payload_frac": slope,
                "payload_mass_kg": req.payload_mass_kg,
            },
            assumptions=[
                _note("amateur_airframe_mass_kg"),
                _note("amateur_airframe_mass_per_payload_frac"),
                "motor mass not included (motor not chosen yet)",
            ],
            provisional=True,
        )
    )

    d_body = _c("amateur_body_diameter_m")
    area = math.pi * (d_body / 2.0) ** 2
    cd = solid.DEFAULT_CD
    v_drag, rho = _burnout_speed_with_drag(h, m, area, cd)
    k = rho * cd * area / (2.0 * m)
    quantities.append(
        DerivedQuantity(
            key="burnout_speed_mps",
            value=v_drag,
            formula=(
                f"k = rho Cd A / (2 m) = {_f(rho)} * {_f(cd)} * {area:.4g} / (2 * {_f(m)}) = "
                f"{k:.4g} /m; v = sqrt(g (exp(2 k h) - 1) / k) = sqrt({_f(G0_MPS2)} * "
                f"(exp(2 * {k:.4g} * {_f(h)}) - 1) / {k:.4g}) = {_f(v_drag)} m/s"
            ),
            inputs={
                "target_altitude_m": h,
                "liftoff_mass_kg": m,
                "body_diameter_m": d_body,
                "cd": cd,
                "air_density_kgpm3": rho,
            },
            assumptions=[
                "coast with constant drag coefficient solid.DEFAULT_CD on the body frontal area",
                "air density frozen at half the target altitude",
                _note("amateur_body_diameter_m"),
            ],
            provisional=True,
        )
    )
    ratio = v_drag / v_vac
    quantities.append(
        DerivedQuantity(
            key="drag_allowance_ratio",
            value=ratio,
            formula=f"v_drag / v_vac = {_f(v_drag)} / {_f(v_vac)} = {_f(ratio)}",
            inputs={"burnout_speed_mps": v_drag, "burnout_speed_vacuum_mps": v_vac, "cd": cd},
            assumptions=["derived from solid.DEFAULT_CD and the representative body diameter"],
            provisional=True,
        )
    )

    t_burn = _c("amateur_burn_time_s")
    impulse = m * (v_drag + G0_MPS2 * t_burn)
    quantities.append(
        DerivedQuantity(
            key="total_impulse_ns",
            value=impulse,
            formula=(
                f"I = m (v + g t_burn) = {_f(m)} * ({_f(v_drag)} + {_f(G0_MPS2)} * {_f(t_burn)}) "
                f"= {_f(impulse)} Ns"
            ),
            inputs={"liftoff_mass_kg": m, "burnout_speed_mps": v_drag, "burn_time_s": t_burn},
            assumptions=[
                _note("amateur_burn_time_s"),
                "constant mass during the burn; drag during the burn ignored",
            ],
            provisional=True,
        )
    )

    letter = motor_class_letter(impulse)
    lo, hi = _motor_class_bounds(letter)
    base_note = DERIVE_CONSTANTS["motor_class_base_impulse_ns"]["source"]
    quantities.append(
        DerivedQuantity(
            key="motor_class_impulse_min_ns",
            value=lo,
            formula=f"class {letter}: {_f(lo)} Ns < I <= {_f(hi)} Ns (I = {_f(impulse)} Ns)",
            inputs={"total_impulse_ns": impulse},
            assumptions=[f"NAR letter classes ({base_note})"],
            provisional=True,
            annotation=letter,
        )
    )
    quantities.append(
        DerivedQuantity(
            key="motor_class_impulse_max_ns",
            value=hi,
            formula=f"class {letter} upper bound = {_f(hi)} Ns",
            inputs={"total_impulse_ns": impulse},
            assumptions=[f"NAR letter classes ({base_note})"],
            provisional=True,
            annotation=letter,
        )
    )
    # bundled motors in this class or the one above
    candidates: list[str] = []
    for motor_id in solid.list_motor_ids():
        imp = solid.load_motor(motor_id).total_impulse_ns
        if lo < imp <= 4.0 * lo:
            candidates.append(motor_id)

    limit = solid.PASS_THRESHOLDS["max_descent_speed_mps"]
    quantities.append(_parachute_quantity(m, limit, "liftoff_mass_kg (airframe + payload)"))

    notes = [
        f"static stability margin must be >= {solid.PASS_THRESHOLDS['min_stability_margin_cal']} "
        "cal (Barrowman, physics.stability); size the fins for it, no closed formula here",
        f"rail exit speed must be >= {solid.PASS_THRESHOLDS['min_rail_exit_speed_mps']} m/s",
        (
            f"bundled motors in class {letter} or one above: {', '.join(candidates)}"
            if candidates
            else f"no bundled motor in class {letter} or one above; cluster or re-scope"
        ),
    ]
    summary = (
        f"amateur: {h:,.0f} m with {req.payload_mass_kg:g} kg needs a burnout speed of about "
        f"{v_drag:,.0f} m/s (vacuum {v_vac:,.0f} m/s, drag factor {ratio:.2f}) for a "
        f"{m:.2f} kg rocket, i.e. a total impulse of roughly {impulse:,.0f} Ns = class {letter}"
        f"{' (' + ', '.join(candidates) + ')' if candidates else ''}; a parachute of "
        f"{quantities[-1].value:.2f} m keeps the descent at {limit:g} m/s. Provisional "
        "airframe mass / burn time / Cd; confirm with simulate_design."
    )
    return DerivedRequirements(
        tier=Tier.AMATEUR,
        goal_kind=req.goal_kind,
        quantities=quantities,
        summary=summary,
        notes=notes,
        candidates={"motor_ids": candidates},
    )


# --------------------------------------------------------------------------- bottle


def _derive_bottle(req: Requirement) -> DerivedRequirements:
    if req.goal_kind is not GoalKind.ALTITUDE:
        raise ValueError("tier 'bottle' derives altitude goals only")
    quantities: list[DerivedQuantity] = []
    warnings: list[str] = []
    h = req.target_altitude_m
    volume = _c("bottle_volume_m3")
    fill = _c("bottle_water_fill_frac")
    eff = _c("bottle_energy_efficiency_frac")
    airframe = _c("bottle_airframe_mass_kg")
    gamma = water.GAMMA_AIR
    p_atm = atm.SEA_LEVEL_PRESSURE_PA
    cap = water.PASS_THRESHOLDS["max_gauge_pressure_pa"]

    m_water = fill * volume * water.WATER_DENSITY_KGPM3
    quantities.append(
        DerivedQuantity(
            key="water_mass_kg",
            value=m_water,
            formula=(
                f"m_water = f V rho_w = {_f(fill)} * {volume:.4g} * "
                f"{_f(water.WATER_DENSITY_KGPM3)} = {_f(m_water)} kg"
            ),
            inputs={
                "water_fill_frac": fill,
                "bottle_volume_m3": volume,
                "water_density_kgpm3": water.WATER_DENSITY_KGPM3,
            },
            assumptions=[_note("bottle_volume_m3"), _note("bottle_water_fill_frac")],
            provisional=True,
        )
    )

    m = airframe + req.payload_mass_kg
    quantities.append(
        DerivedQuantity(
            key="liftoff_dry_mass_kg",
            value=m,
            formula=(
                f"m = m_airframe + m_payload = {_f(airframe)} + {_f(req.payload_mass_kg)} = "
                f"{_f(m)} kg"
            ),
            inputs={"airframe_mass_kg": airframe, "payload_mass_kg": req.payload_mass_kg},
            assumptions=[_note("bottle_airframe_mass_kg"), "water excluded (expelled in flight)"],
            provisional=True,
        )
    )

    v0 = (1.0 - fill) * volume
    expansion = 1.0 - (v0 / volume) ** (gamma - 1.0)
    work_per_pa = v0 / (gamma - 1.0) * expansion  # W = p_abs * work_per_pa
    energy = m * G0_MPS2 * h
    work = energy / eff
    p_abs = work / work_per_pa
    p_gauge = p_abs - p_atm
    clipped = p_gauge > cap
    quantities.append(
        DerivedQuantity(
            key="gauge_pressure_unclipped_pa",
            value=p_gauge,
            formula=(
                f"W = m g h / eta = {_f(m)} * {_f(G0_MPS2)} * {_f(h)} / {_f(eff)} = {_f(work)} J; "
                f"W = p0 V0/(gamma-1) [1 - (V0/V1)^(gamma-1)]; V0 = (1-f) V = {v0:.4g} m3; "
                f"p0 = W / (V0/(gamma-1) * [1 - ({v0:.4g}/{volume:.4g})^{gamma - 1:.1f}]) = "
                f"{_f(work)} / {work_per_pa:.4g} = {_f(p_abs)} Pa abs; p_gauge = p0 - p_atm = "
                f"{_f(p_abs)} - {_f(p_atm)} = {_f(p_gauge)} Pa"
            ),
            inputs={
                "dry_mass_kg": m,
                "target_altitude_m": h,
                "energy_efficiency_frac": eff,
                "expansion_work_j": work,
                "air_volume_m3": v0,
                "bottle_volume_m3": volume,
                "gamma": gamma,
                "atmospheric_pressure_pa": p_atm,
            },
            assumptions=[
                _note("bottle_energy_efficiency_frac"),
                "isentropic expansion work of the air delivers eta of m g h as potential energy",
                "adiabatic (gamma = 1.4) expansion of the air from V0 to the bottle volume",
            ],
            provisional=True,
        )
    )
    p_final = min(p_gauge, cap)
    if clipped:
        warnings.append(
            f"required gauge pressure {p_gauge / 1000:,.0f} kPa exceeds the PET bottle safety cap "
            f"{cap / 1000:,.0f} kPa; clipped to the cap. The target altitude {h:,.0f} m is not "
            "reachable with this bottle/fill/mass: lower the target, the payload or use a "
            "lighter airframe"
        )
    quantities.append(
        DerivedQuantity(
            key="gauge_pressure_pa",
            value=p_final,
            formula=(
                f"p_gauge = min({_f(p_gauge)}, cap {_f(cap)}) = {_f(p_final)} Pa"
                + (" (CLIPPED)" if clipped else "")
            ),
            inputs={"gauge_pressure_unclipped_pa": p_gauge, "max_gauge_pressure_pa": cap},
            assumptions=["water.PASS_THRESHOLDS max_gauge_pressure_pa (provisional safety cap)"],
            provisional=True,
        )
    )
    if p_gauge <= 0.0:
        warnings.append("target altitude needs no pressure at all; check the requirement")

    needs_chute = req.recovery_required or req.payload_mass_kg > 0.0
    quantities.append(
        DerivedQuantity(
            key="parachute_needed_count",
            value=1.0 if needs_chute else 0.0,
            formula=(
                f"parachute = recovery_required ({req.recovery_required}) or payload > 0 "
                f"({req.payload_mass_kg:g} kg) -> {int(needs_chute)}"
            ),
            inputs={
                "recovery_required": 1.0 if req.recovery_required else 0.0,
                "payload_mass_kg": req.payload_mass_kg,
            },
            assumptions=["a payload (egg) or an explicit recovery request needs a parachute"],
        )
    )
    limit = (
        water.PASS_THRESHOLDS["max_descent_speed_with_payload_mps"]
        if req.payload_mass_kg > 0.0
        else water.PASS_THRESHOLDS["max_descent_speed_mps"]
    )
    if needs_chute:
        quantities.append(_parachute_quantity(m, limit, "liftoff_dry_mass_kg (airframe + payload)"))

    clip_text = f" (clipped from {p_gauge / 1000:,.0f} kPa)" if clipped else ""
    chute_text = (
        f"a parachute of {quantities[-1].value:.2f} m for {limit:g} m/s"
        if needs_chute
        else "no parachute needed"
    )
    summary = (
        f"bottle: {h:g} m with {req.payload_mass_kg:g} kg in a {volume * 1000:g} L bottle at "
        f"{fill:.0%} fill ({m_water:.2f} kg of water) needs about {p_final / 1000:,.0f} kPa gauge"
        f"{clip_text}; {chute_text}. "
        "Energy efficiency is provisional (5 reference flights); confirm with simulate_design."
    )
    return DerivedRequirements(
        tier=Tier.BOTTLE,
        goal_kind=req.goal_kind,
        quantities=quantities,
        summary=summary,
        warnings=warnings,
        notes=["pass/fail is decided by physics.water, not by this energy estimate"],
    )


# --------------------------------------------------------------------------- entry point


def derive(
    req: Requirement, tier: Tier, *, launch_latitude_deg: float | None = None
) -> DerivedRequirements:
    """Per-tier closed-form targets for `req`. `launch_latitude_deg` feeds the rotation credit
    of the orbit tiers (None -> DERIVE_CONSTANTS default, marked provisional)."""
    if tier in (Tier.COMMERCIAL, Tier.HEAVY):
        return _derive_orbit(req, tier, launch_latitude_deg)
    if tier is Tier.AMATEUR:
        return _derive_amateur(req)
    if tier is Tier.BOTTLE:
        return _derive_bottle(req)
    raise ValueError(f"unknown tier {tier!r}")  # pragma: no cover
