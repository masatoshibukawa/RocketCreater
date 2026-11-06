"""Collect native controlled training/held-out transitions; no LLM choices are claimed."""

import argparse
import json
import time
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignProjects, DesignSpec, write_json
from rocketwright.analysis import experience, predictor
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness, code_hash
from scripts.report_design_search import verified_files


class ControlledTrial(Harness):
    """Predeclared host experimental design, distinct from autonomous policy evaluation."""

    def _choices(self, c, spec, precision, limits):
        choices, proposals, confirmation = super()._choices(c, spec, precision, limits)
        target = "redesign/fin_root_mm-0.85"
        if target not in choices["offered"] and any(
            k.startswith("redesign/") for k in choices["offered"]
        ):
            raise ValueError("Prescribed root change is outside the eligible pool")
        if target in choices["offered"]:
            choices["offered"][target]["score"] = 1000
            choices["offered"] = dict(
                sorted(choices["offered"].items(), key=lambda kv: -kv[1]["score"])
            )
        return choices, proposals, confirmation


def collect(template, root, reuse_training=None):
    root.mkdir(parents=True, exist_ok=False)
    source, started = code_hash(), time.monotonic()
    precision = Precision(require_cfd=False, require_fem=False)
    limits = SearchLimits(
        planner="baseline",
        use_experience=False,
        max_versions=2,
        max_actions=40,
        budget_s=900,
        reserve_confirmation_fraction=0.1,
    )
    # The two evaluation geometries are absent from training. Choices and the split
    # are declared before observing outcomes; this is not a policy-efficiency ablation.
    definitions = [("train", f, 90.0) for f in (0.20, 0.25, 0.30, 0.35)]
    definitions += [("evaluate", 0.275, 92.0), ("evaluate", 0.325, 94.0)]
    write_json(
        root / "protocol.json",
        dict(
            source_hash=source,
            definitions=definitions,
            precision=precision.model_dump(),
            limits=limits.model_dump(),
            target="redesign/fin_root_mm-0.85",
            planner="prescribed_host_experiment",
        ),
    )
    store = DesignProjects(root / "projects")
    rows, trials, audits = [], [], []
    if reuse_training:
        saved = json.loads((reuse_training / "checkpoint.json").read_text(encoding="utf-8"))
        if saved["source_hash"] != source:
            raise ValueError("Cannot reuse training under changed numerical source")
        trials = [t for t in saved["trials"] if t["split"] == "train"]
        rows = [t["row"] for t in trials]
        if len(rows) != 4 or not all(predictor.sealed(r) for r in rows):
            raise ValueError("Reused training evidence is missing or changed")
    for i, (split, fill, chord) in enumerate(definitions):
        spec = template.model_copy(deep=True)
        spec.design = spec.design.model_copy(
            update=dict(
                initial_gauge_pressure_pa=400000, nozzle_diameter_m=0.022, water_fill_frac=fill
            )
        )
        spec.geometry = spec.geometry.model_copy(update=dict(fin_root_mm=chord))
        spec.assumptions.other_mass_station_fraction = 0.25
        if reuse_training and split == "train":
            if trials[i]["spec"] != spec.model_dump(mode="json"):
                raise ValueError("Reused training does not match the declared experiment")
            continue
        h = ControlledTrial(store, runtime=Runtime())
        state = store.create(spec)
        state = h.start(state["id"], state["revision"], precision, limits)
        for _ in range(limits.max_actions):
            if code_hash() != source:
                raise RuntimeError("Source changed during native collection")
            state = h.step(state["id"], state["revision"])
            a = state["adaptive"]
            print(
                json.dumps(
                    dict(
                        trial=i,
                        split=split,
                        version=state["version"],
                        action=a["decisions"][-1].get("action"),
                    )
                ),
                flush=True,
            )
            measured = [r for r in a["observations"] if predictor.sealed(r)]
            if measured or a["status"] != "running":
                break
        if len(measured) != 1 or measured[0]["prediction_action"] != "redesign/fin_root_mm-0.85":
            raise RuntimeError("Controlled transition did not produce one bound observation")
        row = measured[0]
        trial = dict(
            split=split,
            project_id=state["id"],
            spec=spec.model_dump(mode="json"),
            row=row,
            campaign_status=a["status"],
            collection_stopped_after_outcome=True,
        )
        trials.append(trial)
        if split == "train":
            rows.append(row)
        else:
            change = dict(section="geometry", field="fin_root_mm", value=chord * 0.85)
            retrieved = experience.retrieve(
                rows, spec, change, code=source, precision=precision.model_dump(), limit=24
            )
            fit = predictor.estimate(
                retrieved,
                dict(
                    features=experience.features(spec),
                    before=row["before"],
                    step=-0.15,
                    raw_delta=row["prediction"]["delta_height_m"],
                ),
                correction_limit_m=precision.altitude_error_m * precision.aero_allocation,
            )
            if fit["status"] != "fitted":
                raise RuntimeError("Held-out trial has no fitted model")
            audits.append(
                dict(
                    transition_id=row["transition_id"],
                    prediction=fit,
                    raw_error_m=row["prediction_residual_m"],
                    corrected_error_m=row["prediction_residual_m"] - fit["height_correction_m"],
                    actual_cost_s=row["cost_s"],
                    cost_error_s=row["cost_s"] - fit["predicted_cost_s"],
                )
            )
        write_json(root / "checkpoint.json", dict(source_hash=source, trials=trials, audits=audits))
    result = dict(
        source_hash=source,
        training_rows=rows,
        trials=trials,
        audits=audits,
        training_ids=[r["transition_id"] for r in rows],
        evaluation_ids=[r["transition_id"] for r in audits],
        raw_mae_m=sum(abs(r["raw_error_m"]) for r in audits) / len(audits),
        corrected_mae_m=sum(abs(r["corrected_error_m"]) for r in audits) / len(audits),
        cost_mae_s=sum(abs(r["cost_error_s"]) for r in audits) / len(audits),
        evidence=verified_files(root),
        reused_training_evidence=verified_files(reuse_training) if reuse_training else None,
        elapsed_s=time.monotonic() - started,
        protocol_hash=digest(definitions),
        general_efficiency_improvement_proved=False,
        physical_qualification=False,
        live_llm_calls=0,
        scope="Native prescribed transitions; two held-out geometries; simulation residuals only",
    )
    write_json(root / "report.json", result)
    print(
        json.dumps(
            {k: result[k] for k in ("raw_mae_m", "corrected_mae_m", "cost_mae_s", "elapsed_s")}
        ),
        flush=True,
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--reuse-training", type=Path)
    a = p.parse_args()
    collect(
        DesignSpec.model_validate_json(a.spec.read_text(encoding="utf-8")),
        a.output.resolve(),
        a.reuse_training.resolve() if a.reuse_training else None,
    )


if __name__ == "__main__":
    main()
