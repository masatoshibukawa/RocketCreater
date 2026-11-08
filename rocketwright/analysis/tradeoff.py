"""Bounded temperature/load/pressure experiments; never an aircraft acceptance gate."""

import argparse
import itertools
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.runtime import run as run_process
from rocketwright.analysis.schema import Precision, Strict
from rocketwright.analysis.seed_survey import comparable_starts
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read, serial
from rocketwright.physics.atmosphere import state_scalar

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("thermal", "propulsion", "screen", "refine")


class Study(Strict):
    seeds: tuple[str, ...] = ("provided", "independent-light", "reference/D40-2l")
    temperatures_c: tuple[Annotated[float, Field(ge=-10, le=45)], ...] = (5, 20, 35)
    payloads_g: tuple[Annotated[float, Field(gt=0, le=200)], ...] = (30, 60, 90)
    pressures_kpa: tuple[Annotated[float, Field(gt=0, le=400)], ...] = (200, 300, 400)
    workers: int = Field(default=2, ge=1, le=4)
    budget_s: float = Field(default=3600, ge=300, le=86400)
    refinement_rounds: int = Field(default=2, ge=0, le=4)
    max_refined_cases: int = Field(default=18, ge=0, le=60)
    pressure_resolution_kpa: float = Field(default=25, gt=0, le=100)

    @model_validator(mode="after")
    def finite_unique_grid(self):
        for axis in (self.seeds, self.temperatures_c, self.payloads_g, self.pressures_kpa):
            if not axis or len(set(axis)) != len(axis):
                raise ValueError("Study axes must be nonempty and unique")
        if (
            math.prod(
                map(len, (self.seeds, self.temperatures_c, self.payloads_g, self.pressures_kpa))
            )
            > 200
        ):
            raise ValueError("At most 200 initial cases")
        return self


def reconcile_payload(spec):
    """Explicit migration for this experiment; keep historical input files unchanged."""
    if not spec.requirement or spec.requirement.target_altitude_m <= 0:
        raise ValueError("A positive altitude requirement is required")
    wanted, carried = spec.requirement.payload_mass_kg, spec.design.payload_mass_kg
    if wanted != carried and wanted != 0:
        raise ValueError("Nonzero payload requirement conflicts with the loaded payload")
    data = spec.model_dump(mode="json")
    data["requirement"]["payload_mass_kg"] = carried
    return DesignSpec.model_validate(data), dict(
        field="requirement.payload_mass_kg",
        before=wanted,
        after=carried,
        changed=wanted != carried,
        original_input_preserved=True,
        reason="Explicit study migration from legacy zero default to the known loaded payload",
    )


def case_spec(base, temperature_c, payload_g, pressure_kpa):
    data = base.model_dump(mode="json")
    standard_k, _, _ = state_scalar(base.env.launch_altitude_m, 0)
    data["env"]["temperature_offset_k"] = temperature_c + 273.15 - standard_k
    data["design"].update(
        payload_mass_kg=payload_g / 1000, initial_gauge_pressure_pa=pressure_kpa * 1000
    )
    # Each load experiment is internally consistent. The original 60 g mission stays
    # separately bound in the study report and is never replaced by a lighter-load pass.
    data["requirement"]["payload_mass_kg"] = payload_g / 1000
    return DesignSpec.model_validate(data)


def environment():
    return dict(
        os.environ,
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
        PYTHONUTF8="1",
    )


def seal(folder):
    write_json(
        folder / "manifest.json",
        {
            p.relative_to(folder).as_posix(): sha(p)
            for p in folder.rglob("*")
            if p.is_file() and p.name not in {"manifest.json", "worker.log"}
        },
    )
    return dict(directory=folder.name, manifest_sha256=sha(folder / "manifest.json"))


def check_geometry(evidence, geometry, source):
    path = Path(evidence["artifact"])
    if evidence["key"] != digest(dict(geometry=geometry, source=source)):
        raise ValueError("CAD geometry/source key mismatch")
    if (
        sha(path) != evidence["sha256"]
        or sha(path.parent / "manifest.json") != evidence["manifest_sha256"]
    ):
        raise ValueError("CAD evidence changed")
    for name, expected in read(path.parent / "manifest.json").items():
        p = (path.parent / name).resolve()
        if not p.is_relative_to(path.parent.resolve()) or sha(p) != expected:
            raise ValueError("CAD artifact changed: " + name)


