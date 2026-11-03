"""Staged, code-enumerated design chain for the bottle and amateur tiers.

A design in these tiers is a sequence of part decisions taken in a FIXED order; each stage depends
only on the stages before it, so changing a stage invalidates every stage after it:

* amateur: motor -> mount -> body_tube -> nose_cone -> body_length -> fins (material + planform)
  -> parachute -> deploy_delay (recovery hardware and launch lug are catalog defaults, not
  stages);
* bottle: bottle -> nozzle -> water_fill -> pressure -> fins -> parachute (the launcher is the
  cheapest one that holds the chosen pressure, or none when the budget excludes it).

For one stage, `candidates_for` enumerates every catalog option compatible with the upstream
choices, completes each one into a full build with the DEFAULT RULES of the downstream stages
(`complete_build`, one implementation shared with the auto design), and evaluates it the same way
design_from_parts does: resolve -> check_buildability -> (no error) simulate -> judge -> score.
Every number a candidate carries therefore comes from the bill and the physics, never from a
formula. `auto_design` walks the stages greedily (best candidate per stage, in order) and is the
baseline design of the tier; `design_stage` is one stage with its funnel (enumerated / rejected
with reasons) for the agent to explain and override.

Defaults (`CHAIN_RULES`, all provisional):
* motor: the smallest certified (non-`dummy_*`) motor at or above derive's total impulse that has
  a mount (references._pick_motor); the synthetic `dummy_*` placeholders are only offered when no
  real motor passes the motor stage, and then carry the warning "synthetic placeholder motor".
* airframe (mount, tube, fin material): the best of a small BEAM: every compatible mount x every
  tube it fits x the `beam_fin_materials` lightest fin stocks rated for the motor, each completed
  by the rules below, simulated and scored; motors outside derive's class window +-
  `beam_class_window` simulate only the pre-ranked best combination (speed). The beam is
  memoised per (motor, given mount / tube / material), so every stage sees the same airframe.
* nose: the lightest that fits; body: the buildability minimum (build.min_body_length_m: motor
  bay + packed parachute + shock cord + payload bay) + 1 caliber, clipped to one stock tube when
  the minimum fits in one; fins: the given material with the smallest planform of FIN_GRID that
  gives >= 2.0 cal; parachute: the smallest that packs and descends at <= 5 m/s
  (references._pick_parachute); deploy delay: 0 s = the motor's delay grain that ejects at apogee
  (the grain nearest the coast time is named in the explanation).
* bottle: the bottle closest to derive's 1.5 L; the widest nozzle that fits the neck; derive's
  40 % fill; the lightest fin set; the smallest parachute for <= 5 m/s when there is a payload or
  recovery is required (else none); pressure: scipy brentq on physics.water for the target
  apogee, clipped at the bottle / physics cap.

Score (lexicographic, smaller is better; provisional): buildable without error > passes the
requirement (physics PASS_THRESHOLDS: apogee +-10 %, descent, stability, rail exit; budget) > one
stock tube (a passing body needing couplers ranks below a passing single-tube body) > in derive's
motor class or one either side (motor stage only: a formula must not outrank a passing
simulation, CLAUDE.md section 8) > fewer failure reasons (failing designs: then one stock tube) >
|apogee error| in 1 % bins > cost > liftoff mass > option id (determinism).

When the chain finds no passing design and the requirement has a budget, `auto_design` says so
(`ChainResult.feasibility`): the cheapest passing design without the budget (a cost-first walk)
and the best design within the budget with the reasons it fails (a budget-first walk). The
constants are not bent to make a demo fit.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import numpy as np
from scipy.optimize import brentq

from rocketwright.build import (
    ALLOWANCES,
    BUILD_THRESHOLDS,
    AmateurBuild,
    BottleBuild,
    BuildBill,
    BuildIssue,
    FinGeometry,
    check_buildability,
    min_body_length_m,
    resolve,
    resolve_amateur,
    tube_count,
)
from rocketwright.classify import classify
from rocketwright.derive import DERIVE_CONSTANTS, DerivedRequirements, derive, parachute_diameter_m
from rocketwright.parts import PartsCatalog
from rocketwright.physics import atmosphere as atm
from rocketwright.physics import solid, stability, water
from rocketwright.references import _nearest_delay, _pick_motor, _pick_parachute
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Env,
    GoalKind,
    Requirement,
    SimResult,
    Tier,
)

__all__ = [
    "AMATEUR_STAGES",
    "ALL_STAGES",
    "BOTTLE_STAGES",
    "CHAIN_RULES",
    "FIN_GRID",
    "STAGES",
    "SYNTHETIC_MOTOR_PREFIX",
    "SYNTHETIC_MOTOR_WARNING",
    "Candidate",
    "ChainResult",
    "StageResult",
    "StageTrace",
    "auto_design",
    "candidates_for",
    "complete_build",
    "design_stage",
    "is_synthetic_motor",
    "invalidated_stages",
]

AMATEUR_STAGES: tuple[str, ...] = (
    "motor",
    "mount",
    "body_tube",
    "nose_cone",
    "body_length",
    "fins",
    "parachute",
    "deploy_delay",
)
BOTTLE_STAGES: tuple[str, ...] = ("bottle", "nozzle", "water_fill", "pressure", "fins", "parachute")
STAGES: dict[str, tuple[str, ...]] = {"amateur": AMATEUR_STAGES, "bottle": BOTTLE_STAGES}
ALL_STAGES: tuple[str, ...] = tuple(dict.fromkeys(AMATEUR_STAGES + BOTTLE_STAGES))

# Default rules and enumeration controls. Every value provisional (README 要確認の値).
CHAIN_RULES: dict[str, float] = {
    "default_static_margin_cal": 2.0,  # fins default: smallest planform at or above this
    "default_descent_speed_mps": 5.0,  # parachute default: smallest at or below this
    "default_body_extra_calibers": 1.0,  # body default: buildability minimum + this
    "body_length_grid_points": 6,  # body_length stage: minimum .. stock tube length
    "fill_min_frac": 0.25,
    "fill_max_frac": 0.55,
    "fill_step_frac": 0.05,
    "pressure_min_pa": 50_000.0,  # low end of the brentq bracket
    "pressure_round_pa": 50_000.0,  # "pump-friendly" candidates: multiples of this
    "pressure_lattice_pa": 1_000.0,  # solved pressures are whole kPa (a pump gauge reads no finer)
    "pressure_apogee_rtol": 0.005,  # brentq stops once the apogee is within 0.5 % of the target
    "apogee_error_bin_frac": 0.01,  # |apogee error| is compared in 1 % bins, then cost decides
    # Enumerations larger than this are pre-ranked without a sim (cheap key: no build error,
    # margin within [default, max], cost, dry mass) and only the best are simulated; the fins
    # stage (720+ planforms) has its own, tighter cap to stay under a second.
    "max_sims_per_stage": 16,
    "max_sims_fins_stage": 10,
    "motor_class_window": 1,  # motor stage: derive's class and this many classes either side
    "top_k": 5,
    # Airframe beam (mount x tube x fin material): the lightest this-many fin stocks rated for
    # the motor; motors within derive's class +- beam_class_window simulate up to
    # beam_max_sims combinations, the others only the pre-ranked best one.
    "beam_fin_materials": 2,
    "beam_class_window": 1,
    "beam_max_sims": 12,
}

# Synthetic placeholder motors (catalog/motors/dummy_*.eng): never a design's first choice.
SYNTHETIC_MOTOR_PREFIX = "dummy_"
SYNTHETIC_MOTOR_WARNING = "synthetic placeholder motor"


def is_synthetic_motor(motor_id: str) -> bool:
    return motor_id.startswith(SYNTHETIC_MOTOR_PREFIX)


# Fin planform grid in body calibers (span, root) and root fractions (tip, sweep); the order of
# total fin area does not depend on the tube, so it is sorted once.
FIN_GRID: dict[str, tuple[float, ...]] = {
    "count": (3, 4),
    "span_cal": (0.75, 1.0, 1.25, 1.5, 2.0),
    "root_cal": (1.0, 1.5, 2.0, 2.5),
    "tip_frac": (0.3, 0.6, 1.0),
    "sweep_frac": (0.0, 0.5, 1.0),
}

# Fin stock and airframe power ratings live in the catalog (parts.yaml `max_motor_impulse_ns`, the
# evidence in `rating_note`) and are enforced by build.check_buildability (errors
# `tube_power_rating` / `fin_power_rating`); the chain uses the same rating to pre-filter.
# SIMPLIFICATION: there is still no fin flutter or strength model.

_DIAMETER_TOL_M = BUILD_THRESHOLDS["diameter_tolerance_m"]
_DESCENT_CHECK_ALTITUDE_M = BUILD_THRESHOLDS["descent_check_altitude_m"]


class FinOption(NamedTuple):
    """Amateur fins stage value: a material and (optionally) a planform from FIN_GRID. With the
    planform None the default rule picks it."""

    material_id: str
    count: int | None = None
    span_cal: float | None = None
    root_cal: float | None = None
    tip_frac: float | None = None
    sweep_frac: float | None = None

    @property
    def has_planform(self) -> bool:
        return self.count is not None

    def encode(self) -> str:
        if not self.has_planform:
            return self.material_id
        return (
            f"{self.material_id}|n{self.count}|s{self.span_cal:g}|r{self.root_cal:g}"
            f"|t{self.tip_frac:g}|w{self.sweep_frac:g}"
        )

    @classmethod
    def parse(cls, text: str) -> FinOption:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if not parts:
            raise ValueError("empty fins option")
        if len(parts) == 1:
            return cls(parts[0])
        fields = {p[0]: p[1:] for p in parts[1:]}
        try:
            return cls(
                parts[0],
                int(fields["n"]),
                float(fields["s"]),
                float(fields["r"]),
                float(fields["t"]),
                float(fields["w"]),
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"fins option {text!r}: expected '<material_id>' or "
                "'<material_id>|n<count>|s<span cal>|r<root cal>|t<tip/root>|w<sweep/root>'"
            ) from exc


def _grid_area(g: tuple[int, float, float, float, float]) -> float:
    count, span, root, tip, _ = g
    return count * 0.5 * (root + tip * root) * span


_FIN_GRID_SORTED: tuple[tuple[int, float, float, float, float], ...] = tuple(
    sorted(
        itertools.product(
            FIN_GRID["count"],
            FIN_GRID["span_cal"],
            FIN_GRID["root_cal"],
            FIN_GRID["tip_frac"],
            FIN_GRID["sweep_frac"],
        ),
        key=lambda g: (_grid_area(g), g),
    )
)


# --------------------------------------------------------------------------- results


@dataclass(frozen=True)
class Candidate:
    """One option of one stage, completed into a full build and evaluated."""

    stage: str
    option: str  # the encoded value to pass back in `chosen`
    value: Any  # the decoded value
    label: str
    build: AmateurBuild | BottleBuild
    issues: list[BuildIssue]
    metrics: dict[str, float]
    cost_jpy: float | None
    passed: bool
    simulated: bool
    failure_reasons: list[str]
    score: tuple
    why: str
    in_class_window: bool | None = None  # motor stage only

    def as_dict(self, *, include_build: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "option": self.option,
            "label": self.label,
            "passed": self.passed,
            "why": self.why,
            "metrics": {k: round(v, 3) for k, v in self.metrics.items()},
            "cost_jpy": None if self.cost_jpy is None else round(self.cost_jpy),
            "failure_reasons": self.failure_reasons[:3],
            "issues": [f"{i.severity}:{i.code}" for i in self.issues],
        }
        if self.in_class_window is not None:
            out["in_class_window"] = self.in_class_window
        if include_build:
            out["build"] = self.build.model_dump(mode="json")
        return out


@dataclass(frozen=True)
class StageResult:
    stage: str
    tier: str
    candidates: list[Candidate]  # best first (top k when returned by design_stage)
    enumerated: int  # every option generated, compatible or not
    compatible: int
    simulated: int
    passed: int
    rejected: dict[str, int]  # reason -> candidates (a candidate may count under several)
    next_stage: str | None
    invalidated: list[str] = field(default_factory=list)
    derived_targets: dict[str, Any] = field(default_factory=dict)

    def top_rejections(self, n: int = 6) -> dict[str, int]:
        return dict(sorted(self.rejected.items(), key=lambda kv: (-kv[1], kv[0]))[:n])

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "tier": self.tier,
            "candidates": [c.as_dict() for c in self.candidates],
            "enumerated": self.enumerated,
            "compatible": self.compatible,
            "simulated": self.simulated,
            "passed": self.passed,
            "rejected": self.top_rejections(),
            "next_stage": self.next_stage,
            "invalidated": list(self.invalidated),
            "derived_targets": dict(self.derived_targets),
        }


@dataclass(frozen=True)
class StageTrace:
    stage: str
    option: str
    label: str
    why: str
    fixed: bool  # given by the caller, not ranked
    enumerated: int
    simulated: int
    passed: int
    rejected: dict[str, int]
    alternatives: list[Candidate]  # next best (top 3 without the chosen one)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "chosen": self.option,
            "label": self.label,
            "why": self.why,
            "fixed": self.fixed,
            "funnel": {
                "enumerated": self.enumerated,
                "simulated": self.simulated,
                "passed": self.passed,
                "rejected": dict(self.rejected),
            },
            "alternatives": [
                {"option": c.option, "why": c.why, "passed": c.passed} for c in self.alternatives
            ],
        }


@dataclass(frozen=True)
class ChainResult:
    tier: str
    build: AmateurBuild | BottleBuild
    design: AmateurDesign | BottleDesign
    bill: BuildBill
    issues: list[BuildIssue]
    sim: SimResult  # judged against the requirement, cost from the bill
    trace: list[StageTrace]
    derived_targets: dict[str, Any]
    derived_vs_chain: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    # Set when the design fails and the requirement has a budget: whether any design passes
    # at all, the cheapest passing one (no budget, cost-first walk) and the best one within the
    # budget with its failure reasons (budget-first walk). See auto_design.
    feasibility: dict[str, Any] | None = None


# --------------------------------------------------------------------------- helpers


def _ceil_mm(x: float) -> float:
    return math.ceil(x * 1000.0 - 1e-6) / 1000.0


def _fmt_m(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


# Short keys for the funnel; the first matching fragment wins.
_REASON_KEYS: tuple[tuple[str, str], ...] = (
    ("exceeds budget", "over budget"),
    ("apogee", "apogee off target"),
    ("descent speed", "descent too fast"),
    ("stability margin", "stability margin low"),
    ("rail exit", "rail exit too slow"),
    ("did not leave", "did not leave the rail"),
    ("cannot lift", "cannot lift off"),
    ("initial thrust", "cannot lift off"),
    ("hit the ground", "parachute opens too late"),
    ("gauge pressure", "pressure cap"),
    ("recovery is required", "no parachute"),
    ("payload", "payload not carried"),
)


def _reason_key(reason: str) -> str:
    low = reason.lower()
    for fragment, key in _REASON_KEYS:
        if fragment in low:
            return key
    return reason[:48]


class _Option(NamedTuple):
    value: Any
    reject: str | None = None  # incompatibility reason (not evaluated)
    group: str = ""  # pre-ranking diversity group (fins: material)
    note: str = ""  # appended to the label (pressure: solved / cap / rounded)


@dataclass
class _Eval:
    build: AmateurBuild | BottleBuild
    design: AmateurDesign | BottleDesign | None
    bill: BuildBill | None
    issues: list[BuildIssue]
    margin_cal: float | None
    sim: SimResult | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def passed(self) -> bool:
        return self.sim is not None and not self.reasons and not self.has_error


def _infer_tier(req: Requirement, tier: str | Tier | None, hints: tuple[str, ...] = ()) -> str:
    if tier is not None:
        t = Tier(tier).value
    else:
        only_amateur = set(AMATEUR_STAGES) - set(BOTTLE_STAGES)
        only_bottle = set(BOTTLE_STAGES) - set(AMATEUR_STAGES)
        if any(h in only_amateur for h in hints):
            t = "amateur"
        elif any(h in only_bottle for h in hints):
            t = "bottle"
        else:
            t = (req.tier_override or classify(req).tier).value
    if t not in STAGES:
        raise ValueError(f"the design chain covers the bottle and amateur tiers, not {t!r}")
    return t


def invalidated_stages(tier: str, stage: str, chosen: dict[str, Any]) -> list[str]:
    """Stages of `chosen` that lie downstream of `stage` (they must be redone when `stage`
    changes), in chain order. Unknown stages are a ValueError."""
    order = STAGES.get(tier)
    if order is None:
        raise ValueError(f"tier must be one of {sorted(STAGES)}, got {tier!r}")
    if stage not in order:
        raise ValueError(f"stage {stage!r} is not a {tier} stage; stages: {list(order)}")
    unknown = [s for s in chosen if s not in order]
    if unknown:
        raise ValueError(f"unknown {tier} stage(s) in chosen: {unknown}; stages: {list(order)}")
    idx = order.index(stage)
    return [s for s in order[idx + 1 :] if s in chosen]


# --------------------------------------------------------------------------- the chain


class _Chain:
    """One requirement + site + catalog: decoding, default rules, evaluation (cached by build /
    design JSON for the duration of one public call) and stage ranking."""

    def __init__(
        self,
        req: Requirement,
        env: Env,
        catalog: PartsCatalog,
        tier: str,
        *,
        objective: str = "default",
        sims: dict[str, SimResult] | None = None,
        static: dict[str, tuple] | None = None,
    ) -> None:
        if req.goal_kind is not GoalKind.ALTITUDE:
            raise ValueError("the design chain designs altitude goals (bottle / amateur tiers)")
        self.req = req
        self.env = env
        self.catalog = catalog
        self.tier = tier
        self.order = STAGES[tier]
        self.target = req.target_altitude_m
        self.derived: DerivedRequirements = derive(req, Tier(tier))
        self._evals: dict[str, _Eval] = {}
        # simulations depend on the design, env and target only: variants of one requirement
        # (auto_design's feasibility walks) share them
        self._sims: dict[str, SimResult] = {} if sims is None else sims
        self.objective = objective
        self._static: dict[str, tuple] = {} if static is None else static
        self._pressures: dict[str, tuple[float, str]] = {}
        self._default_motor: str | None = None
        self._density_ratio: float | None = None
        self._beams: dict[tuple[str, str | None, str | None, str | None], tuple[str, str, str]] = {}

    # ----------------------------------------------------------------- derived targets

    def derived_targets(self) -> dict[str, Any]:
        out: dict[str, Any] = {q.key: round(q.value, 4) for q in self.derived.quantities}
        for q in self.derived.quantities:
            if q.annotation:
                out["motor_class_letter"] = q.annotation
        return out

    def _derived(self, key: str) -> float | None:
        try:
            return self.derived.get(key).value
        except KeyError:
            return None

    # ----------------------------------------------------------------- decoding

    def decode(self, stage: str, raw: Any) -> Any:
        if stage not in self.order:
            raise ValueError(f"stage {stage!r} is not a {self.tier} stage; stages: {self.order}")
        if raw is None:
            return None
        if stage in ("body_length", "deploy_delay", "water_fill", "pressure"):
            return float(raw)
        text = str(raw).strip()
        optional = self.tier == "bottle" and stage in ("fins", "parachute")
        if optional and text.lower() in ("", "none", "null"):
            return None
        if stage == "fins" and self.tier == "amateur":
            return FinOption.parse(text)
        return text

    def decode_all(self, chosen: dict[str, Any]) -> dict[str, Any]:
        return {s: self.decode(s, v) for s, v in chosen.items()}

    def encode(self, stage: str, value: Any) -> str:
        if value is None:
            return "none"
        if isinstance(value, FinOption):
            return value.encode()
        if stage == "body_length":
            return f"{value:.3f}"
        if stage == "water_fill":
            return f"{value:.2f}"
        if stage == "pressure":
            return f"{value:.0f}"
        if stage == "deploy_delay":
            return f"{value:g}"
        return str(value)

    # ----------------------------------------------------------------- amateur defaults

    def _mounts_for(self, motor: solid.Motor) -> list[Any]:
        return [
            m
            for m in self.catalog.by_kind("motor_mount", "amateur")
            if abs(m.motor_diameter_m - motor.diameter_m) <= _DIAMETER_TOL_M
        ]

    def _tubes_of(self, mount: Any) -> list[Any]:
        tubes = [
            t for t in self.catalog.by_kind("body_tube", "amateur") if t.id in mount.fits_tubes
        ]
        return sorted(tubes, key=lambda t: (t.outer_diameter_m, t.id))

    @staticmethod
    def rated_for(part: Any, motor: solid.Motor) -> bool:
        """The part's power rating (parts.yaml max_motor_impulse_ns) covers the motor; an
        unrated part is allowed (buildability warns)."""
        rating = getattr(part, "max_motor_impulse_ns", None)
        return rating is None or motor.total_impulse_ns <= rating * (1.0 + 1e-9)

    def real_motor_ids(self) -> list[str]:
        return [m for m in solid.list_motor_ids() if not is_synthetic_motor(m)]

    def default_motor_id(self) -> str:
        if self._default_motor is None:
            self._default_motor = self._pick_default_motor()
        return self._default_motor

    def _pick_default_motor(self) -> str:
        """The smallest motor at or above derive's impulse among the certified motors that have
        a mount in a tube rated for them (synthetic placeholders only when none has)."""

        def buildable(ids: list[str]) -> list[solid.Motor]:
            out = []
            for mid in ids:
                motor = solid.load_motor(mid)
                if any(
                    self.rated_for(t, motor)
                    for mount in self._mounts_for(motor)
                    for t in self._tubes_of(mount)
                ):
                    out.append(motor)
            return out

        pool = buildable(self.real_motor_ids()) or buildable(solid.list_motor_ids())
        if not pool:
            raise ValueError("the parts catalog has no motor mount for any bundled motor")
        required = self._derived("total_impulse_ns") or pool[0].total_impulse_ns
        return _pick_motor(required, [], pool).id

    def default_mount(self, motor: solid.Motor) -> Any:
        """Fallback (no beam): the mount for the narrowest tube."""
        mounts = self._mounts_for(motor)
        if not mounts:  # buildability reports the mismatch
            mounts = sorted(
                self.catalog.by_kind("motor_mount", "amateur"),
                key=lambda m: (abs(m.motor_diameter_m - motor.diameter_m), m.id),
            )[:1]
        if not mounts:
            raise ValueError("the parts catalog has no motor mount")

        def narrowest(m: Any) -> tuple[float, float, str]:
            tubes = self._tubes_of(m)
            return (tubes[0].outer_diameter_m if tubes else math.inf, m.mass_kg, m.id)

        return min(mounts, key=narrowest)

    def default_tube(self, mount: Any) -> Any:
        tubes = self._tubes_of(mount) or sorted(
            self.catalog.by_kind("body_tube", "amateur"), key=lambda t: (t.outer_diameter_m, t.id)
        )
        if not tubes:
            raise ValueError("the parts catalog has no body tube")
        return tubes[0]

    def default_nose(self, tube: Any) -> Any:
        noses = sorted(
            (n for n in self.catalog.by_kind("nose_cone", "amateur") if n.fits_tube_id == tube.id),
            key=lambda n: (n.mass_kg, n.id),
        ) or sorted(self.catalog.by_kind("nose_cone", "amateur"), key=lambda n: n.id)
        if not noses:
            raise ValueError("the parts catalog has no nose cone")
        return noses[0]

    def min_body_length(self, motor: solid.Motor, mount: Any, tube: Any, chute: Any) -> float:
        """build.min_body_length_m with this requirement's payload (the buildability rule)."""
        length, _ = min_body_length_m(motor, mount, tube, chute, self.req.payload_mass_kg)
        return length

    def default_body_length(self, motor: solid.Motor, mount: Any, tube: Any, chute: Any) -> float:
        """The minimum + `default_body_extra_calibers`, but never past one stock tube when the
        minimum fits in one (a coupler costs mass, money and a joint)."""
        lo = self.min_body_length(motor, mount, tube, chute)
        body = _ceil_mm(lo + CHAIN_RULES["default_body_extra_calibers"] * tube.outer_diameter_m)
        stock = math.floor(tube.length_m * 1000.0 + 1e-6) / 1000.0
        if lo <= stock < body:
            body = stock
        return body

    def materials_for(self, motor: solid.Motor) -> list[Any]:
        """Fin stocks rated for the motor, lightest first (all of them, strongest first, when
        none is rated: buildability then reports the rating error)."""
        mats = self.catalog.by_kind("fin_material", "amateur")
        rated = sorted(
            (m for m in mats if self.rated_for(m, motor)),
            key=lambda m: (m.areal_mass_kgpm2, m.id),
        )
        if rated:
            return rated
        return sorted(mats, key=lambda m: (-(m.max_motor_impulse_ns or math.inf), m.id))

    @staticmethod
    def fin_geometry(opt: FinOption, od: float) -> FinGeometry:
        root = round(opt.root_cal * od, 4)
        return FinGeometry(
            count=int(opt.count),
            span_m=round(opt.span_cal * od, 4),
            root_chord_m=root,
            tip_chord_m=round(opt.tip_frac * root, 4),
            sweep_m=round(opt.sweep_frac * root, 4),
        )

    @staticmethod
    def fin_fit_reason(fins: FinGeometry, material: Any, body_length_m: float) -> str | None:
        """Same sheet and root rules as build._check_amateur (pre-filter, no resolve)."""
        extent = max(fins.root_chord_m, fins.sweep_m + fins.tip_chord_m)
        w, h = material.sheet_width_m, material.sheet_height_m
        if not ((fins.span_m <= w and extent <= h) or (fins.span_m <= h and extent <= w)):
            return "fin does not fit the sheet"
        if fins.root_chord_m > body_length_m:
            return "fin root longer than the body"
        return None

    def _margin(self, build: AmateurBuild) -> tuple[float, AmateurDesign, BuildBill]:
        design, bill = resolve_amateur(build, self.catalog)
        motor = solid.load_motor(build.motor_id)
        margin = stability.static_margin_cal(
            design, motor.total_mass_kg, motor_length_m=motor.length_m
        )
        return margin, design, bill

    def _search_planform(
        self, base: AmateurBuild, material: Any, od: float
    ) -> tuple[FinOption | None, float]:
        """Smallest FIN_GRID planform of `material` with margin >= the default target; else
        the best margin found. (None, -inf) when no planform fits the sheet and body."""
        target = CHAIN_RULES["default_static_margin_cal"]
        best: tuple[FinOption | None, float] = (None, -math.inf)
        for g in _FIN_GRID_SORTED:
            opt = FinOption(material.id, *g)
            fins = self.fin_geometry(opt, od)
            if self.fin_fit_reason(fins, material, base.body_length_m) is not None:
                continue
            build = base.model_copy(update={"fin_material_id": material.id, "fins": fins})
            margin, _, _ = self._margin(build)
            if margin >= target:
                return opt, margin
            if margin > best[1]:
                best = (opt, margin)
        return best

    def default_fins(self, base: AmateurBuild, material_id: str) -> FinOption:
        """The smallest FIN_GRID planform of `material_id` with >= the default margin (else the
        best margin; else the smallest grid planform, which buildability then reports)."""
        material = self.catalog.get(material_id, kind="fin_material")
        od = self.catalog.get(base.body_tube_id, kind="body_tube").outer_diameter_m
        opt, _ = self._search_planform(base, material, od)
        return opt if opt is not None else FinOption(material.id, *_FIN_GRID_SORTED[0])

    def _site_density_ratio(self) -> float:
        """sqrt(rho_sea_level / rho_site): derive.parachute_diameter_m is a sea-level formula; the
        descent is judged at the pad + half the check altitude (build._check_amateur)."""
        if self._density_ratio is None:
            rho_sl = float(atm.density_kgpm3(0.0))
            alt = self.env.launch_altitude_m + _DESCENT_CHECK_ALTITUDE_M / 2
            self._density_ratio = math.sqrt(rho_sl / float(atm.density_kgpm3(alt)))
        return self._density_ratio

    def _chute_for(self, landing_kg: float, tier: str, max_packed_m: float | None) -> Any:
        wanted = parachute_diameter_m(landing_kg, CHAIN_RULES["default_descent_speed_mps"])
        return _pick_parachute(
            self.catalog, tier, wanted * self._site_density_ratio(), max_packed_m=max_packed_m
        )

    def _smallest_amateur_chute_id(self) -> str:
        chutes = sorted(
            self.catalog.by_kind("parachute", "amateur"), key=lambda c: (c.diameter_m, c.id)
        )
        if not chutes:
            raise ValueError("the parts catalog has no amateur parachute")
        return chutes[0].id

    def default_amateur_chute(self, build: AmateurBuild) -> Any:
        _, bill = resolve_amateur(build, self.catalog)
        motor = solid.load_motor(build.motor_id)
        landing = (
            bill.dry_mass_kg
            + build.payload_mass_kg
            + motor.total_mass_kg
            - motor.propellant_mass_kg
        )
        tube = self.catalog.get(build.body_tube_id, kind="body_tube")
        chute = self._chute_for(landing, "amateur", tube.inner_diameter_m)
        if chute is None:  # nothing packs: the smallest one, buildability reports it
            chute = self.catalog.get(self._smallest_amateur_chute_id())
        return chute

    # ----------------------------------------------------------------- airframe beam

    def airframe(self, chosen: dict[str, Any]) -> tuple[solid.Motor, Any, Any, str]:
        """(motor, mount, tube, fin material id): the chosen ones, the others from the beam."""
        motor = solid.load_motor(chosen.get("motor") or self.default_motor_id())
        fin_choice: FinOption | None = chosen.get("fins")
        mount_id = chosen.get("mount") or None
        tube_id = chosen.get("body_tube") or None
        material_id = fin_choice.material_id if fin_choice is not None else None
        if mount_id is None or tube_id is None or material_id is None:
            mount_id, tube_id, material_id = self.beam(motor.id, mount_id, tube_id, material_id)
        return (
            motor,
            self.catalog.get(mount_id, kind="motor_mount"),
            self.catalog.get(tube_id, kind="body_tube"),
            material_id,
        )

    def beam_combos(
        self, motor: solid.Motor, mount_id: str | None, tube_id: str | None, mat_id: str | None
    ) -> list[tuple[str, str, str]]:
        """Every (mount, tube, material) the beam tries for `motor` given the fixed ones."""
        if mount_id is not None:
            mounts = [self.catalog.get(mount_id, kind="motor_mount")]
        else:
            mounts = self._mounts_for(motor) or [self.default_mount(motor)]
        if mat_id is not None:
            mats = [mat_id]
        else:
            mats = [
                m.id for m in self.materials_for(motor)[: int(CHAIN_RULES["beam_fin_materials"])]
            ]
        combos: list[tuple[str, str, str]] = []
        for mount in sorted(mounts, key=lambda m: m.id):
            if tube_id is not None:
                if mount_id is None and tube_id not in mount.fits_tubes:
                    continue
                tubes = [tube_id]
            else:
                tubes = [t.id for t in self._tubes_of(mount)] or [self.default_tube(mount).id]
            combos += [(mount.id, t, m) for t in tubes for m in mats]
        if not combos and tube_id is not None:  # the given tube fits no mount: report it
            mount = self.default_mount(motor)
            combos = [(mount.id, tube_id, m) for m in mats]
        return combos

    def beam(
        self, motor_id: str, mount_id: str | None, tube_id: str | None, mat_id: str | None
    ) -> tuple[str, str, str]:
        """Best (mount, tube, material) for the motor: every beam combination completed by the
        default rules and evaluated; the buildable ones (up to the beam's sim budget, pre-ranked
        by the cheap key) are simulated; the best score wins. Memoised."""
        key = (motor_id, mount_id, tube_id, mat_id)
        hit = self._beams.get(key)
        if hit is not None:
            return hit
        motor = solid.load_motor(motor_id)
        evaluated: list[tuple[tuple[str, str, str], _Eval]] = []
        for combo in self.beam_combos(motor, mount_id, tube_id, mat_id):
            m, t, mat = combo
            build = self.complete_amateur(
                {"motor": motor_id, "mount": m, "body_tube": t, "fins": FinOption(mat)}
            )
            evaluated.append((combo, self.evaluate(build, simulate=False)))
        window = self.in_class_window(motor_id, CHAIN_RULES["beam_class_window"])
        cap = int(CHAIN_RULES["beam_max_sims"]) if window in (None, True) else 1
        ok = sorted(
            (i for i, (_, ev) in enumerate(evaluated) if not ev.has_error),
            key=lambda i: (self._prerank_key(evaluated[i][1]), evaluated[i][0]),
        )
        for i in ok[:cap]:
            self.evaluate(evaluated[i][1].build)
        best = min(
            evaluated,
            key=lambda ce: (
                self.score(self._fresh(ce[1]), None, ""),
                ce[0],
            ),
        )[0]
        self._beams[key] = best
        return best

    def _fresh(self, ev: _Eval) -> _Eval:
        return self._evals.get(ev.build.model_dump_json(), ev)

    def recovery_for(self, build: AmateurBuild) -> str | None:
        """The cheapest recovery hardware rated (max_rocket_mass_kg) for the build's liftoff
        mass, counted with that hardware on board; the strongest when none is."""
        hws = sorted(
            self.catalog.by_kind("recovery_hardware", "amateur"), key=lambda p: (p.price_jpy, p.id)
        )
        if not hws:
            return None
        motor = solid.load_motor(build.motor_id)
        # liftoff without recovery hardware; each set adds its mass plus the glue allowance
        bare = build.model_copy(update={"recovery_hardware_id": None})
        _, bill = resolve_amateur(bare, self.catalog)
        frac = 1.0 + float(ALLOWANCES["adhesive_paint_mass_frac"]["value"])
        liftoff0 = bill.dry_mass_kg + build.payload_mass_kg + motor.total_mass_kg
        for hw in hws:
            if hw.max_rocket_mass_kg is None:
                return hw.id
            if liftoff0 + hw.mass_kg * frac <= hw.max_rocket_mass_kg:
                return hw.id
        return max(hws, key=lambda p: (p.max_rocket_mass_kg or math.inf, p.id)).id

    def _default_hardware(self, motor: solid.Motor) -> tuple[str | None, str | None]:
        """(recovery hardware, launch lug). The recovery hardware here is the cheapest one, a
        placeholder that complete_amateur replaces with `recovery_for` the finished build. A lug
        for a 1/8 in (3 mm) rod up to D class (20 Ns), for a 3/16 in (5 mm) rod above.
        SIMPLIFICATION: the catalog has no rail buttons for high power. Provisional."""
        hw = sorted(
            self.catalog.by_kind("recovery_hardware", "amateur"), key=lambda p: (p.price_jpy, p.id)
        )
        lugs = sorted(
            self.catalog.by_kind("launch_lug", "amateur"),
            key=lambda p: (p.fits_rod_diameter_m, p.id),
        )
        lug = None
        if lugs:
            lug = lugs[0] if motor.total_impulse_ns <= 20.0 else lugs[-1]
        return (hw[0].id if hw else None), (lug.id if lug else None)

    def complete_amateur(self, chosen: dict[str, Any]) -> AmateurBuild:
        motor, mount, tube, material_id = self.airframe(chosen)
        nose = (
            self.catalog.get(chosen["nose_cone"], kind="nose_cone")
            if chosen.get("nose_cone")
            else self.default_nose(tube)
        )
        hw, lug = self._default_hardware(motor)
        fin_choice: FinOption | None = chosen.get("fins")
        chute_id: str | None = chosen.get("parachute")
        body = chosen.get("body_length")
        od = tube.outer_diameter_m
        smallest = FinOption(material_id, *_FIN_GRID_SORTED[0])
        chute = self.catalog.get(chute_id or self._smallest_amateur_chute_id(), kind="parachute")

        def base_build(chute: Any) -> AmateurBuild:
            body_len = (
                float(body)
                if body is not None
                else self.default_body_length(motor, mount, tube, chute)
            )
            return AmateurBuild(
                body_tube_id=tube.id,
                body_length_m=body_len,
                nose_cone_id=nose.id,
                motor_mount_id=mount.id,
                motor_id=motor.id,
                fin_material_id=material_id,
                fins=self.fin_geometry(smallest, od),
                parachute_id=chute.id,
                recovery_hardware_id=hw,
                launch_lug_id=lug,
                payload_mass_kg=self.req.payload_mass_kg,
                deploy_delay_s=float(chosen.get("deploy_delay") or 0.0),
            )

        base = base_build(chute)
        base = base.model_copy(update={"recovery_hardware_id": self.recovery_for(base)})
        full_fins = fin_choice is not None and fin_choice.has_planform
        if chute_id is None and not full_fins:
            # provisional chute for the fin search (CG); the body holds its packed bay, so the
            # two are settled together (a few rounds: a longer body is heavier)
            for _ in range(3):
                nxt = self.default_amateur_chute(base)
                if nxt.id == base.parachute_id:
                    break
                base = base_build(nxt).model_copy(
                    update={"recovery_hardware_id": base.recovery_hardware_id}
                )
        if fin_choice is None or not fin_choice.has_planform:
            fin_choice = self.default_fins(base, material_id)
        build = base.model_copy(
            update={
                "fin_material_id": fin_choice.material_id,
                "fins": self.fin_geometry(fin_choice, od),
            }
        )
        if chute_id is None:
            final = self.default_amateur_chute(build)
            update: dict[str, Any] = {"parachute_id": final.id}
            if body is None:
                need = self.default_body_length(motor, mount, tube, final)
                update["body_length_m"] = max(build.body_length_m, need)
            build = build.model_copy(update=update)
        hw = self.recovery_for(build)
        if hw != build.recovery_hardware_id:
            build = build.model_copy(update={"recovery_hardware_id": hw})
        return build

    # ----------------------------------------------------------------- bottle defaults

    def default_bottle(self) -> Any:
        volume = DERIVE_CONSTANTS["bottle_volume_m3"]["value"]
        bottles = self.catalog.by_kind("bottle", "bottle")
        if not bottles:
            raise ValueError("the parts catalog has no bottle")
        return min(bottles, key=lambda b: (abs(b.volume_m3 - volume), b.price_jpy, b.id))

    def nozzles_for(self, bottle: Any) -> list[Any]:
        return [
            n
            for n in self.catalog.by_kind("nozzle", "bottle")
            if abs(n.fits_neck_diameter_m - bottle.neck_diameter_m) <= _DIAMETER_TOL_M
        ]

    def default_nozzle(self, bottle: Any) -> Any:
        nozzles = self.nozzles_for(bottle) or self.catalog.by_kind("nozzle", "bottle")
        if not nozzles:
            raise ValueError("the parts catalog has no nozzle")
        return max(nozzles, key=lambda n: (n.diameter_m, n.id))

    def default_bottle_fins(self) -> str | None:
        sets = sorted(
            self.catalog.by_kind("bottle_fin_set", "bottle"),
            key=lambda f: (f.mass_kg, f.price_jpy, f.id),
        )
        return sets[0].id if sets else None

    def needs_chute(self) -> bool:
        return self.req.payload_mass_kg > 0.0 or self.req.recovery_required

    def default_bottle_chute(self, build: BottleBuild) -> str | None:
        if not self.needs_chute():
            return None
        _, bill = resolve(build.model_copy(update={"parachute_id": None}), self.catalog)
        chute = self._chute_for(bill.dry_mass_kg + build.payload_mass_kg, "bottle", None)
        return None if chute is None else chute.id

    def pressure_cap(self, bottle: Any) -> float:
        return min(bottle.max_gauge_pressure_pa, water.PASS_THRESHOLDS["max_gauge_pressure_pa"])

    def solve_pressure(self, build: BottleBuild) -> tuple[float, str]:
        """Gauge pressure for the target apogee: scipy brentq on physics.water between
        CHAIN_RULES pressure_min_pa and the cap, on a 1 kPa lattice, stopped early once within
        pressure_apogee_rtol. Returns (pressure, "solved" | "cap" | "floor")."""
        key = build.model_copy(update={"initial_gauge_pressure_pa": 1.0}).model_dump_json()
        hit = self._pressures.get(key)
        if hit is not None:
            return hit
        bottle = self.catalog.get(build.bottle_id, kind="bottle")
        cap = self.pressure_cap(bottle)
        lo = min(CHAIN_RULES["pressure_min_pa"], cap)
        lattice = CHAIN_RULES["pressure_lattice_pa"]
        tol = CHAIN_RULES["pressure_apogee_rtol"] * self.target

        def miss(p: float) -> float:
            b = build.model_copy(update={"initial_gauge_pressure_pa": p})
            return self.raw_sim(b).metrics["apogee_m"] - self.target

        class _Done(Exception):
            def __init__(self, p: float) -> None:
                self.p = p

        def lattice_miss(p: float) -> float:
            p_l = max(lo, min(cap, round(p / lattice) * lattice))
            v = miss(p_l)
            if abs(v) <= tol:
                raise _Done(p_l)
            return v

        if miss(cap) < 0.0:
            out = (cap, "cap")
        elif miss(lo) > 0.0:
            out = (lo, "floor")
        else:
            try:
                p = brentq(lattice_miss, lo, cap, xtol=lattice / 2)
                p = max(lo, min(cap, round(p / lattice) * lattice))
            except _Done as done:
                p = done.p
            out = (p, "solved")
        self._pressures[key] = out
        return out

    def apply_launcher(self, build: BottleBuild) -> BottleBuild:
        """The cheapest launcher that holds the pressure, or none when the budget excludes it
        (or none holds it)."""
        launchers = sorted(
            (
                launcher
                for launcher in self.catalog.by_kind("launcher", "bottle")
                if launcher.max_gauge_pressure_pa >= build.initial_gauge_pressure_pa
            ),
            key=lambda launcher: (launcher.price_jpy, launcher.id),
        )
        chosen_id = None
        if launchers:
            _, bill = resolve(build.model_copy(update={"launcher_id": None}), self.catalog)
            cheapest = launchers[0]
            budget = self.req.budget_jpy
            if budget is None or bill.cost_jpy + cheapest.price_jpy <= budget:
                chosen_id = cheapest.id
        return build.model_copy(update={"launcher_id": chosen_id})

    def bottle_airframe(self, chosen: dict[str, Any]) -> tuple[Any, Any, float]:
        bottle = (
            self.catalog.get(chosen["bottle"], kind="bottle")
            if chosen.get("bottle")
            else self.default_bottle()
        )
        nozzle = (
            self.catalog.get(chosen["nozzle"], kind="nozzle")
            if chosen.get("nozzle")
            else self.default_nozzle(bottle)
        )
        fill = chosen.get("water_fill")
        if fill is None:
            fill = DERIVE_CONSTANTS["bottle_water_fill_frac"]["value"]
        return bottle, nozzle, float(fill)

    def complete_bottle(self, chosen: dict[str, Any], *, solve: bool = True) -> BottleBuild:
        bottle, nozzle, fill = self.bottle_airframe(chosen)
        fins = chosen["fins"] if "fins" in chosen else self.default_bottle_fins()
        build = BottleBuild(
            bottle_id=bottle.id,
            water_fill_frac=fill,
            initial_gauge_pressure_pa=float(chosen.get("pressure") or self.pressure_cap(bottle)),
            nozzle_id=nozzle.id,
            fin_set_id=fins,
            parachute_id=None,
            launcher_id=None,
            payload_mass_kg=self.req.payload_mass_kg,
        )
        chute = chosen["parachute"] if "parachute" in chosen else self.default_bottle_chute(build)
        build = build.model_copy(update={"parachute_id": chute})
        if chosen.get("pressure") is None and solve:
            pressure, _ = self.solve_pressure(build)
            build = build.model_copy(update={"initial_gauge_pressure_pa": pressure})
        return self.apply_launcher(build)

    def complete(self, chosen: dict[str, Any]) -> AmateurBuild | BottleBuild:
        if self.tier == "amateur":
            return self.complete_amateur(chosen)
        return self.complete_bottle(chosen)

    # ----------------------------------------------------------------- evaluation

    def raw_sim(self, build: AmateurBuild | BottleBuild) -> SimResult:
        design, _ = resolve(build, self.catalog)
        key = design.model_dump_json()
        sim = self._sims.get(key)
        if sim is None:
            module = solid if isinstance(design, AmateurDesign) else water
            sim = module.simulate(design, self.env, target_apogee_m=self.target)
            self._sims[key] = sim
        return sim

    def evaluate(self, build: AmateurBuild | BottleBuild, *, simulate: bool = True) -> _Eval:
        key = build.model_dump_json()
        ev = self._evals.get(key)
        if ev is None:
            static = self._static.get(key)  # budget-independent: shared between variants
            if static is None:
                issues = check_buildability(build, self.catalog)
                design = bill = None
                margin = None
                if not any(i.code == "unknown_part" for i in issues):
                    design, bill = resolve(build, self.catalog)
                    if isinstance(design, AmateurDesign):
                        motor = solid.load_motor(build.motor_id)
                        margin = stability.static_margin_cal(
                            design, motor.total_mass_kg, motor_length_m=motor.length_m
                        )
                static = (issues, design, bill, margin)
                self._static[key] = static
            issues, design, bill, margin = static
            ev = _Eval(
                build=build, design=design, bill=bill, issues=list(issues), margin_cal=margin
            )
            self._evals[key] = ev
        if simulate and ev.sim is None and not ev.has_error and ev.design is not None:
            ev.sim = self.raw_sim(build)
            ev.reasons = self.judge(ev)
        return ev

    def judge(self, ev: _Eval) -> list[str]:
        """Physics failure reasons plus the requirement-level rules of agent.tools._finalize /
        _judge (budget on the bill's cost, recovery needs a parachute), same wording."""
        assert ev.sim is not None and ev.bill is not None
        reasons = list(ev.sim.failure_reasons)
        cost = round(ev.bill.cost_jpy, 0)
        if self.req.budget_jpy is not None and cost > self.req.budget_jpy:
            reasons.append(f"cost {cost:,.0f} JPY exceeds budget {self.req.budget_jpy:,.0f} JPY")
        if (
            self.req.recovery_required
            and isinstance(ev.design, BottleDesign)
            and not ev.design.has_parachute
        ):
            reasons.append("recovery is required but the design has no parachute")
        return reasons

    # ----------------------------------------------------------------- labels and why

    def label(self, stage: str, value: Any, build: AmateurBuild | BottleBuild) -> str:
        cat = self.catalog
        if stage == "motor":
            m = solid.load_motor(value)
            return f"{m.name} ({m.id}), {m.total_impulse_ns:.0f} Ns"
        if stage == "mount":
            mt = cat.get(value)
            return f"{mt.id}: {mt.motor_diameter_m * 1e3:.0f} mm motor, {mt.length_m * 1e3:.0f} mm"
        if stage == "body_tube":
            return f"{value}: {cat.get(value).outer_diameter_m * 1e3:.1f} mm OD"
        if stage == "nose_cone":
            n = cat.get(value)
            return f"{n.id}: {n.shape}, {n.length_m * 1e3:.0f} mm"
        if stage == "body_length":
            od = cat.get(build.body_tube_id).outer_diameter_m
            return f"{value * 1e3:.0f} mm body ({value / od:.1f} cal)"
        if stage == "fins" and isinstance(build, AmateurBuild):
            f = build.fins
            return (
                f"{f.count} x {build.fin_material_id}: span {f.span_m * 1e3:.0f}, root "
                f"{f.root_chord_m * 1e3:.0f}, tip {f.tip_chord_m * 1e3:.0f}, sweep "
                f"{f.sweep_m * 1e3:.0f} mm"
            )
        if stage == "fins":
            return "no fin set" if value is None else f"{value} ({cat.get(value).count} fins)"
        if stage == "parachute":
            return (
                "no parachute" if value is None else f"{value}: {cat.get(value).diameter_m:.2f} m"
            )
        if stage == "deploy_delay":
            return "0 s: eject at apogee" if value == 0.0 else f"{value:g} s after apogee"
        if stage == "bottle":
            return f"{value}: {cat.get(value).volume_m3 * 1e3:.1f} L"
        if stage == "nozzle":
            return f"{value}: {cat.get(value).diameter_m * 1e3:.1f} mm"
        if stage == "water_fill":
            vol = cat.get(build.bottle_id).volume_m3
            return f"{value:.0%} water ({value * vol * 1e3:.2f} L)"
        if stage == "pressure":
            return f"{value / 1e3:.0f} kPa"
        return str(value)

    def _class_index(self, impulse_ns: float) -> int:
        base = DERIVE_CONSTANTS["motor_class_base_impulse_ns"]["value"]
        return math.ceil(math.log2(max(impulse_ns, 1e-9) / base) - 1e-12)

    def in_class_window(self, motor_id: str, window: float | None = None) -> bool | None:
        required = self._derived("total_impulse_ns")
        if required is None:
            return None
        d = abs(
            self._class_index(solid.load_motor(motor_id).total_impulse_ns)
            - self._class_index(required)
        )
        return d <= (CHAIN_RULES["motor_class_window"] if window is None else window)

    def why(self, stage: str, value: Any, label: str, ev: _Eval) -> str:
        if ev.sim is None:
            errors = [i.message for i in ev.issues if i.severity == "error"]
            what = errors[0] if errors else "pruned before simulation (stage sim cap)"
            return f"{label}: not simulated ({what})"
        m = ev.sim.metrics
        cost = 0.0 if ev.bill is None else ev.bill.cost_jpy
        tol = solid.PASS_THRESHOLDS["apogee_tolerance_frac"]
        text = (
            f"{label}: apogee {_fmt_m(m['apogee_m'])} m (target {_fmt_m(self.target)} m "
            f"+-{tol:.0%})"
        )
        if ev.margin_cal is not None:
            text += f", {ev.margin_cal:.1f} cal"
        text += f", descent {m['descent_speed_mps']:.1f} m/s, {cost:,.0f} JPY"
        if stage == "motor":
            req = self._derived("total_impulse_ns")
            letter = self.derived_targets().get("motor_class_letter", "?")
            if req is not None:
                text += f"; derive: class {letter} ~{req:,.0f} Ns"
        if stage == "deploy_delay" and value == 0.0 and "burnout_time_s" in m:
            coast = m["apogee_time_s"] - m["burnout_time_s"]
            motor = solid.load_motor(ev.build.motor_id)
            grain = _nearest_delay(motor, coast)
            text += f"; coast {coast:.1f} s -> delay grain {grain:g} s"
        if stage == "pressure":
            p = self._derived("gauge_pressure_pa")
            if p is not None:
                text += f"; derive: ~{p / 1e3:.0f} kPa (1.5 L, 40 % fill)"
        reasons = ev.reasons or [i.message for i in ev.issues if i.severity == "error"]
        text += "; passes" if ev.passed else f"; fails: {_reason_key(reasons[0])}"
        return text

    def couplers(self, build: AmateurBuild | BottleBuild) -> int:
        """Stock-tube joints the body needs (0 for one tube and for bottle builds)."""
        if not isinstance(build, AmateurBuild):
            return 0
        tube = self.catalog.get(build.body_tube_id, kind="body_tube")
        return tube_count(build.body_length_m, tube.length_m) - 1

    def score(self, ev: _Eval, in_window: bool | None, option: str) -> tuple:
        """Lexicographic key (module docstring). `objective` "cost" (cheapest passing design)
        puts the cost right after the pass state; "budget" (best design within the budget)
        puts "within budget" before the pass state."""
        cost = round(ev.bill.cost_jpy) if ev.bill is not None else math.inf
        window = 0 if in_window in (None, True) else 1
        joints = int(self.couplers(ev.build) > 0) if ev.bill is not None else 0
        over = int(self.req.budget_jpy is not None and cost > self.req.budget_jpy)
        if ev.sim is None:
            failed, n_reasons, err_bin, mass = 1, 99, math.inf, math.inf
        else:
            err = abs(ev.sim.metrics["apogee_m"] - self.target) / max(self.target, 1e-9)
            failed = 0 if ev.passed else 1
            n_reasons = len(ev.reasons)
            err_bin = round(err / CHAIN_RULES["apogee_error_bin_frac"])
            mass = round(ev.sim.metrics["liftoff_mass_kg"], 4)
        head = int(ev.has_error)
        if self.objective == "cost":
            return (head, failed, cost, joints, window, n_reasons, err_bin, mass, option)
        if self.objective == "budget":
            return (head, over, failed, joints, window, n_reasons, err_bin, cost, mass, option)
        if failed:  # among failing designs fewer failure reasons first, then one stock tube
            return (head, failed, window, n_reasons, joints, err_bin, cost, mass, option)
        return (head, failed, joints, window, n_reasons, err_bin, cost, mass, option)

    def candidate(self, stage: str, opt: _Option, ev: _Eval) -> Candidate:
        option = self.encode(stage, opt.value)
        label = self.label(stage, opt.value, ev.build) + (f" ({opt.note})" if opt.note else "")
        in_window = self.in_class_window(opt.value) if stage == "motor" else None
        metrics: dict[str, float] = {}
        if ev.sim is not None:
            keys = ("apogee_m", "descent_speed_mps", "rail_exit_speed_mps", "liftoff_mass_kg")
            metrics = {k: float(ev.sim.metrics[k]) for k in keys if k in ev.sim.metrics}
        if ev.margin_cal is not None:
            metrics["stability_margin_cal"] = float(ev.margin_cal)
        failures = list(ev.reasons) + [i.message for i in ev.issues if i.severity == "error"]
        return Candidate(
            stage=stage,
            option=option,
            value=opt.value,
            label=label,
            build=ev.build,
            issues=list(ev.issues),
            metrics=metrics,
            cost_jpy=None if ev.bill is None else ev.bill.cost_jpy,
            passed=ev.passed,
            simulated=ev.sim is not None,
            failure_reasons=failures,
            score=self.score(ev, in_window, option),
            why=self.why(stage, opt.value, label, ev),
            in_class_window=in_window,
        )

    # ----------------------------------------------------------------- enumeration

    def options(self, stage: str, chosen: dict[str, Any]) -> list[_Option]:
        cat = self.catalog
        if stage == "motor":
            out = []
            for mid in solid.list_motor_ids():
                motor = solid.load_motor(mid)
                reject = None if self._mounts_for(motor) else "no motor mount for this diameter"
                group = "synthetic" if is_synthetic_motor(mid) else "real"
                note = SYNTHETIC_MOTOR_WARNING if group == "synthetic" else ""
                out.append((motor.total_impulse_ns, _Option(mid, reject, group, note)))
            return [o for _, o in sorted(out, key=lambda x: (x[0], x[1].value))]
        if stage == "mount":
            motor = solid.load_motor(chosen.get("motor") or self.default_motor_id())
            return [
                _Option(
                    m.id,
                    None
                    if abs(m.motor_diameter_m - motor.diameter_m) <= _DIAMETER_TOL_M
                    else "mount takes another motor diameter",
                )
                for m in sorted(cat.by_kind("motor_mount", "amateur"), key=lambda m: m.id)
            ]
        if stage == "body_tube":
            _, mount, _, _ = self.airframe(chosen)
            return [
                _Option(t.id, None if t.id in mount.fits_tubes else "mount does not fit the tube")
                for t in sorted(cat.by_kind("body_tube", "amateur"), key=lambda t: t.id)
            ]
        if stage == "nose_cone":
            _, _, tube, _ = self.airframe(chosen)
            return [
                _Option(n.id, None if n.fits_tube_id == tube.id else "nose does not fit the tube")
                for n in sorted(cat.by_kind("nose_cone", "amateur"), key=lambda n: n.id)
            ]
        if stage == "body_length":
            motor, mount, tube, _ = self.airframe(chosen)
            default = self.complete_amateur({**chosen, "body_length": None})
            chute = cat.get(default.parachute_id, kind="parachute")
            # minimum: motor bay + packed parachute + shock cord + payload (build rule)
            lo = _ceil_mm(self.min_body_length(motor, mount, tube, chute))
            hi = max(lo, math.floor(tube.length_m * 1000.0 + 1e-6) / 1000.0)
            grid = {
                round(float(x), 3)
                for x in np.linspace(lo, hi, int(CHAIN_RULES["body_length_grid_points"]))
            }
            grid.add(default.body_length_m)
            return [_Option(x) for x in sorted(grid)]
        if stage == "fins" and self.tier == "amateur":
            motor, _, tube, _ = self.airframe(chosen)
            body_len = (
                float(chosen["body_length"])
                if chosen.get("body_length") is not None
                else self.complete_amateur(chosen).body_length_m
            )
            out = []
            for material in sorted(cat.by_kind("fin_material", "amateur"), key=lambda m: m.id):
                allowed = self.rated_for(material, motor)
                for g in _FIN_GRID_SORTED:
                    opt = FinOption(material.id, *g)
                    if not allowed:
                        reason = "fin stock not rated for the motor's impulse (parts.yaml)"
                    else:
                        fins = self.fin_geometry(opt, tube.outer_diameter_m)
                        reason = self.fin_fit_reason(fins, material, body_len)
                    out.append(_Option(opt, reason, group=material.id))
            return out
        if stage == "parachute" and self.tier == "amateur":
            _, _, tube, _ = self.airframe(chosen)
            return [
                _Option(
                    c.id,
                    None
                    if c.packed_diameter_m <= tube.inner_diameter_m
                    else "parachute does not pack into the tube",
                )
                for c in sorted(cat.by_kind("parachute", "amateur"), key=lambda c: c.diameter_m)
            ]
        if stage == "deploy_delay":
            motor = solid.load_motor(chosen.get("motor") or self.default_motor_id())
            delays = sorted({d for d in _numeric(motor.delays) if d > 0.0})
            return [_Option(0.0)] + [_Option(d) for d in delays]
        if stage == "bottle":
            return [
                _Option(b.id)
                for b in sorted(cat.by_kind("bottle", "bottle"), key=lambda b: b.volume_m3)
            ]
        if stage == "nozzle":
            bottle, _, _ = self.bottle_airframe(chosen)
            fit = {n.id for n in self.nozzles_for(bottle)}
            return [
                _Option(n.id, None if n.id in fit else "nozzle does not fit the bottle neck")
                for n in sorted(cat.by_kind("nozzle", "bottle"), key=lambda n: n.diameter_m)
            ]
        if stage == "water_fill":
            r = CHAIN_RULES
            n = round((r["fill_max_frac"] - r["fill_min_frac"]) / r["fill_step_frac"]) + 1
            return [
                _Option(round(r["fill_min_frac"] + i * r["fill_step_frac"], 2)) for i in range(n)
            ]
        if stage == "pressure":
            return self._pressure_options(chosen)
        if stage == "fins":  # bottle
            sets = sorted(cat.by_kind("bottle_fin_set", "bottle"), key=lambda f: f.id)
            return [_Option(None)] + [_Option(f.id) for f in sets]
        if stage == "parachute":  # bottle
            chutes = sorted(cat.by_kind("parachute", "bottle"), key=lambda c: c.diameter_m)
            return [_Option(None)] + [_Option(c.id) for c in chutes]
        raise ValueError(f"unknown stage {stage!r}")  # pragma: no cover

    def _pressure_options(self, chosen: dict[str, Any]) -> list[_Option]:
        base = self.complete_bottle({**chosen, "pressure": None}, solve=False)
        bottle = self.catalog.get(base.bottle_id, kind="bottle")
        cap = self.pressure_cap(bottle)
        solved, kind = self.solve_pressure(base.model_copy(update={"launcher_id": None}))
        step = CHAIN_RULES["pressure_round_pa"]
        opts: dict[float, str] = {}
        opts[solved] = {"solved": "solved for the target apogee", "cap": "cap-limited"}.get(
            kind, "lowest pressure tried"
        )
        opts.setdefault(cap, f"cap-limited ({bottle.id} / physics)")
        # the pump-friendly neighbours strictly below and above the solved value
        down = math.floor(solved / step) * step
        up = math.ceil(solved / step) * step
        down = down - step if down >= solved else down
        up = up + step if up <= solved else up
        for p, what in ((down, "down"), (up, "up")):
            if CHAIN_RULES["pressure_min_pa"] <= p <= cap:
                opts.setdefault(float(p), f"rounded {what} to {step / 1e3:.0f} kPa")
        return [_Option(p, note=note) for p, note in sorted(opts.items())]

    # ----------------------------------------------------------------- ranking

    def _prerank_key(self, ev: _Eval) -> tuple:
        margin_off = 0
        if ev.margin_cal is not None:
            lo = CHAIN_RULES["default_static_margin_cal"]
            hi = solid.PASS_THRESHOLDS["max_stability_margin_cal"]
            margin_off = 0 if lo <= ev.margin_cal <= hi else 1
        cost = ev.bill.cost_jpy if ev.bill is not None else math.inf
        mass = ev.bill.dry_mass_kg if ev.bill is not None else math.inf
        return (int(ev.has_error), margin_off, round(cost), round(mass, 5))

    def _select_for_sim(self, evaluated: list[tuple[_Option, _Eval]], cap: int) -> set[int]:
        """Indices to simulate: all buildable ones when they fit the stage cap, else the best by
        a cheap key (no error, margin within [default, max], cost, dry mass), round-robin over
        the option groups (fins: one group per material) so every material is represented."""
        ok = [i for i, (_, ev) in enumerate(evaluated) if not ev.has_error]
        if len(ok) <= cap:
            return set(ok)
        groups: dict[str, list[int]] = {}
        for i in sorted(ok, key=lambda i: (self._prerank_key(evaluated[i][1]), i)):
            groups.setdefault(evaluated[i][0].group, []).append(i)
        order = sorted(groups, key=lambda g: (self._prerank_key(evaluated[groups[g][0]][1]), g))
        picked: list[int] = []
        for rnd in itertools.count():
            added = False
            for g in order:
                if rnd < len(groups[g]) and len(picked) < cap:
                    picked.append(groups[g][rnd])
                    added = True
            if not added or len(picked) >= cap:
                break
        return set(picked)

    def rank(self, stage: str, chosen: dict[str, Any]) -> StageResult:
        options = self.options(stage, chosen)
        rejected: Counter[str] = Counter()
        evaluated: list[tuple[_Option, _Eval]] = []
        held: list[_Option] = []
        for opt in options:
            if opt.reject is not None:
                rejected[opt.reject] += 1
                continue
            if stage == "motor" and opt.group == "synthetic":
                held.append(opt)  # placeholders: only when no certified motor passes
                continue
            build = self.complete({**chosen, stage: opt.value})
            evaluated.append((opt, self.evaluate(build, simulate=False)))
        if stage == "motor":
            # never pruned: every motor's beam airframe is simulated (cached by the beam)
            to_sim = set(range(len(evaluated)))
            for i in to_sim:
                evaluated[i] = (evaluated[i][0], self.evaluate(evaluated[i][1].build))
            if held and any(ev.passed for _, ev in evaluated):
                rejected[f"{SYNTHETIC_MOTOR_WARNING} (a certified motor passes)"] += len(held)
            else:
                for opt in held:
                    ev = self.evaluate(self.complete({**chosen, stage: opt.value}))
                    to_sim.add(len(evaluated))
                    evaluated.append((opt, ev))
        else:
            cap = CHAIN_RULES["max_sims_fins_stage" if stage == "fins" else "max_sims_per_stage"]
            to_sim = self._select_for_sim(evaluated, int(cap))
        cands: list[Candidate] = []
        for i, (opt, ev) in enumerate(evaluated):
            if i in to_sim:
                ev = self.evaluate(ev.build)
            cand = self.candidate(stage, opt, ev)
            cands.append(cand)
            if cand.passed:
                continue
            if ev.has_error:
                for code in sorted({x.code for x in ev.issues if x.severity == "error"}):
                    rejected[f"build error: {code}"] += 1
            elif ev.sim is None:
                rejected["pruned before simulation (stage sim cap)"] += 1
            else:
                for key in sorted({_reason_key(r) for r in ev.reasons}):
                    rejected[key] += 1
        cands.sort(key=lambda c: c.score)
        idx = self.order.index(stage)
        return StageResult(
            stage=stage,
            tier=self.tier,
            candidates=cands,
            enumerated=len(options),
            compatible=len(evaluated),
            simulated=sum(c.simulated for c in cands),
            passed=sum(c.passed for c in cands),
            rejected=dict(rejected),
            next_stage=self.order[idx + 1] if idx + 1 < len(self.order) else None,
            derived_targets=self.derived_targets(),
        )

    # ----------------------------------------------------------------- derive vs chain

    def derived_vs_chain(self, ev: _Eval) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        assert ev.design is not None and ev.bill is not None

        def row(key: str, chain: float, what: str) -> None:
            d = self._derived(key)
            if d is not None:
                rows.append(
                    {
                        "key": key,
                        "derived": round(d, 4),
                        "chain": round(chain, 4),
                        "chain_source": what,
                    }
                )

        if isinstance(ev.build, AmateurBuild):
            motor = solid.load_motor(ev.build.motor_id)
            row("total_impulse_ns", motor.total_impulse_ns, f"motor {motor.id}")
            row(
                "liftoff_mass_kg",
                ev.bill.dry_mass_kg + ev.build.payload_mass_kg,
                "bill dry mass + payload (motor excluded, as in derive)",
            )
            row("parachute_diameter_m", ev.design.parachute_diameter_m, ev.build.parachute_id)
        else:
            row("gauge_pressure_pa", ev.build.initial_gauge_pressure_pa, "pressure stage")
            row(
                "liftoff_dry_mass_kg",
                ev.bill.dry_mass_kg + ev.build.payload_mass_kg,
                "bill + payload",
            )
            if ev.design.parachute_diameter_m is not None:
                row(
                    "parachute_diameter_m",
                    ev.design.parachute_diameter_m,
                    str(ev.build.parachute_id),
                )
        if ev.sim is not None:
            rows.append(
                {
                    "key": "apogee_m",
                    "derived": round(self.target, 4),
                    "chain": round(ev.sim.metrics["apogee_m"], 4),
                    "chain_source": "simulation (derive's formulas aim at the target)",
                }
            )
        return rows


