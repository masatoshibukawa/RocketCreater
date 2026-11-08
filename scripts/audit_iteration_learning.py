"""Leave-one-seed-out prediction audit; this is not a policy-efficiency experiment."""

import argparse
import json
import math
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, write_json
from rocketwright.analysis import experience, policy
from scripts.report_design_search import verified_files


def ascent_groups(report):
    """Source labels and different recovery canopies do not make ascent data independent."""
    initial = {}
    for row in report["observations"]:
        if "start" not in row:
            continue
        if row["start"] not in initial or row["version"] < initial[row["start"]]["version"]:
            initial[row["start"]] = row
    groups = {}
    for label, row in initial.items():
        spec = DesignSpec.model_validate(row["spec"])
        design = spec.design.model_dump(
            mode="json",
            exclude={
                "dry_mass_kg",
                "geometry",
                "parachute_diameter_m",
                "has_parachute",
            },
        )
        groups[label] = digest(
            dict(
                design=design,
                geometry=spec.geometry.model_dump(mode="json"),
                material=spec.material,
                env=spec.env.model_dump(mode="json"),
                assumptions=spec.assumptions.model_dump(mode="json", exclude={"evidence"}),
                dry_mass_g=row["metrics"]["dry_mass_g"],
            )
        )
    return groups


