"""Retrieve measured iteration outcomes; no online changes to LLM weights or pass rules."""

import hashlib
import json
import math
from pathlib import Path

from rocketwright.adaptive import digest


def features(spec):
    return dict(
        volume_l=spec.design.bottle_volume_m3 * 1000,
        pressure_bar=spec.design.initial_gauge_pressure_pa / 100000,
        fill=spec.design.water_fill_frac,
        nozzle_mm=spec.design.nozzle_diameter_m * 1000,
        span_mm=spec.geometry.fin_span_mm,
        thickness_mm=spec.geometry.fin_thickness_mm,
        payload_g=spec.design.payload_mass_kg * 1000,
        material=spec.material,
    )


def signature(change, spec):
    field, section = change["field"], change["section"]
    before = getattr(getattr(spec, section), field) if section else getattr(spec, field)
    after = change["value"]
    direction = (1 if after > before else -1) if isinstance(after, (int, float)) else str(after)
    return f"{section or 'spec'}.{field}:{direction}"


def verified(row):
    evidence = row.get("evidence", {})
    try:
        path = Path(evidence["artifact"])
        manifest = path.parent / "manifest.json"
        if (
            hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]
            or hashlib.sha256(manifest.read_bytes()).hexdigest() != evidence["manifest_sha256"]
        ):
            return False
        for name, expected in json.loads(manifest.read_text(encoding="utf-8")).items():
            child = (path.parent / name).resolve()
            if (
                not child.is_relative_to(path.parent.resolve())
                or child.is_symlink()
                or hashlib.sha256(child.read_bytes()).hexdigest() != expected
            ):
                return False
        return True
    except (KeyError, OSError, ValueError):
        return False


def retrieve(records, spec, change, *, code, precision, limit=6):
    current, sig = features(spec), signature(change, spec)
    scales = dict(
        volume_l=1,
        pressure_bar=2,
        fill=0.3,
        nozzle_mm=10,
        span_mm=70,
        thickness_mm=2,
        payload_g=100,
    )
    selected, seen = [], set()
    for row in records:
        # Different solver versions/precision/failed or stale results cannot teach a gain.
        if (
            row.get("code") != code
            or row.get("precision_hash") != digest(precision)
            or row.get("signature") != sig
            or row.get("status") != "measured"
            or row.get("evidence_id") in seen
            or not verified(row)
        ):
            continue
        f = row["features"]
        distance = sum(((current[k] - f[k]) / scale) ** 2 for k, scale in scales.items())
        distance += 1 if current["material"] != f["material"] else 0
        if distance > 4:
            continue
        seen.add(row["evidence_id"])
        selected.append(dict(row, similarity=1 / (1 + distance)))
    return sorted(selected, key=lambda r: (-r["similarity"], r["evidence_id"]))[:limit]


def estimate(rows, target):
    if not rows:
        return dict(samples=0, mean_delta_height_m=None, mean_cost_s=None, score_adjustment=0)
    weights = [r["similarity"] for r in rows]
    height = sum(w * r["delta"]["apogee_m"] for w, r in zip(weights, rows, strict=True)) / sum(
        weights
    )
    cost = sum(w * r["cost_s"] for w, r in zip(weights, rows, strict=True)) / sum(weights)
    # Shrink small-sample feedback; preserve negative outcomes, not just successful choices.
    strength = len(rows) / (len(rows) + 3)
    tradeoff = sum(
        w
        * (r["delta"].get("static_margin_cal", 0) - max(0, r["delta"].get("incidence_deg", 0)) / 15)
        for w, r in zip(weights, rows, strict=True)
    ) / sum(weights)
    score = strength * 30 * math.tanh(height / max(1, target * 0.1) + tradeoff)
    return dict(
        samples=len(rows),
        mean_delta_height_m=height,
        mean_cost_s=cost,
        score_adjustment=score,
        confidence="local empirical estimate; not causal proof",
    )


def training_rows(decisions, outcomes):
    """Offline dataset only. Split by project/seed before any fitting or evaluation."""
    rows = []
    for outcome in outcomes:
        index = outcome.get("decision_index")
        if index is None or not 0 <= index < len(decisions):
            continue
        decision = decisions[index]
        if not decision.get("selection_context"):
            continue
        rows.append(
            dict(
                input=decision["selection_context"],
                model_input=decision.get("prompt_view"),
                selected=decision["action"],
                reason=decision["reason"],
                outcome=outcome,
                fit_eligible=outcome.get("status") == "measured",
                automatic_training=False,
            )
        )
    return rows
