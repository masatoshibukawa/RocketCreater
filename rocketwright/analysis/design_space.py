"""Registered joint design variables, preserving the mission and pressure ceiling."""

import copy

import numpy as np
from scipy.stats import qmc

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.schema import STOCKS

# Host bounds, not material allowables or hardware pressure qualification.
AXES = {
    "water_fill_frac": (0.08, 0.35),
    "nozzle_mm": (7.0, 22.0),
    "fin_root_mm": (50.0, 160.0),
    "fin_tip_ratio": (0.20, 0.60),
    "fin_sweep_fraction": (0.0, 1.0),
    "fin_span_mm": (45.0, 145.0),
    "fin_thickness_mm": (1.2, 3.6),
    "nose_length_mm": (60.0, 280.0),
    "nose_wall_mm": (1.0, 1.6),
    "equipment_station_fraction": (0.15, 0.40),
    "payload_station_fraction": (0.06, 0.20),
    "material_index": (0.0, float(len(STOCKS))),
}


def decode(anchor, unit):
    """A bounded joint proposal; root/tip/sweep remain geometrically compatible."""
    u = np.asarray(unit, dtype=float)
    if u.shape != (len(AXES),) or not np.isfinite(u).all() or np.any((u < 0) | (u > 1)):
        raise ValueError("A finite unit-cube coordinate is required")
    values = {k: lo + x * (hi - lo) for x, (k, (lo, hi)) in zip(u, AXES.items(), strict=True)}
    d = copy.deepcopy(anchor.model_dump(mode="json"))
    g = d["geometry"]
    for key in ("fin_root_mm", "fin_span_mm", "fin_thickness_mm", "nose_length_mm", "nose_wall_mm"):
        g[key] = round(values[key], 3)
    g["fin_tip_mm"] = round(g["fin_root_mm"] * values["fin_tip_ratio"], 3)
    g["fin_sweep_mm"] = round(
        (g["fin_root_mm"] - g["fin_tip_mm"]) * values["fin_sweep_fraction"], 3
    )
    g["fin_tail_inset_mm"] = 0.0
    g["dimensions_measured"] = False
    d["design"].update(
        water_fill_frac=round(values["water_fill_frac"], 4),
        nozzle_diameter_m=round(values["nozzle_mm"], 3) / 1000,
        geometry=g,
    )
    d["assumptions"].update(
        other_mass_station_fraction=round(values["equipment_station_fraction"], 4),
        payload_station_fraction=round(values["payload_station_fraction"], 4),
    )
    d["material"] = list(STOCKS)[min(int(values["material_index"]), len(STOCKS) - 1)]
    d["measured_printed_mass_g"] = None
    candidate = DesignSpec.model_validate(d)
    assert_contract(candidate, anchor)
    return candidate


def assert_contract(candidate, anchor):
    if (
        candidate.requirement != anchor.requirement
        or candidate.design.payload_mass_kg != anchor.design.payload_mass_kg
        or candidate.design.initial_gauge_pressure_pa != anchor.design.initial_gauge_pressure_pa
        or candidate.design.initial_gauge_pressure_pa > 400000
        or candidate.other_dry_mass_g != anchor.other_dry_mass_g
        or candidate.env != anchor.env
    ):
        raise ValueError("Joint proposals cannot change the mission, environment or pressure cap")


def samples(count, seed, *, center=None, radius=1.0):
    """Latin hypercube coverage; local boxes are centered on measured promising points."""
    if count < 1 or not 0 < radius <= 1:
        raise ValueError("Positive sample count and unit-box radius required")
    points = qmc.LatinHypercube(d=len(AXES), seed=seed).random(count)
    if center is not None:
        center = np.asarray(center)
        lower, upper = np.maximum(0, center - radius), np.minimum(1, center + radius)
        points = lower + points * (upper - lower)
    return points
