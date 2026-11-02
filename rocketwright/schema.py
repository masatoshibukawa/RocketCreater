"""Pydantic models shared by physics, agent, API and UI.

All quantities are SI and field names carry unit suffixes (`_m`, `_kg`, `_s`, `_pa`, ...).
Display-unit conversion happens only in the UI/report layer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

__all__ = [
    "MAX_TRACE_POINTS",
    "UNIT_SUFFIXES",
    "Tier",
    "GoalKind",
    "Requirement",
    "Env",
    "BottleDesign",
    "FinSet",
    "AmateurDesign",
    "Stage",
    "Booster",
    "MultistageDesign",
    "Design",
    "DesignAdapter",
    "TracePoint",
    "decimate_trace",
    "SimResult",
    "Quantiles",
    "LandingPoint",
    "Ellipse95",
    "LandingScatter",
    "OrbitSample",
    "OrbitInsertionStats",
    "DispersionResult",
]

MAX_TRACE_POINTS = 500

# Accepted unit suffixes for metric/quantile keys, e.g. "apogee_m", "max_speed_mps".
UNIT_SUFFIXES: tuple[str, ...] = (
    "_m",
    "_m2",
    "_m3",
    "_mps",
    "_mps2",
    "_s",
    "_kg",
    "_n",
    "_ns",
    "_pa",
    "_k",
    "_deg",
    "_rad",
    "_cal",
    "_jpy",
    "_frac",
    "_ratio",
    "_count",
    "_g",
)


class Tier(StrEnum):
    BOTTLE = "bottle"
    AMATEUR = "amateur"
    COMMERCIAL = "commercial"
    HEAVY = "heavy"


class GoalKind(StrEnum):
    ALTITUDE = "altitude"
    ORBIT = "orbit"


class _Frozen(BaseModel):
    """Immutable base model that rejects unknown keys (tool inputs must fail loudly on typos)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _check_unit_keys(v: dict[str, object]) -> dict[str, object]:
    bad = [k for k in v if not k.endswith(UNIT_SUFFIXES)]
    if bad:
        raise ValueError(f"keys must end with a unit suffix {UNIT_SUFFIXES}: {bad}")
    return v


# --------------------------------------------------------------------------- inputs


class Requirement(_Frozen):
    """Normalised user request. `target_altitude_m` is the apogee for altitude goals and the
    perigee for orbit goals (circular unless `target_apogee_m` is given)."""

    goal_kind: GoalKind
    target_altitude_m: float = Field(ge=0)
    target_apogee_m: float | None = Field(default=None, ge=0)
    payload_mass_kg: float = Field(default=0.0, ge=0)
    budget_jpy: float | None = Field(default=None, gt=0)  # None = unconstrained
    recovery_required: bool = False
    tier_override: Tier | None = None  # explicit user choice; classify warns on conflict
    text: str = ""  # original free-text request (for guard.py and audit)

    @model_validator(mode="after")
    def _check_orbit_fields(self) -> Requirement:
        if self.goal_kind is GoalKind.ALTITUDE and self.target_apogee_m is not None:
            raise ValueError("target_apogee_m is only meaningful for orbit goals")
        if self.target_apogee_m is not None and self.target_apogee_m < self.target_altitude_m:
            raise ValueError("target_apogee_m must be >= target_altitude_m (perigee)")
        return self


class Env(_Frozen):
    """Launch-site environment. Holds no random seed; seeds are passed to simulate()/dispersion().
    Defaults are zeros, not a real site: demo scenarios must set the site explicitly."""

    launch_latitude_deg: float = Field(default=0.0, ge=-90, le=90)
    launch_altitude_m: float = Field(default=0.0, ge=-500)
    wind_speed_mps: float = Field(default=0.0, ge=0)
    wind_direction_deg: float = Field(default=0.0, ge=0, lt=360)  # direction the wind blows FROM
    temperature_offset_k: float = 0.0  # offset applied to the USSA76 profile
    rail_length_m: float = Field(default=1.5, gt=0)  # launcher length; used by solid/water only
    earth_rotation: bool = False  # CLAUDE.md section 7: optional, default off


