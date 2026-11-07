"""Same screening equations with a longer discharge limit for slow broad-domain cases."""

import copy
import math

import numpy as np

from rocketwright.analysis.record import compile_record
from rocketwright.analysis.screening import axial_flight, estimated_volumes
from rocketwright.analysis.worker import serial
from rocketwright.physics import fin_candidates
from rocketwright.physics.bottle_integrity import loads, thermal
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.physics.flight_loads import MassDistribution
from rocketwright.schema import BottleDesign


def measure(spec, anchor, cad):
    volumes = estimated_volumes(spec, anchor, cad)
    record = compile_record(spec, volumes)
    cfg = AnalysisConfig.model_validate(record["config"])
    cfg.loads.max_time_s = 60
    design = BottleDesign.model_validate(record["design"])
    temperature = cfg.loads.ambient_k - 273.15
    warm = thermal.wait(design, cfg, ambient_c=temperature, initial_c=temperature, sealed=True)
    cfg.loads.initial_k = warm["final_c"]["gas"] + 273.15
    cfg.loads.initial_wall_k = warm["final_c"]["skin"] + 273.15
    design = design.model_copy(
        update={
            "initial_gauge_pressure_pa": warm["trace"]["absolute_pressure_pa"][-1]
            - cfg.loads.ambient_pa
        }
    )
    propulsion = loads.propulsion(design, cfg.loads)
    if not propulsion["completed"]:
        raise RuntimeError("Expanded discharge incomplete at 60-second phase limits")
    a, g = record["assembly"], spec.geometry
    area = math.pi * (g.body_diameter_mm / 2000) ** 2
    cd = design.axial_drag_coefficient or 0.55
    nominal = axial_flight(
        design,
        propulsion,
        area=area,
        cd=cd,
        density=cfg.flight.air_density_kg_m3,
        rail_m=spec.env.rail_length_m,
    )
    departure, free_margin = nominal.get("rail_exit_s"), None
    if departure is not None:
        mass_model = MassDistribution(design, a, propulsion)
        times = np.asarray(propulsion["trace"]["time_s"])
        samples = np.r_[departure, times[times > departure], max(departure, times[-1])]
        aft_cg = max(mass_model.properties(float(t))[1] for t in samples)
        free_margin = (a["cp_mm"] - aft_cg * 1000) / g.body_diameter_mm
    heights = []
    for mass_factor, drag_factor in ((0.9, 0.75), (1.1, 1.25)):
        altered = copy.deepcopy(propulsion)
        delta = design.dry_mass_kg * (mass_factor - 1)
        altered["trace"]["mass_kg"] = [m + delta for m in propulsion["trace"]["mass_kg"]]
        heights.append(
            axial_flight(
                design,
                altered,
                area=area,
                cd=cd * drag_factor,
                density=cfg.flight.air_density_kg_m3,
            )["apogee_m"]
        )
    material = record["config"]["fin_material"]
    force = nominal["max_q_pa"] * area * a["fin_set_CNalpha_per_rad"] * math.radians(15) / 2
    beam = fin_candidates.beam(
        g.fin_span_mm / 1000,
        g.fin_root_mm / 1000,
        g.fin_tip_mm / 1000,
        g.fin_thickness_mm / 1000,
        material["young_pa"] * material["warm_ratio"],
        material["density"],
        record["config"]["fin_root_k_n_m"],
        force,
        tab=spec.assumptions.root_capture_mm / 1000,
    )
    return serial(
        dict(
            **nominal,
            dry_mass_g=a["dry_mass_g"],
            static_margin_cal=(a["cp_mm"] - a["wet_cg_mm"]) / g.body_diameter_mm,
            axial_free_margin_cal=free_margin,
            scenario_height_m=[min(heights), max(heights)],
            impulse_ns=propulsion["impulse_ns"],
            conservative_beam_ratio=beam["max_deflection_m"] / (g.fin_span_mm / 1000),
            mass_basis="CAD-scaled estimate; selected geometry must be regenerated",
            qualification=False,
            discharge_phase_limit_s=60,
        )
    )
