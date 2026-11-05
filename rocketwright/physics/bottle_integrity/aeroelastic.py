"""Partitioned low-angle load/large-deformation fin iteration, with explicit stop gates."""

import numpy as np

from .fem import fin_deck, run_deck


def mean_twist(nodes, displacements):
    sections = {}
    for i, (x, y, z) in nodes.items():
        if y <= 0:
            continue
        u = displacements[i]
        sections.setdefault(round(y, 9), []).append([x + u[0], z + u[2]])
    angles = []
    for points in sections.values():
        p = np.asarray(points)
        if np.ptp(p[:, 0]) > 1e-5:
            slope = np.polyfit(p[:, 0], p[:, 1], 1)[0]
            angles.append(-np.rad2deg(np.arctan(slope)))
    return float(np.mean(angles)), float(max(abs(np.asarray(angles))))


def coupled_fin(executable, output, assembly, cfg, q_pa, *, temperature_c=20.0, resolution=1):
    incidence = 3.0
    history = []
    result = None
    meta = None
    nodes = None
    elements = None
    converged = False
    domain = True
    for iteration in range(18):
        lines, nodes, elements, meta = fin_deck(
            assembly,
            cfg,
            q_pa,
            resolution=resolution,
            temperature_c=temperature_c,
            incidence_deg=incidence,
        )
        result = run_deck(executable, output / f"iteration-{iteration:02d}", "fin", lines)
        twist, peak = mean_twist(nodes, result["node_displacements_m"])
        desired = 3.0 + twist
        residual = desired - incidence
        history.append(
            {
                "iteration": iteration,
                "incidence_deg": incidence,
                "twist_deg": twist,
                "residual_deg": residual,
                "tip_scale_m": result["max_displacement_m"],
            }
        )
        if abs(desired) > 15 or peak + 3 > 15:
            domain = False
            break
        if abs(residual) < 0.01:
            converged = True
            break
        incidence += 0.6 * residual
    return {
        "completed": converged,
        "aero_domain_pass": domain,
        "history": history,
        "fem": result,
        "geometry": {"nodes": nodes, "elements": [e[0] for e in elements]},
        "metadata": meta,
        "qualified": False,
        "scope": "mean-twist pressure feedback; nonlinear 3D solid and follower load",
        "limitations": [
            "low-angle quasi-steady load, no resolved spanwise CFD coupling",
            "mean-twist fixed point is not a flutter or strength certificate",
        ],
    }
