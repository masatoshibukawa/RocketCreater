"""Compare NN width/depth with fixed data, then evaluate the frozen choice on held-out LHS."""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.search_surrogate import TARGETS, features, predict, targets

ARCHITECTURES = ((64, 32), (128, 64), (128, 64, 32), (128, 128, 64, 32))
SEEDS = (9021, 9022, 9023)


def fit_architecture(x, y, vx, vy, *, architecture, seed, categories):
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.neural_network import MLPRegressor
    from threadpoolctl import threadpool_limits

    fx = features(x, categories)
    xm, xs = fx.mean(0), np.maximum(fx.std(0), 1e-8)
    ym, ys = y.mean(0), np.maximum(y.std(0), 1e-8)
    reg = MLPRegressor(
        hidden_layer_sizes=architecture,
        max_iter=500,
        random_state=seed,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=25,
        alpha=0.01,
        learning_rate_init=0.002,
        batch_size=128,
    )
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        reg.fit((fx - xm) / xs, (y - ym) / ys)
    model = dict(
        schema=1,
        categories=categories,
        targets=TARGETS,
        architecture=[fx.shape[1], *architecture, 3],
        x_mean=xm.tolist(),
        x_scale=xs.tolist(),
        y_mean=ym.tolist(),
        y_scale=ys.tolist(),
        weights=[w.tolist() for w in reg.coefs_],
        biases=[b.tolist() for b in reg.intercepts_],
        epochs=int(reg.n_iter_),
        seed=seed,
        training_count=len(x),
        convergence_warning=any(issubclass(w.category, ConvergenceWarning) for w in caught),
        validation_count=len(vx),
        predicted_acceptance=False,
    )
    estimate = predict(model, vx)
    mae, baseline = np.abs(estimate - vy).mean(0), np.abs(ym - vy).mean(0)
    model.update(
        validation_mae=mae.tolist(),
        validation_mean_baseline_mae=baseline.tolist(),
        validation_enabled=bool(np.isfinite(estimate).all() and np.all(mae[:2] < baseline[:2])),
    )
    return model


def select_architecture(rows):
    """Fixed validation-only rule; compare height/margin relative to the two-layer baseline."""
    summaries = []
    for architecture in ARCHITECTURES:
        group = [r for r in rows if tuple(r["architecture"]) == architecture]
        if len(group) != 9:
            raise ValueError("Three anchors and three initializations per architecture required")
        ratios = []
        for row in group:
            base = next(
                r
                for r in rows
                if tuple(r["architecture"]) == ARCHITECTURES[0]
                and r["anchor"] == row["anchor"]
                and r["seed"] == row["seed"]
            )
            ratios.append(
                np.array(row["validation_mae"][:2]) / np.maximum(base["validation_mae"][:2], 1e-12)
            )
        summaries.append(
            dict(
                architecture=list(architecture),
                score=float(np.mean(ratios)),
                mean_validation_mae=np.mean([r["validation_mae"] for r in group], axis=0).tolist(),
                training_elapsed_s=sum(r["elapsed_s"] for r in group),
                validation_enabled=all(r["validation_enabled"] for r in group),
            )
        )
    eligible = [r for r in summaries if r["validation_enabled"]]
    if not eligible:
        raise ValueError("No architecture passes validation")
    return dict(
        selected=min(eligible, key=lambda r: r["score"])["architecture"], summaries=summaries
    )


