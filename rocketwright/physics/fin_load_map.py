"""Transfer a free-fin normal force and its two moments to a structural mesh."""

import numpy as np
from scipy.optimize import root

from rocketwright.physics.bottle_integrity import fem
from rocketwright.physics.concrete_fin import polygon_moments


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
    if not solved.success or np.linalg.norm(w @ positions - target) > 1e-8:
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