def case_worker(context, folder):
    """One externally timed process, four host methods; shared CAD is read-only."""
    spec = DesignSpec.model_validate(context["spec"])
    if spec.requirement.payload_mass_kg != spec.design.payload_mass_kg:
        raise ValueError("Case payload contract mismatch")
    if code_hash() != context["source_hash"]:
        raise ValueError("Source changed before case execution")
    check_geometry(context["geometry_evidence"], spec.geometry.model_dump(), context["source_hash"])
    artifacts = {"geometry": context["geometry_evidence"]["artifact"]}
    results = {}
    for method in METHODS:
        destination = folder / method
        destination.mkdir()
        ctx = dict(context, artifacts=dict(artifacts))
        write_json(destination / "input.json", ctx)
        results[method] = serial(Worker(ctx, destination).run(method))
        write_json(destination / "data.json", results[method])
        artifacts[method] = str(destination / "data.json")
    if code_hash() != context["source_hash"]:
        raise ValueError("Source changed during case execution")
    record = read(folder / "refine/record.json")
    a, cfg = record["assembly"], record["config"]
    thermal, propulsion, coarse, refined = (results[k] for k in METHODS)
    flight = refined["fine"]
    p = Precision.model_validate(context["precision"])
    static = (a["cp_mm"] - a["wet_cg_mm"]) / spec.geometry.body_diameter_mm
    peak_pa = max(thermal["peak_absolute_pressure_pa"], max(propulsion["trace"]["pressure_pa"]))
    checks = dict(
        altitude=flight["apogee_m"] >= spec.requirement.target_altitude_m,
        static_margin=static >= p.minimum_static_margin_cal,
        attitude=flight["ascent_incidence_deg"] <= p.maximum_incidence_deg,
        temporal=refined["metrics"]["temporal_pass"],
        aero_domain=all(
            f["aero_domain_pass"] for f in (coarse, flight, refined["sensitivity_flight"])
        ),
        thermal_balance=thermal["metrics"]["thermal_balance"],
        propulsion_balance=propulsion["metrics"]["propulsion_balance"],
    )
    return dict(
        status="completed",
        checks=checks,
        screening_pass=all(checks.values()),
        metrics=dict(
            apogee_m=flight["apogee_m"],
            static_margin_cal=static,
            incidence_deg=flight["ascent_incidence_deg"],
            dry_mass_g=a["dry_mass_g"],
            cg_mm=a["wet_cg_mm"],
            cp_mm=a["cp_mm"],
            peak_gauge_kpa=(peak_pa - cfg["loads"]["ambient_pa"]) / 1000,
            launch_gauge_kpa=(
                thermal["trace"]["absolute_pressure_pa"][-1] - cfg["loads"]["ambient_pa"]
            )
            / 1000,
            gas_final_c=thermal["final_c"]["gas"],
            fin_final_c=thermal["final_c"]["fin"],
            air_density_kg_m3=cfg["flight"]["air_density_kg_m3"],
            time_step_difference_m=refined["altitude_change_m"],
            drag_plus_10pct_height_m=refined["sensitivity_flight"]["apogee_m"],
            impulse_ns=propulsion["impulse_ns"],
            peak_thrust_n=propulsion["peak_thrust_n"],
        ),
        pressure_qualification=None,
        physical_qualification=False,
        acceptance_performed=False,
    )


def boundary_choices(rows, target, resolution):
    """Refine observed height crossings, not a claimed monotone/physical safety boundary."""
    groups, seen = {}, set()
    for r in rows:
        x = r["condition"]
        key = (x["seed"], x["temperature_c"], x["payload_g"])
        seen.add((*key, x["pressure_kpa"]))
        if r["status"] == "completed" and all(
            r["checks"][k]
            for k in ("aero_domain", "temporal", "thermal_balance", "propulsion_balance")
        ):
            groups.setdefault(key, []).append(r)
    result = []
    for key, group in sorted(groups.items()):
        group.sort(key=lambda r: r["condition"]["pressure_kpa"])
        for low, high in zip(group, group[1:], strict=False):
            p0, p1 = (r["condition"]["pressure_kpa"] for r in (low, high))
            midpoint = (p0 + p1) / 2
            if p1 - p0 <= resolution or (*key, midpoint) in seen:
                continue
            if (low["metrics"]["apogee_m"] - target) * (high["metrics"]["apogee_m"] - target) < 0:
                result.append(
                    dict(
                        condition=dict(
                            seed=key[0],
                            temperature_c=key[1],
                            payload_g=key[2],
                            pressure_kpa=midpoint,
                        ),
                        parents=[low["id"], high["id"]],
                        reason="Measured screening altitude crosses the target",
                    )
                )
    return result


