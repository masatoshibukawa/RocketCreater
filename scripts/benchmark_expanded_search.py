"""Frozen, paired DE trials separating predictor quality from wider-domain coverage."""

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import AXES as ORIGINAL_AXES
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts import adaptive_evolution
from scripts.expanded_design_data import AXES, decode, from_original
from scripts.expanded_screening import measure
from scripts.expanded_surrogate import contract, core_coordinates, predict
from scripts.mixed_genetic import canonical
from scripts.search_surrogate import predict as expert_predict

METHODS = ("core-old", "core-broad", "wide-old", "wide-new")
SEEDS = (51893, 63841, 77933)
CATEGORIES = {11: 3}


def expanded_points(points, anchor, domain):
    x = np.asarray(points, float)
    if x.ndim != 2 or x.shape[1] != 12 or domain not in ("core", "wide"):
        raise ValueError("Twelve design coordinates and an explicit domain are required")
    expanded = from_original(x, anchor)
    if domain == "wide":
        expanded[:, :12] = x
    return expanded


def initial_population(count, seed, anchor, domain):
    points = qmc.LatinHypercube(12, seed=seed).random(count)
    if domain == "wide":
        # Half of each wide population starts in the known region; the rest spans new bounds.
        points[: count // 2] = from_original(points[: count // 2], anchor)[:, :12]
    return canonical(points, CATEGORIES)


def fixed_mission(spec, anchor):
    if (
        spec.requirement != anchor.requirement
        or spec.env != anchor.env
        or spec.design.payload_mass_kg != anchor.design.payload_mass_kg
        or spec.design.initial_gauge_pressure_pa != anchor.design.initial_gauge_pressure_pa
        or spec.other_dry_mass_g != anchor.other_dry_mass_g
        or spec.geometry.fin_count != anchor.geometry.fin_count
        or spec.assumptions.mount != anchor.assumptions.mount
        or spec.assumptions.solar_w_m2 != anchor.assumptions.solar_w_m2
        or spec.assumptions.warm_wait_s != anchor.assumptions.warm_wait_s
    ):
        raise ValueError("A candidate changed a fixed mission or context")


def make_advisor(bundle, anchor, method, counts):
    domain, variant = method.split("-")

    def rank(points):
        x = expanded_points(points, anchor, domain)
        original, supported = core_coordinates(x, anchor)
        counts["proposed"] += len(x)
        counts["old_supported"] += int(supported.sum())
        if variant == "old":
            # No extrapolation or clipping presented as valid advice. The DE implementation
            # selects randomly when all three proposals for an owner lack finite advice.
            values = np.full(len(x), np.nan)
            if supported.any():
                y = expert_predict(bundle["nominal_expert"], original[supported])
                values[supported] = 2000 * np.maximum(0, 1.12 - y[:, 1]) - y[:, 0]
        else:
            y = predict(bundle, x, hybrid=variant == "new")
            values = 2000 * np.maximum(0, 1.12 - y[:, 1]) - y[:, 0]
        # Geometry rejection applies equally to both advisors, without a simulator call.
        for i, unit in enumerate(x):
            try:
                decode(anchor, unit)
            except ValueError:
                values[i] = np.nan
        counts["finite_advice"] += int(np.isfinite(values).sum())
        return values

    return rank


def experiment(job):
    model_path, method, seed, index, population, generations, destination, source = job
    begin = time.monotonic()
    bundle = read(model_path)
    anchor = DesignSpec.model_validate(bundle["anchor"])
    domain = method.split("-")[0]
    initial = initial_population(population, seed + index, anchor, domain)
    rows, counts = [], dict(proposed=0, old_supported=0, finite_advice=0)
    if code_hash() != source:
        raise ValueError("Physics changed")
    with destination.open("w", encoding="utf-8") as log:

        def objective(unit):
            expanded = expanded_points(unit[None, :], anchor, domain)[0]
            row = dict(
                unit=expanded.tolist(),
                optimizer_unit=unit.tolist(),
                status="invalid_geometry",
                screening_attempts=0,
                spec_hash=None,
            )
            loss = 1e12
            try:
                spec = decode(anchor, expanded)
                fixed_mission(spec, anchor)
                row["spec"] = spec.model_dump(mode="json")
                row.update(
                    spec_hash=digest(row["spec"]), status="analysis_failed", screening_attempts=1
                )
                # Same equations and 60-second phase ceiling for every arm, without retries.
                m = measure(spec, anchor, bundle["cad"])
                if not np.isfinite(
                    [
                        m["static_margin_cal"],
                        m["scenario_height_m"][0],
                        m["conservative_beam_ratio"],
                    ]
                ).all():
                    raise ValueError("Nonfinite physical outcome")
                row.update(metrics=m, status="completed")
                loss = 2000 * max(0, 1.12 - m["static_margin_cal"]) - m["scenario_height_m"][0]
            except (ValueError, RuntimeError) as error:
                row["error"] = str(error)
            row["loss"] = loss
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            return loss

        fit = adaptive_evolution.minimize(
            objective,
            initial,
            generations=generations,
            seed=seed + 100000,
            method="de",
            categories=CATEGORIES,
            advisor=make_advisor(bundle, anchor, method, counts),
        )
    valid = [r for r in rows if r["status"] == "completed"]
    best = min(valid, key=lambda r: r["loss"], default=None)
    if code_hash() != source or len(rows) != population * (generations + 1):
        raise ValueError("Changed source or simulator-call budget")
    return dict(
        method=method,
        seed=seed,
        anchor=index,
        initial_sha256=digest(initial.tolist()),
        expanded_initial_sha256=digest(expanded_points(initial, anchor, domain).tolist()),
        evaluations=fit.nfev,
        expected_evaluations=population * (generations + 1),
        screening_attempts=sum(r["screening_attempts"] for r in rows),
        completed=len(valid),
        rejected=len(rows) - len(valid),
        unique_specs=len({r["spec_hash"] for r in valid}),
        best_loss=float(fit.fun),
        best=best,
        history=fit.history,
        predicted_candidates=fit.predicted_candidates,
        advice=counts,
        elapsed_s=time.monotonic() - begin,
        data_file=destination.name,
        data_sha256=sha(destination),
    )


def native_pass(row, precision):
    return bool(
        row["status"] == "completed"
        and row["temporal_pass"]
        and row["aero_domain_pass"]
        and row["metrics"]["static_margin_cal"] >= precision.minimum_static_margin_cal
        and row["metrics"]["incidence_deg"] <= precision.maximum_incidence_deg
    )


def validate_bundles(training, source):
    report = read(training / "report.json")
    if not report["source_unchanged"] or report["source_hash"] != source:
        raise ValueError("Incompatible training source")
    paths = []
    for entry in report["anchors"]:
        path = training / entry["model_file"]
        b = read(path)
        if (
            sha(path) != entry["model_sha256"]
            or b["source_hash"] != source
            or b["input_contract"] != contract(source)
            or not b["validation_enabled"]
            or not b["nominal_expert"]["validation_enabled"]
            or b["nominal_expert"]["anchor"] != b["anchor"]
            or b["nominal_expert"]["cad"] != b["cad"]
        ):
            raise ValueError("Changed or incompatible frozen bundle")
        anchor = DesignSpec.model_validate(b["anchor"])
        if anchor.design.payload_mass_kg != 0.06 or anchor.requirement.target_altitude_m != 30:
            raise ValueError("This experiment requires the original 60 g / 30 m mission")
        # Explicit identity control: released hybrid routing must preserve the old expert.
        x = from_original(initial_population(32, 18731, anchor, "core"), anchor)
        original, supported = core_coordinates(x, anchor)
        if not supported.all() or not np.array_equal(
            predict(b, x), expert_predict(b["nominal_expert"], original)
        ):
            raise ValueError("Nominal routing identity control failed")
        fixed_mission(decode(anchor, x[0]), anchor)
        paths.append(path)
    if len(paths) != 3:
        raise ValueError("Three frozen anchor bundles required")
    return report, paths


def run(training, output, *, population=48, generations=20, workers=3):
    source, begin = code_hash(), time.monotonic()
    tr, models = validate_bundles(training, source)
    output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__)] + [
        Path(__file__).with_name(name)
        for name in (
            "adaptive_evolution.py",
            "mixed_genetic.py",
            "expanded_surrogate.py",
            "expanded_design_data.py",
            "expanded_screening.py",
            "search_surrogate.py",
            "search_joint_designs.py",
        )
    ]
    hashes = {p.name: sha(p) for p in paths}
    model_hashes = {p.name: sha(p) for p in models}
    report = dict(
        source_hash=source,
        script_hashes=hashes,
        model_hashes=model_hashes,
        training_report_sha256=sha(training / "report.json"),
        methods=METHODS,
        seeds=SEEDS,
        population=population,
        generations=generations,
        workers=workers,
        axes_core=ORIGINAL_AXES,
        axes_wide=dict(list(AXES.items())[:12]),
        fixed_context=(
            "All eight context inputs fixed at each source anchor; 60 g, 400 kPa, four fins"
        ),
        pairing="core-old/core-broad and wide-old/wide-new; paired seed and initial population",
        prediction_factor=3,
        random_bypass_probability=0.3,
        discharge_phase_limit_s=60,
        retries=False,
        nominal_identity_control=True,
        training_cost_s=tr["elapsed_s"],
        promotion="One measured objective incumbent per method/anchor across the three seeds",
        detail_selection="Best native-screen-passing candidate per wide method by drag+10% height",
        physical_qualification=False,
        acceptance_performed=False,
        runs=[],
        results=[],
    )
    write_json(output / "plan.json", report)
    jobs = [
        (
            model,
            method,
            seed,
            index,
            population,
            generations,
            output / f"{method}-{seed}-{index}.jsonl",
            source,
        )
        for seed in SEEDS
        for index, model in enumerate(models)
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
                            "rejected",
                        )
                    }
                ),
                flush=True,
            )
    for domain in ("core", "wide"):
        for seed in SEEDS:
            for index in range(3):
                group = [
                    r
                    for r in report["runs"]
                    if r["method"].startswith(domain) and r["seed"] == seed and r["anchor"] == index
                ]
                if len(group) != 2 or len({r["expanded_initial_sha256"] for r in group}) != 1:
                    raise ValueError("Unmatched initial populations")
    promotions = []
    for method in METHODS:
        for index in range(3):
            group = [
                r
                for r in report["runs"]
                if r["method"] == method and r["anchor"] == index and r["best"] is not None
            ]
            winner = min(group, key=lambda r: r["best_loss"])
            label = f"{method}-{index}"
            promotions.append(
                (
                    label,
                    DesignSpec.model_validate(winner["best"]["spec"]),
                    output / label,
                    source,
                    Precision(),
                    240,
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
    report["detailed_candidates"] = {}
    for method in ("wide-old", "wide-new"):
        eligible = [
            r
            for r in report["results"]
            if r["label"].rsplit("-", 1)[0] == method and native_pass(r, Precision())
        ]
        if eligible:
            best = max(eligible, key=lambda r: r["drag_plus_10pct_height_m"])
            write_json(output / f"selected-{method}.json", best["spec"])
            report["detailed_candidates"][method] = best["label"]
    report.update(
        source_unchanged=code_hash() == source
        and hashes == {p.name: sha(p) for p in paths}
        and model_hashes == {p.name: sha(p) for p in models},
        elapsed_s=time.monotonic() - begin,
        matched_initial_populations=True,
        matched_evaluations=True,
    )
    write_json(output / "report.json", report)
    if not report["source_unchanged"]:
        raise ValueError("Experiment inputs changed")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("training", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--population", type=int, default=48)
    p.add_argument("--generations", type=int, default=20)
    p.add_argument("--workers", type=int, default=3)
    a = p.parse_args()
    if not 8 <= a.population <= 128 or not 1 <= a.generations <= 80 or not 1 <= a.workers <= 4:
        p.error("Use population 8–128, generations 1–80, workers 1–4")
    run(a.training, a.output, population=a.population, generations=a.generations, workers=a.workers)
