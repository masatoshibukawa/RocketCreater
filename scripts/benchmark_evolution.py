"""Matched repeated-seed GA/DE ablation, with optional frozen neural proposal ranking."""

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from scipy.optimize import differential_evolution

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import AXES, samples
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts import adaptive_evolution, mixed_genetic
from scripts.search_joint_designs import proposal
from scripts.search_surrogate import advisor

METHODS = ("ga", "de", "ga-adaptive", "de-adaptive", "ga-nn", "de-nn")
SEEDS = (3107, 4829, 9901)


def experiment(job):
    model, method, seed, anchor_id, population_size, generations, destination, source = job
    begin = time.monotonic()
    if code_hash() != source:
        raise ValueError("Physics source changed")
    anchor = DesignSpec.model_validate(model["anchor"])
    category = {int(k): v for k, v in model["categories"].items()}
    initial = mixed_genetic.canonical(samples(population_size, seed + anchor_id), category)
    rows = []
    with destination.open("w", encoding="utf-8") as log:

        def objective(unit):
            row, loss = proposal(unit, anchor, model["cad"], "initial")
            row["loss"] = loss
            rows.append(row)
            # Full candidate and observed metrics are retained, not just best-value curves.
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            return loss

        if method == "ga":
            result = mixed_genetic.minimize(
                objective, initial, generations=generations, seed=seed + 100000, categories=category
            )
        elif method == "de":
            result = differential_evolution(
                objective,
                [(0, 1)] * len(AXES),
                init=initial,
                maxiter=generations,
                seed=seed + 100000,
                polish=False,
                tol=0,
                atol=0,
            )
        else:
            result = adaptive_evolution.minimize(
                objective,
                initial,
                generations=generations,
                seed=seed + 100000,
                method=method.split("-")[0],
                categories=category,
                advisor=advisor(model) if method.endswith("-nn") else None,
            )
    valid = [r for r in rows if r["status"] == "completed"]
    best = min(valid, key=lambda r: r["loss"], default=None)
    feasible = [r for r in valid if r["metrics"]["static_margin_cal"] >= 1]
    high = max(feasible, key=lambda r: r["metrics"]["scenario_height_m"][0], default=None)
    if code_hash() != source:
        raise ValueError("Physics source changed")
    return dict(
        method=method,
        seed=seed,
        anchor=anchor_id,
        evaluations=int(result.nfev),
        expected_evaluations=population_size * (generations + 1),
        initial_sha256=digest(initial.tolist()),
        best_loss=float(result.fun),
        best=best,
        best_stable_screen_height_m=high["metrics"]["scenario_height_m"][0] if high else None,
        rejected=len(rows) - len(valid),
        unique_specs=len({r["spec_hash"] for r in valid}),
        history=getattr(result, "history", None),
        predicted_candidates=getattr(result, "predicted_candidates", 0),
        neural_enabled=method.endswith("-nn") and model["validation_enabled"],
        elapsed_s=time.monotonic() - begin,
        data_file=destination.name,
        data_sha256=sha(destination),
    )


def run(training, output, *, population_size=32, generations=10, workers=2):
    output.mkdir(parents=True, exist_ok=False)
    start, source = time.monotonic(), code_hash()
    training_report = read(training / "report.json")
    if not training_report["source_unchanged"] or training_report["source_hash"] != source:
        raise ValueError("Unverified or incompatible training source")
    models = []
    for i, entry in enumerate(training_report["anchors"]):
        if sha(training / f"model-{i}.json") != entry["model_sha256"]:
            raise ValueError("Model changed after held-out evaluation")
        if sha(training / f"examples-{i}.jsonl") != entry["examples_sha256"]:
            raise ValueError("Training examples changed")
        models.append(read(training / f"model-{i}.json"))
    paths = [
        Path(__file__),
        Path(__file__).with_name("adaptive_evolution.py"),
        Path(__file__).with_name("mixed_genetic.py"),
        Path(__file__).with_name("search_joint_designs.py"),
        Path(__file__).with_name("search_surrogate.py"),
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        methods=METHODS,
        seeds=SEEDS,
        population_size=population_size,
        generations=generations,
        workers=workers,
        training_report_sha256=sha(training / "report.json"),
        training_cost_evaluations=sum(r["evaluated"] for r in training_report["anchors"]),
        training_cost_s=training_report["elapsed_s"],
        runs=[],
        results=[],
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(output / "plan.json", report)
    jobs = [
        (
            model,
            method,
            seed,
            anchor_id,
            population_size,
            generations,
            output / f"{method}-{seed}-{anchor_id}.jsonl",
            source,
        )
        for seed in SEEDS
        for anchor_id, model in enumerate(models)
        for method in METHODS
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(experiment, jobs):
            report["runs"].append(row)
            write_json(output / "progress.json", report)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "method",
                            "seed",
                            "anchor",
                            "evaluations",
                            "best_loss",
                            "best_stable_screen_height_m",
                        )
                    }
                ),
                flush=True,
            )
    if any(r["evaluations"] != r["expected_evaluations"] for r in report["runs"]):
        raise ValueError("Optimizer-call budgets differ; comparison cannot be marked matched")
    for seed in SEEDS:
        for anchor_id in range(len(models)):
            group = [r for r in report["runs"] if r["seed"] == seed and r["anchor"] == anchor_id]
            if len({r["initial_sha256"] for r in group}) != 1:
                raise ValueError("Initial populations differ")
    # Same native budget: one measured incumbent per anchor, selected over the three seed runs.
    promotions = []
    for method in METHODS:
        for anchor_id in range(len(models)):
            group = [
                r
                for r in report["runs"]
                if r["method"] == method and r["anchor"] == anchor_id and r["best"] is not None
            ]
            row = min(group, key=lambda r: r["best_loss"])
            label = f"{method}-{anchor_id}"
            promotions.append(
                (
                    label,
                    DesignSpec.model_validate(row["best"]["spec"]),
                    output / label,
                    source,
                    Precision(),
                    180,
                    time.monotonic() + 3600,
                )
            )
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(_case, promotions):
            report["results"].append(row)
            write_json(output / "native-progress.json", report)
            print(
                json.dumps(
                    dict(native=row["label"], status=row["status"], metrics=row.get("metrics"))
                ),
                flush=True,
            )
    report.update(
        elapsed_s=time.monotonic() - start,
        matched_evaluations=True,
        matched_initial_populations=True,
        source_unchanged=code_hash() == source and hashes == {p.name: sha(p) for p in paths},
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Changed code during benchmark")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--population", type=int, default=32)
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--workers", type=int, default=2)
    a = p.parse_args()
    if not 8 <= a.population <= 128 or not 1 <= a.generations <= 80 or not 1 <= a.workers <= 4:
        p.error("Use population 8–128, generations 1–80, workers 1–4")
    run(
        a.training,
        a.output,
        population_size=a.population,
        generations=a.generations,
        workers=a.workers,
    )
