"""Analytic outer-envelope bounds in the rotated computational frame."""

import math

import numpy as np


def bounds(dimensions, cg_mm, angle_deg, thickness_mm=0, cant_deg=0):
    """Exact extrema of the conical/cylindrical body and extruded planar fins.

    Returns x/y/z minima and maxima in body diameters. Shoes are included as
    rectangular envelopes, matching interpolated_wall.cuh. This is geometry
    clearance only, not evidence of boundary-independent aerodynamics.
    """
    g = dimensions
    d, length = g["body_diameter"], g["overall"]
    values = [
        d,
        length,
        g["nose_length"],
        g["fin_root"],
        g["fin_tip"],
        g["fin_span"],
        g["fin_sweep"],
        g["fin_tail_inset"],
        cg_mm,
        angle_deg,
        thickness_mm,
        cant_deg,
        g.get("fin_root_offset", 0),
        g.get("fin_shoe_width", 0),
    ]
    if (
        not np.isfinite(values).all()
        or d <= 0
        or not 0 < g["nose_length"] < length
        or thickness_mm < 0
        or abs(angle_deg) > 180
        or abs(cant_deg) > 15
        or g.get("fin_count", 4) != 4
    ):
        raise ValueError("Finite four-fin conical geometry and supported angles required")
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    rotation = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    center = np.array([cg_mm, 0, 0])
    stations = np.array([0, g["nose_length"], length])
    radii = np.array([0, d / 2, d / 2])
    axial = np.column_stack([stations, np.zeros(3), np.zeros(3)])
    axial = (axial - center) @ rotation.T + center
    reach = radii[:, None] * [abs(s), abs(c), 1]
    lower, upper = (axial - reach).min(0), (axial + reach).max(0)
    root = length - g["fin_tail_inset"] - g["fin_root"]
    offset, shoe = g.get("fin_root_offset", 0), g.get("fin_shoe_width", 0)
    x = root + np.array([0, g["fin_sweep"], g["fin_sweep"] + g["fin_tip"], g["fin_root"]])
    radial = d / 2 + offset + np.array([0, g["fin_span"], g["fin_span"], 0])
    tangent = math.tan(math.radians(cant_deg)) * (x - root - g["fin_root"] / 2)
    for blade in range(4):
        a = blade * math.pi / 2
        er, et = np.array([0, math.cos(a), math.sin(a)]), np.array([0, -math.sin(a), math.cos(a)])
        points = np.concatenate(
            [
                np.column_stack([x, np.zeros(4), np.zeros(4)])
                + radial[:, None] * er
                + (tangent + side * thickness_mm / 2)[:, None] * et
                for side in (-1, 1)
            ]
        )
        if offset > 0 and shoe > 0:
            vertices = [
                np.array([xc, 0, 0]) + r * er + t * et
                for xc in (root, root + g["fin_root"])
                for r in (d / 2, d / 2 + offset)
                for t in (-shoe / 2, shoe / 2)
            ]
            points = np.concatenate([points, vertices])
        points = (points - center) @ rotation.T + center
        lower, upper = np.minimum(lower, points.min(0)), np.maximum(upper, points.max(0))
    return lower / d, upper / d


def clearance(
    dimensions, cg_mm, angle_deg, *, upstream, width, thickness_mm=0, cant_deg=0, outlet_x=15
):
    lo, hi = bounds(dimensions, cg_mm, angle_deg, thickness_mm, cant_deg)
    return dict(
        bounds_min_D=lo.tolist(),
        bounds_max_D=hi.tolist(),
        inlet_D=float(upstream + lo[0]),
        outlet_D=float(outlet_x - hi[0]),
        transverse_D=float(width / 2 - max(abs(lo[1:]).max(), abs(hi[1:]).max())),
    )


def upstream_for(dimensions, cg_mm, angle_deg, thickness_mm=0, *, minimum_clearance=3.0):
    lo, _ = bounds(dimensions, cg_mm, angle_deg, thickness_mm)
    # Quarter-diameter rounding is deterministic across mesh refinement levels.
    return max(3.0, math.ceil((minimum_clearance - lo[0] - 1e-12) * 4) / 4)