def audit(root, *, checkpoint=False):
    root = Path(root)
    evidence = verified_files(root)
    report = json.loads(
        (root / ("progress.json" if checkpoint else "report.json")).read_text(encoding="utf-8")
    )
    groups = ascent_groups(report)
    if checkpoint:
        dataset = []
        for campaign in report["campaigns"]:
            rows = json.loads(
                (root / (campaign["project_id"] + "-learning.json")).read_text(encoding="utf-8")
            )
            dataset.extend(
                dict(row, seed=campaign["label"], project_id=campaign["project_id"]) for row in rows
            )
    else:
        dataset = json.loads((root / "learning.json").read_text(encoding="utf-8"))
    specs = {}
    for observation in report["observations"]:
        spec = DesignSpec.model_validate(observation["spec"])
        specs[policy.identity(spec)] = spec
    eligible = [r for r in dataset if r["fit_eligible"] and experience.verified(r["outcome"])]
    raw_count, unique, seen = len(eligible), [], {}
    for row in eligible:
        outcome = row["outcome"]
        before = specs.get(outcome["from_spec_hash"])
        change = row["input"]["choices"].get(row["selected"], {}).get("target")
        if (
            before is not None
            and isinstance(change, dict)
            and "dry_mass_g" in outcome.get("before", {})
        ):
            transition = experience.transition_id(before, change, outcome["before"])
            key = (
                groups.get(row["seed"], row["seed"]),
                outcome["code"],
                outcome["precision_hash"],
                transition,
            )
            if key in seen:
                if not math.isclose(
                    seen[key], outcome["delta"]["apogee_m"], rel_tol=1e-8, abs_tol=1e-8
                ):
                    raise ValueError(
                        "Conflicting results for a duplicated deterministic transition"
                    )
                continue
            seen[key] = outcome["delta"]["apogee_m"]
            # Reconstruct complete covariates for legacy records from their saved input.
            section, field = change["section"], change["field"]
            outcome = dict(
                outcome,
                transition_id=transition,
                features=experience.features(before),
                change_from=getattr(getattr(before, section), field)
                if section
                else getattr(before, field),
                change_to=change["value"],
            )
            row = dict(row, outcome=outcome)
        unique.append(row)
    eligible = unique
    rows, skipped = [], []
    for row in eligible:
        outcome = row["outcome"]
        before = specs.get(outcome["from_spec_hash"])
        selected = row["input"]["choices"].get(row["selected"], {})
        prediction = selected.get("prediction")
        if before is None or not prediction or not isinstance(selected.get("target"), dict):
            skipped.append(dict(seed=row["seed"], action=row["selected"], reason="missing_input"))
            continue
        # Hold out the entire initial-design family, including all revisions and results.
        family = groups.get(row["seed"], row["seed"])
        training = [r for r in eligible if groups.get(r["seed"], r["seed"]) != family]
        train_outcomes = []
        for sample in training:
            forecast = (
                sample["input"]["choices"].get(sample["selected"], {}).get("prediction") or {}
            )
            predicted = forecast.get("raw_delta_height_m", forecast.get("delta_height_m"))
            train_outcomes.append(
                dict(
                    sample["outcome"],
                    offline_prediction_residual_m=(
                        sample["outcome"]["delta"]["apogee_m"] - predicted
                        if predicted is not None
                        else None
                    ),
                )
            )
        matches = experience.retrieve(
            train_outcomes,
            before,
            selected["target"],
            code=outcome["code"],
            precision=row["input"]["context"]["precision"],
        )
        estimate = experience.estimate(matches, before.requirement.target_altitude_m)
        base = prediction.get("raw_delta_height_m", prediction["delta_height_m"])
        actual = outcome["delta"]["apogee_m"]
        n = estimate["samples"]
        weight = n / (n + 3)
        adjusted = (1 - weight) * base + weight * (estimate["mean_delta_height_m"] or 0)
        residuals = [r for r in matches if r["offline_prediction_residual_m"] is not None]
        residual_weight = len(residuals) / (len(residuals) + 3)
        correction = (
            (
                sum(r["similarity"] * r["offline_prediction_residual_m"] for r in residuals)
                / sum(r["similarity"] for r in residuals)
                * residual_weight
            )
            if residuals
            else 0
        )
        p = row["input"]["context"]["precision"]
        bound = p["altitude_error_m"] * p["aero_allocation"]
        corrected = base + max(-bound, min(bound, correction))
        rows.append(
            dict(
                seed=row["seed"],
                action=row["selected"],
                training_seed_count=len({r["seed"] for r in training}),
                matched_samples=n,
                actual_delta_height_m=actual,
                axial_prediction_m=base,
                history_adjusted_prediction_m=adjusted,
                axial_absolute_error_m=abs(base - actual),
                history_adjusted_absolute_error_m=abs(adjusted - actual),
                residual_corrected_prediction_m=corrected,
                residual_corrected_absolute_error_m=abs(corrected - actual),
            )
        )
    matched = [r for r in rows if r["matched_samples"] > 0]

    def mean(key):
        return sum(r[key] for r in matched) / len(matched) if matched else None

    return dict(
        source_hash=report["source_hash"],
        audit_version="deduplicated-physical-transitions-v2",
        checkpoint_only=checkpoint,
        evidence=evidence,
        split="leave one equivalent-ascent family out; offline predictive audit, not online timing",
        equivalent_ascent_groups=groups,
        eligible_outcomes=len(eligible),
        eligible_records_before_deduplication=raw_count,
        duplicate_transitions_excluded=raw_count - len(eligible),
        held_out_predictions=len(rows),
        predictions_with_cross_seed_history=len(matched),
        axial_mae_m=mean("axial_absolute_error_m"),
        history_adjusted_mae_m=mean("history_adjusted_absolute_error_m"),
        residual_corrected_mae_m=mean("residual_corrected_absolute_error_m"),
        rows=rows,
        skipped=skipped,
        automatic_weight_training=False,
        general_efficiency_improvement_proved=False,
        limitations=[
            "Only chosen actions have measured outcomes; selection bias remains",
            "Few initial-design families cannot establish generalization",
            "Equal-budget repeated policy trials are required to claim efficiency improvement",
            "This fixed shrinkage predictor is diagnostic; the LLM still chooses actions",
            "Residual correction is an exploratory comparison after inspecting the mean-gain audit",
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--checkpoint", action="store_true", help="Only completed screening campaigns"
    )
    args = parser.parse_args()
    result = audit(args.root, checkpoint=args.checkpoint)
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "skipped"}}))


if __name__ == "__main__":
    main()