def _numeric(delays: tuple[str, ...]) -> list[float]:
    out = []
    for d in delays:
        try:
            out.append(float(d))
        except ValueError:
            continue
    return out


# --------------------------------------------------------------------------- public API


def complete_build(
    req: Requirement,
    env: Env,
    chosen: dict[str, Any],
    catalog: PartsCatalog,
    *,
    tier: str | Tier | None = None,
) -> AmateurBuild | BottleBuild:
    """The full build for the `chosen` stages (stage -> option id / value; encoded strings are
    accepted) with every other stage filled in by the default rules."""
    t = _infer_tier(req, tier, tuple(chosen))
    chain = _Chain(req, env, catalog, t)
    return chain.complete(chain.decode_all(chosen))


def candidates_for(
    stage: str,
    req: Requirement,
    env: Env,
    chosen: dict[str, Any],
    catalog: PartsCatalog,
    *,
    tier: str | Tier | None = None,
) -> list[Candidate]:
    """Every compatible option of `stage` given the upstream stages of `chosen` (downstream
    entries are ignored), each completed by the default rules and evaluated, best first."""
    t = _infer_tier(req, tier, (stage, *chosen))
    return design_stage(req, env, chosen, stage, catalog, tier=t, k=None).candidates


def design_stage(
    req: Requirement,
    env: Env,
    chosen: dict[str, Any],
    stage: str,
    catalog: PartsCatalog,
    *,
    tier: str | Tier | None = None,
    k: int | None = 5,
) -> StageResult:
    """Rank the options of `stage`: top `k` candidates (None = all) with the funnel. Entries of
    `chosen` downstream of `stage` are dropped and listed in `invalidated`; `stage` itself is
    re-decided; missing upstream stages take their default rules."""
    t = _infer_tier(req, tier, (stage, *chosen))
    invalid = invalidated_stages(t, stage, chosen)
    order = STAGES[t]
    upstream = {s: v for s, v in chosen.items() if order.index(s) < order.index(stage)}
    chain = _Chain(req, env, catalog, t)
    res = chain.rank(stage, chain.decode_all(upstream))
    cands = res.candidates if k is None else res.candidates[: max(1, k)]
    return StageResult(
        stage=res.stage,
        tier=res.tier,
        candidates=cands,
        enumerated=res.enumerated,
        compatible=res.compatible,
        simulated=res.simulated,
        passed=res.passed,
        rejected=res.rejected,
        next_stage=res.next_stage,
        invalidated=invalid,
        derived_targets=res.derived_targets,
    )


