"""Finite, validated redesign proposals conditioned on failed flight/part criteria."""

import copy

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.schema import STOCKS


def identity(spec):
    return digest(spec.model_dump(mode="json", exclude={"name"}))


def proposals(spec, limits, unmet, visited):
    result = {}

    def add(key, section, field, value, why, score):
        data = copy.deepcopy(spec.model_dump(mode="json"))
        if section:
            data[section][field] = value
        else:
            data[field] = value
        if section == "geometry" or field == "material":
            # A changed printed part cannot inherit a weighing of the previous geometry/material.
            data["measured_printed_mass_g"] = None
            data["geometry"]["dimensions_measured"] = False
        try:
            proposed = DesignSpec.model_validate(data)
        except ValueError:
            return
        if identity(proposed) in visited or identity(proposed) == identity(spec):
            return
        result[key] = dict(
            spec=proposed.model_dump(mode="json"),
            reason=why,
            score=score,
            change={"section": section, "field": field, "value": value},
        )

    if "altitude" in unmet:
        for p in limits.pressure_kpa:
            if (
                (p * 1000 < spec.design.initial_gauge_pressure_pa)
                if "altitude_high" in unmet
                else (p * 1000 > spec.design.initial_gauge_pressure_pa)
            ):
                add(
                    f"redesign/pressure-{p:g}",
                    "design",
                    "initial_gauge_pressure_pa",
                    p * 1000,
                    "Altitude shortfall with unused operating pressure scenarios",
                    90 - p / 100,
                )
        for f in limits.fills:
            add(
                f"redesign/fill-{f:g}",
                "design",
                "water_fill_frac",
                f,
                "Compare water/gas balance at the same geometry",
                70,
            )
        for d in limits.nozzle_mm:
            add(
                f"redesign/nozzle-{d:g}",
                "design",
                "nozzle_diameter_m",
                d / 1000,
                "Change thrust duration and drag exposure",
                65,
            )
    if limits.allow_geometry_change:
        g = spec.geometry
        if set(unmet) & {"attitude", "static_margin", "frozen_pitch", "aero_domain"}:
            for span in (g.fin_span_mm * 1.15, g.fin_span_mm * 1.3):
                add(
                    f"redesign/span-{span:.3f}",
                    "geometry",
                    "fin_span_mm",
                    span,
                    "Upper-layer attitude failure asks the lower layer for more fin authority",
                    95,
                )
            add(
                "redesign/forward-payload",
                "assumptions",
                "payload_station_fraction",
                0.08,
                "Explore a forward payload station; retention geometry remains unqualified",
                80,
            )
        if "fin_deformation" in unmet or "modes" in unmet:
            for thick in (g.fin_thickness_mm * 1.25, g.fin_thickness_mm * 1.5):
                add(
                    f"redesign/thickness-{thick:.3f}",
                    "geometry",
                    "fin_thickness_mm",
                    thick,
                    "Reduce fin deformation, then recalculate CAD mass and flight",
                    95,
                )
            add(
                "redesign/reinforced-mount",
                "assumptions",
                "mount",
                "reinforced",
                "Increase the assumed root stiffness with its added mass",
                90,
            )
        if "altitude" in unmet:
            add(
                "redesign/thinner-fin",
                "geometry",
                "fin_thickness_mm",
                g.fin_thickness_mm * 0.85,
                "Compare reduced printed mass and stiffness alongside operating scenarios",
                70,
            )
            # Competing operating and part choices remain available together.
            for field, factors in {
                "fin_root_mm": (0.85, 1.15),
                "fin_tip_mm": (0.7, 1.2),
                "fin_span_mm": (0.8, 1.15),
                "fin_sweep_mm": (0.7, 1.2),
                "nose_length_mm": (0.8, 1.2),
                "nose_wall_mm": (0.75,),
            }.items():
                for factor in factors:
                    add(
                        f"redesign/{field}-{factor:g}",
                        "geometry",
                        field,
                        getattr(g, field) * factor,
                        "Explore mass, drag and restoring moment; provisional until recalculated",
                        70,
                    )
        if set(unmet) & {"altitude", "static_margin", "attitude"}:
            for station in (0.25, 0.4):
                add(
                    f"redesign/equipment-station-{station:g}",
                    "assumptions",
                    "other_mass_station_fraction",
                    station,
                    "Rearrange equipment mass; packaging and retention require verification",
                    70,
                )
            for inset in (0.0, 15.0):
                add(
                    f"redesign/fin-station-{inset:g}",
                    "geometry",
                    "fin_tail_inset_mm",
                    inset,
                    "Compare fin station while retaining the same material and mass model",
                    70,
                )
    if limits.allow_material_change and set(unmet) & {"fin_deformation", "modes", "altitude"}:
        for material in STOCKS:
            add(
                "redesign/material-" + material.split()[-1],
                None,
                "material",
                material,
                "Compare the registered density/stiffness assumption and recalculate mass",
                70,
            )
    return dict(sorted(result.items(), key=lambda kv: (-kv[1]["score"], kv[0])))
