"""Versioned broad design/context coverage; never expands the production pressure limit."""

import argparse
import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import AXES as ORIGINAL_AXES
from rocketwright.analysis.schema import MOUNTS, STOCKS
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from rocketwright.physics.atmosphere import state_scalar
from scripts.expanded_screening import measure as extended_measure
from scripts.mixed_genetic import canonical
from scripts.search_joint_designs import measure
from scripts.search_surrogate import predict, targets

AXES = {
    "water_fill_frac": (0.03, 0.75),
    "nozzle_mm": (3.0, 35.0),
    "fin_root_mm": (35.0, 200.0),
    "fin_tip_ratio": (0.10, 0.90),
    "fin_sweep_fraction": (0.0, 1.0),
    "fin_span_mm": (15.0, 150.0),
    "fin_thickness_mm": (1.2, 6.0),
    "nose_length_mm": (30.0, 280.0),
    "nose_wall_mm": (1.0, 3.0),
    "equipment_station_fraction": (0.05, 0.85),
    "payload_station_fraction": (0.02, 0.75),
    "material_index": (0.0, float(len(STOCKS))),
    "pressure_kpa": (50.0, 400.0),
    "payload_g": (10.0, 200.0),
    "temperature_c": (1.0, 45.0),
    "other_dry_mass_g": (80.0, 300.0),
    "solar_w_m2": (0.0, 1200.0),
    "warm_wait_s": (0.0, 600.0),
    "fin_count_index": (0.0, 4.0),
    "mount_index": (0.0, float(len(MOUNTS))),
}
CATEGORIES = {11: len(STOCKS), 18: 4, 19: len(MOUNTS)}
FAMILIES = ("core", "context", "wide", "boundary", "residual")
WEIGHTS = (3, 1, 2, 1, 1)
SPLITS = ("train", "validation", "test")
SEED = 975313


def decode(anchor, unit):
    u = np.asarray(unit, float)
    if u.shape != (len(AXES),) or not np.isfinite(u).all() or np.any((u < 0) | (u > 1)):
        raise ValueError("Finite expanded unit coordinates required")
    v = {k: lo + x * (hi - lo) for x, (k, (lo, hi)) in zip(u, AXES.items(), strict=True)}
    data = copy.deepcopy(anchor.model_dump(mode="json"))
    g = data["geometry"]
    for key in ("fin_root_mm", "fin_span_mm", "fin_thickness_mm", "nose_length_mm", "nose_wall_mm"):
        g[key] = round(v[key], 3)
    g["fin_tip_mm"] = round(g["fin_root_mm"] * v["fin_tip_ratio"], 3)
    g["fin_sweep_mm"] = min(
        round((g["fin_root_mm"] - g["fin_tip_mm"]) * v["fin_sweep_fraction"], 3),
        g["fin_root_mm"] - g["fin_tip_mm"],
    )
    g.update(
        fin_count=3 + min(int(v["fin_count_index"]), 3),
        fin_tail_inset_mm=0,
        dimensions_measured=False,
    )
    data["design"].update(
        water_fill_frac=round(v["water_fill_frac"], 4),
        nozzle_diameter_m=round(v["nozzle_mm"], 3) / 1000,
        initial_gauge_pressure_pa=round(v["pressure_kpa"] * 1000, 3),
        payload_mass_kg=round(v["payload_g"] / 1000, 6),
        geometry=g,
    )
    data["requirement"]["payload_mass_kg"] = data["design"]["payload_mass_kg"]
    data["assumptions"].update(
        other_mass_station_fraction=round(v["equipment_station_fraction"], 4),
        payload_station_fraction=round(v["payload_station_fraction"], 4),
        solar_w_m2=round(v["solar_w_m2"], 3),
        warm_wait_s=round(v["warm_wait_s"], 3),
        mount=list(MOUNTS)[min(int(v["mount_index"]), len(MOUNTS) - 1)],
    )
    standard_k = state_scalar(anchor.env.launch_altitude_m, 0)[0]
    data["env"]["temperature_offset_k"] = round(v["temperature_c"], 4) + 273.15 - standard_k
    data["material"] = list(STOCKS)[min(int(v["material_index"]), len(STOCKS) - 1)]
    data["other_dry_mass_g"] = round(v["other_dry_mass_g"], 3)
    data["measured_printed_mass_g"] = None
    candidate = DesignSpec.model_validate(data)
    if candidate.design.initial_gauge_pressure_pa > 400000:
        raise ValueError("Pressure exceeds the existing simulation campaign ceiling")
    return candidate


