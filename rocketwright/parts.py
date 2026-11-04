"""Parts catalog (v2 `parts.yaml`, see catalog/PARTS_SCHEMA.md) for the bottle and amateur tiers.

A design in these tiers is a choice of parts (rocketwright.build); masses, dimensions and prices
come from the parts, never from the agent (CLAUDE.md section 2). Every part carries a `source`
URL or `provisional: true`.

* `Part` subclasses, one per `kind`, validate the kind-specific fields of the schema table.
* `load_parts(path)` reads and caches a catalog; it checks ids are unique, cross-references
  (`fits_tube_id`) exist and the source-or-provisional rule. A v1 file (only `items:`) or a
  missing file gives an empty catalog with a warning instead of an exception, so the rest of
  the system keeps working while the catalog is being rewritten.
* `PartsCatalog.get(id, kind=...)` / `.by_kind(kind, tier=...)` are the two lookups the build
  layer and the `list_parts` tool need.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

__all__ = [
    "DEFAULT_PARTS_PATH",
    "KINDS",
    "BodyTube",
    "Bottle",
    "BottleFinSet",
    "Coupler",
    "FinMaterial",
    "LaunchLug",
    "Launcher",
    "MotorMount",
    "NoseCone",
    "Nozzle",
    "Parachute",
    "Part",
    "PartsCatalog",
    "RecoveryHardware",
    "load_parts",
]

DEFAULT_PARTS_PATH = Path(__file__).resolve().parent / "catalog" / "parts.yaml"

PartTier = Literal["amateur", "bottle"]


class Part(BaseModel):
    """Common fields of every catalog entry. Unknown keys are ignored (the data file may carry
    editorial fields such as `license`); `source` or `provisional` is mandatory."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    kind: str
    tier: PartTier
    name: str = Field(min_length=1)
    mass_kg: float = Field(ge=0)
    price_jpy: float = Field(ge=0)
    source: str | None = None
    provisional: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _source_or_provisional(self) -> Part:
        if not self.provisional and not self.source:
            raise ValueError(f"part {self.id!r} needs a `source` URL or `provisional: true`")
        return self


class BodyTube(Part):
    kind: Literal["body_tube"]
    outer_diameter_m: float = Field(gt=0)
    inner_diameter_m: float = Field(gt=0)
    length_m: float = Field(gt=0)  # stock length; mass_kg is the mass at this length
    # Power rating: the largest motor total impulse the airframe is built for (the upper bound
    # of the largest NAR/TRA class its kits fly, `rating_note` names the evidence). None =
    # unrated (buildability warns instead of checking).
    max_motor_impulse_ns: float | None = Field(default=None, gt=0)
    rating_note: str = ""

    @model_validator(mode="after")
    def _id_lt_od(self) -> BodyTube:
        if self.inner_diameter_m >= self.outer_diameter_m:
            raise ValueError(f"body tube {self.id!r}: inner diameter must be < outer diameter")
        return self


class NoseCone(Part):
    kind: Literal["nose_cone"]
    fits_tube_id: str
    shape: Literal["conical", "ogive", "elliptical"]
    length_m: float = Field(gt=0)  # exposed length
    shoulder_length_m: float = Field(ge=0)


class MotorMount(Part):
    kind: Literal["motor_mount"]
    motor_diameter_m: float = Field(gt=0)
    fits_tube_id: str  # primary tube (used when seeding); `fits_tube_ids` lists the others
    fits_tube_ids: list[str] = Field(default_factory=list)
    length_m: float = Field(gt=0)

    @property
    def fits_tubes(self) -> frozenset[str]:
        return frozenset([self.fits_tube_id, *self.fits_tube_ids])


class FinMaterial(Part):
    kind: Literal["fin_material"]
    thickness_m: float = Field(gt=0)
    areal_mass_kgpm2: float = Field(gt=0)
    sheet_width_m: float = Field(gt=0)
    sheet_height_m: float = Field(gt=0)
    max_motor_impulse_ns: float | None = Field(default=None, gt=0)  # as BodyTube
    rating_note: str = ""


class Parachute(Part):
    kind: Literal["parachute"]
    diameter_m: float = Field(gt=0)
    packed_diameter_m: float = Field(gt=0)
    cd: float = Field(default=1.5, gt=0)


class Coupler(Part):
    """Tube coupler joining two stock tubes of `fits_tube_id` (a body longer than one stock tube
    needs tubes - 1 of them)."""

    kind: Literal["coupler"]
    fits_tube_id: str
    length_m: float = Field(gt=0)


class RecoveryHardware(Part):
    kind: Literal["recovery_hardware"]
    # The heaviest rocket (liftoff mass) the shock cord and its mount are sold for; None =
    # unrated.
    max_rocket_mass_kg: float | None = Field(default=None, gt=0)
    rating_note: str = ""


class LaunchLug(Part):
    kind: Literal["launch_lug"]
    fits_rod_diameter_m: float = Field(gt=0)


class Bottle(Part):
    kind: Literal["bottle"]
    volume_m3: float = Field(gt=0)
    body_diameter_m: float = Field(gt=0)
    length_m: float = Field(gt=0)
    neck_diameter_m: float = Field(gt=0)
    max_gauge_pressure_pa: float = Field(gt=0)


class Nozzle(Part):
    kind: Literal["nozzle"]
    diameter_m: float = Field(gt=0)
    fits_neck_diameter_m: float = Field(gt=0)


class BottleFinSet(Part):
    kind: Literal["bottle_fin_set"]
    count: int = Field(ge=1)
    span_m: float = Field(gt=0)