def run(training, original, output):
    import sklearn

    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    tr, old = read(training / "report.json"), read(original / "report.json")
    if any(not r["source_unchanged"] or r["source_hash"] != source for r in (tr, old)):
        raise ValueError("Incompatible physical source")
    files = [Path(__file__), Path(__file__).with_name("search_surrogate.py")]
    hashes = {p.name: sha(p) for p in files}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        architectures=ARCHITECTURES,
        seeds=SEEDS,
        training_report_sha256=sha(training / "report.json"),
        original_report_sha256=sha(original / "report.json"),
        rows=[],
        selection_metric="mean validation height/margin MAE ratio to paired 64/32 baseline",
        sklearn_version=sklearn.__version__,
        new_physics_evaluations=0,
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(output / "plan.json", report)
    for i in range(3):
        path = training / f"examples-{i}.jsonl"
        model_path = training / f"model-{i}.json"
        if (
            sha(path) != tr["anchors"][i]["examples_sha256"]
            or sha(model_path) != tr["anchors"][i]["model_sha256"]
        ):
            raise ValueError("Changed training evidence")
        previous = read(model_path)
        records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
        train, val = (
            [r for r in records if r["split"] == split] for split in ("train", "validation")
        )
        if {r["spec_hash"] for r in train} & {r["spec_hash"] for r in val}:
            raise ValueError("Overlapping training and validation")
        x, y = (
            np.array([r["unit"] for r in train]),
            np.array([targets(r["metrics"]) for r in train]),
        )
        vx, vy = np.array([r["unit"] for r in val]), np.array([targets(r["metrics"]) for r in val])
        for architecture in ARCHITECTURES:
            for seed in SEEDS:
                started = time.monotonic()
                model = fit_architecture(
                    x,
                    y,
                    vx,
                    vy,
                    architecture=architecture,
                    seed=seed,
                    categories={int(k): v for k, v in previous["categories"].items()},
                )
                model.update(
                    {
                        k: previous[k]
                        for k in (
                            "source_hash",
                            "anchor",
                            "cad",
                            "reference_geometry_sha256",
                            "examples_sha256",
                            "curriculum_units",
                        )
                    }
                )
                name = f"model-{i}-{'-'.join(map(str, architecture))}-{seed}.json"
                write_json(output / name, model)
                entry = dict(
                    anchor=i,
                    architecture=list(architecture),
                    seed=seed,
                    model_file=name,
                    model_sha256=sha(output / name),
                    validation_mae=model["validation_mae"],
                    validation_enabled=model["validation_enabled"],
                    epochs=model["epochs"],
                    convergence_warning=model["convergence_warning"],
                    elapsed_s=time.monotonic() - started,
                    parameters=sum(
                        np.asarray(v).size for k in ("weights", "biases") for v in model[k]
                    ),
                )
                report["rows"].append(entry)
                write_json(output / "progress.json", report)
                print(json.dumps(entry), flush=True)
    selection = select_architecture(report["rows"])
    # Freeze the choice before loading held-out labels. Tests never select architecture or seed.
    write_json(output / "selection.json", selection)
    report["selection"] = selection
    report["selection_sha256"] = sha(output / "selection.json")
    report["held_out"] = []
    for i in range(3):
        path = original / f"examples-{i}.jsonl"
        if sha(path) != old["anchors"][i]["examples_sha256"]:
            raise ValueError("Changed held-out evidence")
        held = [
            r
            for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())
            if r["split"] == "test" and r["status"] == "completed"
        ]
        used = {
            r["spec_hash"]
            for r in map(
                json.loads,
                (training / f"examples-{i}.jsonl").read_text(encoding="utf-8").splitlines(),
            )
        }
        if used & {r["spec_hash"] for r in held}:
            raise ValueError("Held-out design was used for training/validation")
        x, y = np.array([r["unit"] for r in held]), np.array([targets(r["metrics"]) for r in held])
        for row in report["rows"]:
            if row["anchor"] != i or row["architecture"] not in (
                list(ARCHITECTURES[0]),
                selection["selected"],
            ):
                continue
            path = output / row["model_file"]
            if sha(path) != row["model_sha256"]:
                raise ValueError("Changed frozen model")
            error = np.abs(predict(read(path), x) - y)
            report["held_out"].append(
                dict(
                    anchor=i,
                    architecture=row["architecture"],
                    seed=row["seed"],
                    count=len(x),
                    mae=error.mean(0).tolist(),
                    maximum_error=error.max(0).tolist(),
                )
            )
    report.update(
        elapsed_s=time.monotonic() - begin,
        source_unchanged=(code_hash() == source and hashes == {p.name: sha(p) for p in files}),
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Implementation changed during architecture comparison")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("training", "original", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--ml-libraries", type=Path)
    a = p.parse_args()
    if a.ml_libraries:
        sys.path.append(str(a.ml_libraries.resolve()))
    run(a.training, a.original, a.output)
