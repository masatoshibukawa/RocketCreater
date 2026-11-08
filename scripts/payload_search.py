"""Payload/altitude tradeoff shared by evolutionary, neural and policy searches."""

import numpy as np
from scipy.stats import qmc

from scripts.expanded_design_data import AXES, decode, from_original
from scripts.mixed_genetic import canonical

DIMENSIONS = 13
CATEGORIES = {11: 3}
CONTINUOUS = [*range(11), 12]
PAYLOAD_RANGE_G = AXES["payload_g"]
TARGET_M = 30.0
STATIC_TARGET = 1.12
BEAM_LIMIT = 0.05


def expanded(points, anchor):
    points = np.atleast_2d(np.asarray(points, float))
    if (
        points.shape[1] != DIMENSIONS
        or not np.isfinite(points).all()
        or np.any((points < 0) | (points > 1))
    ):
        raise ValueError("Thirteen bounded finite design/payload coordinates required")
    result = from_original(np.full((len(points), 12), 0.5), anchor)
    result[:, :12] = points[:, :12]
    result[:, 13] = points[:, 12]
    return result


def candidate(anchor, unit):
    spec = decode(anchor, expanded(unit, anchor)[0])
    if (
        spec.env != anchor.env
        or spec.other_dry_mass_g != anchor.other_dry_mass_g
        or spec.design.initial_gauge_pressure_pa != anchor.design.initial_gauge_pressure_pa
        or spec.geometry.fin_count != anchor.geometry.fin_count
        or spec.assumptions.mount != anchor.assumptions.mount
        or spec.requirement.target_altitude_m != TARGET_M
        or spec.requirement.payload_mass_kg != spec.design.payload_mass_kg
    ):
        raise ValueError("Fixed context or matching payload requirement changed")
    return spec


def initial(count, seed, anchor):
    points = qmc.LatinHypercube(DIMENSIONS, seed=seed).random(count)
    points[: count // 2, :12] = from_original(points[: count // 2, :12], anchor)[:, :12]
    return canonical(points, CATEGORIES)


def violations(y):
    y = np.atleast_2d(np.asarray(y, float))
    if y.shape[1] != 3 or not np.isfinite(y).all():
        raise ValueError("Finite height, margin and beam ratio required")
    return np.column_stack(
        (
            np.maximum(0, (TARGET_M - y[:, 0]) / TARGET_M),
            np.maximum(0, (STATIC_TARGET - y[:, 1]) / STATIC_TARGET),
            np.maximum(0, (y[:, 2] - BEAM_LIMIT) / BEAM_LIMIT),
        )
    )


def loss(y, payload_g):
    """Feasible beats infeasible; inside feasibility maximize payload, not altitude."""
    violation = violations(y).sum(1)
    payload = np.broadcast_to(np.asarray(payload_g, float), violation.shape)
    if not np.isfinite(payload).all() or np.any((payload < 10 - 1e-8) | (payload > 200 + 1e-8)):
        raise ValueError("Payload outside the declared 10–200 g study")
    return np.where(violation > 0, 1 + violation, -payload / 200)


def metrics_vector(metrics):
    return np.array(
        [
            metrics["scenario_height_m"][0],
            metrics["static_margin_cal"],
            metrics["conservative_beam_ratio"],
        ]
    )


def payload(points):
    return 10 + 190 * np.asarray(points)[..., 12]


def move(unit, action, remaining):
    unit, action = np.asarray(unit, float), np.asarray(action, float)
    if action.shape != (*unit.shape[:-1], len(CONTINUOUS)) or not np.isfinite(action).all():
        raise ValueError("Twelve finite continuous actions required")
    result = unit.copy()
    scale = 0.03 + 0.22 * np.asarray(remaining)
    result[..., CONTINUOUS] = np.clip(
        result[..., CONTINUOUS] + np.expand_dims(scale, -1) * np.clip(action, -1, 1), 0, 1
    )
    return canonical(result, CATEGORIES)


def observation(unit, anchor_ids, y, remaining):
    unit, y = np.atleast_2d(unit), np.atleast_2d(y)
    return np.column_stack(
        (
            unit[:, CONTINUOUS],
            np.eye(3)[np.minimum((unit[:, 11] * 3).astype(int), 2)],
            np.eye(3)[np.atleast_1d(anchor_ids)],
            y[:, 0] / 30,
            y[:, 1] / 3,
            np.log1p(np.maximum(y[:, 2], 0)),
            np.atleast_1d(remaining),
        )
    ).astype(np.float32)
