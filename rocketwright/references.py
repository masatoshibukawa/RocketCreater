"""Reference vehicles: real rockets with a published requirement, design and performance.

Entries live in `rocketwright/catalog/references/<tier>.yaml`. Every entry must cite at least one
public source; numbers not confirmed by a human are `provisional: true`. Two uses:

1. Precision: `reproduce()` flies the published design through our own physics and reports the
   error against the published performance (`scripts/check_references.py`, tests).
2. Design seeds: `find_nearest()` picks the closest references to a Requirement so the agent can
   start from a real vehicle instead of a blank sheet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rocketwright.physics import multistage, solid, water
from rocketwright.schema import (
    UNIT_SUFFIXES,
    Design,
    Env,
    GoalKind,
    MultistageDesign,
    Requirement,
    SimResult,
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
