"""Use computed 6DOF incidence/temperature for search loads; keep final FEM/CFD gates."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.screening import estimated_volumes
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read
from scripts.adaptive_evolution import minimize, reflect
from scripts.expanded_screening import measure
from scripts.preview_coarse_flight import verify_folder
from scripts.search_fixed_mission import CATEGORIES, candidate, encode

RESERVES = dict(height_m=20.5, static_margin_cal=1.02, beam_ratio=0.045, incidence_deg=14)


def evaluate(spec, cad, scratch, *, geometry_basis="CAD-scaled estimate"):
    worker = Worker(
        dict(
            spec=spec.model_dump(mode="json"),
            precision=Precision().model_dump(),
            runtime=Runtime().model_dump(),
            artifacts={},
            timeout_s=60,
        ),
        scratch,
    )
    worker.data["geometry"] = dict(cad_metrics=cad)
    worker.setup()
    worker.data["thermal"] = worker.thermal()
    worker.data["propulsion"] = worker.propulsion()
    worker.data["screen"] = worker.screen()
    modes = worker.modes()
    a = worker.assembly
    return dict(
        apogee_m=worker.data["screen"]["apogee_m"],
        incidence_deg=worker.data["screen"]["ascent_incidence_deg"],
        beam_ratio=modes["metrics"]["fin_deflection_ratio"],
        static_margin_cal=(a["cp_mm"] - a["wet_cg_mm"]) / spec.geometry.body_diameter_mm,
        dry_mass_g=a["dry_mass_g"],
        temperature_c=modes["temperature_c"],
        aero_domain_pass=worker.data["screen"]["aero_domain_pass"],
        load_scope=modes["load_scope"],
        geometry_basis=geometry_basis,
    )


def score(metrics):
    h, s, b, a = (
        metrics[k] for k in ("apogee_m", "static_margin_cal", "beam_ratio", "incidence_deg")
    )
    if not np.isfinite([h, s, b, a]).all():
        raise ValueError("Nonfinite flight screen")
    v = (
        max(0, (RESERVES["height_m"] - h) / RESERVES["height_m"])
        + max(0, (RESERVES["static_margin_cal"] - s) / RESERVES["static_margin_cal"])
        + max(0, (b - RESERVES["beam_ratio"]) / RESERVES["beam_ratio"])
        + max(0, (a - RESERVES["incidence_deg"]) / RESERVES["incidence_deg"])
        + (0 if metrics["aero_domain_pass"] else 1)
    )
    return 1 + v if v else -h / (h + 20)


def run(parent, output, *, population=28, generations=40):
    output.mkdir(parents=True, exist_ok=False)
    scratch = output / "scratch"
    scratch.mkdir()
    source, start = code_hash(), time.monotonic()
    saved = read(parent / "result.json")
    if saved["source_hash"] != source or saved["status"] != "completed":
        raise ValueError("Current-source native parent required")
    verified = verify_folder(parent)
    anchor = DesignSpec.model_validate(saved["spec"])
    if (
        anchor.design.axial_drag_coefficient != 1.4
        or anchor.design.initial_gauge_pressure_pa != 400000
        or anchor.design.payload_mass_kg != 0.04
        or anchor.requirement.target_altitude_m != 20
    ):
        raise ValueError("Expected fixed mission and explicit Cd=1.4 assumption")
    cad = read(parent / "geometry/data.json")["cad_metrics"]
    paths = [
        Path(__file__),
        parent / "result.json",
        parent / "manifest.json",
        Path("scripts/adaptive_evolution.py"),
        Path("scripts/search_fixed_mission.py"),
        Path("scripts/expanded_design_data.py"),
        Path("scripts/expanded_screening.py"),
    ]
    hashes = {str(p): sha(p) for p in paths}
    plan = dict(
        source_hash=source,
        inputs=hashes,
        verified_parent_files=verified,
        reserves=RESERVES,
        precision=Precision().model_dump(),
        population=population,
        generations=generations,
        scope="Assumed Cd=1.4; analytic-aero 6DOF and beam for search, not CFD/FEM acceptance",
        prefilter="Axial altitude >=18 m and analytic initial static margin >=0.8; heuristic only",
        acceptance_performed=False,
        physical_qualification=False,
    )
    write_json(output / "protocol.json", plan)
    baseline = evaluate(anchor, cad, scratch, geometry_basis="fresh CAD")
    write_json(output / "baseline.json", baseline)
    if not np.isclose(baseline["apogee_m"], read(parent / "screen/data.json")["apogee_m"]):
        raise ValueError("Full-flight evaluator does not reproduce native parent")
    print(dict(baseline=baseline), flush=True)
    rng = np.random.default_rng(1404020)
    initial = qmc.LatinHypercube(12, seed=1404020).random(population)
    initial[0] = encode(anchor)
    initial[1 : population // 2] = reflect(
        initial[0] + rng.normal(0, 0.035, (population // 2 - 1, 12))
    )
    rows, cache, best = [], {}, float("inf")
    with (output / "evaluations.jsonl").open("w", encoding="utf-8") as stream:

        def objective(unit):
            nonlocal best
            if time.monotonic() - start > 2400:
                raise TimeoutError("Flight-feedback search budget exhausted")
            row = dict(unit=unit.tolist(), status="invalid", loss=100.0)
            try:
                spec = candidate(anchor, unit)
                key = digest(spec.model_dump(mode="json"))
                if key in cache:
                    return cache[key]
                quick = measure(spec, anchor, cad)
                row.update(spec=spec.model_dump(mode="json"), spec_sha256=key, axial=quick)
                if quick["apogee_m"] < 18 or quick["static_margin_cal"] < 0.8:
                    row.update(
                        status="axial_only",
                        loss=2
                        + max(0, (20 - quick["apogee_m"]) / 20)
                        + max(0, 1 - quick["static_margin_cal"]),
                    )
                else:
                    metrics = evaluate(spec, estimated_volumes(spec, anchor, cad), scratch)
                    row.update(status="flight_completed", metrics=metrics, loss=score(metrics))
                cache[key] = row["loss"]
            except (ValueError, RuntimeError) as error:
                row["error"] = str(error)
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["status"] == "flight_completed" and row["loss"] < best:
                best = row["loss"]
                write_json(output / "best.json", row)
            if len(rows) % population == 0:
                stream.flush()
                print(
                    dict(
                        calls=len(rows),
                        full_flights=sum(r["status"] == "flight_completed" for r in rows),
                        best_loss=best,
                        elapsed_s=time.monotonic() - start,
                    ),
                    flush=True,
                )
            return row["loss"]

        search = minimize(
            objective,
            initial,
            generations=generations,
            seed=1404020,
            method="de",
            categories=CATEGORIES,
        )
    if source != code_hash() or any(sha(Path(k)) != v for k, v in hashes.items()):
        raise ValueError("Changed source/input")
    selected = min((r for r in rows if r["status"] == "flight_completed"), key=lambda r: r["loss"])
    native = _case(
        (
            "selected",
            DesignSpec.model_validate(selected["spec"]),
            output / "selected",
            source,
            Precision(),
            300,
            time.monotonic() + 600,
        )
    )
    if native["status"] == "completed":
        actual_cad = read(output / "selected/geometry/data.json")["cad_metrics"]
        native["beam_probe"] = evaluate(
            DesignSpec.model_validate(native["spec"]),
            actual_cad,
            scratch,
            geometry_basis="fresh CAD",
        )
    report = dict(
        **plan,
        baseline=baseline,
        selected=selected,
        result=native,
        calls=search.nfev,
        unique_attempts=len(rows),
        history=search.history,
        full_flights=sum(r["status"] == "flight_completed" for r in rows),
        source_unchanged=source == code_hash(),
        input_unchanged=all(sha(Path(k)) == v for k, v in hashes.items()),
        evaluations_sha256=sha(output / "evaluations.jsonl"),
        elapsed_s=time.monotonic() - start,
    )
    write_json(output / "report.json", report)
    print(
        dict(native=native["status"], metrics=native.get("metrics"), beam=native.get("beam_probe")),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
