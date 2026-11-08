"""Fresh-source DE search under an explicit drag assumption; never design acceptance."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.adaptive_evolution import minimize
from scripts.expanded_screening import measure
from scripts.reevaluate_fixed_mission import MISSION, mission_spec
from scripts.search_fixed_mission import CATEGORIES, candidate, encode

RESERVES = dict(height_m=22.0, static_margin_cal=1.10, beam_ratio=0.20)


def drag_spec(original, cd):
    if not np.isfinite(cd) or cd < 0.1 or cd > 5:
        raise ValueError("Use an explicit drag assumption between 0.1 and 5")
    data = mission_spec(original).model_dump(mode="json")
    data["design"]["axial_drag_coefficient"] = cd
    return DesignSpec.model_validate(data)


def score(metrics):
    values = np.array(
        [metrics[k] for k in ("apogee_m", "static_margin_cal", "conservative_beam_ratio")]
    )
    if not np.isfinite(values).all():
        raise ValueError("Finite measured metrics required")
    h, s, b = values
    violation = (
        max(0, (RESERVES["height_m"] - h) / RESERVES["height_m"])
        + max(0, (RESERVES["static_margin_cal"] - s) / RESERVES["static_margin_cal"])
        + max(0, (b - RESERVES["beam_ratio"]) / RESERVES["beam_ratio"])
    )
    return 1 + violation if violation else -h / (h + 20)


def run(parent, output, *, cd=1.4, population=40, generations=80):
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    files = [
        Path(__file__),
        parent / "report.json",
        Path("scripts/adaptive_evolution.py"),
        Path("scripts/expanded_screening.py"),
        Path("scripts/expanded_design_data.py"),
        Path("scripts/search_fixed_mission.py"),
        Path("scripts/reevaluate_fixed_mission.py"),
    ]
    hashes = {str(p): sha(p) for p in files}
    previous = read(parent / "report.json")
    # Only specifications are imported across versions. CAD, predictions, physical
    # labels, acceptance and learned weights are never reused from the old source.
    starts = [r for r in previous["results"] if r["status"] == "completed"]
    seeds = [next(r for r in starts if r["label"] == f"de-nn-{i}") for i in range(3)]
    plan = dict(
        source_hash=source,
        input_hashes=hashes,
        parent_source=previous["source_hash"],
        mission=MISSION,
        drag_assumption=cd,
        reserves=RESERVES,
        population=population,
        generations=generations,
        precision=Precision().model_dump(),
        acceptance_performed=False,
        physical_qualification=False,
        imported_information="Design specifications only; fresh CAD and physics on current source",
        aerodynamic_scope="Assumed constant axial Cd with analytic normal force; not CFD flight",
        predictor_used=False,
    )
    write_json(output / "protocol.json", plan)
    jobs = [
        (
            f"anchor-{i}",
            drag_spec(r["spec"], cd),
            output / f"anchor-{i}",
            source,
            Precision(),
            300,
            time.monotonic() + 900,
        )
        for i, r in enumerate(seeds)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        anchors = list(pool.map(_case, jobs))
    write_json(output / "anchors.json", anchors)
    if any(r["status"] != "completed" for r in anchors):
        raise RuntimeError("A fresh anchor failed; inspect anchors.json")
    results = []
    with (output / "evaluations.jsonl").open("w", encoding="utf-8") as stream:
        for i, row in enumerate(anchors):
            anchor = DesignSpec.model_validate(row["spec"])
            cad = read(output / f"anchor-{i}" / "geometry/data.json")["cad_metrics"]
            seed = 4142020 + i
            initial = qmc.LatinHypercube(12, seed=seed).random(population)
            related = [r for r in starts if r["label"].endswith(f"-{i}")]
            for n, prior in enumerate(related):
                initial[n] = encode(drag_spec(prior["spec"], cd))
            cache, rows = {}, []

            def objective(unit, anchor=anchor, cad=cad, cache=cache, rows=rows, i=i):
                item = dict(anchor=i, unit=unit.tolist(), status="invalid", score=100.0)
                try:
                    spec = candidate(anchor, unit)
                    if spec.design.axial_drag_coefficient != cd:
                        raise ValueError("Drag assumption changed")
                    key = digest(spec.model_dump(mode="json"))
                    if key in cache:
                        return cache[key]
                    metrics = measure(spec, anchor, cad)
                    value = score(metrics)
                    item.update(
                        status="completed",
                        spec=spec.model_dump(mode="json"),
                        spec_sha256=key,
                        metrics=metrics,
                        score=value,
                    )
                    cache[key] = value
                except (ValueError, RuntimeError) as error:
                    item["error"] = str(error)
                rows.append(item)
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                if len(rows) % (population * 5) == 0:
                    stream.flush()
                    best = min(rows, key=lambda item: item["score"])
                    print(
                        dict(
                            anchor=i,
                            evaluations=len(rows),
                            score=best["score"],
                            metrics=best.get("metrics"),
                        ),
                        flush=True,
                    )
                return item["score"]

            evolution = minimize(
                objective,
                initial,
                generations=generations,
                seed=seed,
                method="de",
                categories=CATEGORIES,
            )
            best = min((r for r in rows if r["status"] == "completed"), key=lambda r: r["score"])
            results.append(
                dict(
                    label=f"drag-de-{i}",
                    selected=best,
                    history=evolution.history,
                    nfev=evolution.nfev,
                    unique_attempts=len(rows),
                )
            )
            write_json(output / "search-progress.json", results)
    if source != code_hash() or any(sha(Path(k)) != v for k, v in hashes.items()):
        raise ValueError("Source or input changed during search")
    jobs = [
        (
            r["label"],
            DesignSpec.model_validate(r["selected"]["spec"]),
            output / r["label"],
            source,
            Precision(),
            300,
            time.monotonic() + 900,
        )
        for r in results
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        native = list(pool.map(_case, jobs))
    write_json(
        output / "report.json",
        dict(
            **plan,
            search=results,
            results=native,
            elapsed_s=time.monotonic() - begin,
            evaluations_sha256=sha(output / "evaluations.jsonl"),
            source_unchanged=source == code_hash(),
            input_unchanged=all(sha(Path(k)) == v for k, v in hashes.items()),
        ),
    )
    for row in native:
        print(
            dict(label=row["label"], status=row["status"], metrics=row.get("metrics")), flush=True
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--cd", type=float, default=1.4)
    p.add_argument("--population", type=int, default=40)
    p.add_argument("--generations", type=int, default=80)
    a = p.parse_args()
    if not 8 <= a.population <= 128 or not 1 <= a.generations <= 200:
        p.error("Use population 8–128 and generations 1–200")
    run(a.parent, a.output, cd=a.cd, population=a.population, generations=a.generations)
