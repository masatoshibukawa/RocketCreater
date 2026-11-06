"""Leave-one-seed-out prediction audit; this is not a policy-efficiency experiment."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignSpec, write_json
from rocketwright.analysis import experience, policy
from scripts.report_design_search import verified_files


def audit(root):
    root = Path(root)
    evidence = verified_files(root)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    dataset = json.loads((root / "learning.json").read_text(encoding="utf-8"))
    specs = {}
    for observation in report["observations"]:
        spec = DesignSpec.model_validate(observation["spec"])
        specs[policy.identity(spec)] = spec
    eligible = [r for r in dataset if r["fit_eligible"] and experience.verified(r["outcome"])]
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
        training = [r for r in eligible if r["seed"] != row["seed"]]
        matches = experience.retrieve(
            [r["outcome"] for r in training],
            before,
            selected["target"],
            code=outcome["code"],
            precision=row["input"]["context"]["precision"],
        )
        estimate = experience.estimate(matches, before.requirement.target_altitude_m)
        base, actual = prediction["delta_height_m"], outcome["delta"]["apogee_m"]
        n = estimate["samples"]
        weight = n / (n + 3)
        adjusted = (1 - weight) * base + weight * (estimate["mean_delta_height_m"] or 0)
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
            )
        )
    matched = [r for r in rows if r["matched_samples"] > 0]

    def mean(key):
        return sum(r[key] for r in matched) / len(matched) if matched else None

    return dict(
        source_hash=report["source_hash"],
        evidence=evidence,
        split="leave one entire seed family out; offline predictive audit, not online timing",
        eligible_outcomes=len(eligible),
        held_out_predictions=len(rows),
        predictions_with_cross_seed_history=len(matched),
        axial_mae_m=mean("axial_absolute_error_m"),
        history_adjusted_mae_m=mean("history_adjusted_absolute_error_m"),
        rows=rows,
        skipped=skipped,
        automatic_weight_training=False,
        general_efficiency_improvement_proved=False,
        limitations=[
            "Only chosen actions have measured outcomes; selection bias remains",
            "Few initial-design families cannot establish generalization",
            "Equal-budget repeated policy trials are required to claim efficiency improvement",
            "This fixed shrinkage predictor is diagnostic; the LLM still chooses actions",
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "skipped"}}))


if __name__ == "__main__":
    main()
