"""Inputs and physics used by the hybrid-start, 1.5 L egg-recovery experiment."""

from __future__ import annotations

import math
from pathlib import Path
from random import Random

import yaml

from rocketwright.agent.tools import execute_tool
from rocketwright.cost import estimate_cost_jpy
from rocketwright.physics import recovery, water
from rocketwright.schema import BottleDesign, Env, Requirement

REQUIREMENT = Requirement(
    goal_kind="altitude",
    target_altitude_m=30,
    payload_mass_kg=0.060,
    budget_jpy=3000,
    recovery_required=True,
)
VOLUME_M3 = 0.0015
ENV = Env(launch_latitude_deg=35, launch_altitude_m=20, wind_speed_mps=2, wind_direction_deg=270)
FILL_PCT = (25, 35, 45)
PRESSURE_KPA = tuple(range(200, 501, 25))  # simulation search domain, not equipment ratings
NOZZLE_MM = (9, 22)
SELECTION_SEED, CONFIRMATION_SEED = 71, 1701


def starts() -> dict[str, dict]:
    path = Path(__file__).with_name("catalog") / "bottle_starts.yaml"
    records = yaml.safe_load(path.read_text(encoding="utf-8"))
    side = records["D02"]["canopy_octagon_side_m"]
    area = 2 * (1 + math.sqrt(2)) * side**2
    records["D02"]["canopy_diameter_m"] = math.sqrt(4 * area / math.pi)
    # Independent draw inside the same mission envelope, with no literature flight data.
    rng = Random(29)
    records["new"] = {
        "title": "Constraint-generated airframe",
        "dry_mass_kg": rng.choice([0.11, 0.13, 0.14, 0.16]),
        "canopy_diameter_m": rng.choice([0.40, 0.45, 0.55]),
        "initial_nozzle_mm": rng.choice(NOZZLE_MM),
        "assumptions": "Seed 29 selects mass, canopy and nozzle from provisional discrete sets.",
    }
    return records


def design_at(record: dict, nozzle_mm: int, pressure_kpa: int, fill_pct: int) -> BottleDesign:
    if nozzle_mm not in NOZZLE_MM or pressure_kpa not in PRESSURE_KPA or fill_pct not in FILL_PCT:
        raise ValueError("outside the registered search domain")
    # The 9 mm insert adds 10 g relative to the open neck (parts.yaml).
    mass = record["dry_mass_kg"] + 0.010 * (
        int(nozzle_mm == 9) - int(record["initial_nozzle_mm"] == 9)
    )
    return BottleDesign(
        bottle_volume_m3=VOLUME_M3,
        water_fill_frac=fill_pct / 100,
        initial_gauge_pressure_pa=pressure_kpa * 1000,
        nozzle_diameter_m=nozzle_mm / 1000,
        dry_mass_kg=mass,
        payload_mass_kg=REQUIREMENT.payload_mass_kg,
        has_fins=True,
        has_parachute=True,
        parachute_diameter_m=record["canopy_diameter_m"],
    )


def component_screen(design: BottleDesign) -> dict:
    """Cheap screen; depletion and complete opening are assumptions, not measured events."""
    area = math.pi * (design.nozzle_diameter_m / 2) ** 2
    empty_mass = design.dry_mass_kg + design.payload_mass_kg
    wet_mass = (
        empty_mass + water.WATER_DENSITY_KGPM3 * design.bottle_volume_m3 * design.water_fill_frac
    )
    thrust_weight = 2 * design.initial_gauge_pressure_pa * area / (wet_mass * water.G0_MPS2)
    descent = recovery.descend(
        empty_mass,
        design.parachute_diameter_m,
        ENV,
        REQUIREMENT.target_altitude_m,
    )
    cost = estimate_cost_jpy(design)
    speed_limit = water.PASS_THRESHOLDS["max_descent_speed_with_payload_mps"]
    return {
        "initial_thrust_weight": thrust_weight,
        "screen_descent_mps": descent.descent_speed_mps,
        "estimated_cost_jpy": cost,
        "eligible": (
            thrust_weight > 1
            and descent.descent_speed_mps <= speed_limit
            and cost <= REQUIREMENT.budget_jpy
        ),
    }


def flight_tool(name: str, design: BottleDesign, trial_id: str, *, env=ENV, **options) -> dict:
    args = {
        "design": design.model_dump(mode="json"),
        "env": env.model_dump(mode="json"),
        "requirement": REQUIREMENT.model_dump(mode="json"),
        **options,
    }
    result = execute_tool(name, args, trial_id)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result
