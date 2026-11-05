"""Common types of the pluggable aerodynamics layer (docs/aero.md).

Conventions shared by every backend:

* Coefficients use the reference area `ref_area_m2` = pi d_ref^2 / 4 and reference length
  `ref_diameter_m` given in the result (CFD backends: the body diameter of the airframe from
  rocketwright.geometry; L0: the physics module's own drag area). `cd_for_physics()` converts
  `cd` to the area the flight model uses.
* Stations are metres from the nose tip, positive aft. `cm` of a case is the pitching moment
  coefficient about `cm_ref_from_nose_m`, positive when the normal force acts aft of that point
  (restoring for a positive normal-force slope), i.e. cm = cn * (x_cp - x_ref) / d_ref.
* `fidelity`: "L0" = closed-form engineering estimate (instant), "L2" = CFD.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from rocketwright.schema import AmateurDesign, BottleDesign, Design

__all__ = [
    "AeroBackend",
    "AeroCase",
    "AeroQuery",
    "AeroResult",
    "cd_for_physics",
    "physics_ref_diameter_m",
]


@dataclass(frozen=True)
class AeroQuery:
    design: Design
    speed_mps: float = 15.0
    alphas_deg: tuple[float, ...] = (0.0, 4.0)
    cg_from_nose_m: float | None = None  # None: the geometry's CG estimate
    extra: dict[str, object] = field(default_factory=dict)  # backend-specific options

    def __post_init__(self) -> None:
        if not self.speed_mps > 0:
            raise ValueError("speed_mps must be > 0")
        if not self.alphas_deg:
            raise ValueError("alphas_deg must not be empty")
        object.__setattr__(self, "alphas_deg", tuple(float(a) for a in self.alphas_deg))
        object.__setattr__(self, "speed_mps", float(self.speed_mps))


class AeroCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    speed_mps: float
    alpha_deg: float
    cd: float
    cn: float
    cm: float
    cm_ref_from_nose_m: float = 0.0


class AeroResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    cd: float = Field(gt=0)
    cn_alpha_per_rad: float | None = None
    x_cp_from_nose_m: float | None = None
    static_margin_cal: float | None = None
    cg_from_nose_m: float | None = None
    ref_diameter_m: float = Field(gt=0)
    per_case: list[AeroCase] = Field(default_factory=list)
    backend: str
    fidelity: Literal["L0", "L2"]
    provisional: bool = True
    notes: list[str] = Field(default_factory=list)
    source: str
    wall_time_s: float | None = None
    cached: bool = False
    artifacts_dir: str | None = None

    @property
    def ref_area_m2(self) -> float:
        return math.pi * self.ref_diameter_m**2 / 4.0

    def with_cg(self, cg_from_nose_m: float | None) -> AeroResult:
        """Same coefficients with the static margin recomputed for another CG (cache hits)."""
        if cg_from_nose_m is None or self.x_cp_from_nose_m is None:
            return self.model_copy(update={"cg_from_nose_m": cg_from_nose_m})
        margin = (self.x_cp_from_nose_m - cg_from_nose_m) / self.ref_diameter_m
        return self.model_copy(
            update={"cg_from_nose_m": cg_from_nose_m, "static_margin_cal": margin}
        )

    def summary(self) -> dict[str, object]:
        out = self.model_dump(mode="json", exclude={"per_case"})
        out["cases"] = len(self.per_case)
        return out


@runtime_checkable
class AeroBackend(Protocol):
    name: str
    fidelity: Literal["L0", "L2"]
    cacheable: bool

    def available(self) -> tuple[bool, str]: ...

    def supports(self, design: Design) -> tuple[bool, str]: ...

    def evaluate(self, query: AeroQuery) -> AeroResult: ...


def physics_ref_diameter_m(design: Design) -> float:
    """Diameter whose cross-section the flight model multiplies its Cd with."""
    if isinstance(design, BottleDesign):
        from rocketwright.physics import water

        return water.bottle_diameter_m(design.bottle_volume_m3)
    if isinstance(design, AmateurDesign):
        return design.body_diameter_m
    raise ValueError(f"no aero reference diameter for tier {design.tier!r}")


def cd_for_physics(result: AeroResult, design: Design) -> float:
    """`result.cd` re-referenced to the flight model's drag area (same drag force)."""
    return result.cd * (result.ref_diameter_m / physics_ref_diameter_m(design)) ** 2
