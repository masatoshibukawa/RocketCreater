"""Learn wider contextual coverage while retaining verified history and nominal experts."""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.benchmark_surrogate_depth import fit_architecture
from scripts.expanded_design_data import AXES, CATEGORIES, FAMILIES, from_original
from scripts.expanded_surrogate import contract, core_coordinates, inverse, predict, transform
from scripts.report_refined_rl import local_file
from scripts.search_surrogate import predict as dense_predict
from scripts.search_surrogate import targets

ARCHITECTURE = (128, 128, 64, 32)
SEEDS = (9021, 9022, 9023)


def scores(y, estimate):
    error = np.abs(estimate - y)
    boundary = np.abs(y[:, 1] - 1.12) <= 0.25
    return dict(
        count=len(y),
        mae=error.mean(0).tolist(),
        maximum_error=error.max(0).tolist(),
        false_static_headroom=int(np.sum((estimate[:, 1] >= 1.12) & (y[:, 1] < 1.12))),
        true_static_headroom=int(np.sum(y[:, 1] >= 1.12)),
        predicted_static_headroom=int(np.sum(estimate[:, 1] >= 1.12)),
        missed_static_headroom=int(np.sum((estimate[:, 1] < 1.12) & (y[:, 1] >= 1.12))),
        boundary_count=int(boundary.sum()),
        boundary_mae=error[boundary].mean(0).tolist() if boundary.any() else None,
    )


def arrays(rows):
    return np.array([r["unit"] for r in rows]), np.array([targets(r["metrics"]) for r in rows])


