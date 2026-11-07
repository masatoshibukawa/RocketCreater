"""Phase diagnostics; a guide-restrained trajectory is not a qualified launcher."""

import math

import numpy as np


def diagnose(assembly, flight):
    """Report sampled analytic CP/CG margins and ideal-guide reaction demands.

    The exit value is interpolated from the full trajectory. These diagnostics
    neither change the initial-static acceptance gate nor prove guide capacity.
    CFD restoring derivatives remain the separate stability analysis's task.
    """
    rows = flight.get("load_samples", [])
    exit_s, apex_s = flight.get("rail_exit_s"), flight.get("apogee_s")
    if not rows or exit_s is None or apex_s is None or not 0 < exit_s < apex_s:
        raise ValueError("Completed rail departure and ascent samples are required")
    t = np.array([r["time_s"] for r in rows])
    cg = np.array([r["cg_m"] for r in rows])
    diameter = assembly["dimensions_mm"]["body_diameter"] / 1000
    cp = assembly["cp_mm"] / 1000
    if (
        not np.isfinite(np.r_[t, cg, diameter, cp]).all()
        or diameter <= 0
        or np.any(np.diff(t) <= 0)
        or t[0] > exit_s
        or t[-1] < apex_s
    ):
        raise ValueError("Finite ordered samples bracketing departure and apogee required")
    free = (t >= exit_s) & (t <= apex_s)
    margin = (cp - np.r_[np.interp(exit_s, t, cg), cg[free], np.interp(apex_s, t, cg)]) / diameter
    guided = [r for r in rows if r["time_s"] <= exit_s]
    forces = np.array([r["rail_force_n"] for r in guided])
    moments = np.array([r["rail_moment_nm"] for r in guided])
    if not guided or not np.isfinite(np.r_[forces.ravel(), moments.ravel()]).all():
        raise ValueError("Finite guide reaction samples required")
    return dict(
        initial_with_gas_margin_cal=float((cp - cg[0]) / diameter),
        exit_margin_cal=float(margin[0]),
        free_ascent_min_margin_cal=float(margin.min()),
        free_ascent_samples=int(free.sum()),
        rail_exit_s=float(exit_s),
        rail_exit_speed_mps=float(flight["rail_exit_speed_mps"]),
        maximum_guide_force_n=float(np.linalg.norm(forces, axis=1).max()),
        maximum_guide_moment_nm=float(np.linalg.norm(moments, axis=1).max()),
        guide_capacity_verified=False,
        physical_qualification=False,
        acceptance_changed=False,
        scope="sampled analytic CP/CG; ideal continuous two-axis guide, no friction or clearance",
    )


def exploration_score(metrics, target, profile="initial"):
    """A guided profile ranks diagnostic candidates, never alters final acceptance."""
    if profile not in {"initial", "guided"}:
        raise ValueError("Unknown exploration profile")
    key = "static_margin_cal" if profile == "initial" else "axial_free_margin_cal"
    margin = metrics.get(key)
    if margin is None or not math.isfinite(margin):
        return (math.inf, math.inf)
    low = metrics["scenario_height_m"][0]
    violation = max(0, (target - low) / target) + max(0, 1 - margin)
    if profile == "guided":
        violation += max(0, metrics["conservative_beam_ratio"] / 0.05 - 1)
    return (violation, -low)
