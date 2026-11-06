"""Flight -> CFD -> Cd -> flight -> design loop for a bottle rocket (docs/aero.md section 7).

Each round flies the current design, solves the airframe at that flight's top speed, re-tunes
the launch pressure to the listed value that lands nearest the target with the new Cd, and
flies again. It stops when the Cd moved less than CD_TOLERANCE_FRAC and the pressure stayed.

SIMPLIFICATION: the Cd of one speed (the flight's maximum, rounded to 1 m/s so that nearby
flights share a cached solve) is used for the whole flight, as in agent/tools.py.
SIMPLIFICATION: only the pressure is re-tuned. Fill, nozzle and airframe stay as given.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict

from rocketwright.aero.base import AeroQuery, cd_for_physics
from rocketwright.aero.registry import evaluate
from rocketwright.geometry import AssembledShape
from rocketwright.physics import water
from rocketwright.schema import BottleDesign, Design, Env

__all__ = ["AeroLoopResult", "AeroLoopRound", "run_aero_loop"]

CD_TOLERANCE_FRAC = 0.02
DEFAULT_MAX_ROUNDS = 6
DEFAULT_ALPHAS_DEG = (0.0, 4.0)
MIN_CFD_SPEED_MPS = 1.0
SIM_SEED = 0  # the nominal water model is deterministic and ignores it
CALIBRATION_NOTE = (
    "water.py's Cd 0.8 and air impulse efficiency 0.25 were calibrated as a pair against "
    "measured flights; with a CFD Cd that pair no longer holds, so this apogee is not a "
    "calibrated prediction"
)


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class AeroLoopRound(_Record):
    round: int
    flight_pressure_kpa: float  # the flight this round's CFD speed comes from
    flight_cd: float
    flight_apogee_m: float
    max_speed_mps: float
    cfd_speed_mps: float
    cd: float  # CFD result on the flight model's drag area
    cd_change_frac: float
    x_cp_from_nose_m: float | None
    static_margin_cal: float | None
    pressure_kpa: float  # after the design update
    apogee_m: float  # flown with `pressure_kpa` and `cd`
    descent_speed_mps: float
    elapsed_s: float
    cached: bool
    backend: str
    fidelity: str


class AeroLoopResult(_Record):
    rounds: list[AeroLoopRound]
    converged: bool
    final_design: BottleDesign
    artifacts_dir: str | None
    notes: list[str]


def _fly(design: BottleDesign, env: Env, target_apogee_m: float) -> dict[str, float]:
    return water.simulate(design, env, SIM_SEED, target_apogee_m=target_apogee_m).metrics


def _at(design: BottleDesign, pressure_kpa: float, cd: float) -> BottleDesign:
    return design.model_copy(
        update={"initial_gauge_pressure_pa": pressure_kpa * 1000.0, "axial_drag_coefficient": cd}
    )


def _retune(
    design: BottleDesign, env: Env, target_apogee_m: float, pressures: list[float], cd: float
) -> BottleDesign:
    """The listed pressure whose flight with this Cd lands nearest the target."""

    def miss(pressure_kpa: float) -> float:
        apogee = _fly(_at(design, pressure_kpa, cd), env, target_apogee_m)["apogee_m"]
        return abs(apogee - target_apogee_m)

    return _at(design, min(pressures, key=miss), cd)


def run_aero_loop(
    design: Design,
    env: Env,
    *,
    target_apogee_m: float,
    pressures_kpa: Iterable[float],
    backend: str = "auto",
    shape: AssembledShape | None = None,
    cg_from_nose_m: float | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    alphas_deg: tuple[float, ...] = DEFAULT_ALPHAS_DEG,
    extra: Mapping[str, object] | None = None,
) -> AeroLoopResult:
    """Iterate flight and CFD on `design`. `extra` goes to the backend (AeroQuery.extra)."""
    pressures = [float(p) for p in pressures_kpa]
    if not isinstance(design, BottleDesign):
        raise ValueError("the aero loop tunes launch pressure: bottle designs only")
    if not pressures or min(pressures) <= 0:
        raise ValueError("pressures_kpa must list at least one pressure, all > 0")
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    if not target_apogee_m > 0:
        raise ValueError("target_apogee_m must be > 0")

    cd = design.axial_drag_coefficient or water.DEFAULT_CD
    current = design.model_copy(update={"axial_drag_coefficient": cd})
    rounds: list[AeroLoopRound] = []
    notes: list[str] = []
    artifacts_dir = None
    converged = False
    for number in range(1, max_rounds + 1):
        started = time.monotonic()
        flown = current
        flight = _fly(flown, env, target_apogee_m)
        speed = float(round(flight["max_speed_mps"]))
        if speed < MIN_CFD_SPEED_MPS:
            raise ValueError(f"the vehicle did not fly (top speed {flight['max_speed_mps']:.2f})")
        query = AeroQuery(
            design=flown,
            speed_mps=speed,
            alphas_deg=alphas_deg,
            cg_from_nose_m=cg_from_nose_m,
            extra=dict(extra or {}),
            shape=shape,
        )
        solved = evaluate(query, backend=backend)
        new_cd = cd_for_physics(solved, flown)
        current = _retune(flown, env, target_apogee_m, pressures, new_cd)
        after = _fly(current, env, target_apogee_m)
        change = abs(new_cd - cd) / cd
        rounds.append(
            AeroLoopRound(
                round=number,
                flight_pressure_kpa=flown.initial_gauge_pressure_pa / 1000.0,
                flight_cd=cd,
                flight_apogee_m=flight["apogee_m"],
                max_speed_mps=flight["max_speed_mps"],
                cfd_speed_mps=speed,
                cd=new_cd,
                cd_change_frac=change,
                x_cp_from_nose_m=solved.x_cp_from_nose_m,
                static_margin_cal=solved.static_margin_cal,
                pressure_kpa=current.initial_gauge_pressure_pa / 1000.0,
                apogee_m=after["apogee_m"],
                descent_speed_mps=after["descent_speed_mps"],
                elapsed_s=time.monotonic() - started,
                cached=solved.cached,
                backend=solved.backend,
                fidelity=solved.fidelity,
            )
        )
        notes += [n for n in solved.notes if n not in notes]
        artifacts_dir = solved.artifacts_dir or artifacts_dir
        cd = new_cd
        pressure_held = current.initial_gauge_pressure_pa == flown.initial_gauge_pressure_pa
        if change < CD_TOLERANCE_FRAC and pressure_held:
            converged = True
            break
    if not converged:
        notes.append(f"not converged after {max_rounds} rounds")
    if any(r.fidelity != "L0" for r in rounds):
        notes.append(CALIBRATION_NOTE)
    return AeroLoopResult(
        rounds=rounds,
        converged=converged,
        final_design=current,
        artifacts_dir=artifacts_dir,
        notes=notes,
    )
