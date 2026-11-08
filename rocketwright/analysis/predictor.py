"""Small local ridge models learn simulation residuals/costs, never acceptance labels."""

import json
import math
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.analysis import experience
from rocketwright.analysis.predictor_selection import COST_MODELS, HEIGHT_MODELS, select

FEATURES = ("raw_delta", "fill", "pressure", "mass", "thickness", "root", "span", "step")


def vector(features, before, step, raw_delta):
    return np.array(
        [
            raw_delta / 5,
            features["fill"] / 0.3,
            features["pressure_bar"] / 4,
            before["dry_mass_g"] / 300,
            features["thickness_mm"] / 3,
            features["root_mm"] / 100,
            features["span_mm"] / 100,
            step,
        ],
        dtype=float,
    )


def sealed(row):
    """The saved observation binds features and measured cost as well as solver data."""
    evidence = row.get("learning_evidence", {})
    if not experience.verified(row) or not experience.verified_artifact(evidence):
        return False
    try:
        saved = json.loads(Path(evidence["artifact"]).read_text(encoding="utf-8"))
        return saved == {
            k: v for k, v in row.items() if k not in {"learning_evidence", "similarity"}
        }
    except (OSError, ValueError):
        return False


def ridge_estimate(rows, query, *, correction_limit_m):
    rows = [r for r in rows if r.get("prediction_residual_m") is not None and sealed(r)]
    seen, unique = set(), []
    for row in rows:
        key = row.get("transition_id")
        if key and key not in seen:
            unique.append(row)
            seen.add(key)
    rows = unique
    result = dict(status="insufficient_samples", samples=len(rows), minimum_samples=4)
    if len(rows) < 4:
        return result
    try:
        x = np.array(
            [
                vector(
                    r["features"],
                    r["before"],
                    (r["change_to"] - r["change_from"]) / max(abs(r["change_from"]), 1),
                    r["prediction"]["delta_height_m"],
                )
                for r in rows
            ]
        )
        y = np.array([[r["prediction_residual_m"], math.log1p(r["cost_s"])] for r in rows])
        if any(r["cost_s"] < 0 for r in rows):
            raise ValueError("Negative cost")
        q = vector(**query)
        weights = np.array([r["similarity"] for r in rows])
        if not all(np.isfinite(v).all() for v in (x, y, q, weights)) or np.any(weights <= 0):
            raise ValueError("Invalid fitted data")
    except (KeyError, TypeError, ValueError):
        return dict(result, status="invalid_training_data")
    center = np.average(x, axis=0, weights=weights)
    offset = np.average(y, axis=0, weights=weights)
    dx = x - center
    # Fixed regularization, not tuned on the held-out evaluation outcomes.
    penalty = 3.0
    coef = np.linalg.solve(
        dx.T @ (weights[:, None] * dx) + penalty * np.eye(x.shape[1]),
        dx.T @ (weights[:, None] * (y - offset)),
    )
    estimate = (q - center) @ coef + offset
    n = len(rows)
    correction = float(estimate[0]) * n / (n + 3)
    bound = max(0.0, correction_limit_m)
    correction = max(-bound, min(bound, correction))
    costs = [r["cost_s"] for r in rows]
    log_cost = max(0.0, min(math.log1p(max(costs) * 2), float(estimate[1])))
    cost = max(min(costs) * 0.5, math.expm1(log_cost))
    artifact = dict(
        features=list(FEATURES),
        center=center.tolist(),
        offset=offset.tolist(),
        coefficients=coef.tolist(),
        ridge=penalty,
        training_ids=[r["transition_id"] for r in rows],
        training_hashes=[r["learning_evidence"]["sha256"] for r in rows],
    )
    return dict(
        status="fitted",
        samples=n,
        model=artifact,
        model_hash=digest(artifact),
        height_correction_m=correction,
        predicted_cost_s=cost,
        correction_limit_m=bound,
        scope="local simulated residual and cost; not a pass",
        uncertainty="not calibrated; compare on unseen initial families",
    )