def _walk(
    chain: _Chain, fixed: dict[str, Any], k: int, stages: tuple[str, ...] | None = None
) -> tuple[AmateurBuild | BottleBuild, _Eval, list[StageTrace]]:
    """Greedy walk of the chain (best candidate per stage, `fixed` stages kept). With `stages`,
    only those are ranked; the others keep their default rules."""
    chosen = chain.decode_all(fixed)
    trace: list[StageTrace] = []
    for stage in chain.order:
        if stages is not None and stage not in stages and stage not in fixed:
            continue
        if stage in fixed:
            ev = chain.evaluate(chain.complete(chosen))
            cand = chain.candidate(stage, _Option(chosen[stage]), ev)
            trace.append(
                StageTrace(
                    stage, cand.option, cand.label, cand.why, True, 1, 1, int(cand.passed), {}, []
                )
            )
            continue
        res = chain.rank(stage, chosen)
        if not res.candidates:
            raise ValueError(
                f"no compatible {stage} option for the upstream choices "
                f"{ {s: chain.encode(s, v) for s, v in chosen.items()} }: {res.rejected}"
            )
        best = res.candidates[0]
        chosen[stage] = best.value
        trace.append(
            StageTrace(
                stage=stage,
                option=best.option,
                label=best.label,
                why=best.why,
                fixed=False,
                enumerated=res.enumerated,
                simulated=res.simulated,
                passed=res.passed,
                rejected=res.top_rejections(),
                alternatives=res.candidates[1 : 1 + k],
            )
        )
    build = chain.complete(chosen)
    ev = chain.evaluate(build)
    if ev.design is None or ev.bill is None:
        raise ValueError(f"the chosen parts do not resolve: {[i.message for i in ev.issues]}")
    if ev.sim is None:  # a buildability error: simulate anyway so the caller sees the flight
        ev.sim = chain.raw_sim(build)
        ev.reasons = chain.judge(ev)
    return build, ev, trace