def nominal_context(anchor):
    return dict(
        pressure_kpa=anchor.design.initial_gauge_pressure_pa / 1000,
        payload_g=anchor.design.payload_mass_kg * 1000,
        temperature_c=state_scalar(anchor.env.launch_altitude_m, anchor.env.temperature_offset_k)[0]
        - 273.15,
        other_dry_mass_g=anchor.other_dry_mass_g,
        solar_w_m2=anchor.assumptions.solar_w_m2,
        warm_wait_s=anchor.assumptions.warm_wait_s,
        fin_count_index=anchor.geometry.fin_count - 3 + 0.5,
        mount_index=list(MOUNTS).index(anchor.assumptions.mount) + 0.5,
    )


def from_original(points, anchor):
    x = np.empty((len(points), len(AXES)))
    for i, (key, (lo, hi)) in enumerate(ORIGINAL_AXES.items()):
        blo, bhi = AXES[key]
        x[:, i] = (lo + np.asarray(points)[:, i] * (hi - lo) - blo) / (bhi - blo)
    for key, value in nominal_context(anchor).items():
        lo, hi = AXES[key]
        x[:, list(AXES).index(key)] = (value - lo) / (hi - lo)
    if np.any((x < 0) | (x > 1)):
        raise ValueError("Original anchor lies outside broad context envelope")
    return canonical(x, CATEGORIES)


def parent_split(spec_hash):
    value = int(spec_hash[:8], 16) % 100
    return "train" if value < 70 else "validation" if value < 85 else "test"


def sample_rows(count, anchor, parents, *, seed, split):
    if count < 8 or count % 8 or split not in SPLITS:
        raise ValueError("Use a sample count divisible by eight and a declared split")
    rng = np.random.default_rng(seed)
    output = []
    for family, weight in zip(FAMILIES, WEIGHTS, strict=True):
        n = count * weight // 8
        if family in ("core", "context"):
            points = from_original(
                qmc.LatinHypercube(12, seed=seed + len(output)).random(n), anchor
            )
            if family == "context":
                points[:, 12:] = qmc.LatinHypercube(
                    len(AXES) - 12, seed=seed + 1 + len(output)
                ).random(n)
        else:
            points = qmc.LatinHypercube(len(AXES), seed=seed + len(output)).random(n)
        group_ids = [None] * n
        if family == "residual":
            pool = [r for r in parents if parent_split(r["spec_hash"]) == split]
            if not pool:
                raise ValueError("Missing disjoint residual-parent group")
            chosen = [pool[i] for i in rng.integers(len(pool), size=n)]
            original = np.clip(
                np.array([r["unit"] for r in chosen]) + rng.normal(0, 0.08, (n, 12)), 0, 1
            )
            # Material remains categorical; do not jitter its numerical code.
            original[:, 11] = [r["unit"][11] for r in chosen]
            points = from_original(original, anchor)
            group_ids = [r["spec_hash"] for r in chosen]
        if family == "boundary":
            axes = rng.choice([i for i in range(len(AXES)) if i not in CATEGORIES], size=n)
            points[np.arange(n), axes] = rng.integers(2, size=n)
        points = canonical(points, CATEGORIES)
        output.extend(
            dict(unit=unit.tolist(), distribution=family, split=split, parent=parent)
            for unit, parent in zip(points, group_ids, strict=True)
        )
    rng.shuffle(output)
    return output


def simulate(job):
    model, sample = job
    start = time.monotonic()
    row = dict(
        sample, status="invalid_geometry", spec_hash=None, metrics=None, screening_attempts=0
    )
    try:
        anchor = DesignSpec.model_validate(model["anchor"])
        spec = decode(anchor, sample["unit"])
        row.update(spec_hash=digest(spec.model_dump(mode="json")), status="analysis_failed")
        row["screening_attempts"] = 1
        try:
            metrics = measure(spec, anchor, model["cad"])
        except RuntimeError as error:
            if str(error) != "Screen discharge incomplete":
                raise
            row["screening_attempts"] = 2
            row["extended_discharge"] = True
            metrics = extended_measure(spec, anchor, model["cad"])
        if not np.isfinite(targets(metrics)).all():
            raise ValueError("Nonfinite physical labels")
        row.update(status="completed", metrics=metrics)
    except (ValueError, RuntimeError) as exc:
        row["error"] = str(exc)
    row["elapsed_s"] = time.monotonic() - start
    return row