class Launcher(Part):
    kind: Literal["launcher"]
    max_gauge_pressure_pa: float = Field(gt=0)
    rail_length_m: float = Field(gt=0)


AnyPart = Annotated[
    Union[  # noqa: UP007 - Union keeps Annotated readable
        BodyTube,
        NoseCone,
        MotorMount,
        FinMaterial,
        Parachute,
        RecoveryHardware,
        LaunchLug,
        Coupler,
        Bottle,
        Nozzle,
        BottleFinSet,
        Launcher,
    ],
    Field(discriminator="kind"),
]
_PartAdapter: TypeAdapter[AnyPart] = TypeAdapter(AnyPart)

KINDS: tuple[str, ...] = (
    "body_tube",
    "nose_cone",
    "motor_mount",
    "fin_material",
    "parachute",
    "recovery_hardware",
    "launch_lug",
    "coupler",
    "bottle",
    "nozzle",
    "bottle_fin_set",
    "launcher",
)
# Which kinds reference a body tube through `fits_tube_id`.
_TUBE_REFERENCING_KINDS = ("nose_cone", "motor_mount", "coupler")


class PartsCatalog:
    """Immutable, id-indexed view of the parts list."""

    def __init__(self, parts: list[Part], *, path: Path | None = None) -> None:
        self._parts: tuple[Part, ...] = tuple(parts)
        self._by_id: dict[str, Part] = {p.id: p for p in self._parts}
        self.path = path

    def __len__(self) -> int:
        return len(self._parts)

    @property
    def parts(self) -> tuple[Part, ...]:
        return self._parts

    def ids(self) -> list[str]:
        return list(self._by_id)

    def get(self, part_id: str, kind: str | None = None) -> Any:
        """The part with `part_id`. With `kind`, a part of another kind is a ValueError (the
        build layer passes the expected kind so a swapped id is reported clearly)."""
        part = self._by_id.get(part_id)
        if part is None:
            hint = self.ids() if kind is None else [p.id for p in self.by_kind(kind)]
            raise KeyError(f"unknown part id {part_id!r}; available: {hint}")
        if kind is not None and part.kind != kind:
            raise ValueError(
                f"part {part_id!r} is a {part.kind}, expected a {kind}; "
                f"{kind} ids: {[p.id for p in self.by_kind(kind)]}"
            )
        return part

    def by_kind(self, kind: str, tier: str | None = None) -> list[Any]:
        return [p for p in self._parts if p.kind == kind and (tier is None or p.tier == tier)]

    def coupler_for(self, tube_id: str) -> Any | None:
        """The lightest coupler that fits `tube_id` (ties: cheapest, id), or None."""
        fits = [c for c in self.by_kind("coupler") if c.fits_tube_id == tube_id]
        return min(fits, key=lambda c: (c.mass_kg, c.price_jpy, c.id), default=None)


def _validate_catalog(parts: list[Part]) -> None:
    seen: set[str] = set()
    for p in parts:
        if p.id in seen:
            raise ValueError(f"duplicate part id {p.id!r}")
        seen.add(p.id)
    by_id = {p.id: p for p in parts}
    for p in parts:
        if p.kind not in _TUBE_REFERENCING_KINDS:
            continue
        refs = [p.fits_tube_id, *getattr(p, "fits_tube_ids", [])]  # type: ignore[attr-defined]
        for ref in refs:
            tube = by_id.get(ref)
            if tube is None or tube.kind != "body_tube":
                raise ValueError(
                    f"part {p.id!r}: fits_tube_id {ref!r} is not a body_tube in the catalog"
                )
            if tube.tier != p.tier:
                raise ValueError(f"part {p.id!r} and tube {tube.id!r} are in different tiers")


def parse_parts(data: Any, *, path: Path | None = None) -> PartsCatalog:
    """Build a catalog from the parsed YAML mapping. `items:` (v1) is ignored; a missing
    `parts:` key gives an empty catalog with a warning."""
    if not isinstance(data, dict) or "parts" not in data:
        warnings.warn(
            f"parts catalog {path or '<data>'} has no `parts:` key (v1 file?); using an empty "
            "catalog: list_parts / design_from_parts will find nothing until it is rewritten "
            "to the v2 format",
            stacklevel=2,
        )
        return PartsCatalog([], path=path)
    raw_parts = data.get("parts") or []
    if not isinstance(raw_parts, list):
        raise ValueError(f"parts catalog {path}: `parts:` must be a list")
    parts: list[Part] = []
    for i, raw in enumerate(raw_parts):
        if not isinstance(raw, dict):
            raise ValueError(f"parts catalog {path}: entry {i} is not a mapping")
        try:
            parts.append(_PartAdapter.validate_python(raw))
        except ValueError as exc:
            raise ValueError(f"parts catalog {path}: entry {raw.get('id', i)!r}: {exc}") from exc
    _validate_catalog(parts)
    return PartsCatalog(parts, path=path)


@lru_cache(maxsize=8)
def _load_parts_cached(path: Path) -> PartsCatalog:
    if not path.is_file():
        warnings.warn(f"parts catalog {path} not found; using an empty catalog", stacklevel=3)
        return PartsCatalog([], path=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_parts(data, path=path)


def load_parts(path: Path | str | None = None) -> PartsCatalog:
    """Read and cache the catalog at `path` (default: catalog/parts.yaml)."""
    p = DEFAULT_PARTS_PATH if path is None else Path(path)
    return _load_parts_cached(p.resolve())