def _short(build: AmateurBuild | BottleBuild) -> str:
    if isinstance(build, AmateurBuild):
        return f"{build.motor_id} in {build.body_tube_id}"
    return build.bottle_id


def _summary(chain: _Chain, build: AmateurBuild | BottleBuild, ev: _Eval) -> dict[str, Any]:
    """Compact description of a walked design for the feasibility report."""
    assert ev.sim is not None and ev.bill is not None
    out: dict[str, Any] = {
        "cost_jpy": round(ev.bill.cost_jpy),
        "apogee_m": round(ev.sim.metrics["apogee_m"], 1),
        "passes_physics": not ev.sim.failure_reasons and not ev.has_error,
        "failure_reasons": list(ev.reasons)
        + [i.message for i in ev.issues if i.severity == "error"],
        "build": build.model_dump(mode="json"),
    }
    if isinstance(build, AmateurBuild):
        out["parts"] = {
            "motor": build.motor_id,
            "body_tube": build.body_tube_id,
            "body_length_m": build.body_length_m,
            "couplers": chain.couplers(build),
            "fin_material": build.fin_material_id,
            "parachute": build.parachute_id,
        }
    return out


# The feasibility walks rank the stages that set the price and the capability (motor and airframe;
# bottle: all of them, they are cheap) and keep the default rules for the rest (speed).
_FEASIBILITY_STAGES: dict[str, tuple[str, ...]] = {
    "amateur": ("motor", "mount", "body_tube"),
    "bottle": BOTTLE_STAGES,
}


