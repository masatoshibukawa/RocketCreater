"""Cost estimation (CLAUDE.md section 5): BOM-style roll-up for bottle/amateur, mass-based
estimate for commercial/heavy.

Every constant below is `provisional` (no source yet) and is listed in README "Values to
confirm". Phase 3 replaces the bottle/amateur roll-up with real catalog prices.

`cost_breakdown` returns the same estimate as `estimate_cost_jpy` split into labelled items for
the UI (labels in Japanese, notes showing the arithmetic); the items always sum to the estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rocketwright.schema import AmateurDesign, BottleDesign, Design, MultistageDesign

__all__ = ["COST_CONSTANTS", "CostItem", "cost_breakdown", "estimate_cost_jpy", "liftoff_mass_kg"]

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


def _p(key: str) -> bool:
    return bool(COST_CONSTANTS[key]["provisional"])


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


# --------------------------------------------------------------------------- breakdown


@dataclass(frozen=True)
class CostItem:
    """One line of the cost breakdown shown in the UI. `note` spells out the arithmetic."""

    label: str
    jpy: float
    note: str
    provisional: bool


def _yen(value: float) -> str:
    return f"{value:,.0f} 円"


def _kg(value: float) -> str:
    """Mass for a note: up to 3 decimals below 100 kg, whole kilograms above."""
    if value >= 100.0:
        return f"{value:,.0f} kg"
    return f"{value:,.3f}".rstrip("0").rstrip(".") + " kg"


def _breakdown_bottle(design: BottleDesign) -> list[CostItem]:
    items = [
        CostItem(
            "ボトル・ノズル・フィン・発射台",
            _c("bottle_base_jpy"),
            f"定額 {_yen(_c('bottle_base_jpy'))}",
            _p("bottle_base_jpy"),
        )
    ]
    if design.has_parachute:
        items.append(
            CostItem(
                "パラシュート",
                _c("bottle_parachute_jpy"),
                f"定額 {_yen(_c('bottle_parachute_jpy'))}",
                _p("bottle_parachute_jpy"),
            )
        )
    return items


def _breakdown_amateur(design: AmateurDesign) -> list[CostItem]:
    chute_area_m2 = math.pi * (design.parachute_diameter_m / 2) ** 2
    airframe_per_kg = _c("amateur_airframe_jpy_per_kg")
    fin = _c("amateur_fin_jpy")
    chute_per_m2 = _c("amateur_parachute_jpy_per_m2")
    return [
        CostItem(
            "機体（チューブ・ノーズ・フィン）",
            airframe_per_kg * design.dry_mass_kg,
            f"{airframe_per_kg:,.0f} 円/kg × {_kg(design.dry_mass_kg)}",
            _p("amateur_airframe_jpy_per_kg"),
        ),
        CostItem(
            "フィン",
            fin * design.fins.count,
            f"{fin:,.0f} 円/枚 × {design.fins.count} 枚",
            _p("amateur_fin_jpy"),
        ),
        CostItem(
            "モーター",
            _c("amateur_motor_jpy"),
            f"定額 {_yen(_c('amateur_motor_jpy'))}（{design.motor_id}）",
            _p("amateur_motor_jpy"),
        ),
        CostItem(
            "パラシュート",
            chute_per_m2 * chute_area_m2,
            f"{chute_per_m2:,.0f} 円/m² × {chute_area_m2:.3f} m²"
            f"（直径 {design.parachute_diameter_m:.2f} m）",
            _p("amateur_parachute_jpy_per_m2"),
        ),
        CostItem(
            "電子機器（高度計・開傘）",
            _c("amateur_electronics_jpy"),
            f"定額 {_yen(_c('amateur_electronics_jpy'))}",
            _p("amateur_electronics_jpy"),
        ),
    ]


def _breakdown_multistage(design: MultistageDesign) -> list[CostItem]:
    """The mass-based estimate split across stages / boosters / fairing / payload in proportion
    to their mass (the same masses `liftoff_mass_kg` adds up)."""
    key = (
        "commercial_jpy_per_kg_liftoff"
        if design.tier == "commercial"
        else "heavy_jpy_per_kg_liftoff"
    )
    per_kg = _c(key)
    provisional = _p(key) or _p("booster_mass_kg_placeholder")
    rate = f"{per_kg:,.0f} 円/kg"
    items: list[CostItem] = []
    for i, stage in enumerate(design.stages, start=1):
        mass = stage.propellant_mass_kg / (1.0 - stage.structural_fraction)
        structure = mass - stage.propellant_mass_kg
        items.append(
            CostItem(
                f"第{i}段（推進剤＋構造）",
                per_kg * mass,
                f"{rate} × {_kg(mass)}（推進剤 {_kg(stage.propellant_mass_kg)} "
                f"＋ 構造 {_kg(structure)}）",
                provisional,
            )
        )
    booster_count = sum(b.count for b in design.boosters)
    if booster_count:
        per_booster = _c("booster_mass_kg_placeholder")
        mass = booster_count * per_booster
        items.append(
            CostItem(
                "ブースタ",
                per_kg * mass,
                f"{rate} × {_kg(mass)}（{_kg(per_booster)}/本 × {booster_count} 本、仮置き）",
                provisional,
            )
        )
    if design.fairing_mass_kg > 0:
        items.append(
            CostItem(
                "フェアリング",
                per_kg * design.fairing_mass_kg,
                f"{rate} × {_kg(design.fairing_mass_kg)}",
                provisional,
            )
        )
    if design.payload_mass_kg > 0:
        items.append(
            CostItem(
                "積載インターフェース（積載質量分）",
                per_kg * design.payload_mass_kg,
                f"{rate} × {_kg(design.payload_mass_kg)}",
                provisional,
            )
        )
    return items


def cost_breakdown(design: Design) -> list[CostItem]:
    """Itemised version of `estimate_cost_jpy(design)`; the items sum to the estimate."""
    if isinstance(design, BottleDesign):
        return _breakdown_bottle(design)
    if isinstance(design, AmateurDesign):
        return _breakdown_amateur(design)
    if isinstance(design, MultistageDesign):
        return _breakdown_multistage(design)
    raise TypeError(f"unsupported design type {type(design).__name__}")
