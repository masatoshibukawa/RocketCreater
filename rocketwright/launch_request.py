"""Size a launcher for a satellite handed over by SatelliteCreator (`launch_request.json`).

The satellite side owns the mass, orbit and envelope; this module turns them into a
`Requirement` and finds the smallest vehicle, derived from the nearest reference, that passes
the multistage simulation.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rocketwright.agent.tools import execute_tool
from rocketwright.references import load_references
from rocketwright.schema import Env, GoalKind, Requirement

__all__ = [
    "DEFAULT_ENV",
    "LaunchRequest",
    "LauncherResult",
    "load_launch_request",
    "size_launcher",
    "to_requirement",
]

REFERENCE_ID = "electron"
MAX_ENGINE_COUNT = 9  # the reference vehicle's first stage
DISPERSION_N = 100
DISPERSION_SEED = 42
MIN_SUCCESS_RATE = 0.9  # provisional: the same bar as the bottle workflow's selection
# Provisional: the Uchinoura-like site of scenarios/demo_commercial.yaml, eastward launch.
DEFAULT_ENV = Env(
    launch_latitude_deg=31.25,
    launch_altitude_m=20,
    wind_speed_mps=5.0,
    wind_direction_deg=200,
    earth_rotation=True,
)

Simulate = Callable[[dict[str, Any], Env, Requirement], dict[str, Any]]
Dispersion = Callable[[dict[str, Any], Env, Requirement, int, int], dict[str, Any]]


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    height: float = Field(gt=0)


class LaunchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    satellite_name: str = Field(min_length=1)
    payload_mass_kg: float = Field(gt=0)
    target_perigee_m: float = Field(gt=0)
    target_apogee_m: float = Field(gt=0)
    inclination_deg: float | None = Field(default=None, ge=0, le=180)
    envelope_mm: Envelope
    sources: dict[str, str]
    provisional: bool

    @model_validator(mode="after")
    def _check_orbit(self) -> LaunchRequest:
        if self.target_apogee_m < self.target_perigee_m:
            raise ValueError("target_apogee_m must be >= target_perigee_m")
        return self


class LauncherResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    satellite_name: str
    reference_id: str
    engine_count: int
    design: dict[str, Any]
    metrics: dict[str, float]
    cost_jpy: float
    success_rate: float
    warnings: list[str]


def load_launch_request(path: str | Path) -> LaunchRequest:
    return LaunchRequest.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def to_requirement(request: LaunchRequest) -> Requirement:
    return Requirement(
        goal_kind=GoalKind.ORBIT,
        target_altitude_m=request.target_perigee_m,
        target_apogee_m=request.target_apogee_m,
        payload_mass_kg=request.payload_mass_kg,
        text=f"{request.satellite_name} を {request.target_perigee_m / 1000:g} km の軌道へ投入する",
    )


def _simulate(design: dict[str, Any], env: Env, requirement: Requirement) -> dict[str, Any]:
    return execute_tool(
        "simulate_design",
        {
            "design": design,
            "env": env.model_dump(mode="json"),
            "seed": None,
            "requirement": requirement.model_dump(mode="json"),
            "tune_pitch": True,
            "aero_backend": None,
        },
        "launch-request",
    )


def _dispersion(
    design: dict[str, Any], env: Env, requirement: Requirement, n: int, seed: int
) -> dict[str, Any]:
    return execute_tool(
        "run_dispersion",
        {
            "design": design,
            "env": env.model_dump(mode="json"),
            "n": n,
            "seed": seed,
            "requirement": requirement.model_dump(mode="json"),
        },
        "launch-request",
    )


def _scaled(base: dict[str, Any], engine_count: int, payload_mass_kg: float) -> dict[str, Any]:
    """The reference with fewer first-stage engines and propellant and fairing to match.

    SIMPLIFICATION: structural fractions stay at the reference's values; a real vehicle this
    small would be structurally less efficient.
    """
    scale = engine_count / MAX_ENGINE_COUNT
    stages = [
        {**stage, "propellant_mass_kg": stage["propellant_mass_kg"] * scale}
        for stage in base["stages"]
    ]
    stages[0]["engine_count"] = engine_count
    return {
        **base,
        "stages": stages,
        "fairing_mass_kg": base["fairing_mass_kg"] * scale,
        "payload_mass_kg": payload_mass_kg,
    }


def _warnings(request: LaunchRequest, env: Env) -> list[str]:
    warnings = [
        "envelope_mm is not checked: the catalog has no fairing dimensions",
        "the first-stage size is scaled from the reference at constant structural fraction",
    ]
    if request.provisional:
        warnings.append("the satellite marks these values as provisional")
    if request.inclination_deg is not None:
        warnings.append(
            f"inclination {request.inclination_deg:g} deg is ignored: the ascent model is 2-D"
        )
        if request.inclination_deg < abs(env.launch_latitude_deg):
            warnings.append(
                f"inclination {request.inclination_deg:g} deg is below the launch latitude "
                f"{abs(env.launch_latitude_deg):g} deg, so a direct ascent cannot reach it"
            )
    return warnings


def size_launcher(
    request: LaunchRequest,
    *,
    env: Env = DEFAULT_ENV,
    simulate: Simulate = _simulate,
    dispersion: Dispersion = _dispersion,
) -> LauncherResult:
    """Smallest size of the reference that reaches the orbit and survives the dispersion.

    When no size reaches MIN_SUCCESS_RATE the most robust one is returned with a warning: the
    open-loop ascent has no guidance to correct thrust and Isp scatter.
    """
    requirement = to_requirement(request)
    reference = next(entry for entry in load_references() if entry.id == REFERENCE_ID)
    base = reference.design.model_dump(mode="json")
    best: LauncherResult | None = None
    for engine_count in range(1, MAX_ENGINE_COUNT + 1):
        candidate = _scaled(base, engine_count, request.payload_mass_kg)
        result = simulate(candidate, env, requirement)
        if not result.get("success"):
            continue
        design = result.get("tuned_design") or candidate
        spread = dispersion(design, env, requirement, DISPERSION_N, DISPERSION_SEED)
        sized = LauncherResult(
            satellite_name=request.satellite_name,
            reference_id=REFERENCE_ID,
            engine_count=engine_count,
            design=design,
            metrics=result["metrics"],
            cost_jpy=result["cost_jpy"],
            success_rate=spread["success_rate"],
            warnings=_warnings(request, env),
        )
        if sized.success_rate >= MIN_SUCCESS_RATE:
            return sized
        if best is None or sized.success_rate > best.success_rate:
            best = sized
    if best is None:
        raise ValueError(f"no size of {REFERENCE_ID} reaches the orbit of {request.satellite_name}")
    shortfall = f"no size reaches a success rate of {MIN_SUCCESS_RATE:g}; this is the most robust"
    return best.model_copy(update={"warnings": [*best.warnings, shortfall]})
