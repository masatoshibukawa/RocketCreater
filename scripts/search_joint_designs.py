"""Joint variable search, fresh-CAD promotion, then explicit detailed-confirmation input."""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scipy.optimize import differential_evolution

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.design_space import AXES, decode, samples
from rocketwright.analysis.flight_phases import exploration_score
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.runtime import run as run_process
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.screening import estimated_volumes, evaluate
from rocketwright.analysis.seed_survey import _case, comparable_starts
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.tradeoff import environment, reconcile_payload
from rocketwright.analysis.worker import read, serial
from rocketwright.physics import fin_candidates
from scripts import adaptive_evolution, mixed_genetic

ROOT = Path(__file__).resolve().parents[1]


def score(metrics, target, profile="initial"):
    """Joint feasibility first, then conservative scenario height; never acceptance."""
    return exploration_score(metrics, target, profile)


def measure(spec, anchor, cad):
    volumes = estimated_volumes(spec, anchor, cad)
    result = evaluate(spec, volumes)
    record = compile_record(spec, volumes)
    a, g = record["assembly"], spec.geometry
    mat = record["config"]["fin_material"]
    force = result["max_q_pa"] * math.pi * (g.body_diameter_mm / 2000) ** 2
    force *= a["fin_set_CNalpha_per_rad"] * math.radians(15) / 2
    beam = fin_candidates.beam(
        g.fin_span_mm / 1000,
        g.fin_root_mm / 1000,
        g.fin_tip_mm / 1000,
        g.fin_thickness_mm / 1000,
        mat["young_pa"] * mat["warm_ratio"],
        mat["density"],
        record["config"]["fin_root_k_n_m"],
        force,
        tab=spec.assumptions.root_capture_mm / 1000,
    )
    result["conservative_beam_ratio"] = beam["max_deflection_m"] / (g.fin_span_mm / 1000)
    return serial(result)


def proposal(unit, anchor, cad, profile, seen=None):
    """A rejected genotype is evidence, not a fatal error or a passing design."""
    row = dict(unit=unit.tolist(), status="failed")
    loss = 1e12
    try:
        spec = decode(anchor, unit)
        row.update(
            spec=spec.model_dump(mode="json"), spec_hash=digest(spec.model_dump(mode="json"))
        )
        if seen is not None:
            if row["spec_hash"] in seen:
                return dict(row, status="duplicate"), loss
            seen.add(row["spec_hash"])
        m = measure(spec, anchor, cad)
        row.update(metrics=m, status="completed")
        key = "static_margin_cal" if profile == "initial" else "axial_free_margin_cal"
        margin = m[key]
        # Search headroom does not replace the final 1-caliber acceptance check.
        loss = 10000 if margin is None else 2000 * max(0, 1.12 - margin) - m["scenario_height_m"][0]
        if profile == "guided":
            loss += 2000 * max(0, m["conservative_beam_ratio"] - 0.045)
    except (ValueError, RuntimeError) as error:
        row["error"] = str(error)
    return row, loss


