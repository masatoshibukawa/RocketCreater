"""Collect fresh mixed-variable simulations, then fit and separately test an advisory NN."""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import AXES, samples
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.mixed_genetic import canonical
from scripts.search_joint_designs import proposal
from scripts.search_surrogate import fit, predict, targets


def measure(job):
    anchor, cad, unit = job
    row, loss = proposal(np.array(unit), DesignSpec.model_validate(anchor), cad, "initial")
    return dict(
        unit=unit,
        status=row["status"],
        spec_hash=row.get("spec_hash"),
        metrics=row.get("metrics"),
        error=row.get("error"),
        loss=loss,
    )


def run(reference, output, *, count=2048, workers=2):
    output.mkdir(parents=True, exist_ok=False)
    start, source = time.monotonic(), code_hash()
    reference_report = read(reference / "report.json")
    if source != reference_report["source_hash"] or not reference_report["source_unchanged"]:
        raise ValueError("Reference physics source differs")
    categories = {list(AXES).index("material_index"): int(AXES["material_index"][1])}
    module_paths = [
        Path(__file__),
        Path(__file__).with_name("search_surrogate.py"),
        Path(__file__).with_name("search_joint_designs.py"),
    ]
    hashes = {p.name: sha(p) for p in module_paths}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        examples_per_anchor=count,
        seed=912437,
        anchors=[],
        physical_qualification=False,
    )
    write_json(output / "plan.json", dict(report, train_fraction=0.7, validation_fraction=0.15))
    for anchor_no in range(3):
        folder = reference / f"g{anchor_no}"
        context, geometry = read(folder / "input.json"), read(folder / "data.json")
        spec, cad = context["spec"], geometry["cad_metrics"]
        points = canonical(samples(count, 912437 + anchor_no), categories)
        jobs = ((spec, cad, u.tolist()) for u in points)
        rows = []
        with (output / f"examples-{anchor_no}.jsonl").open("w", encoding="utf-8") as stream:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                for index, row in enumerate(pool.map(measure, jobs, chunksize=8)):
                    row["split"] = (
                        "train"
                        if index < int(count * 0.7)
                        else "validation"
                        if index < int(count * 0.85)
                        else "test"
                    )
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows.append(row)
                    if len(rows) % 256 == 0:
                        stream.flush()
                        print(json.dumps(dict(anchor=anchor_no, examples=len(rows))), flush=True)
        valid = [r for r in rows if r["status"] == "completed"]
        seen, unique = set(), []
        for r in valid:
            if r["spec_hash"] not in seen:
                seen.add(r["spec_hash"])
                unique.append(r)
        groups = {
            k: [r for r in unique if r["split"] == k] for k in ("train", "validation", "test")
        }
        arrays = {
            k: (np.array([r["unit"] for r in v]), np.array([targets(r["metrics"]) for r in v]))
            for k, v in groups.items()
        }
        model = fit(*arrays["train"], *arrays["validation"], categories=categories)
        model.update(
            source_hash=source,
            anchor=spec,
            cad=cad,
            reference_geometry_sha256=sha(folder / "data.json"),
            examples_sha256=sha(output / f"examples-{anchor_no}.jsonl"),
        )
        write_json(output / f"model-{anchor_no}.json", model)
        # Freeze weights before reading test labels for evaluation.
        tx, ty = arrays["test"]
        prediction = predict(model, tx)
        entry = dict(
            anchor=anchor_no,
            evaluated=len(rows),
            rejected=len(rows) - len(valid),
            unique=len(unique),
            counts={k: len(v) for k, v in groups.items()},
            test_mae=np.abs(prediction - ty).mean(0).tolist(),
            test_mean_baseline_mae=np.abs(np.asarray(model["y_mean"]) - ty).mean(0).tolist(),
            test_max_error=np.abs(prediction - ty).max(0).tolist(),
            validation_enabled=model["validation_enabled"],
            model_sha256=sha(output / f"model-{anchor_no}.json"),
            examples_sha256=model["examples_sha256"],
            epochs=model["epochs"],
        )
        report["anchors"].append(entry)
        write_json(output / "progress.json", report)
        print(json.dumps(entry), flush=True)
    report.update(
        elapsed_s=time.monotonic() - start,
        source_unchanged=code_hash() == source and hashes == {p.name: sha(p) for p in module_paths},
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Source changed during collection")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reference", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--count", type=int, default=2048)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--ml-libraries", type=Path)
    a = p.parse_args()
    if a.ml_libraries:
        sys.path.append(str(a.ml_libraries.resolve()))
    if not 256 <= a.count <= 16384 or not 1 <= a.workers <= 4:
        p.error("Use 256–16384 examples per anchor and 1–4 workers")
    run(a.reference, a.output, count=a.count, workers=a.workers)
