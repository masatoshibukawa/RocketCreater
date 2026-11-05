"""Conservative axial reduction of momentum-exchange samples; body axes x aft."""

import numpy as np


def body_samples(ids, stats, grid, cells, upstream, diameter_m, cg_m, angle_deg, rotated):
    nx, ny, nz = grid
    ids = np.asarray(ids, dtype=np.int64)
    xyz = (
        np.column_stack(
            [
                (ids % nx + 0.5) / cells - upstream,
                (ids // nx % ny + 0.5 - ny / 2) / cells,
                (ids // (nx * ny) + 0.5 - nz / 2) / cells,
            ]
        )
        * diameter_m
    )
    force = np.asarray(stats[1:]).T.copy()
    if rotated:
        angle = np.deg2rad(angle_deg)
        c, s = np.cos(angle), np.sin(angle)
        transform = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        ref = np.array([cg_m, 0, 0])
        xyz = (xyz - ref) @ transform.T + ref
        force = force @ transform.T
    return xyz, force


def reduce_line(xyz_m, force_coeff, length_m, diameter_m, bins=64):
    """Retain both force and intrinsic couple at each axial bin centre.

    Off-axis lever arms and the within-bin axial offset remain in the couple,
    so summing the reduced loads reproduces force and moment at any origin.
    """
    if bins < 2 or length_m <= 0 or diameter_m <= 0:
        raise ValueError("Positive geometry and at least two bins required")
    xyz_m, force_coeff = np.asarray(xyz_m), np.asarray(force_coeff)
    if xyz_m.shape != force_coeff.shape or xyz_m.shape[1:] != (3,):
        raise ValueError("Expected matching N by 3 coordinates and force coefficients")
    if not np.isfinite(xyz_m).all() or not np.isfinite(force_coeff).all():
        raise ValueError("Nonfinite surface loads")
    station = (np.arange(bins) + 0.5) * length_m / bins
    index = np.clip((xyz_m[:, 0] / length_m * bins).astype(int), 0, bins - 1)
    force = np.zeros((bins, 3))
    couple = np.zeros_like(force)
    offset = xyz_m.copy()
    offset[:, 0] -= station[index]
    np.add.at(force, index, force_coeff)
    np.add.at(couple, index, np.cross(offset, force_coeff) / diameter_m)
    return {
        "station_m": station.tolist(),
        "force_coeff": force.tolist(),
        "couple_coeff_at_station": couple.tolist(),
        "force_coeff_total": force.sum(0).tolist(),
        "moment_coeff_at_nose": (np.cross(xyz_m, force_coeff).sum(0) / diameter_m).tolist(),
        "ref_diameter_m": diameter_m,
        "ref_area_m2": float(np.pi * diameter_m**2 / 4),
        "axes": "x nose to tail, right-handed xyz; moments normalized by q*A*D",
    }