def run(
    template,
    root,
    *,
    count=192,
    rounds=3,
    promote=12,
    budget_s=3600,
    generations=0,
    profile="initial",
    optimizer="de",
    seed=7261,
):
    if optimizer not in {"de", "ga", "de-adaptive", "ga-adaptive"}:
        raise ValueError("Unknown evolutionary candidate generator")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    start, source, script_hash = time.monotonic(), code_hash(), sha(Path(__file__))

    def optimizer_digest():
        return digest(
            {
                module.__name__: sha(Path(module.__file__))
                for module in (mixed_genetic, adaptive_evolution)
            }
        )

    optimizer_hash = optimizer_digest()
    template, reconciliation = reconcile_payload(template)
    if template.design.initial_gauge_pressure_pa > 400000:
        raise ValueError("Use the existing pressure ceiling")
    precision = Precision()
    target = template.requirement.target_altitude_m
    all_starts, _ = comparable_starts(template)
    anchors = {k: all_starts[k] for k in ("provided", "independent-light", "reference/D40-2l")}
    write_json(root / "input.json", template.model_dump(mode="json"))
    pool = dict(
        axes=AXES,
        methods=[
            "Latin hypercube",
            "local-box refinement",
            "axial scenario screen",
            "fresh CAD and 6DOF",
        ],
        count_per_seed=count,
        rounds=rounds,
        promote=promote,
        seed=seed,
        budget_s=budget_s,
        workers=2,
        evolutionary_generations=generations,
        evolutionary_optimizer=optimizer,
        optimizer_sha256=optimizer_hash,
        evolutionary_population_size=6 * len(AXES),
        categorical_axes=["material_index"],
        promotion_policy="Best measured evolutionary loss per anchor, then joint feasibility",
        fin_count_search_enabled=False,
        exploration_profile=profile,
        guided_profile_is_diagnostic_only=True,
        reconciliation=reconciliation,
        pressure_cap_pa=400000,
        requirement=template.requirement.model_dump(mode="json"),
        unchanged_acceptance=precision.model_dump(),
        limitations=[
            "Isotropic material scenarios",
            "Mass-station packaging unverified",
            "Fixed analytic Cd in exploration",
        ],
    )
    write_json(root / "pool.json", pool)
    cad = {}
    for i, (label, spec) in enumerate(anchors.items()):
        folder = root / f"g{i}"
        folder.mkdir()
        context = dict(
            spec=spec.model_dump(mode="json"),
            precision=precision.model_dump(),
            runtime=Runtime().model_dump(),
            artifacts={},
            timeout_s=120,
        )
        write_json(folder / "input.json", context)
        run_process(
            [
                sys.executable,
                "-m",
                "rocketwright.analysis.worker",
                str(folder / "input.json"),
                str(folder / "data.json"),
                "geometry",
            ],
            cwd=ROOT,
            log=folder / "worker.log",
            timeout=120,
            env=environment(),
        )
        cad[label] = read(folder / "data.json")["cad_metrics"]
    rows, seen, winners = [], set(), []
    for round_no in range(rounds):
        for i, (label, anchor) in enumerate(anchors.items()):
            prior = sorted(
                [r for r in rows if r.get("seed") == label and r["status"] == "completed"],
                key=lambda r: score(r["metrics"], target, profile),
            )
            # Retain global coverage while refining four independent promising neighborhoods.
            batches = [(None, count if round_no == 0 else count // 4, 1.0)]
            if round_no:
                batches += [(r["unit"], count // 4, 0.20 / round_no) for r in prior[:3]]
            for j, (center, n, radius) in enumerate(batches):
                for unit in samples(
                    n, seed + 1000 * round_no + 50 * i + j, center=center, radius=radius
                ):
                    if time.monotonic() - start > budget_s * 0.45:
                        break
                    row, _ = proposal(unit, anchor, cad[label], profile, seen)
                    if row["status"] == "duplicate":
                        continue
                    row.update(
                        id=f"q{len(rows):04d}",
                        seed=label,
                        round=round_no,
                    )
                    rows.append(row)
            print(
                json.dumps(
                    dict(
                        round=round_no,
                        seed=label,
                        samples=len(rows),
                        best=min(
                            (r["metrics"] for r in rows if r["status"] == "completed"),
                            key=lambda m: score(m, target, profile),
                            default=None,
                        ),
                    )
                ),
                flush=True,
            )
            write_json(
                root / "exploration.json",
                dict(source_hash=source, script_sha256=script_hash, pool=pool, results=rows),
            )
    if generations:
        for i, (label, anchor) in enumerate(anchors.items()):

            def objective(unit, label=label, anchor=anchor):
                if time.monotonic() - start > budget_s * 0.65:
                    raise TimeoutError("Exploration budget reserved for native promotion")
                row, value = proposal(unit, anchor, cad[label], profile)
                row.update(
                    id=f"q{len(rows):04d}",
                    seed=label,
                    round="evolution",
                    optimizer_loss=value,
                )
                rows.append(row)
                if len(rows) % 144 == 0:
                    completed = [r for r in rows if r["status"] == "completed"]
                    best = (
                        min(completed, key=lambda r: score(r["metrics"], target, profile))
                        if completed
                        else None
                    )
                    progress = dict(
                        evolution=label,
                        evaluations=len(rows),
                        best=best["metrics"] if best else None,
                    )
                    write_json(root / "evolution-progress.json", progress)
                    print(json.dumps(progress), flush=True)
                return value

            try:
                category = {list(AXES).index("material_index"): int(AXES["material_index"][1])}
                initial = mixed_genetic.canonical(
                    samples(6 * len(AXES), seed + 100000 + i), category
                )
                write_json(root / f"population-{i}.json", dict(seed=label, points=initial.tolist()))
                if optimizer.endswith("-adaptive"):
                    fit = adaptive_evolution.minimize(
                        objective,
                        initial,
                        generations=generations,
                        seed=seed + 200000 + i,
                        categories=category,
                        method=optimizer.split("-")[0],
                    )
                elif optimizer == "ga":
                    fit = mixed_genetic.minimize(
                        objective,
                        initial,
                        generations=generations,
                        seed=seed + 200000 + i,
                        categories=category,
                    )
                else:
                    fit = differential_evolution(
                        objective,
                        [(0, 1)] * len(AXES),
                        seed=seed + 200000 + i,
                        maxiter=generations,
                        init=initial,
                        polish=False,
                        tol=0,
                        atol=0,
                    )
                write_json(
                    root / f"optimizer-{i}.json",
                    dict(
                        method=optimizer,
                        seed=label,
                        evaluations=int(fit.nfev),
                        loss=float(fit.fun),
                        initial_sha256=sha(root / f"population-{i}.json"),
                        history=getattr(fit, "history", None),
                    ),
                )
                measured = [
                    r
                    for r in rows
                    if r.get("seed") == label
                    and r.get("round") == "evolution"
                    and r["status"] == "completed"
                ]
                if measured:
                    winners.append(min(measured, key=lambda r: r["optimizer_loss"]))
                print(
                    json.dumps(
                        dict(evolution=label, loss=float(fit.fun), evaluations=int(fit.nfev))
                    ),
                    flush=True,
                )
            except TimeoutError as error:
                print(json.dumps(dict(evolution=label, error=str(error))), flush=True)
            write_json(
                root / "exploration.json",
                dict(source_hash=source, script_sha256=script_hash, pool=pool, results=rows),
            )
    if (
        code_hash() != source
        or sha(Path(__file__)) != script_hash
        or optimizer_digest() != optimizer_hash
    ):
        raise ValueError("Source changed during search")
    viable = sorted(
        [r for r in rows if r["status"] == "completed"],
        key=lambda r: score(r["metrics"], target, profile),
    )
    # Three distinct geometry/material families get representation; rest follow joint feasibility.
    chosen = list(winners)
    for label in anchors:
        if len(chosen) >= promote or any(r["seed"] == label for r in chosen):
            continue
        group = [r for r in viable if r["seed"] == label]
        if group:
            chosen.append(group[0])
    # Distinct finite proposals only; repeated optimizer evaluations are not independent designs.
    chosen_hashes = {r["spec_hash"] for r in chosen}
    for row in viable:
        if len(chosen) >= promote:
            break
        if row["spec_hash"] not in chosen_hashes:
            chosen.append(row)
            chosen_hashes.add(row["spec_hash"])
    available = budget_s - (time.monotonic() - start)
    share = min(180, available / max(len(chosen), 1))
    jobs = [
        (
            r["id"],
            DesignSpec.model_validate(r["spec"]),
            root / f"n{i:02d}",
            source,
            precision,
            share,
            start + budget_s,
        )
        for i, r in enumerate(chosen)
    ]
    native = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        for row in executor.map(_case, jobs):
            native.append(row)
            print(
                json.dumps(
                    dict(promoted=row["label"], status=row["status"], metrics=row.get("metrics"))
                ),
                flush=True,
            )
            write_json(root / "native-progress.json", native)
    eligible = [
        r
        for r in native
        if r["status"] == "completed"
        and r["temporal_pass"]
        and r["aero_domain_pass"]
        and r["metrics"]["static_margin_cal"] >= precision.minimum_static_margin_cal
        and r["metrics"]["incidence_deg"] <= precision.maximum_incidence_deg
    ]
    eligible.sort(key=lambda r: r["drag_plus_10pct_height_m"], reverse=True)
    if eligible:
        write_json(root / "selected.json", eligible[0]["spec"])
    guided = sorted(
        [
            r
            for r in native
            if r["status"] == "completed"
            and r["temporal_pass"]
            and r["aero_domain_pass"]
            and r["phase_diagnostics"]["free_ascent_min_margin_cal"]
            >= precision.minimum_static_margin_cal
            and r["metrics"]["incidence_deg"] <= precision.maximum_incidence_deg
        ],
        key=lambda r: r["drag_plus_10pct_height_m"],
        reverse=True,
    )
    if guided:
        write_json(root / "selected-guided-diagnostic.json", guided[0]["spec"])
    report = dict(
        source_hash=source,
        script_sha256=script_hash,
        source_unchanged=(
            code_hash() == source
            and sha(Path(__file__)) == script_hash
            and optimizer_digest() == optimizer_hash
        ),
        pool=pool,
        sampled=len(rows),
        failed=sum(r["status"] != "completed" for r in rows),
        elapsed_s=time.monotonic() - start,
        results=native,
        selected=eligible[0]["label"] if eligible else None,
        screening_feasible=sum(r["metrics"]["apogee_m"] >= target for r in eligible),
        guided_diagnostic_selected=guided[0]["label"] if guided else None,
        guided_diagnostic_height_pass=sum(r["metrics"]["apogee_m"] >= target for r in guided),
        physical_qualification=False,
        acceptance_performed=False,
    )
    write_json(root / "report.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--count", type=int, default=192)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--promote", type=int, default=12)
    p.add_argument("--budget", type=float, default=3600)
    p.add_argument("--evolve-generations", type=int, default=0)
    p.add_argument("--profile", choices=("initial", "guided"), default="initial")
    p.add_argument("--optimizer", choices=("de", "ga", "de-adaptive", "ga-adaptive"), default="de")
    p.add_argument("--seed", type=int, default=7261)
    a = p.parse_args()
    if (
        not 8 <= a.count <= 512
        or not 1 <= a.rounds <= 5
        or not 3 <= a.promote <= 24
        or not 300 <= a.budget <= 86400
        or not 0 <= a.evolve_generations <= 80
    ):
        p.error("Use 8–512 samples, 1–5 rounds, 3–24 promotions and 300–86400 seconds")
    run(
        DesignSpec.model_validate(read(a.input)),
        a.output,
        count=a.count,
        rounds=a.rounds,
        promote=a.promote,
        budget_s=a.budget,
        generations=a.evolve_generations,
        profile=a.profile,
        optimizer=a.optimizer,
        seed=a.seed,
    )