def _feasibility(
    req: Requirement,
    env: Env,
    catalog: PartsCatalog,
    tier: str,
    fixed: dict[str, Any],
    k: int,
    main: tuple[AmateurBuild | BottleBuild, _Eval],
    sims: dict[str, SimResult],
    static: dict[str, tuple],
) -> dict[str, Any]:
    """No design passed within the budget: is there one at any price (cheapest passing, by a
    cost-first walk without the budget), and which design within the budget comes closest (a
    budget-first walk) and why does it fail."""
    budget = req.budget_jpy
    free = _Chain(
        req.model_copy(update={"budget_jpy": None}),
        env,
        catalog,
        tier,
        objective="cost",
        sims=sims,
        static=static,
    )
    b_free, ev_free, _ = _walk(free, fixed, k, _FEASIBILITY_STAGES[tier])
    cheapest = _summary(free, b_free, ev_free) if ev_free.passed else None
    m_build, m_ev = main
    assert m_ev.bill is not None
    if m_ev.bill.cost_jpy <= budget:
        within_chain, w_build, w_ev = None, m_build, m_ev
    else:
        within_chain = _Chain(req, env, catalog, tier, objective="budget", sims=sims, static=static)
        w_build, w_ev, _ = _walk(within_chain, fixed, k, _FEASIBILITY_STAGES[tier])
    best_within = None
    if w_ev.bill is not None and w_ev.bill.cost_jpy <= budget:
        best_within = _summary(within_chain or free, w_build, w_ev)
    if cheapest is not None:
        verdict = (
            f"no passing design within the {budget:,.0f} JPY budget; the cheapest passing "
            f"design found costs {cheapest['cost_jpy']:,.0f} JPY "
            f"({cheapest['cost_jpy'] - budget:+,.0f} JPY over the budget)"
        )
    else:
        # the main walk's design is the best one (the cost-first walk's is merely the cheapest)
        reasons = [r for r in m_ev.reasons if "exceeds budget" not in r] or [
            i.message for i in m_ev.issues if i.severity == "error"
        ]
        verdict = (
            "no passing design with the bundled parts and motors at any price (the best one, "
            f"{_short(m_build)}, fails: {reasons[0] if reasons else 'the budget only'})"
        )
    if best_within is not None:
        verdict += (
            f"; the best design within the budget costs {best_within['cost_jpy']:,.0f} JPY and "
            f"fails: {'; '.join(best_within['failure_reasons'][:2])}"
        )
    else:
        verdict += "; no buildable design fits the budget"
    return {
        "verdict": verdict,
        "budget_jpy": budget,
        "passing_design_exists": cheapest is not None,
        "cheapest_passing": cheapest,
        "best_within_budget": best_within,
        "method": (
            "greedy chain walks over the "
            + ", ".join(_FEASIBILITY_STAGES[tier])
            + " stages (the others by their default rules): cost-first without the budget "
            "(cheapest passing found) and within-budget-first (best within budget)"
        ),
    }


