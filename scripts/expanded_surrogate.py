"""Context-aware surrogate inference with explicit bounds and a nominal-domain expert."""

from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha
from rocketwright.analysis.design_space import AXES as ORIGINAL_AXES
from scripts.expanded_design_data import AXES, CATEGORIES, decode, from_original
from scripts.search_surrogate import predict as dense_predict


def contract(source):
    recipe = {
        name: sha(Path(__file__).with_name(name))
        for name in ("expanded_design_data.py", "expanded_screening.py", "search_joint_designs.py")
    }
    return digest(
        dict(
            version="expanded-context-v1",
            axes=AXES,
            categories=CATEGORIES,
            source=source,
            recipe=recipe,
        )
    )


def transform(y):
    y = np.asarray(y, float)
    if y.ndim != 2 or y.shape[1] != 3 or not np.isfinite(y).all() or np.any(y[:, (0, 2)] < 0):
        raise ValueError("Finite height, signed margin and nonnegative deflection targets required")
    return np.column_stack((np.log1p(y[:, 0]), np.arcsinh(y[:, 1]), np.log1p(y[:, 2])))


def inverse(y):
    y = np.asarray(y, float)
    with np.errstate(over="raise", invalid="raise"):
        result = np.column_stack(
            (np.maximum(0, np.expm1(y[:, 0])), np.sinh(y[:, 1]), np.maximum(0, np.expm1(y[:, 2])))
        )
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite context prediction")
    return result


def core_coordinates(points, anchor):
    x = np.asarray(points, float)
    original = np.empty((len(x), 12))
    for i, (key, (lo, hi)) in enumerate(ORIGINAL_AXES.items()):
        blo, bhi = AXES[key]
        original[:, i] = (blo + x[:, i] * (bhi - blo) - lo) / (hi - lo)
    nominal = from_original(np.full((1, 12), 0.5), anchor)[0, 12:]
    is_core = np.all((original >= -1e-10) & (original <= 1 + 1e-10), axis=1)
    is_core &= np.all(np.abs(x[:, 12:] - nominal) < 1e-10, axis=1)
    return np.clip(original, 0, 1), is_core


def predict(bundle, points, *, hybrid=True):
    x = np.asarray(points, float)
    if (
        x.ndim != 2
        or x.shape[1] != len(AXES)
        or not np.isfinite(x).all()
        or np.any((x < 0) | (x > 1))
    ):
        raise ValueError("Query is outside the declared expanded input domain")
    if bundle["input_contract"] != contract(bundle["source_hash"]):
        raise ValueError("Changed axes or input contract")
    results = np.array([inverse(dense_predict(member, x)) for member in bundle["members"]])
    result = results.mean(0)
    if hybrid:
        original, core = core_coordinates(x, DesignSpec.model_validate(bundle["anchor"]))
        if core.any():
            result[core] = dense_predict(bundle["nominal_expert"], original[core])
    return result


def advisor(bundle, anchor, cad, source):
    """Ranking only. Context, baseline geometry and physics must match exactly."""
    if (
        bundle["source_hash"] != source
        or bundle["anchor"] != anchor.model_dump(mode="json")
        or bundle["cad"] != cad
        or not bundle["validation_enabled"]
    ):
        raise ValueError("Unvalidated or incompatible context advisor")

    def rank(points):
        y = predict(bundle, points)
        values = 2000 * np.maximum(0, 1.12 - y[:, 1]) - y[:, 0]
        for i, unit in enumerate(points):
            try:
                decode(anchor, unit)
            except ValueError:
                values[i] = np.inf
        return values

    return rank
