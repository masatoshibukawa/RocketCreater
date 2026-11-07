"""Training-only grouped validation selects bounded local residual predictors."""

import numpy as np

HEIGHT_MODELS = (
    "raw",
    "mean",
    "shrunk_mean",
    "legacy_ridge",
    "ridge_3",
    "ridge_0.3",
    "ridge_0.03",
    "ridge_0.003",
    "local_0.2",
    "local_0.5",
)
COST_MODELS = ("mean", "ridge_3", "ridge_0.3", "local_0.5")


def predict(name, x, y, weights, q):
    w = np.asarray(weights, float).copy()
    if name == "raw":
        return 0.0
    if name.startswith("local_"):
        width = float(name.split("_")[1])
        # Normalize exponents before exp to avoid complete underflow far from support.
        distances = np.sum((x - q) ** 2, axis=1)
        w *= np.exp(-(distances - distances.min()) / (2 * width**2))
    center = np.average(x, axis=0, weights=w)
    offset = float(np.average(y, weights=w))
    value = offset
    if name.startswith("ridge_") or name == "legacy_ridge":
        penalty = 3.0 if name == "legacy_ridge" else float(name.split("_")[1])
        dx = x - center
        coef = np.linalg.solve(
            dx.T @ (w[:, None] * dx) + penalty * np.eye(x.shape[1]), dx.T @ (w * (y - offset))
        )
        value += float((q - center) @ coef)
    if name in {"shrunk_mean", "legacy_ridge"}:
        value *= len(x) / (len(x) + 3)
    return float(value)


def select(x, y, weights, q, groups, *, models, bound=None):
    """Leave all observations of an initial state out together; no query outcome input.

    OOF errors are diagnostics for method selection, not calibrated confidence bounds.
    Distinct transition IDs with the same initial state do not count as extra folds.
    """
    x, y, weights, q = map(lambda a: np.asarray(a, float), (x, y, weights, q))
    groups = np.asarray(groups)
    if x.ndim != 2 or y.shape != (len(x),) or weights.shape != y.shape or q.shape != x.shape[1:]:
        raise ValueError("Mismatched training arrays")
    if not all(np.isfinite(v).all() for v in (x, y, weights, q)) or np.any(weights <= 0):
        raise ValueError("Finite values and positive weights required")
    if len(groups) != len(x) or len(set(groups)) < 4:
        raise ValueError("At least four independent initial-state groups required")
    errors, scores = {}, {}
    for name in models:
        e = np.zeros(len(x))
        for group in dict.fromkeys(groups):
            held = groups == group
            for j in np.flatnonzero(held):
                p = predict(name, x[~held], y[~held], weights[~held], x[j])
                if bound is not None:
                    p = np.clip(p, -bound, bound)
                e[j] = y[j] - p
        errors[name] = e
        scores[name] = float(np.average(abs(e), weights=weights))
    best = min(scores.values())
    # Prefer simpler models when their validation errors are indistinguishable at 5%.
    selected = next(name for name in models if scores[name] <= best * 1.05 + 1e-12)
    value = predict(selected, x, y, weights, q)
    if bound is not None:
        value = float(np.clip(value, -bound, bound))
    distance = float(np.min(np.linalg.norm(x - q, axis=1)))
    return dict(
        selected=selected,
        prediction=float(value),
        validation_mae=scores,
        selected_validation_mae=scores[selected],
        validation_max_abs_error=float(abs(errors[selected]).max()),
        validation_residuals=errors[selected].tolist(),
        groups=groups.tolist(),
        nearest_feature_distance=distance,
        uncertainty_scope="group-held-out training errors; not a confidence interval",
    )
