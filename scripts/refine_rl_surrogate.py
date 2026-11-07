"""Refit design surrogates with verified past simulator rollouts, reserving new test seeds."""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.search_surrogate import fit, predict, targets


def partition_records(records, held_out):
    """Reserve held-out identities even if they also occur in a historical rollout."""
    validation = {
        r["spec_hash"]: r
        for r in records
        if r["split"] == "validation" and r["spec_hash"] not in held_out
    }
    train = {
        r["spec_hash"]: r
        for r in records
        if r["split"] == "train"
        and r["spec_hash"] not in validation
        and r["spec_hash"] not in held_out
    }
    return train, validation


def run(training, evolution, rl, output):
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    original = read(training / "report.json")
    if not original["source_unchanged"] or original["source_hash"] != source:
        raise ValueError("Original surrogate physics source differs")
    records = [[] for _ in range(3)]
    inputs = {}
    for folder in (evolution, rl):
        report = read(folder / "report.json")
        if not report["source_unchanged"] or report["source_hash"] != source:
            raise ValueError("Historical simulator source differs")
        inputs[folder.name] = sha(folder / "report.json")
        for entry in report["runs"]:
            path = folder / entry["data_file"]
            if path.parent.resolve() != folder.resolve() or sha(path) != entry["data_sha256"]:
                raise ValueError("Changed historical simulator measurements")
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["status"] == "completed":
                    records[entry["anchor"]].append(
                        dict(
                            unit=row["unit"],
                            metrics=row["metrics"],
                            spec_hash=row["spec_hash"],
                            split="validation" if entry["seed"] == 9901 else "train",
                            origin=f"{folder.name}/{entry['method']}/{entry['seed']}",
                        )
                    )
    report = dict(
        source_hash=source,
        historical_reports=inputs,
        anchors=[],
        validation_seed=9901,
        reserved_new_test_seeds=[14291, 22639, 37117],
        original_test_examples_used=False,
        physical_qualification=False,
    )
    write_json(output / "plan.json", report)
    for i in range(3):
        model_path, examples_path = training / f"model-{i}.json", training / f"examples-{i}.jsonl"
        entry = original["anchors"][i]
        if (
            sha(model_path) != entry["model_sha256"]
            or sha(examples_path) != entry["examples_sha256"]
        ):
            raise ValueError("Original training evidence changed")
        old = read(model_path)
        original_rows = list(
            map(json.loads, examples_path.read_text(encoding="utf-8").splitlines())
        )
        held_out = {
            r["spec_hash"]
            for r in original_rows
            if r["split"] == "test" and r["status"] == "completed"
        }
        for row in original_rows:
            if row["status"] == "completed" and row["split"] != "test":
                records[i].append(
                    dict(
                        unit=row["unit"],
                        metrics=row["metrics"],
                        spec_hash=row["spec_hash"],
                        split=row["split"],
                        origin="original-lhs",
                    )
                )
        # Whole optimizer seed is held for validation; remove overlaps from training first.
        train, validation = partition_records(records[i], held_out)
        selected = list(train.values()) + list(validation.values())
        data_path = output / f"examples-{i}.jsonl"
        with data_path.open("w", encoding="utf-8") as stream:
            for row in selected:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        tx, ty = (
            np.array([r["unit"] for r in train.values()]),
            np.array([targets(r["metrics"]) for r in train.values()]),
        )
        vx, vy = (
            np.array([r["unit"] for r in validation.values()]),
            np.array([targets(r["metrics"]) for r in validation.values()]),
        )
        model = fit(tx, ty, vx, vy, categories={int(k): v for k, v in old["categories"].items()})
        promising = sorted(
            train.values(),
            key=lambda r: (
                2000 * max(0, 1.12 - r["metrics"]["static_margin_cal"])
                - r["metrics"]["scenario_height_m"][0]
            ),
        )[:128]
        model.update(
            source_hash=source,
            anchor=old["anchor"],
            cad=old["cad"],
            reference_geometry_sha256=old["reference_geometry_sha256"],
            examples_sha256=sha(data_path),
            curriculum_units=[r["unit"] for r in promising],
        )
        write_json(output / f"model-{i}.json", model)
        report["anchors"].append(
            dict(
                anchor=i,
                counts=dict(train=len(train), validation=len(validation)),
                old_validation_mae=np.abs(predict(old, vx) - vy).mean(0).tolist(),
                validation_mae=model["validation_mae"],
                validation_enabled=model["validation_enabled"],
                model_sha256=sha(output / f"model-{i}.json"),
                examples_sha256=sha(data_path),
                curriculum_count=len(promising),
                evaluated=len(selected),
            )
        )
        write_json(output / "progress.json", report)
        print(json.dumps(report["anchors"][-1]), flush=True)
    report.update(
        source_unchanged=code_hash() == source,
        elapsed_s=time.monotonic() - begin,
        new_physics_evaluations=0,
    )
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("training", "evolution", "rl", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--ml-libraries", type=Path)
    a = p.parse_args()
    if a.ml_libraries:
        sys.path.append(str(a.ml_libraries.resolve()))
    run(a.training, a.evolution, a.rl, a.output)
