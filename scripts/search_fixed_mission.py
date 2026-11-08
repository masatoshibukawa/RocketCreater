"""Redesign the fixed 400 kPa / 40 g / 20 m mission; never accept on NN predictions."""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.schema import STOCKS, Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.adaptive_evolution import minimize
from scripts.expanded_design_data import AXES, decode, from_original
from scripts.expanded_screening import measure
from scripts.gpu_payload_surrogate import Predictor, cuda_setup
from scripts.payload_search import metrics_vector
from scripts.reevaluate_fixed_mission import MISSION, mission_spec

CATEGORIES = {11: len(STOCKS)}
# Screening-only heuristic: worst-q * 15-degree beam loads differ from concurrent
# CFD flight loads. The production beam AND FEM limit remains 0.05 in Precision.
RESERVES = dict(height_m=22.0, static_margin_cal=1.15, beam_ratio=0.20)


def expanded(points, anchor):
    points = np.atleast_2d(np.asarray(points, float))
    if (
        points.shape[1] != 12
        or not np.isfinite(points).all()
        or np.any((points < 0) | (points > 1))
    ):
        raise ValueError("Twelve finite bounded design coordinates required")
    result = from_original(np.full((len(points), 12), 0.5), anchor)
    result[:, :12] = points
    result[:, 12] = 1  # 400 kPa, never optimized in this mission.
    result[:, 13] = (40 - 10) / (200 - 10)
    return result


def candidate(anchor, unit):
    spec = mission_spec(decode(anchor, expanded(unit, anchor)[0]).model_dump(mode="json"))
    if (
        spec.env != anchor.env
        or spec.other_dry_mass_g != anchor.other_dry_mass_g
        or spec.assumptions.mount != anchor.assumptions.mount
        or spec.geometry.fin_count != anchor.geometry.fin_count
    ):
        raise ValueError("Search changed fixed context")
    return spec


def encode(spec):
    g, a, d = spec.geometry, spec.assumptions, spec.design
    values = [
        d.water_fill_frac,
        d.nozzle_diameter_m * 1000,
        g.fin_root_mm,
        g.fin_tip_mm / g.fin_root_mm,
        g.fin_sweep_mm / max(g.fin_root_mm - g.fin_tip_mm, 1e-9),
        g.fin_span_mm,
        g.fin_thickness_mm,
        g.nose_length_mm,
        g.nose_wall_mm,
        a.other_mass_station_fraction,
        a.payload_station_fraction,
        list(STOCKS).index(spec.material) + 0.5,
    ]
    return np.array(
        [(v - lo) / (hi - lo) for v, (lo, hi) in zip(values, list(AXES.values())[:12], strict=True)]
    )


def loss(y):
    y = np.atleast_2d(np.asarray(y, float))
    if y.shape[1] != 3 or not np.isfinite(y).all():
        raise ValueError("Finite altitude, static margin and beam ratio required")
    v = (
        np.maximum(0, (RESERVES["height_m"] - y[:, 0]) / RESERVES["height_m"])
        + np.maximum(0, (RESERVES["static_margin_cal"] - y[:, 1]) / RESERVES["static_margin_cal"])
        + np.maximum(0, (y[:, 2] - RESERVES["beam_ratio"]) / RESERVES["beam_ratio"])
    )
    # Positive values remain infeasible; otherwise prefer height reserve.
    return np.where(v > 0, 1 + v, -y[:, 0] / (y[:, 0] + 20))


