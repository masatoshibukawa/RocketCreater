"""Cost estimation (CLAUDE.md section 5): BOM-style roll-up for bottle/amateur, mass-based
estimate for commercial/heavy.

Every constant below is `provisional` (no source yet) and is listed in README "Values to
confirm". Phase 3 replaces the bottle/amateur roll-up with real catalog prices.
"""

from __future__ import annotations

import math

from rocketwright.schema import AmateurDesign, BottleDesign, Design, MultistageDesign

__all__ = ["COST_CONSTANTS", "estimate_cost_jpy", "liftoff_mass_kg"]

# SIMPLIFICATION: flat placeholder prices. All values provisional (JPY).
COST_CONSTANTS: dict[str, dict[str, float | bool]] = {
    "bottle_base_jpy": {"value": 1500.0, "provisional": True},  # bottle, nozzle, fins, launcher
    "bottle_parachute_jpy": {"value": 800.0, "provisional": True},
    "amateur_airframe_jpy_per_kg": {"value": 12000.0, "provisional": True},  # tubes, nose, fins
    "amateur_fin_jpy": {"value": 500.0, "provisional": True},  # per fin
    "amateur_motor_jpy": {"value": 8000.0, "provisional": True},  # mid-power reload, flat
    "amateur_parachute_jpy_per_m2": {"value": 6000.0, "provisional": True},
    "amateur_electronics_jpy": {"value": 10000.0, "provisional": True},  # altimeter + deploy
    "commercial_jpy_per_kg_liftoff": {"value": 80000.0, "provisional": True},
    "heavy_jpy_per_kg_liftoff": {"value": 25000.0, "provisional": True},
    "booster_mass_kg_placeholder": {"value": 20000.0, "provisional": True},  # per strap-on
}


def _c(key: str) -> float:
    return float(COST_CONSTANTS[key]["value"])


def liftoff_mass_kg(design: MultistageDesign) -> float:
    """Gross liftoff mass: stage propellant + structure, fairing, payload and boosters."""
    total = design.fairing_mass_kg + design.payload_mass_kg
    for stage in design.stages:
        total += stage.propellant_mass_kg / (1.0 - stage.structural_fraction)
    # SIMPLIFICATION: booster mass is a placeholder until the catalog carries it.
    total += sum(b.count for b in design.boosters) * _c("booster_mass_kg_placeholder")
    return total


def estimate_cost_jpy(design: Design) -> float:
    if isinstance(design, BottleDesign):
        cost = _c("bottle_base_jpy")
        if design.has_parachute:
            cost += _c("bottle_parachute_jpy")
        return cost
    if isinstance(design, AmateurDesign):
        chute_area_m2 = math.pi * (design.parachute_diameter_m / 2) ** 2
        return (
            _c("amateur_airframe_jpy_per_kg") * design.dry_mass_kg
            + _c("amateur_fin_jpy") * design.fins.count
            + _c("amateur_motor_jpy")
            + _c("amateur_parachute_jpy_per_m2") * chute_area_m2
            + _c("amateur_electronics_jpy")
        )
    if isinstance(design, MultistageDesign):
        per_kg = (
            _c("commercial_jpy_per_kg_liftoff")
            if design.tier == "commercial"
            else _c("heavy_jpy_per_kg_liftoff")
        )
        return per_kg * liftoff_mass_kg(design)
    raise TypeError(f"unsupported design type {type(design).__name__}")
