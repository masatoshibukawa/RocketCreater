"""Low-cost counterfactuals. Their rankings never constitute design acceptance."""

import copy
import math
import time

import numpy as np
from scipy.integrate import solve_ivp

from rocketwright.analysis import policy
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.schema import SearchLimits
from rocketwright.physics.bottle_integrity import loads, thermal
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.schema import BottleDesign


def axial_flight(design, propulsion, *, area, cd, density=1.225, max_step=0.02):
    """Vertical rigid trajectory using the production discharge model's time history.

    Omits attitude, wind, launch-tube impulse and rail friction. Not a 6DOF replacement.
    """
    trace = propulsion["trace"]
    ts = np.asarray(trace["time_s"])
    mass = np.asarray(trace["mass_kg"])
    thrust = np.asarray(trace["thrust_n"])
    active = np.flatnonzero(thrust > mass * 9.80665)
    if not len(active):
        return dict(apogee_m=0.0, max_q_pa=0.0, lifted=False)
    start = float(ts[active[0]])

    def rhs(t, y):
        m = float(np.interp(t, ts, mass))
        force = float(np.interp(t, ts, thrust, right=0))
        return [y[1], (force - 0.5 * density * cd * area * y[1] * abs(y[1])) / m - 9.80665]

    def apex(t, y):
        return y[1] if t > start + 1e-7 else 1e-9

    apex.terminal, apex.direction = True, -1
    sol = solve_ivp(
        rhs, (start, 60), [0, 1e-9], events=apex, rtol=2e-7, atol=1e-9, max_step=max_step
    )
    if not sol.success or not len(sol.t_events[0]):
        raise RuntimeError("Axial screening did not reach apogee")
    return dict(
        apogee_m=float(sol.y[0, -1]),
        max_q_pa=float(0.5 * density * np.max(sol.y[1] ** 2)),
        lifted=True,
    )


def estimated_volumes(spec, anchor, cad):
    """Scale measured CAD volumes by analytic plate/shell ratios, retaining mounting volume.

    This is deliberately an estimate. Actual CAD is regenerated after a geometry choice.
    """

    def plate(g):
        return (
            (g.fin_root_mm + g.fin_tip_mm) * g.fin_span_mm / 2 + 10.5 * g.fin_root_mm
        ) * g.fin_thickness_mm

    def shell(g):
        radius = g.body_diameter_mm / 2
        return math.pi * radius * (radius**2 + g.nose_length_mm**2) ** 0.5 * g.nose_wall_mm

    return {
        "fin": {
            "volume_mm3": cad["fin"]["volume_mm3"] * plate(spec.geometry) / plate(anchor.geometry)
        },
        "nose": {
            "volume_mm3": cad["nose"]["volume_mm3"] * shell(spec.geometry) / shell(anchor.geometry)
        },
    }


def evaluate(spec, cad):
    record = compile_record(spec, cad)
    cfg = AnalysisConfig.model_validate(record["config"])
    d = BottleDesign.model_validate(record["design"])
    temperature = cfg.loads.ambient_k - 273.15
    warm = thermal.wait(d, cfg, ambient_c=temperature, initial_c=temperature, sealed=True)
    cfg.loads.initial_k = warm["final_c"]["gas"] + 273.15
    cfg.loads.initial_wall_k = warm["final_c"]["skin"] + 273.15
    d = d.model_copy(
        update={
            "initial_gauge_pressure_pa": warm["trace"]["absolute_pressure_pa"][-1]
            - cfg.loads.ambient_pa
        }
    )
    p = loads.propulsion(d, cfg.loads)
    if not p["completed"]:
        raise RuntimeError("Screen discharge incomplete")
    a, g = record["assembly"], spec.geometry
    area = math.pi * (g.body_diameter_mm / 2000) ** 2
    cd = d.axial_drag_coefficient or 0.55
    nominal = axial_flight(d, p, area=area, cd=cd, density=cfg.flight.air_density_kg_m3)
    variants = []
    for mass_factor, drag_factor in ((0.9, 0.75), (1.1, 1.25)):
        altered = copy.deepcopy(p)
        delta = d.dry_mass_kg * (mass_factor - 1)
        altered["trace"]["mass_kg"] = [m + delta for m in p["trace"]["mass_kg"]]
        variants.append(
            axial_flight(
                d, altered, area=area, cd=cd * drag_factor, density=cfg.flight.air_density_kg_m3
            )["apogee_m"]
        )
    static = (a["cp_mm"] - a["wet_cg_mm"]) / g.body_diameter_mm
    # Uniform cantilever strip estimate, evaluated at the declared incidence cap separately.
    return dict(
        **nominal,
        dry_mass_g=a["dry_mass_g"],
        static_margin_cal=static,
        scenario_height_m=[min(variants), max(variants)],
        impulse_ns=p["impulse_ns"],
        mass_basis="CAD-scaled estimate; selected geometry must be regenerated",
        qualification=False,
    )


def violation(row, target, static_target):
    return max(0, (target - row["apogee_m"]) / target) + max(
        0, (static_target - row["static_margin_cal"]) / static_target
    )


def survey(spec, cad, precision, limits, *, deadline):
    from rocketwright.agent.design_projects import DesignSpec

    limits = SearchLimits.model_validate(limits)
    baseline = evaluate(spec, cad)
    # Evaluate all major families, including cross-layer effects before choosing a new revision.
    proposed = policy.proposals(spec, limits, ["altitude", "static_margin", "fin_deformation"], [])
    rows, errors = {}, {}
    ordered = sorted(proposed, key=lambda k: (proposed[k]["change"]["field"], k))
    # Round-robin families prevents a long pressure list from consuming the survey.
    groups = {}
    for key in ordered:
        groups.setdefault(proposed[key]["change"]["field"], []).append(key)
    order = [
        group[i]
        for i in range(max(map(len, groups.values()), default=0))
        for group in groups.values()
        if i < len(group)
    ]
    for key in order[: limits.survey_candidates]:
        if time.monotonic() + 2 >= deadline:
            errors[key] = "survey_time_budget"
            break
        t = time.monotonic()
        try:
            candidate = DesignSpec.model_validate(proposed[key]["spec"])
            result = evaluate(candidate, estimated_volumes(candidate, spec, cad))
            gain = violation(
                baseline, spec.requirement.target_altitude_m, precision.minimum_static_margin_cal
            ) - violation(
                result, spec.requirement.target_altitude_m, precision.minimum_static_margin_cal
            )
            rows[key] = dict(
                spec_hash=policy.identity(candidate),
                predicted=result,
                delta_height_m=result["apogee_m"] - baseline["apogee_m"],
                delta_mass_g=result["dry_mass_g"] - baseline["dry_mass_g"],
                delta_static_margin_cal=result["static_margin_cal"] - baseline["static_margin_cal"],
                violation_reduction=gain,
                measured_cost_s=time.monotonic() - t,
            )
        except (ValueError, RuntimeError) as exc:
            errors[key] = str(exc)
    return dict(
        baseline=baseline,
        candidates=rows,
        errors=errors,
        scope="Axial counterfactuals; scenario ranges are assumptions, not confidence intervals",
        metrics={"survey_completed": True},
        physical_qualification=False,
    )