# --------------------------------------------------------------------------- designs


class BottleDesign(_Frozen):
    tier: Literal["bottle"] = "bottle"
    bottle_volume_m3: float = Field(gt=0)  # a 1.5 L bottle is 0.0015
    water_fill_frac: float = Field(gt=0, lt=1)
    initial_gauge_pressure_pa: float = Field(gt=0)
    nozzle_diameter_m: float = Field(gt=0)
    dry_mass_kg: float = Field(gt=0)  # airframe without water and payload
    payload_mass_kg: float = Field(default=0.0, ge=0)
    has_fins: bool = True
    has_parachute: bool = False
    parachute_diameter_m: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _parachute_consistency(self) -> BottleDesign:
        if self.has_parachute and self.parachute_diameter_m is None:
            raise ValueError("parachute_diameter_m is required when has_parachute is true")
        return self


class FinSet(_Frozen):
    count: int = Field(ge=3, le=8)
    root_chord_m: float = Field(gt=0)
    tip_chord_m: float = Field(ge=0)
    span_m: float = Field(gt=0)
    sweep_m: float = Field(default=0.0, ge=0)  # leading-edge sweep distance at the tip
    thickness_m: float = Field(default=0.003, gt=0)


class AmateurDesign(_Frozen):
    tier: Literal["amateur"] = "amateur"
    body_diameter_m: float = Field(gt=0)
    body_length_m: float = Field(gt=0)
    nose_shape: Literal["conical", "ogive", "elliptical"] = "ogive"  # Barrowman-supported shapes
    nose_length_m: float = Field(gt=0)
    fins: FinSet
    motor_id: str = Field(min_length=1)  # catalog/motors/*.eng id
    dry_mass_kg: float = Field(gt=0)  # airframe without motor and payload
    payload_mass_kg: float = Field(default=0.0, ge=0)
    parachute_diameter_m: float = Field(gt=0)
    deploy_delay_s: float = Field(default=0.0, ge=0)  # after burnout


class Stage(_Frozen):
    propellant_mass_kg: float = Field(gt=0)
    structural_fraction: float = Field(gt=0, lt=1)  # structure / (structure + propellant)
    engine_id: str = Field(min_length=1)  # catalog/engines.yaml id
    engine_count: int = Field(default=1, ge=1)


class Booster(_Frozen):
    booster_id: str = Field(min_length=1)
    count: int = Field(ge=1)


class MultistageDesign(_Frozen):
    # Both commercial and heavy use this model; the discriminator maps both literals here.
    tier: Literal["commercial", "heavy"]
    stages: list[Stage] = Field(min_length=1, max_length=3)  # index 0 burns first
    boosters: list[Booster] = Field(default_factory=list)  # heavy only
    fairing_mass_kg: float = Field(default=0.0, ge=0)
    payload_mass_kg: float = Field(ge=0)
    pitch_start_s: float = Field(ge=0)
    initial_pitch_deg: float = Field(gt=0, lt=90)  # pitch-kick angle from vertical

    @model_validator(mode="after")
    def _boosters_only_for_heavy(self) -> MultistageDesign:
        if self.tier == "commercial" and self.boosters:
            raise ValueError("boosters are only allowed for tier 'heavy'")
        return self


Design = Annotated[
    Union[BottleDesign, AmateurDesign, MultistageDesign],  # noqa: UP007 - Union keeps Annotated readable
    Field(discriminator="tier"),
]
# `Design` is a type alias, so a bare design is parsed/dumped through this adapter.
DesignAdapter: TypeAdapter[Design] = TypeAdapter(Design)


# --------------------------------------------------------------------------- results


class TracePoint(_Frozen):
    t_s: float = Field(ge=0)
    altitude_m: float
    downrange_m: float = 0.0  # horizontal distance from the pad (multistage: along-track)
    east_m: float = 0.0  # 3-D models fill these; multistage leaves them 0
    north_m: float = 0.0
    speed_mps: float = Field(ge=0)
    mass_kg: float | None = Field(default=None, gt=0)
    extra: dict[str, float] = Field(default_factory=dict)  # model-specific, unit-suffixed keys