def auto_design(
    req: Requirement,
    env: Env,
    catalog: PartsCatalog,
    *,
    tier: str | Tier | None = None,
    fixed: dict[str, Any] | None = None,
    k: int = 3,
    feasibility: bool = True,
) -> ChainResult:
    """Greedy walk of the chain: at each stage the best candidate (given the stages already
    chosen and the caller's `fixed` ones, which are kept as given) is adopted. Deterministic.

    When the result does not pass and the requirement has a budget (and `feasibility`), the
    result's `feasibility` says whether any design passes at a higher cost (the cheapest one
    found) and what the best design within the budget is and why it fails."""
    fixed = dict(fixed or {})
    t = _infer_tier(req, tier, tuple(fixed))
    sims: dict[str, SimResult] = {}
    static: dict[str, tuple] = {}
    chain = _Chain(req, env, catalog, t, sims=sims, static=static)
    invalidated_stages(t, chain.order[0], fixed)  # validates the stage names
    build, ev, trace = _walk(chain, fixed, k)
    assert ev.sim is not None and ev.bill is not None and ev.design is not None
    sim = ev.sim.model_copy(
        update={
            "cost_jpy": round(ev.bill.cost_jpy, 0),
            "failure_reasons": list(ev.reasons),
            "success": not ev.reasons,
        }
    )
    warnings: list[str] = []
    if isinstance(build, AmateurBuild) and is_synthetic_motor(build.motor_id):
        warnings.append(
            f"{SYNTHETIC_MOTOR_WARNING} {build.motor_id}: no certified motor in the catalog "
            "passes this requirement; the curve is not a real motor (replace it before any "
            "real use)"
        )
    report = None
    if feasibility and not ev.passed and req.budget_jpy is not None:
        report = _feasibility(req, env, catalog, t, fixed, k, (build, ev), sims, static)
        warnings.append(report["verdict"])
    return ChainResult(
        tier=t,
        build=build,
        design=ev.design,
        bill=ev.bill,
        issues=list(ev.issues),
        sim=sim,
        trace=trace,
        derived_targets=chain.derived_targets(),
        derived_vs_chain=chain.derived_vs_chain(ev),
        warnings=warnings,
        feasibility=report,
    )
