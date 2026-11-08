"""Pressure/payload extension with the completed fixed-pressure study kept immutable."""

import numpy as np
from scipy.stats import qmc

from scripts import payload_search as base
from scripts.expanded_design_data import CATEGORIES as FULL_CATEGORIES
from scripts.expanded_design_data import decode
from scripts.gpu_payload_surrogate import Predictor as BasePredictor
from scripts.mixed_genetic import canonical
from scripts.search_surrogate import features

CATEGORIES = base.CATEGORIES
DIMENSIONS = 14
CONTINUOUS = [*range(11), 12, 13]
PRESSURE_RANGE_KPA = (50.0, 400.0)
loss, metrics_vector, payload, violations = (
    base.loss,
    base.metrics_vector,
    base.payload,
    base.violations,
)


def expanded(points, anchor):
    points = np.atleast_2d(np.asarray(points, float))
    if (
        points.shape[1] != 14
        or not np.isfinite(points).all()
        or np.any((points < 0) | (points > 1))
    ):
        raise ValueError("Fourteen bounded finite coordinates required")
    result = base.expanded(points[:, :13], anchor)
    result[:, 12] = points[:, 13]
    return result


def candidate(anchor, unit):
    # Reuse the original fixed-context guard for the first 13 coordinates.
    original = base.candidate(anchor, np.asarray(unit)[:13])
    spec = decode(anchor, expanded(unit, anchor)[0])
    actual = spec.model_dump(mode="json")
    check = original.model_dump(mode="json")
    check["design"]["initial_gauge_pressure_pa"] = actual["design"]["initial_gauge_pressure_pa"]
    if actual != check or not 50000 <= spec.design.initial_gauge_pressure_pa <= 400000:
        raise ValueError("Pressure study changed other context or exceeded its ceiling")
    return spec


def initial(count, seed, anchor):
    # Exact projected starts match the fixed-pressure study. Half retain its 400 kPa setting.
    points = base.initial(count, seed, anchor)
    pressure = qmc.LatinHypercube(1, seed=seed + 5531).random(count)
    pressure[: count // 2] = 1
    return canonical(np.column_stack((points, pressure)), CATEGORIES)


def move(unit, action, remaining):
    unit, action = np.asarray(unit, float), np.asarray(action, float)
    if action.shape != (*unit.shape[:-1], 13) or not np.isfinite(action).all():
        raise ValueError("Thirteen finite actions required")
    old = base.move(unit[..., :13], action[..., :12], remaining)
    pressure = np.clip(
        unit[..., 13] + (0.03 + 0.22 * np.asarray(remaining)) * np.clip(action[..., -1], -1, 1),
        0,
        1,
    )
    return np.concatenate((old, np.expand_dims(pressure, -1)), axis=-1)


def observation(unit, anchor_ids, y, remaining):
    unit = np.atleast_2d(unit)
    obs = base.observation(unit[:, :13], anchor_ids, y, remaining)
    return np.column_stack((obs[:, :-1], unit[:, 13], obs[:, -1])).astype(np.float32)


class Predictor(BasePredictor):
    def predict(self, points, anchor_ids):
        points, ids = np.atleast_2d(points), np.atleast_1d(anchor_ids)
        if ids.shape != (len(points),) or np.any((ids < 0) | (ids > 2)):
            raise ValueError("One valid anchor identity per candidate required")
        result = np.empty((len(points), 3))
        with self.torch.no_grad():
            for i in range(3):
                mask = ids == i
                if not mask.any():
                    continue
                x = features(expanded(points[mask], self.anchors[i]), FULL_CATEGORIES)
                result[mask] = (
                    self.models[i]
                    .physical(self.torch.as_tensor(x, dtype=self.torch.float32, device=self.device))
                    .cpu()
                    .numpy()
                )
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite GPU pressure/payload prediction")
        self.calls += 1
        self.candidates += len(points)
        return result
