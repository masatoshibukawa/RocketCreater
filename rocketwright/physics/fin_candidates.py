"""Tapered beam screening and explicit mass reconciliation for assumed fin profiles."""

import copy

import numpy as np
from scipy.linalg import eigvalsh, solve

# Parameter scenarios, not properties assigned to a commercial material or print process.
PROFILES = {
    "compliant_assumption": dict(young_pa=1e9, density=1100, warm_ratio=0.35),
    "reference_assumption": dict(young_pa=2e9, density=1200, warm_ratio=0.5),
    "stiff_assumption": dict(young_pa=20e9, density=1600, warm_ratio=0.85),
}


def beam(span, root, tip, thickness, young, density, root_k, force, *, tab=0.01, n=40):
    """Euler-Bernoulli beam with consistent mass and a finite root foundation.

    Rotation is positive slope. The support is uniformly distributed over -tab..0;
    its 2x2 stiffness retains translation/rotation coupling. Bending is normal to
    the plate. Torsion, laminate orthotropy, thermal prestress and buckling are absent.
    """
    if min(span, root, tip, thickness, young, density, root_k, tab) <= 0 or n < 2:
        raise ValueError("Positive physical parameters and at least two elements required")
    size, length = 2 * (n + 1), span / n
    k, m, f = np.zeros((size, size)), np.zeros((size, size)), np.zeros(size)
    for i in range(n):
        chord = root + (tip - root) * (i + 0.5) / n
        ei = young * chord * thickness**3 / 12
        ke = (
            ei
            / length**3
            * np.array(
                [
                    [12, 6 * length, -12, 6 * length],
                    [6 * length, 4 * length * length, -6 * length, 2 * length * length],
                    [-12, -6 * length, 12, -6 * length],
                    [6 * length, 2 * length * length, -6 * length, 4 * length * length],
                ]
            )
        )
        me = (
            density
            * chord
            * thickness
            * length
            / 420
            * np.array(
                [
                    [156, 22 * length, 54, -13 * length],
                    [22 * length, 4 * length * length, 13 * length, -3 * length * length],
                    [54, 13 * length, 156, -22 * length],
                    [-13 * length, -3 * length * length, -22 * length, 4 * length * length],
                ]
            )
        )
        load = force * chord / (span * (root + tip) / 2)
        fe = load * np.array([length / 2, length * length / 12, length / 2, -length * length / 12])
        ids = np.arange(2 * i, 2 * i + 4)
        k[np.ix_(ids, ids)] += ke
        m[np.ix_(ids, ids)] += me
        f[ids] += fe
    k[:2, :2] += root_k * np.array([[1, -tab / 2], [-tab / 2, tab * tab / 3]])
    # Root tab lumped mass/inertia, consistently at its centroid.
    tab_mass = density * root * tab * thickness
    m[:2, :2] += tab_mass * np.array([[1, -tab / 2], [-tab / 2, tab * tab / 3]])
    u = solve(k, f, assume_a="pos")
    eigenvalue = eigvalsh(k, m, subset_by_index=[0, 1])
    return dict(
        tip_m=float(u[-2]),
        max_deflection_m=float(np.max(np.abs(u[::2]))),
        first_modes_hz=(np.sqrt(eigenvalue) / (2 * np.pi)).tolist(),
        mass_one_fin_kg=float(density * thickness * (span * (root + tip) / 2 + root * tab)),
        root_force_n=float(root_k * (u[0] - tab / 2 * u[1])),
        relative_equilibrium_residual=float(np.linalg.norm(k @ u - f) / max(abs(force), 1e-9)),
    )


def reconcile_mass(design, assembly, fin_mass_kg):
    """Replace only the four-fin group; preserve payload and liquid reservoir centroid."""
    article = copy.deepcopy(assembly)
    fin = next(b for b in article["bill"] if b["id"] == "carton_fin")
    delta = fin_mass_kg - fin["mass_g"] / 1000
    station = fin["station_mm"] / 1000
    fin["mass_g"] = fin_mass_kg * 1000
    fin["basis"] = "assumed solid fin geometry/density; not weighed hardware"
    dry = design.dry_mass_kg
    payload = design.payload_mass_kg
    water = 1000 * design.bottle_volume_m3 * design.water_fill_frac
    for key, total in [
        ("dry_cg_mm", dry),
        ("loaded_cg_mm", dry + payload),
        ("wet_cg_mm", dry + payload + water),
    ]:
        if key in article:
            article[key] = (article[key] * total + 1000 * station * delta) / (total + delta)
    article["dry_mass_g"] = 1000 * (dry + delta)
    candidate = design.model_copy(update={"dry_mass_kg": dry + delta})
    if not np.isclose(sum(b["mass_g"] for b in article["bill"]), article["dry_mass_g"], atol=1e-5):
        raise ValueError("BOM mass does not close")
    return candidate, article
