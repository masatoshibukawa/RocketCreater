"""Small local ridge models learn simulation residuals/costs, never acceptance labels."""

import json
import math
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.analysis import experience

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


def estimate(rows, query, *, correction_limit_m):
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