def run(training, advisors, output, *, counts=(8192, 2048, 2048), workers=3):
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    tr, ar = read(training / "report.json"), read(advisors / "report.json")
    if any(not r["source_unchanged"] or r["source_hash"] != source for r in (tr, ar)):
        raise ValueError("Physical source differs")
    paths = [
        Path(__file__),
        Path(__file__).with_name("search_joint_designs.py"),
        Path(__file__).with_name("search_surrogate.py"),
        Path(__file__).with_name("expanded_screening.py"),
    ]
    hashes = {p.name: sha(p) for p in paths}
    report = dict(
        schema="expanded-context-data-v1",
        source_hash=source,
        script_hashes=hashes,
        axes=AXES,
        categories=CATEGORIES,
        family_weights=dict(zip(FAMILIES, WEIGHTS, strict=True)),
        seed=SEED,
        split_counts=dict(zip(SPLITS, counts, strict=True)),
        anchors=[],
        training_report_sha256=sha(training / "report.json"),
        advisor_report_sha256=sha(advisors / "report.json"),
        physical_qualification=False,
        acceptance_performed=False,
        limitations=[
            "CAD-scaled volume and axial flight; no wind/attitude inference",
            "Fixed bottle envelopes and three assumed materials",
            "Rejected geometry/incomplete analyses are retained, never zero-filled",
            "Payload/context variations do not relax the original design requirement",
        ],
    )
    write_json(output / "plan.json", report)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i in range(3):
            model_path, data_path = advisors / f"model-{i}.json", training / f"examples-{i}.jsonl"
            if (
                sha(model_path) != ar["anchors"][i]["model_sha256"]
                or sha(data_path) != tr["anchors"][i]["examples_sha256"]
            ):
                raise ValueError("Changed advisor or historical data")
            model = read(model_path)
            historical = [
                r
                for r in map(json.loads, data_path.read_text(encoding="utf-8").splitlines())
                if r["split"] == "train"
            ]
            x = np.array([r["unit"] for r in historical])
            y = np.array([targets(r["metrics"]) for r in historical])
            error = np.abs(predict(model, x) - y)
            priorities = error[:, 0] / 0.2 + error[:, 1] / 0.03
            parents = []
            for split in SPLITS:
                indices = [
                    j
                    for j in np.argsort(-priorities)
                    if parent_split(historical[j]["spec_hash"]) == split
                ]
                parents.extend(historical[j] for j in indices[:128])
            samples = [
                s
                for j, (split, n) in enumerate(zip(SPLITS, counts, strict=True))
                for s in sample_rows(
                    n,
                    DesignSpec.model_validate(model["anchor"]),
                    parents,
                    seed=SEED + i * 1000 + j * 100,
                    split=split,
                )
            ]
            rows = []
            with (output / f"examples-{i}.jsonl").open("w", encoding="utf-8") as stream:
                context = {k: model[k] for k in ("anchor", "cad")}
                for row in pool.map(simulate, ((context, s) for s in samples), chunksize=4):
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    rows.append(row)
                    if len(rows) % 128 == 0:
                        stream.flush()
                        print(
                            json.dumps(
                                dict(
                                    anchor=i, examples=len(rows), elapsed_s=time.monotonic() - begin
                                )
                            ),
                            flush=True,
                        )
            complete = [r for r in rows if r["status"] == "completed"]
            sets = [
                {r["spec_hash"] for r in rows if r["split"] == split and r["spec_hash"]}
                for split in SPLITS
            ]
            overlaps = len(sets[0] & sets[1]) + len(sets[0] & sets[2]) + len(sets[1] & sets[2])
            entry = dict(
                anchor=i,
                anchor_spec=model["anchor"],
                cad=model["cad"],
                evaluated=len(rows),
                completed=len(complete),
                overlapping_designs=overlaps,
                examples_sha256=sha(output / f"examples-{i}.jsonl"),
                counts={s: sum(r["split"] == s for r in complete) for s in SPLITS},
                by_distribution={
                    f: {
                        s: sum(r["distribution"] == f and r["status"] == s for r in rows)
                        for s in ("completed", "invalid_geometry", "analysis_failed")
                    }
                    for f in FAMILIES
                },
                max_case_s=max(r["elapsed_s"] for r in rows),
                screening_attempts=sum(r["screening_attempts"] for r in rows),
                extended_discharge_cases=sum(r.get("extended_discharge", False) for r in rows),
            )
            report["anchors"].append(entry)
            write_json(output / "progress.json", report)
            print(
                json.dumps({k: v for k, v in entry.items() if k not in ("anchor_spec", "cad")}),
                flush=True,
            )
            if overlaps:
                raise ValueError("Cross-split duplicate designs; do not train")
    report.update(
        source_unchanged=code_hash() == source and hashes == {p.name: sha(p) for p in paths},
        elapsed_s=time.monotonic() - begin,
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Implementation changed during data collection")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("training", "advisors", "output"):
        p.add_argument(field, type=Path)
    p.add_argument("--train", type=int, default=8192)
    p.add_argument("--validation", type=int, default=2048)
    p.add_argument("--test", type=int, default=2048)
    p.add_argument("--workers", type=int, default=3)
    a = p.parse_args()
    if any(n < 8 or n % 8 for n in (a.train, a.validation, a.test)) or not 1 <= a.workers <= 4:
        p.error("Counts must be positive multiples of eight; workers 1–4")
    run(a.training, a.advisors, a.output, counts=(a.train, a.validation, a.test), workers=a.workers)
