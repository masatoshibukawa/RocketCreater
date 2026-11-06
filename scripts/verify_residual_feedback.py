"""Exercise bound residual retrieval with two new native local-model campaigns."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import DesignProjects, DesignSpec, write_json
from rocketwright.analysis import experience
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness, code_hash
from scripts.report_design_search import verified_files


def run(template, root, runtime):
    root.mkdir(parents=True, exist_ok=False)
    source = code_hash()
    store = DesignProjects(root / "projects")
    memory, campaigns = [], []
    # Same original mission and numerical bounds; screening flags are explicit.
    precision = Precision(require_cfd=False, require_fem=False)
    limits = SearchLimits(
        max_versions=2,
        max_actions=60,
        budget_s=900,
        memory_gib=24,
        reserve_confirmation_fraction=0.1,
        survey_candidates=40,
    )
    for fill in (0.25, 0.35):
        spec = template.model_copy(deep=True)
        spec.design = spec.design.model_copy(
            update={
                "initial_gauge_pressure_pa": 400000,
                "water_fill_frac": fill,
            }
        )
        spec.assumptions.other_mass_station_fraction = 0.25
        s = store.create(spec)
        h = Harness(store, runtime=runtime, prior_experience=memory)
        s = h.start(s["id"], s["revision"], precision, limits)
        while s["adaptive"]["status"] == "running":
            if code_hash() != source:
                raise RuntimeError("Numerical source changed during verification")
            s = h.step(s["id"], s["revision"])
            a = s["adaptive"]
            print(
                json.dumps(
                    dict(
                        project=s["id"],
                        version=s["version"],
                        status=a["status"],
                        action=a["decisions"][-1].get("action"),
                    )
                ),
                flush=True,
            )
        a = s["adaptive"]
        rows = [r for r in a["observations"] if r.get("status") == "measured"]
        if not rows or not all(
            experience.verified(r) and "prediction_residual_m" in r for r in rows
        ):
            raise RuntimeError(
                "Native residual records are missing or fail their evidence bindings"
            )
        memory.extend(rows)
        shown = []
        for decision in a["decisions"]:
            for key, candidate in decision.get("prompt_view", {}).get("choices", {}).items():
                history = candidate.get("history", {})
                if history.get("residual_samples", 0):
                    shown.append(
                        dict(
                            action=key,
                            selected=decision["action"] == key,
                            expected=candidate["expected"],
                            history=history,
                            forecast_cost_s=candidate["cost_s"],
                        )
                    )
        campaigns.append(
            dict(
                project_id=s["id"],
                fill=fill,
                status=a["status"],
                versions=s["version"],
                decisions=len(a["decisions"]),
                shown_verified_corrections=shown,
                requirement=s["spec"]["requirement"],
                precision=a["precision"],
                limits=a["limits"],
                spent_s=limits.budget_s - a["remaining_s"],
                outcomes=[
                    dict(
                        signature=r["signature"],
                        transition_id=r["transition_id"],
                        delta=r["delta"],
                    cost_s=r["cost_s"],
                        residual_m=r["prediction_residual_m"],
                        prediction_sha256=r["prediction_evidence"]["sha256"],
                        before_sha256=r["before_evidence"]["sha256"],
                        after_sha256=r["evidence"]["sha256"],
                    )
                    for r in rows
                ],
            )
        )
    if not campaigns[1]["shown_verified_corrections"]:
        raise RuntimeError("Second native model received no bound cross-campaign correction")
    result = dict(
        source_hash=source,
        campaigns=campaigns,
        evidence=verified_files(root),
        feedback_integration_pass=True,
        automatic_weight_training=False,
        general_efficiency_improvement_proved=False,
        physical_qualification=False,
        scope="Separate regression budget; not a continuation/reset of the multi-start campaign",
    )
    write_json(root / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    run(
        DesignSpec.model_validate_json(args.spec.read_text(encoding="utf-8")),
        args.root,
        Runtime.model_validate_json(args.runtime.read_text(encoding="utf-8")),
    )


if __name__ == "__main__":
    main()