def run(data, history, advisors, output):
    import sklearn

    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    dr, hr, ar = [read(p / "report.json") for p in (data, history, advisors)]
    if any(not r["source_unchanged"] or r["source_hash"] != source for r in (dr, hr, ar)):
        raise ValueError("Incompatible dataset or physics")
    if (
        dr["schema"] != "expanded-context-data-v1"
        or digest(dr["axes"]) != digest(AXES)
        or {int(k): v for k, v in dr["categories"].items()} != CATEGORIES
    ):
        raise ValueError("Dataset bounds or categorical encoding differ")
    for name in ("expanded_design_data.py", "expanded_screening.py", "search_joint_designs.py"):
        if dr["script_hashes"][name] != sha(Path(__file__).with_name(name)):
            raise ValueError("Dataset generation recipe changed")
    paths = [
        Path(__file__),
        Path(__file__).with_name("expanded_surrogate.py"),
        Path(__file__).with_name("expanded_design_data.py"),
        Path(__file__).with_name("benchmark_surrogate_depth.py"),
        Path(__file__).with_name("search_surrogate.py"),
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        data_report_sha256=sha(data / "report.json"),
        history_report_sha256=sha(history / "report.json"),
        advisor_report_sha256=sha(advisors / "report.json"),
        architecture=ARCHITECTURE,
        seeds=SEEDS,
        axes=AXES,
        categories=CATEGORIES,
        anchors=[],
        learning_curve=[],
        tests=[],
        input_contract=contract(source),
        versions=dict(numpy=np.__version__, sklearn=sklearn.__version__),
        physical_qualification=False,
        acceptance_performed=False,
        design_acceptance="NN predictions cannot establish acceptance",
    )
    write_json(output / "plan.json", report)
    test_sets = []
    for i in range(3):
        fresh_path = local_file(data, f"examples-{i}.jsonl", dr["anchors"][i]["examples_sha256"])
        historical_path = local_file(
            history, f"examples-{i}.jsonl", hr["anchors"][i]["examples_sha256"]
        )
        expert_path = local_file(advisors, f"model-{i}.json", ar["anchors"][i]["model_sha256"])
        fresh = [
            r
            for r in map(json.loads, fresh_path.read_text(encoding="utf-8").splitlines())
            if r["status"] == "completed"
        ]
        old = [
            r
            for r in map(json.loads, historical_path.read_text(encoding="utf-8").splitlines())
            if r["split"] == "train"
        ]
        expert = read(expert_path)
        if (
            expert["anchor"] != dr["anchors"][i]["anchor_spec"]
            or expert["cad"] != dr["anchors"][i]["cad"]
        ):
            raise ValueError("Context anchor or CAD differs")
        anchor = DesignSpec.model_validate(expert["anchor"])
        old_x, old_y = arrays(old)
        old_x = from_original(old_x, anchor)
        groups = {s: [r for r in fresh if r["split"] == s] for s in ("train", "validation", "test")}
        reserved = {r["spec_hash"] for s in ("validation", "test") for r in groups[s]}
        if reserved & {r["spec_hash"] for r in old + groups["train"]}:
            raise ValueError("Training and fresh evaluation overlap")
        if {r["spec_hash"] for r in groups["validation"]} & {
            r["spec_hash"] for r in groups["test"]
        }:
            raise ValueError("Validation and test overlap")
        nx, ny = arrays(groups["train"])
        vx, vy = arrays(groups["validation"])
        test_sets.append(groups["test"])
        sizes = sorted(set((min(2048, len(nx)), min(4096, len(nx)), len(nx))))
        members, full_files = [], []
        full_validation = None
        for n in sizes:
            x, y = np.r_[old_x, nx[:n]], np.r_[old_y, ny[:n]]
            for seed in SEEDS if n == len(nx) else SEEDS[:1]:
                start = time.monotonic()
                model = fit_architecture(
                    x,
                    transform(y),
                    vx,
                    transform(vy),
                    architecture=ARCHITECTURE,
                    seed=seed,
                    categories=CATEGORIES,
                )
                prediction = inverse(dense_predict(model, vx))
                entry = dict(
                    anchor=i,
                    fresh_train_count=n,
                    historical_train_count=len(old),
                    seed=seed,
                    total_train_count=len(x),
                    elapsed_s=time.monotonic() - start,
                    validation=scores(vy, prediction),
                    epochs=model["epochs"],
                    by_distribution={
                        f: scores(
                            vy[[r["distribution"] == f for r in groups["validation"]]],
                            prediction[[r["distribution"] == f for r in groups["validation"]]],
                        )
                        for f in FAMILIES
                    },
                )
                path = output / f"member-{i}-{n}-{seed}.json"
                model.update(
                    target_transform="log1p-height_asinh-margin_log1p-deflection",
                    input_contract=contract(source),
                    source_hash=source,
                    predicted_acceptance=False,
                )
                write_json(path, model)
                entry.update(model_file=path.name, model_sha256=sha(path))
                report["learning_curve"].append(entry)
                if n == len(nx):
                    members.append(model)
                    full_files.append(dict(file=path.name, sha256=sha(path)))
                write_json(output / "progress.json", report)
                print(
                    json.dumps(
                        {
                            k: entry[k]
                            for k in (
                                "anchor",
                                "fresh_train_count",
                                "seed",
                                "elapsed_s",
                                "validation",
                            )
                        }
                    ),
                    flush=True,
                )
        bundle = dict(
            schema="expanded-context-ensemble-v1",
            source_hash=source,
            input_contract=contract(source),
            anchor=expert["anchor"],
            cad=expert["cad"],
            members=members,
            nominal_expert=expert,
            axes=AXES,
            categories=CATEGORIES,
            validation_enabled=False,
            predicted_acceptance=False,
            target_transform="log1p-height_asinh-margin_log1p-deflection",
        )
        full_validation = predict(bundle, vx, hybrid=False)
        baseline = np.mean(np.r_[old_y, ny], axis=0)
        per_family = {}
        for family in FAMILIES:
            mask = np.array([r["distribution"] == family for r in groups["validation"]])
            measured = scores(vy[mask], full_validation[mask])
            mean_mae = np.abs(vy[mask] - baseline).mean(0)
            per_family[family] = dict(
                **measured,
                mean_baseline_mae=mean_mae.tolist(),
                enabled=bool(
                    mask.sum() >= 30 and np.all(np.array(measured["mae"][:2]) < mean_mae[:2])
                ),
            )
        bundle["validation_enabled"] = all(r["enabled"] for r in per_family.values())
        path = output / f"context-model-{i}.json"
        write_json(path, bundle)
        report["anchors"].append(
            dict(
                anchor=i,
                historical_train_count=len(old),
                fresh_train_count=len(nx),
                total_train_count=len(old) + len(nx),
                validation_count=len(vx),
                validation_by_distribution=per_family,
                validation_enabled=bundle["validation_enabled"],
                model_file=path.name,
                model_sha256=sha(path),
                members=full_files,
                hybrid_validation=scores(vy, predict(bundle, vx)),
            )
        )
        write_json(output / "progress.json", report)
    # All model weights, routing and validation gates are frozen before test labels are evaluated.
    write_json(output / "frozen-models.json", report["anchors"])
    report["frozen_models_sha256"] = sha(output / "frozen-models.json")
    for i, rows in enumerate(test_sets):
        bundle = read(output / f"context-model-{i}.json")
        x, y = arrays(rows)
        broad, hybrid = predict(bundle, x, hybrid=False), predict(bundle, x)
        original, core = core_coordinates(x, DesignSpec.model_validate(bundle["anchor"]))
        per_family = {}
        for family in FAMILIES:
            mask = np.array([r["distribution"] == family for r in rows])
            per_family[family] = dict(
                broad=scores(y[mask], broad[mask]), hybrid=scores(y[mask], hybrid[mask])
            )
        curves = []
        for entry in report["learning_curve"]:
            if entry["anchor"] == i and entry["seed"] == SEEDS[0]:
                prediction = inverse(dense_predict(read(output / entry["model_file"]), x))
                curves.append(
                    dict(
                        fresh_train_count=entry["fresh_train_count"],
                        test=scores(y, prediction),
                        by_distribution={
                            f: scores(
                                y[[r["distribution"] == f for r in rows]],
                                prediction[[r["distribution"] == f for r in rows]],
                            )
                            for f in FAMILIES
                        },
                    )
                )
        expert_prediction = dense_predict(bundle["nominal_expert"], original[core])
        report["tests"].append(
            dict(
                anchor=i,
                broad=scores(y, broad),
                hybrid=scores(y, hybrid),
                by_distribution=per_family,
                learning_curve=curves,
                nominal_expert=scores(y[core], expert_prediction),
                routed_core_count=int(core.sum()),
                core_max_prediction_change=float(np.max(np.abs(hybrid[core] - expert_prediction))),
            )
        )
    report.update(
        elapsed_s=time.monotonic() - begin,
        source_unchanged=code_hash() == source and hashes == {p.name: sha(p) for p in paths},
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Implementation changed during training")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("data", "history", "advisors", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--ml-libraries", type=Path)
    a = p.parse_args()
    if a.ml_libraries:
        sys.path.append(str(a.ml_libraries.resolve()))
    run(a.data, a.history, a.advisors, a.output)
