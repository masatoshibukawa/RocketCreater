"""Transfer a free-fin normal force and its two moments to a structural mesh."""

import numpy as np
from scipy.optimize import root

from rocketwright.physics.bottle_integrity import fem
from rocketwright.physics.concrete_fin import polygon_moments


def resultant_deck(assembly, cfg, resultant, *, resolution, temperature_c):
    """Conserve Fn, Mchord and Mspan with a signed minimum-norm pressure.

    This reconstructs an equivalent distribution, not the original CFD traction.
    Signed pressure also represents a pure couple without dividing by zero force.
    """
    lines, nodes, elements, metadata = fem.fin_deck(
        assembly, cfg, 0, resolution=resolution, temperature_c=temperature_c
    )
    faces = []
    top = max(p[2] for p in nodes.values())
    for eid, (ids, _) in enumerate(elements, 1):
        corners = np.array([nodes[i] for i in ids[4:8]])
        if np.min(corners[:, 1]) < -1e-10 or not np.allclose(corners[:, 2], top):
            continue
        area, center, _ = polygon_moments(corners[:, :2])
        faces.append((eid, area, *center))
    faces = np.asarray(faces)
    r = np.asarray(resultant, dtype=float)
    if r.shape != (6,) or not np.isfinite(r).all():
        raise ValueError("Finite six-component local fin resultant required")
    scale = assembly["dimensions_mm"]["fin_span"] / 1000
    matrix = np.array([np.ones(len(faces)), faces[:, 3] / scale, -faces[:, 2] / scale])
    target = r[[2, 3, 4]] / [1, scale, scale]
    gram = (matrix * faces[:, 1]) @ matrix.T
    pressure = matrix.T @ np.linalg.solve(gram, target)
    mapped = matrix @ (faces[:, 1] * pressure)
    if not np.allclose(mapped, target, rtol=1e-9, atol=1e-10):
        raise ValueError("Fin load transfer did not conserve resultants")
    start = lines.index("*DLOAD") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("*"))
    lines[start:end] = [
        f"{int(face[0])},P2,{-p:.12e}" for face, p in zip(faces, pressure, strict=True)
    ]
    metadata.update(
        target_normal_resultant=r[[2, 3, 4]].tolist(),
        mapped_normal_resultant=(mapped * [1, scale, scale]).tolist(),
        omitted_tangential_resultant=r[[0, 1, 5]].tolist(),
        pressure_range_pa=[float(pressure.min()), float(pressure.max())],
        normal_load_scope=(
            "CFD force and two root moments; signed reconstructed pressure; tangential load omitted"
        ),
    )
    return lines, nodes, elements, metadata


def deck(assembly, cfg, force_n, centroid_m, *, resolution, temperature_c):
    lines, nodes, elements, metadata = fem.fin_deck(
        assembly, cfg, 0, resolution=resolution, temperature_c=temperature_c
    )
    faces = []
    top = max(p[2] for p in nodes.values())
    for eid, (ids, _) in enumerate(elements, 1):
        corners = np.array([nodes[i] for i in ids[4:8]])
        if np.min(corners[:, 1]) < -1e-10 or not np.allclose(corners[:, 2], top):
            continue
        area, mean, _ = polygon_moments(corners[:, :2])
        faces.append((eid, area, *mean))
    faces = np.array(faces)
    scale = assembly["dimensions_mm"]["fin_span"] / 1000
    positions = faces[:, 2:4] / scale
    target = np.asarray(centroid_m) / scale

    def weights(beta):
        exponent = positions @ beta
        values = faces[:, 1] * np.exp(exponent - exponent.max())
        return values / values.sum()

    solved = root(lambda beta: weights(beta) @ positions - target, [0.0, 0.0])
    w = weights(solved.x)
    # A uniform load can start at the exact root; MINPACK may report no progress
    # despite a conserved resultant. Accept only the independently checked residual.
    if not np.isfinite(w).all() or np.linalg.norm(w @ positions - target) > 1e-8:
        raise ValueError("CFD resultant cannot be represented by same-sign normal face pressure")
    start = lines.index("*DLOAD") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("*"))
    lines[start:end] = [
        f"{int(face[0])},P2,{-force_n * weight / face[1]:.12e}"
        for face, weight in zip(faces, w, strict=True)
    ]
    metadata.update(
        force_target_n=force_n,
        centroid_target_m=list(centroid_m),
        force_mapped_n=float((force_n * w).sum()),
        centroid_mapped_m=(w @ faces[:, 2:4]).tolist(),
        normal_load_scope=(
            "normal force and two root moments preserved on undeformed faces; "
            "tangential traction omitted"
        ),
    )
    return lines, nodes, elements, metadata