def run(models, parents, output, *, population=40, generations=50):
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    files = [
        Path(__file__),
        Path("scripts/adaptive_evolution.py"),
        Path("scripts/expanded_design_data.py"),
        Path("scripts/expanded_screening.py"),
        Path("scripts/gpu_payload_surrogate.py"),
        Path("scripts/reevaluate_fixed_mission.py"),
        models / "report.json",
        *[models / f"context-model-{i}.json" for i in range(3)],
        *[p / "report.json" for p in parents],
    ]
    hashes = {str(p): sha(p) for p in files}
    model_report = read(models / "report.json")
    bundles = [read(models / f"context-model-{i}.json") for i in range(3)]
    if (
        not model_report["source_unchanged"]
        or model_report["source_hash"] != source
        or any(b["source_hash"] != source for b in bundles)
    ):
        raise ValueError("Predictor physical source differs")
    for i in range(3):
        if sha(models / f"context-model-{i}.json") != model_report["anchors"][i]["model_sha256"]:
            raise ValueError("Predictor bytes differ from verified training report")
    warm = []
    for parent in parents:
        report = read(parent / "report.json")
        if report["source_hash"] != source or not report["source_unchanged"]:
            raise ValueError("Warm-start source differs")
        warm.extend(
            DesignSpec.model_validate(r["spec"])
            for r in report["results"]
            if r["status"] == "completed"
        )
    cuda_setup()
    predictor = Predictor(bundles)
    plan = dict(
        schema="fixed-mission-redesign-v1",
        mission=MISSION,
        reserves=RESERVES,
        population=population,
        generations=generations,
        source_hash=source,
        input_hashes=hashes,
        precision=Precision().model_dump(),
        methods=["ga-nn", "de-nn"],
        acceptance_unchanged=True,
        physical_qualification=False,
        predictor_retrained=False,
    )
    write_json(output / "plan.json", plan)
    runs, selected, all_rows = [], [], []
    stream = (output / "evaluations.jsonl").open("w", encoding="utf-8")
    for i, bundle in enumerate(bundles):
        anchor = DesignSpec.model_validate(bundle["anchor"])
        starts = [
            encode(s)
            for s in warm
            if (
                s.geometry.body_diameter_mm == anchor.geometry.body_diameter_mm
                and s.geometry.body_height_mm == anchor.geometry.body_height_mm
            )
        ]
        for j, method in enumerate(("ga", "de")):
            label, rows, cache = f"{method}-nn-{i}", [], {}
            seed = 40820 + 100 * i + j
            initial = qmc.LatinHypercube(12, seed=seed).random(population)
            for n, unit in enumerate(starts[: population // 2]):
                initial[n] = unit

            def objective(unit, label=label, anchor=anchor, bundle=bundle, cache=cache, rows=rows):
                row = dict(run=label, unit=unit.tolist(), status="invalid", loss=100.0)
                try:
                    spec = candidate(anchor, unit)
                    key = digest(spec.model_dump(mode="json"))
                    if key in cache:
                        return cache[key]
                    metrics = measure(spec, anchor, bundle["cad"])
                    value = float(loss(metrics_vector(metrics))[0])
                    row.update(
                        status="completed",
                        loss=value,
                        spec_sha256=key,
                        metrics=metrics,
                        spec=spec.model_dump(mode="json"),
                    )
                    cache[key] = value
                except (ValueError, RuntimeError) as error:
                    row["error"] = str(error)
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                if len(rows) % population == 0:
                    stream.flush()
                    best = min(rows, key=lambda item: item["loss"])
                    print(
                        dict(
                            run=label,
                            calls=len(rows),
                            best=best["loss"],
                            metrics=best.get("metrics"),
                        ),
                        flush=True,
                    )
                return row["loss"]

            def advice(points, i=i):
                points = np.column_stack((points, np.full(len(points), (40 - 10) / 190)))
                return loss(predictor.predict(points, np.full(len(points), i)))

            result = minimize(
                objective,
                initial,
                generations=generations,
                seed=seed,
                method=method,
                categories=CATEGORIES,
                advisor=advice,
            )
            best = min((r for r in rows if r["status"] == "completed"), key=lambda r: r["loss"])
            selected.append(dict(best, label=label))
            runs.append(
                dict(
                    label=label,
                    nfev=result.nfev,
                    unique_attempts=len(rows),
                    history=result.history,
                    best=best,
                )
            )
            all_rows.extend(rows)
            write_json(output / "search-progress.json", runs)
    stream.close()
    if code_hash() != source or any(sha(p) != hashes[str(p)] for p in files):
        raise ValueError("Source or input changed during search")
    jobs = [
        (
            r["label"],
            DesignSpec.model_validate(r["spec"]),
            output / r["label"],
            source,
            Precision(),
            300,
            time.monotonic() + 1200,
        )
        for r in selected
    ]
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(_case, jobs):
            results.append(row)
            write_json(output / "native-progress.json", results)
            print(
                dict(native=row["label"], status=row["status"], metrics=row.get("metrics")),
                flush=True,
            )
    result = dict(
        **plan,
        runs=runs,
        results=results,
        source_unchanged=code_hash() == source,
        input_unchanged=all(sha(p) == hashes[str(p)] for p in files),
        unique_attempts=len(all_rows),
        predictor_candidates=predictor.candidates,
        evaluations_sha256=sha(output / "evaluations.jsonl"),
        elapsed_s=time.monotonic() - begin,
        acceptance_performed=False,
    )
    write_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models", type=Path, default=Path("output/payload-gpu-model2"))
    parser.add_argument(
        "--parents",
        type=Path,
        nargs="+",
        default=[Path("output/payload-search1"), Path("output/pressure-payload-search1")],
    )
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=50)
    args = parser.parse_args()
    if not 8 <= args.population <= 128 or not 1 <= args.generations <= 200:
        parser.error("Use population 8–128 and generations 1–200")
    sys.path.insert(0, str(Path("output/torch-cuda-libs").resolve()))
    run(
        args.models,
        args.parents,
        args.output,
        population=args.population,
        generations=args.generations,
    )
