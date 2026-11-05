"""Local Lyapunov and bending/torsion dynamic screening with explicit validity limits."""

import numpy as np
from scipy.linalg import eigvalsh, solve_continuous_lyapunov


def lyapunov_matrix(a):
    a = np.asarray(a, dtype=float)
    eig = np.linalg.eigvals(a)
    if max(eig.real) >= 0:
        return {"hurwitz": False, "spectral_abscissa_per_s": float(max(eig.real))}
    p = solve_continuous_lyapunov(a.T, -np.eye(len(a)))
    residual = a.T @ p + p @ a + np.eye(len(a))
    return {
        "hurwitz": True,
        "spectral_abscissa_per_s": float(max(eig.real)),
        "P": p.tolist(),
        "min_P_eigenvalue": float(min(eigvalsh(p))),
        "residual": float(np.linalg.norm(residual)),
        "quadratic_decay_bound_per_s": float(1 / max(eigvalsh(p))),
    }


def pitch(assembly, flight, design, cfg):
    trace = flight["trace"]
    length = assembly["dimensions_mm"]["overall"] / 1000
    area = np.pi * (assembly["dimensions_mm"]["body_diameter"] / 2000) ** 2
    inertia = (design.dry_mass_kg + design.payload_mass_kg) * length**2 / 12
    cp = assembly["cp_mm"] / 1000
    cn = assembly["fin_set_CNalpha_per_rad"] + 2
    matrices = []
    times = []
    for t, q, cg, v in zip(
        trace["time_s"], trace["q_pa"], trace["cg_m"], trace["velocity_mps"], strict=True
    ):
        if flight["rail_exit_s"] < t < flight["apogee_s"] and q > 10:
            k = q * area * cn * (cp - cg)
            c = q * area * length**2 / (2 * max(np.linalg.norm(v), 0.1)) * cfg.pitch_damping
            matrices.append(np.array([[0.0, 1.0], [-k / inertia, -c / inertia]]))
            times.append(t)
    checks = [lyapunov_matrix(a) for a in matrices]
    stable = bool(checks) and all(c["hurwitz"] for c in checks)
    common = None
    if stable:
        # A certificate is tested against every sampled matrix, not inferred from frozen poles.
        ps = [np.array(c["P"]) for c in checks]
        candidates = [ps[0], ps[len(ps) // 2], ps[-1], sum(ps) / len(ps)]
        margins = [max(max(eigvalsh(a.T @ p + p @ a)) for a in matrices) for p in candidates]
        best = int(np.argmin(margins))
        common = {
            "max_lyapunov_eigenvalue": float(margins[best]),
            "P": candidates[best].tolist(),
            "sampled_common_certificate": bool(margins[best] < 0),
        }
    return {
        "completed": True,
        "all_frozen_points_hurwitz": stable,
        "common_quadratic": common,
        "time_s": times,
        "local": checks,
        "qualified": False,
        "scope": "local pitch, fixed velocity direction, surrogate dry inertia",
        "limitations": [
            "frozen stability does not prove time-varying or nonlinear stability",
            "sampled common P does not cover unsampled states or flexible/slosh modes",
        ],
    }


def flutter(assembly, cfg, *, temperature_c=20.0, max_speed=40.0):
    """2 elastic coordinates plus one aerodynamic lag; exploratory parameter sensitivity.

    The lag and damping are assumptions. Eigenvalue crossing is a request for a
    validated aeroelastic model, not a measured flutter speed.
    """
    g = assembly["dimensions_mm"]
    span = g["fin_span"] / 1000
    chord = (g["fin_root"] + g["fin_tip"]) / 2000
    thick = cfg.fin_thickness_m
    material = cfg.fin_material or cfg.material
    ratio = np.interp(
        temperature_c, [material.reference_c, material.warm_c], [1, material.warm_ratio]
    )
    e = material.young_pa * ratio
    shear = e / (2 * (1 + material.poisson))
    mass = material.density * chord * span * thick * 0.236
    inertia = mass * chord**2 / 12
    coupling = mass * 0.1 * chord
    m = np.array([[mass, coupling], [coupling, inertia]])
    k = np.diag([3 * e * (chord * thick**3 / 12) / span**3, shear * (chord * thick**3 / 3) / span])
    frequency = np.sqrt(eigvalsh(k, m)) / (2 * np.pi)
    c = np.diag(2 * 0.02 * np.sqrt(np.diag(k) * np.diag(m)))
    area = np.pi * (g["body_diameter"] / 2000) ** 2
    cn = assembly["fin_set_CNalpha_per_rad"] / 2
    rows = []
    # Sweep adverse and favourable elastic-axis offsets, plus convection lag uncertainty.
    for offset in [-0.25, 0.0, 0.25]:
        for lag_scale in [0.5, 1.0, 2.0]:
            for speed in np.linspace(1, max_speed, 80):
                q = 0.5 * 1.204 * speed**2
                tau = lag_scale * chord / (2 * speed)
                a = np.zeros((5, 5))
                a[:2, 2:4] = np.eye(2)
                a[2:4, :2] = -np.linalg.solve(m, k)
                a[2:4, 2:4] = -np.linalg.solve(m, c)
                a[2:4, 4] = np.linalg.solve(m, q * area * cn * np.array([-1.0, offset * chord]))
                # Positive h velocity increases opposing lift; alpha drives aero lag.
                a[4, 1] = 1 / tau
                a[4, 2] = 1 / (speed * tau)
                a[4, 4] = -1 / tau
                eig = np.linalg.eigvals(a)
                mode = eig[np.argmax(eig.real)]
                rows.append(
                    [
                        offset,
                        lag_scale,
                        speed,
                        float(mode.real),
                        float(abs(mode.imag) / (2 * np.pi)),
                    ]
                )
    crossings = []
    for offset in [-0.25, 0.0, 0.25]:
        for lag_scale in [0.5, 1.0, 2.0]:
            unstable = [r for r in rows if r[0] == offset and r[1] == lag_scale and r[3] >= 0]
            crossings.append(
                {
                    "offset_chord": offset,
                    "lag_scale": lag_scale,
                    "first_sampled_instability_mps": unstable[0][2] if unstable else None,
                }
            )
    return {
        "completed": True,
        "qualified": False,
        "dry_modes_hz": frequency.tolist(),
        "crossings": crossings,
        "trace": rows,
        "temperature_c": temperature_c,
        "scope": "assumed two-mode typical section and aerodynamic lag; diagnostic only",
    }
