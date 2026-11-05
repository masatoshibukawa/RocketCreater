"""Nonlinear pad and unilateral compliant-stop transient response."""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import root

from .schema import ContactConfig


def contact_force(displacement, velocity, p: ContactConfig):
    penetration = max(abs(displacement) - p.gap_m, 0)
    sign = np.sign(displacement)
    elastic = p.stop_k * penetration**1.5
    force = max(0, elastic + p.stop_c * np.sqrt(penetration) * sign * velocity)
    return sign * force, elastic, (force - elastic) * sign * velocity


def response(time_s, proper_mps2, payload_kg, p: ContactConfig, *, initial_proper=9.80665):
    t = np.asarray(time_s)
    accel = np.asarray(proper_mps2)
    if t.ndim != 1 or len(t) < 2 or len(t) != len(accel) or np.any(np.diff(t) <= 0):
        raise ValueError("Acceleration needs strictly increasing paired times")
    masses = np.array([p.support_kg, payload_kg])

    def forces(x, v):
        relative = x[1] - x[0]
        speed = v[1] - v[0]
        fc, _, loss = contact_force(relative, speed, p)
        pad = p.pad_k * relative + p.pad_cubic * relative**3 + p.pad_c * speed + fc
        wall = p.wall_k * x[0] + p.wall_c * v[0]
        return np.array([pad - wall, -pad]), pad, wall, fc, loss

    eq = root(lambda x: forces(x, np.zeros(2))[0] - masses * initial_proper, [0.0, 0.0])
    if not eq.success:
        raise RuntimeError("Initial support equilibrium failed")

    def energy(x, v):
        r = x[1] - x[0]
        d = max(abs(r) - p.gap_m, 0)
        return (
            0.5 * np.sum(masses * v * v)
            + 0.5 * p.wall_k * x[0] ** 2
            + 0.5 * p.pad_k * r * r
            + p.pad_cubic * r**4 / 4
            + p.stop_k * d**2.5 / 2.5
        )

    def rhs(s, y):
        x, v = y[:2], y[2:4]
        f, _, _, _, loss = forces(x, v)
        base = np.interp(s, t, accel)
        dissipated = p.wall_c * v[0] ** 2 + p.pad_c * (v[1] - v[0]) ** 2 + loss
        base_work = -np.sum(masses * v) * base
        return np.r_[v, f / masses - base, dissipated, base_work]

    sol = solve_ivp(
        rhs,
        (t[0], t[-1]),
        np.r_[eq.x, 0.0, 0.0, 0.0, 0.0],
        t_eval=t,
        method="DOP853",
        rtol=2e-8,
        atol=1e-10,
        max_step=p.max_step_s,
    )
    if not sol.success:
        raise RuntimeError(sol.message)
    z = sol.y.T
    relative = z[:, 1] - z[:, 0]
    f = np.array([forces(y[:2], y[2:4])[1:4] for y in z])
    e = np.array([energy(y[:2], y[2:4]) for y in z])
    balance = e - e[0] + z[:, 4] - z[:, 5]
    denominator = max(float(np.max(e)), float(np.max(abs(z[:, 5]))), 1e-9)
    contact = abs(relative) > p.gap_m
    return {
        "contact_occurred": bool(np.any(contact)),
        "peak_penetration_mm": float(np.maximum(abs(relative) - p.gap_m, 0).max() * 1000),
        "peak_contact_force_n": float(abs(f[:, 2]).max()),
        "peak_payload_force_n": float(abs(f[:, 0]).max()),
        "peak_payload_proper_mps2": float(abs(f[:, 0]).max() / payload_kg),
        "peak_wall_reaction_n": float(abs(f[:, 1]).max()),
        "nominal_contact_pressure_pa": float(abs(f[:, 2]).max() / p.contact_area_m2),
        "work_balance_relative": float(np.max(abs(balance)) / denominator),
        "scope": "2 axial DOFs, cubic pad, unilateral compliant stop; contact area assumed",
        "fracture_status": "unknown_without_specimen_allowables",
        "trace": {
            "time_s": t.tolist(),
            "relative_mm": (relative * 1000).tolist(),
            "contact_n": f[:, 2].tolist(),
            "payload_n": f[:, 0].tolist(),
        },
    }
