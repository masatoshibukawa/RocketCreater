"""Design summary for the UI (`POST /artifacts/summary`): cost with its breakdown, bill of
materials, mass budget and overall dimensions of a design, all from code (CLAUDE.md section 2).

The `drawing` entry is left `None` here; the API fills it after storing the rendered side view,
because the summary itself has no artifact store.

Geometry rules are shared with `drawing.py` so the numbers match the picture:

* bottle: diameter from `physics.water.bottle_diameter_m`, length = (nose + body + neck)
  diameters from the drawing's ratios (SIMPLIFICATION, see drawing.py);
* multistage: the drawing's cylinder rule (diameter = k x total propellant^(1/3), stage length
  from propellant at `PROPELLANT_BULK_DENSITY_KGPM3`, fairing `FAIRING_LENGTH_DIAMETERS` long).
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from rocketwright import drawing
from rocketwright.build import AmateurBuild, BottleBuild, BuildBill, check_buildability, resolve
from rocketwright.cost import CostItem, cost_breakdown, estimate_cost_jpy, liftoff_mass_kg
from rocketwright.parts import PartsCatalog, load_parts
from rocketwright.report import bom_rows
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    MultistageDesign,
    Requirement,
)

__all__ = ["design_summary", "design_summary_from_build"]

WATER_DENSITY_KGPM3 = 1000.0


def _mass_bottle(design: BottleDesign) -> dict[str, float]:
    water = design.water_fill_frac * design.bottle_volume_m3 * WATER_DENSITY_KGPM3
    return {
        "liftoff_mass_kg": design.dry_mass_kg + design.payload_mass_kg + water,
        "dry_mass_kg": design.dry_mass_kg,
        "payload_mass_kg": design.payload_mass_kg,
        "propellant_mass_kg": water,  # water; the compressed air is not counted
    }


def _mass_amateur(design: AmateurDesign, warnings: list[str]) -> dict[str, float]:
    motor_total = 0.0
    propellant = 0.0
    try:
        from rocketwright.physics.solid import load_motor

        motor = load_motor(design.motor_id)
        motor_total = float(motor.total_mass_kg)
        propellant = float(motor.propellant_mass_kg)
    except Exception as exc:  # unknown motor id or stub physics: report, do not guess
        warnings.append(f"motor {design.motor_id!r} not in the catalog; motor mass set to 0: {exc}")
    return {
        "liftoff_mass_kg": design.dry_mass_kg + design.payload_mass_kg + motor_total,
        "dry_mass_kg": design.dry_mass_kg,  # airframe without motor and payload (schema)
        "payload_mass_kg": design.payload_mass_kg,
        "propellant_mass_kg": propellant,
        "motor_mass_kg": motor_total,  # loaded motor (case + propellant)
    }


def _mass_multistage(design: MultistageDesign) -> dict[str, float]:
    propellant = sum(s.propellant_mass_kg for s in design.stages)
    structure = sum(
        s.propellant_mass_kg * s.structural_fraction / (1.0 - s.structural_fraction)
        for s in design.stages
    )
    liftoff = liftoff_mass_kg(design)
    booster = liftoff - propellant - structure - design.fairing_mass_kg - design.payload_mass_kg
    return {
        "liftoff_mass_kg": liftoff,
        "dry_mass_kg": liftoff - propellant - design.payload_mass_kg,
        "payload_mass_kg": design.payload_mass_kg,
        "propellant_mass_kg": propellant,  # stage propellant; boosters are a placeholder mass
        "structure_mass_kg": structure,
        "fairing_mass_kg": design.fairing_mass_kg,
        "booster_mass_kg": max(booster, 0.0),
    }


def _dims_bottle(design: BottleDesign) -> dict[str, float]:
    if design.geometry:
        return {
            "length_m": design.geometry.overall_mm / 1000,
            "diameter_m": design.geometry.body_diameter_mm / 1000,
        }
    from rocketwright.physics.water import bottle_diameter_m

    d = bottle_diameter_m(design.bottle_volume_m3)
    ratio = (
        drawing.BOTTLE_NOSE_DIAMETERS + drawing.BOTTLE_ASPECT_RATIO + drawing.BOTTLE_NECK_DIAMETERS
    )
    return {"length_m": ratio * d, "diameter_m": d}


def _dims_amateur(design: AmateurDesign) -> dict[str, float]:
    return {
        "length_m": design.nose_length_m + design.body_length_m,
        "diameter_m": design.body_diameter_m,
    }


def _dims_multistage(design: MultistageDesign) -> dict[str, float]:
    # Same rule as drawing._render_multistage (private helpers reused on purpose).
    k = drawing._multistage_diameter_const()
    booster_prop = 0.0
    for b in design.boosters:
        per = drawing._booster_propellant_kg(b.booster_id)
        if per is not None:
            booster_prop += per * b.count
    total_prop = sum(s.propellant_mass_kg for s in design.stages) + booster_prop
    d = k * total_prop ** (1.0 / 3.0)
    area = math.pi * d**2 / 4.0
    stages = sum(
        s.propellant_mass_kg / (drawing.PROPELLANT_BULK_DENSITY_KGPM3 * area) for s in design.stages
    )
    fairing = drawing.FAIRING_LENGTH_DIAMETERS * d
    return {"length_m": fairing + stages, "diameter_m": d}


def design_summary(design: Design, requirement: Requirement | None = None) -> dict[str, Any]:
    """Cost, breakdown, BOM, mass budget and dimensions of `design` as a JSON-ready dict.

    Raises ValueError when `requirement.tier_override` names a different tier than the design.
    """
    if requirement is not None and requirement.tier_override is not None:
        if requirement.tier_override.value != design.tier:
            raise ValueError(
                f"design tier {design.tier!r} does not match the requirement's tier "
                f"{requirement.tier_override.value!r}"
            )
    warnings: list[str] = []
    if isinstance(design, BottleDesign):
        mass, dims = _mass_bottle(design), _dims_bottle(design)
    elif isinstance(design, AmateurDesign):
        mass, dims = _mass_amateur(design, warnings), _dims_amateur(design)
    elif isinstance(design, MultistageDesign):
        mass, dims = _mass_multistage(design), _dims_multistage(design)
    else:
        raise TypeError(f"unsupported design type {type(design).__name__}")
    return {
        "tier": design.tier,
        "cost_jpy": float(estimate_cost_jpy(design)),
        "cost_breakdown": [asdict(item) for item in cost_breakdown(design)],
        "bom": bom_rows(design),
        "drawing": None,
        "mass": mass,
        "dimensions": dims,
        "warnings": warnings,
    }


def _bill_cost_items(bill: BuildBill) -> list[CostItem]:
    return [
        CostItem(
            row.name,
            row.price_jpy,
            f"{row.part_id} × {row.qty}" + ("（仮置き）" if row.provisional else ""),
            row.provisional,
        )
        for row in bill.parts
    ]


def _bill_bom_rows(bill: BuildBill, catalog: PartsCatalog) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in bill.parts:
        source = "provisional"
        if not row.provisional:
            try:
                source = catalog.get(row.part_id).source or "provisional"
            except KeyError:
                source = "catalog"
        rows.append(
            {
                "item_id": row.part_id,
                "name": row.name,
                "qty": row.qty,
                "mass_kg": row.mass_kg,
                "price_jpy": row.price_jpy,
                "source_or_provisional": source,
            }
        )
    return rows


def design_summary_from_build(
    build: AmateurBuild | BottleBuild,
    catalog: PartsCatalog | None = None,
    requirement: Requirement | None = None,
) -> dict[str, Any]:
    """`design_summary` of the build's resolved design, with the cost, the cost breakdown and
    the BOM taken from the parts bill (exact part rows) instead of cost.py's estimate, plus
    `build`, `bill` and the buildability `issues`."""
    cat = catalog if catalog is not None else load_parts()
    design, bill = resolve(build, cat)
    out = design_summary(design, requirement)
    out["design"] = design.model_dump(mode="json")
    out["build"] = build.model_dump(mode="json")
    out["bill"] = bill.model_dump(mode="json")
    out["cost_jpy"] = float(bill.cost_jpy)
    out["cost_breakdown"] = [asdict(item) for item in _bill_cost_items(bill)]
    out["bom"] = _bill_bom_rows(bill, cat)
    out["issues"] = [i.model_dump() for i in check_buildability(build, cat)]
    return out