def estimate(rows, query, *, correction_limit_m):
    """Validate method choice on training groups; preserve the small-data fallback."""
    if len(rows) < 6:
        return ridge_estimate(rows, query, correction_limit_m=correction_limit_m)
    unique = {}
    for r in rows:
        key = r.get("transition_id")
        if key and key not in unique and r.get("prediction_residual_m") is not None and sealed(r):
            unique[key] = r
    rows = list(unique.values())
    if len(rows) < 6:
        return ridge_estimate(rows, query, correction_limit_m=correction_limit_m)
    cohorts = {
        (r.get("code"), r.get("precision_hash"), r.get("signature"), r.get("screen_step_s", 0.02))
        for r in rows
    }
    if len(cohorts) != 1:
        return dict(status="incompatible_training_cohorts", samples=len(rows))
    try:
        x = np.array(
            [
                vector(
                    r["features"],
                    r["before"],
                    (r["change_to"] - r["change_from"]) / max(abs(r["change_from"]), 1),
                    r["prediction"]["delta_height_m"],
                )
                for r in rows
            ]
        )
        q = vector(**query)
        weights = np.array([r["similarity"] for r in rows])
        costs = np.array([r["cost_s"] for r in rows])
        targets = np.array([r["prediction_residual_m"] for r in rows])
        if (
            not all(np.isfinite(v).all() for v in (x, q, weights, costs, targets))
            or np.any(weights <= 0)
            or np.any(costs < 0)
        ):
            raise ValueError("Invalid fitted data")
    except (KeyError, TypeError, ValueError):
        return dict(status="invalid_training_data", samples=len(rows), minimum_samples=4)
    groups = [
        digest(dict(features=r["features"], dry_mass_g=r["before"]["dry_mass_g"])) for r in rows
    ]
    if len(set(groups)) < 4:
        baseline = ridge_estimate(rows, query, correction_limit_m=correction_limit_m)
        baseline["selection_fallback"] = "fewer than four initial-state groups"
        return baseline
    bound = max(0.0, correction_limit_m)
    height = select(
        x,
        [r["prediction_residual_m"] for r in rows],
        weights,
        q,
        groups,
        models=HEIGHT_MODELS,
        bound=bound,
    )
    costs = np.array([r["cost_s"] for r in rows])
    cost = select(x, np.log1p(costs), weights, q, groups, models=COST_MODELS)
    correction = height["prediction"]
    # Outside this normalized feature neighborhood, abstain from residual extrapolation.
    supported = height["nearest_feature_distance"] <= 1.5
    if not supported:
        correction = 0.0
    predicted_cost = float(
        np.clip(
            np.expm1(np.clip(cost["prediction"], 0, np.log1p(costs.max() * 2))),
            costs.min() * 0.5,
            costs.max() * 2,
        )
    )
    model = dict(
        features=list(FEATURES),
        height_selection=height,
        log_cost_selection=cost,
        training_ids=[r["transition_id"] for r in rows],
        training_hashes=[r["learning_evidence"]["sha256"] for r in rows],
        training_vectors=x.tolist(),
        height_targets=[r["prediction_residual_m"] for r in rows],
        log_cost_targets=np.log1p(costs).tolist(),
        weights=weights.tolist(),
        query_vector=q.tolist(),
        support_distance_limit=1.5,
    )
    return dict(
        status="fitted",
        samples=len(rows),
        model=model,
        model_hash=digest(model),
        height_correction_m=correction,
        predicted_cost_s=predicted_cost,
        correction_limit_m=bound,
        selected_method=height["selected"],
        validation_mae_m=height["selected_validation_mae"],
        nearest_feature_distance=height["nearest_feature_distance"],
        correction_supported=supported,
        uncertainty="Training-only grouped errors; no calibrated confidence interval",
        scope="Predict simulated residual/cost only; acceptance and budgets unchanged",
    )


def snippets(rows, limit=2):
    return [
        dict(
            id=r.get("transition_id", r["evidence_id"]),
            signature=r["signature"],
            similarity=round(r["similarity"], 3),
            delta_height_m=r["delta"]["apogee_m"],
            prediction_residual_m=r.get("prediction_residual_m"),
            cost_s=r["cost_s"],
        )
        for r in rows[:limit]
    ]