def run(template, root, *, study=None, precision=None, emit=print):
    study, precision = study or Study(), precision or Precision()
    base, reconciliation = reconcile_payload(template)
    mission_payload_g = base.design.payload_mass_kg * 1000
    if mission_payload_g not in study.payloads_g:
        raise ValueError("The original payload must be included in the study")
    pool, _ = comparable_starts(base)
    if any(k not in pool for k in study.seeds):
        raise ValueError("Select registered, nonduplicate starts")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    source, begin = code_hash(), time.monotonic()
    deadline = begin + study.budget_s
    write_json(root / "input-original.json", template.model_dump(mode="json"))
    write_json(root / "input-reconciled.json", base.model_dump(mode="json"))
    geometry, geometry_spent = {}, 0.0
    geometry_share = min(120, study.budget_s * 0.1 / len(study.seeds))
    for i, label in enumerate(study.seeds):
        folder = root / f"g{i}"
        folder.mkdir()
        context = dict(
            spec=pool[label].model_dump(mode="json"),
            precision=precision.model_dump(),
            runtime=Runtime().model_dump(),
            artifacts={},
            timeout_s=geometry_share,
        )
        write_json(folder / "input.json", context)
        t = time.monotonic()
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
            timeout=min(geometry_share, deadline - time.monotonic()),
            env=environment(),
        )
        geometry_spent += time.monotonic() - t
        geometry[label] = dict(
            artifact=str(folder / "data.json"),
            sha256=sha(folder / "data.json"),
            manifest_sha256=sha(folder / "manifest.json"),
            key=digest(dict(geometry=pool[label].geometry.model_dump(), source=source)),
        )
        emit(dict(geometry=label, status="completed"))
    coordinates = [
        dict(seed=s, temperature_c=t, payload_g=m, pressure_kpa=p)
        for s, t, m, p in itertools.product(
            study.seeds, study.temperatures_c, study.payloads_g, study.pressures_kpa
        )
    ]
    share = (study.budget_s - geometry_share * len(study.seeds)) / (
        len(coordinates) + study.max_refined_cases
    )
    rows = []

    def execute(job):
        index, proposal, phase = job
        condition = proposal["condition"]
        spec = case_spec(
            pool[condition["seed"]],
            condition["temperature_c"],
            condition["payload_g"],
            condition["pressure_kpa"],
        )
        folder = root / f"c{index:03}"
        folder.mkdir()
        remaining = min(share, deadline - time.monotonic())
        context = dict(
            spec=spec.model_dump(mode="json"),
            precision=precision.model_dump(),
            runtime=Runtime().model_dump(),
            timeout_s=remaining,
            source_hash=source,
            geometry_evidence=geometry[condition["seed"]],
        )
        write_json(folder / "input.json", context)
        t = time.monotonic()
        try:
            if remaining <= 1 or code_hash() != source:
                raise RuntimeError("Source changed or time budget exhausted")
            run_process(
                [
                    sys.executable,
                    "-m",
                    "rocketwright.analysis.tradeoff",
                    str(folder / "input.json"),
                    str(folder),
                ],
                cwd=ROOT,
                log=folder / "worker.log",
                timeout=remaining,
                env=environment(),
            )
            result = read(folder / "calculation.json")
        except (OSError, ValueError, RuntimeError) as exc:
            result = dict(status="failed", error=str(exc)[-1500:], screening_pass=False)
        result.update(
            id=folder.name,
            condition=condition,
            phase=phase,
            parents=proposal.get("parents", []),
            selection_reason=proposal.get("reason"),
            matches_original_payload=condition["payload_g"] == mission_payload_g,
            elapsed_s=time.monotonic() - t,
            allocated_s=share,
            source_hash=source,
            pressure_qualification=None,
            physical_qualification=False,
            acceptance_performed=False,
        )
        write_json(folder / "result.json", result)
        result["evidence"] = seal(folder)
        return result

    def batch(proposals, phase):
        offset = len(rows)
        with ThreadPoolExecutor(max_workers=study.workers) as executor:
            for row in executor.map(
                execute, [(offset + i, p, phase) for i, p in enumerate(proposals)]
            ):
                rows.append(row)
                emit({k: row[k] for k in ("id", "condition", "status", "phase", "elapsed_s")})
                write_json(root / "progress.json", dict(source_hash=source, results=rows))

    batch([dict(condition=c) for c in coordinates], "initial")
    refined = 0
    for round_id in range(study.refinement_rounds):
        if code_hash() != source:
            break
        choices = boundary_choices(
            rows, base.requirement.target_altitude_m, study.pressure_resolution_kpa
        )
        # Prefer the actual mission; do not spend the whole reserve on lighter loads.
        choices.sort(
            key=lambda r: (
                r["condition"]["payload_g"] != mission_payload_g,
                r["condition"]["seed"],
                r["condition"]["temperature_c"],
            )
        )
        chosen = choices[: study.max_refined_cases - refined]
        if not chosen:
            break
        batch(chosen, f"height-boundary-{round_id + 1}")
        refined += len(chosen)
    report = dict(
        source_hash=source,
        source_unchanged=code_hash() == source,
        study=study.model_dump(),
        precision=precision.model_dump(),
        baseline_requirement=base.requirement.model_dump(mode="json"),
        reconciliation=reconciliation,
        geometry=geometry,
        geometry_spent_s=geometry_spent,
        results=rows,
        initial_case_count=len(coordinates),
        refined_case_count=refined,
        elapsed_s=time.monotonic() - begin,
        charged_case_s=geometry_spent + sum(r["elapsed_s"] for r in rows),
        unrefined_crossings=boundary_choices(
            rows, base.requirement.target_altitude_m, study.pressure_resolution_kpa
        ),
        pressure_qualification=None,
        physical_qualification=False,
        acceptance_performed=False,
        scope="Conditional small-angle/6DOF study with shared verified CAD volumes; "
        "temperature-specific initial filling then sealed solar waiting. No certified "
        "pressure limit, CFD/FEM validation, or continuous-domain robustness proof.",
    )
    write_json(root / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    write_json(args.folder / "calculation.json", case_worker(read(args.input), args.folder))
