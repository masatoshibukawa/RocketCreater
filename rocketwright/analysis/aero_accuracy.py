"""Numerical diagnostics; differences are not experimental validation or error bounds."""

import numpy as np
from scipy.optimize import brentq


def relative_change(before, after, floor=0.05):
    a, b = np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    if a.shape != b.shape or not np.isfinite([a, b]).all():
        raise ValueError("Comparable finite aerodynamic coefficients required")
    return float(np.max(abs(a - b) / np.maximum(np.maximum(abs(a), abs(b)), floor)))


def holdout(speeds, angles):
    """An integer interior point absent from both lookup axes (stable directory names)."""

    def middle(axis):
        pairs = [(b - a, a, b) for a, b in zip(axis[:-1], axis[1:], strict=True) if b - a >= 2]
        if not pairs:
            raise ValueError("No independent integer holdout remains")
        _, a, b = max(pairs)
        return int((a + b) // 2)

    return middle(speeds), middle([a for a in angles if a <= 15])


def grid_order(cells, values):
    """Three-grid observed order only for monotone data admitting a positive order.

    Unequal refinement ratios use the h**p difference equation. A fitted order
    is a diagnostic: three points alone do not establish an asymptotic regime.
    See NASA NPARC spatial-convergence tutorial linked in the design guide.
    """
    h = 1 / np.asarray(cells, dtype=float)
    v = np.asarray(values, dtype=float)
    if (
        h.shape != (3,)
        or v.shape != (3,)
        or not np.isfinite([h, v]).all()
        or not np.all(np.diff(h) < 0)
    ):
        raise ValueError("Three finite increasingly fine grids required")
    d1, d2 = v[0] - v[1], v[1] - v[2]
    result = dict(
        values=v.tolist(),
        cells=list(cells),
        observed_order=None,
        fine_gci=None,
        asymptotic_range_verified=False,
    )
    if abs(d1) < 1e-10 or abs(d2) < 1e-10:
        return dict(result, classification="indistinguishable")
    if d1 * d2 <= 0:
        return dict(result, classification="oscillatory")
    ratio = d1 / d2

    def residual(p):
        return ((h[0] / h[1]) ** p - 1) / (1 - (h[2] / h[1]) ** p) - ratio

    try:
        p = brentq(residual, 0.05, 6)
    except ValueError:
        return dict(result, classification="no_resolved_positive_order")
    # Conditional estimator, explicitly not a certification of asymptotic behavior.
    estimate = 1.25 * abs(d2) / (max(abs(v[2]), 0.05) * ((h[1] / h[2]) ** p - 1))
    return dict(
        result, classification="monotone", observed_order=float(p), fine_gci=float(estimate)
    )


def fin_envelope(table, trajectory):
    """Retain concurrent loads at extremes of Fn, Mchord and Mspan during ascent.

    Uses all four meridional blades; circumferential orientation is not resolved.
    Later structural checks use the same three cases on each mesh.
    """
    rows = []
    trace = trajectory["trace"]
    for i, t in enumerate(trace["time_s"]):
        if t > trajectory["apogee_s"]:
            continue
        q = trace["q_pa"][i]
        if q <= 1e-8:
            continue
        vb = np.asarray(trajectory["load_samples"][i]["air_velocity_body_mps"])
        speed = np.linalg.norm(vb)
        angle = np.degrees(np.arctan2(np.linalg.norm(vb[:2]), vb[2]))
        for blade, load in enumerate(table.fin_resultants(speed, angle, q)):
            rows.append(
                dict(
                    time_s=t,
                    blade=blade,
                    speed_mps=float(speed),
                    angle_deg=float(angle),
                    q_pa=q,
                    local_resultant=load.tolist(),
                    speed_clamped=bool(speed < table.speeds[0] or speed > table.speeds[-1]),
                )
            )
    if not rows:
        raise ValueError("No ascent fin load samples")
    selected = sorted(
        {max(range(len(rows)), key=lambda i: abs(rows[i]["local_resultant"][j])) for j in (2, 3, 4)}
    )
    return [rows[i] for i in selected]