def decimate_trace(
    points: list[TracePoint], max_points: int = MAX_TRACE_POINTS
) -> list[TracePoint]:
    """Uniformly thin a trace to at most `max_points`, always keeping the first and last sample."""
    n = len(points)
    if n <= max_points:
        return list(points)
    idx = [round(i * (n - 1) / (max_points - 1)) for i in range(max_points)]
    return [points[i] for i in idx]


class SimResult(_Frozen):
    tier: Tier
    success: bool
    failure_reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)  # keys end in a UNIT_SUFFIXES entry
    cost_jpy: float = Field(ge=0)
    trace: list[TracePoint] = Field(default_factory=list)  # thinned to MAX_TRACE_POINTS
    warnings: list[str] = Field(default_factory=list)
    # Provenance: the tool_use id (set by agent/tools.py). Empty by default so that
    # determinism (same input + seed -> identical result) is not broken by a UUID.
    source_id: str = ""

    @field_validator("metrics")
    @classmethod
    def _metric_keys_have_units(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_unit_keys(v)  # type: ignore[return-value]

    @field_validator("trace")
    @classmethod
    def _cap_trace(cls, v: list[TracePoint]) -> list[TracePoint]:
        return decimate_trace(v)

    @model_validator(mode="after")
    def _failed_has_reason(self) -> SimResult:
        if not self.success and not self.failure_reasons:
            raise ValueError("a failed SimResult must list at least one failure reason")
        return self


class Quantiles(_Frozen):
    p05: float
    p50: float
    p95: float

    @model_validator(mode="after")
    def _ordered(self) -> Quantiles:
        if not (self.p05 <= self.p50 <= self.p95):
            raise ValueError("quantiles must satisfy p05 <= p50 <= p95")
        return self


class LandingPoint(_Frozen):
    east_m: float
    north_m: float


class Ellipse95(_Frozen):
    center_east_m: float
    center_north_m: float
    semi_major_m: float = Field(ge=0)
    semi_minor_m: float = Field(ge=0)
    angle_deg: float  # major axis from east, counter-clockwise


class LandingScatter(_Frozen):
    """Landing-point scatter for the bottle and amateur tiers."""

    points: list[LandingPoint] = Field(max_length=5000)
    ellipse_95: Ellipse95


class OrbitSample(_Frozen):
    perigee_m: float
    apogee_m: float
    payload_margin_kg: float


class OrbitInsertionStats(_Frozen):
    """Orbit-insertion error distribution for the commercial and heavy tiers."""

    perigee_error_m: Quantiles
    apogee_error_m: Quantiles
    payload_margin_kg: Quantiles
    samples: list[OrbitSample] = Field(default_factory=list, max_length=5000)


class DispersionResult(_Frozen):
    tier: Tier
    n: int = Field(ge=1)
    seed: int
    success_rate: float = Field(ge=0, le=1)
    quantiles: dict[str, Quantiles] = Field(default_factory=dict)  # same keys as SimResult.metrics
    failure_counts: dict[str, int] = Field(default_factory=dict)  # reason -> count
    landing: LandingScatter | None = None
    orbit_insertion: OrbitInsertionStats | None = None
    warnings: list[str] = Field(default_factory=list)
    source_id: str = ""

    @field_validator("quantiles")
    @classmethod
    def _quantile_keys_have_units(cls, v: dict[str, Quantiles]) -> dict[str, Quantiles]:
        return _check_unit_keys(v)  # type: ignore[return-value]

    @model_validator(mode="after")
    def _tier_specific_block(self) -> DispersionResult:
        suborbital = self.tier in (Tier.BOTTLE, Tier.AMATEUR)
        if suborbital and (self.landing is None or self.orbit_insertion is not None):
            raise ValueError(
                "bottle/amateur dispersion must provide landing and not orbit_insertion"
            )
        if not suborbital and (self.orbit_insertion is None or self.landing is not None):
            raise ValueError(
                "commercial/heavy dispersion must provide orbit_insertion and not landing"
            )
        return self
