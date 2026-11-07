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
        root_mm=spec.geometry.fin_root_mm,
        tip_mm=spec.geometry.fin_tip_mm,
        sweep_mm=spec.geometry.fin_sweep_mm,
        fin_station_mm=spec.geometry.fin_tail_inset_mm,
        nose_mm=spec.geometry.nose_length_mm,
        nose_wall_mm=spec.geometry.nose_wall_mm,
        body_diameter_mm=spec.geometry.body_diameter_mm,
        body_height_mm=spec.geometry.body_height_mm,
        other_mass_g=spec.other_dry_mass_g,
        fixed_bottle_mass_g=spec.assumptions.fixed_bottle_mass_g,
        equipment_station=spec.assumptions.other_mass_station_fraction,
        payload_station=spec.assumptions.payload_station_fraction,
        wind_mps=spec.env.wind_speed_mps,
        gust_mps=spec.assumptions.gust_mps,
        mount=spec.assumptions.mount,
    )


def signature(change, spec):
    field, section = change["field"], change["section"]
    before = getattr(getattr(spec, section), field) if section else getattr(spec, field)
    after = change["value"]
    direction = (1 if after > before else -1) if isinstance(after, (int, float)) else str(after)
    return f"{section or 'spec'}.{field}:{direction}"


def verified_artifact(evidence):
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
    except (KeyError, TypeError, OSError, ValueError):
        return False


def transition_id(spec, change, before):
    """Do not count deterministic copies with different source/recovery labels twice."""
    design = spec.design.model_dump(
        mode="json", exclude={"dry_mass_kg", "geometry", "parachute_diameter_m", "has_parachute"}
    )
    return digest(
        dict(
            design=design,
            geometry=spec.geometry.model_dump(mode="json"),
            material=spec.material,
            env=spec.env.model_dump(mode="json"),
            assumptions=spec.assumptions.model_dump(mode="json", exclude={"evidence"}),
            actual_dry_mass_g=before["dry_mass_g"],
            change=change,
        )
    )


def verified(row):
    if not verified_artifact(row.get("evidence", {})):
        return False
    # Legacy observations can be displayed, but cannot teach a residual without
    # the original prediction and before/after artifact bindings below.
    if "prediction_residual_m" not in row:
        return True
    try:
        if not all(
            verified_artifact(row[key]) for key in ("before_evidence", "prediction_evidence")
        ):
            return False
        before = json.loads(Path(row["before_evidence"]["artifact"]).read_text(encoding="utf-8"))
        after = json.loads(Path(row["evidence"]["artifact"]).read_text(encoding="utf-8"))
        survey = json.loads(
            Path(row["prediction_evidence"]["artifact"]).read_text(encoding="utf-8")
        )
        prediction = survey["candidates"][row["prediction_action"]]
        delta = after["apogee_m"] - before["apogee_m"]
        expected = delta - prediction["delta_height_m"]
        return (
            prediction == row["prediction"]
            and math.isclose(row["before"]["apogee_m"], before["apogee_m"], abs_tol=1e-10)
            and math.isclose(row["after"]["apogee_m"], after["apogee_m"], abs_tol=1e-10)
            and math.isclose(row["delta"]["apogee_m"], delta, abs_tol=1e-10)
            and math.isclose(row["prediction_residual_m"], expected, abs_tol=1e-10)
        )
    except (KeyError, TypeError, OSError, ValueError):
        return False


def retrieve(records, spec, change, *, code, precision, screen_step_s=0.02, limit=6):
    current, sig = features(spec), signature(change, spec)
    scales = dict(
        volume_l=1,
        pressure_bar=2,
        fill=0.3,
        nozzle_mm=10,
        span_mm=70,
        thickness_mm=2,
        payload_g=100,
        root_mm=60,
        tip_mm=40,
        sweep_mm=50,
        fin_station_mm=30,
        nose_mm=80,
        nose_wall_mm=1.5,
        body_diameter_mm=30,
        body_height_mm=150,
        other_mass_g=150,
        fixed_bottle_mass_g=100,
        equipment_station=0.3,
        payload_station=0.2,
        wind_mps=3,
        gust_mps=2,
    )
    selected, seen = [], set()
    for row in records:
        # Different solver versions/precision/failed or stale results cannot teach a gain.
        if (
            row.get("code") != code
            or row.get("precision_hash") != digest(precision)
            or row.get("screen_step_s", 0.02) != screen_step_s
            or row.get("signature") != sig
            or row.get("status") != "measured"
            or row.get("transition_id", row.get("evidence_id")) in seen
            or not verified(row)
        ):
            continue
        f = row["features"]
        distance = sum(
            ((current[k] - f.get(k, current[k])) / scale) ** 2 for k, scale in scales.items()
        )
        distance += 1 if current["material"] != f["material"] else 0
        distance += 1 if current["mount"] != f.get("mount", current["mount"]) else 0
        # Legacy records lack some dimensions; only new bound records teach online residuals.
        if row.get("change_from") is not None and isinstance(change["value"], (int, float)):
            field, section = change["field"], change["section"]
            before = getattr(getattr(spec, section), field) if section else getattr(spec, field)
            step = change["value"] - before
            past_step = row["change_to"] - row["change_from"]
            distance += ((step - past_step) / max(abs(step), abs(past_step), 1e-12)) ** 2
        if distance > 4:
            continue
        seen.add(row.get("transition_id", row["evidence_id"]))
        selected.append(dict(row, similarity=1 / (1 + distance)))
    return sorted(selected, key=lambda r: (-r["similarity"], r["evidence_id"]))[:limit]


def estimate(rows, target, *, correction_limit_m=0.75):
    """Correct prediction error, never double-count an already predicted physical gain."""
    if not rows:
        return dict(
            samples=0,
            mean_delta_height_m=None,
            mean_cost_s=None,
            residual_samples=0,
            height_correction_m=0.0,
            score_adjustment=0.0,
        )
    weights = [r["similarity"] for r in rows]
    height = sum(w * r["delta"]["apogee_m"] for w, r in zip(weights, rows, strict=True)) / sum(
        weights
    )
    cost = sum(w * r["cost_s"] for w, r in zip(weights, rows, strict=True)) / sum(weights)
    residuals = [r for r in rows if r.get("prediction_residual_m") is not None and verified(r)]
    n = len(residuals)
    correction = (
        sum(r["similarity"] * r["prediction_residual_m"] for r in residuals)
        / sum(r["similarity"] for r in residuals)
        * n
        / (n + 3)
        if n
        else 0.0
    )
    bound = max(0.0, correction_limit_m)
    bounded = max(-bound, min(bound, correction))
    return dict(
        samples=len(rows),
        mean_delta_height_m=height,
        mean_cost_s=cost,
        residual_samples=n,
        height_correction_m=bounded,
        correction_limit_m=bound,
        correction_clipped=bounded != correction,
        # Diagnostic only; the harness recomputes joint requirement violation.
        score_adjustment=30 * math.tanh(bounded / max(1, target * 0.1)),
        confidence="local residual estimate; not a confidence bound or causal proof",
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
                fit_eligible=outcome.get("status") == "measured" and verified(outcome),
                fit_scope="measured outcome prediction, not imitation of the selected action",
                policy_imitation_eligible=False,
                automatic_training=False,
            )
        )
    return rows
