"""Independent, bounded native screening of initial airframes before adaptive search."""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis import flight_phases, seeds
from rocketwright.analysis.portfolio import rank, starts
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.runtime import run as run_process
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("geometry", "thermal", "propulsion", "screen", "refine")
CONTROLLED = (
    "water_fill_frac",
    "initial_gauge_pressure_pa",
    "nozzle_diameter_m",
    "payload_mass_kg",
    "has_parachute",
    "parachute_diameter_m",
    "axial_drag_coefficient",
)


def comparable_starts(template):
    """Fixed operating conditions; source variants are not independent validation samples."""
    result, aliases, seen = {}, {}, {}
    for label, spec in starts(template).items():
        data = spec.model_dump(mode="json")
        data["design"].update({k: getattr(template.design, k) for k in CONTROLLED})
        data["design"]["geometry"] = data["geometry"]
        # The saved mass belongs to its original printed geometry; every seed gets new CAD.
        data["measured_printed_mass_g"] = None
        s = DesignSpec.model_validate(data)
        physical = s.model_dump(exclude={"name"})
        physical["assumptions"].pop("evidence")
        # Dry mass is recomputed from the fresh CAD and other_dry_mass_g.
        physical["design"].pop("dry_mass_kg")
        key = digest(physical)
        if key in seen:
            aliases[label] = seen[key]
        else:
            seen[key], result[label] = label, s
    return result, aliases


def _case(job):
    label, spec, folder, source, precision, share, global_deadline = job
    start = time.monotonic()
    deadline = min(start + share, global_deadline)
    folder.mkdir(parents=True)
    artifacts, statuses = {}, []
    row = dict(label=label, spec=spec.model_dump(mode="json"), status="failed")
    write_json(folder / "spec.json", row["spec"])
    try:
        if code_hash() != source:
            raise RuntimeError("Source changed; results cannot be combined")
        env = dict(
            os.environ,
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            NUMEXPR_NUM_THREADS="1",
            PYTHONUTF8="1",
        )
        for method in METHODS:
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                raise RuntimeError("Initial screening time budget exhausted")
            destination = folder / method
            destination.mkdir()
            context = dict(
                spec=row["spec"],
                precision=precision.model_dump(),
                runtime=Runtime().model_dump(),
                artifacts=artifacts,
                timeout_s=remaining,
            )
            write_json(destination / "input.json", context)
            run_process(
                [
                    sys.executable,
                    "-m",
                    "rocketwright.analysis.worker",
                    str(destination / "input.json"),
                    str(destination / "data.json"),
                    method,
                ],
                cwd=ROOT,
                log=destination / "worker.log",
                timeout=remaining,
                env=env,
            )
            artifacts[method] = str(destination / "data.json")
            statuses.append(method)
        if code_hash() != source:
            raise RuntimeError("Source changed; results cannot be combined")
        geometry, refinement = read(artifacts["geometry"]), read(artifacts["refine"])
        a, fine = geometry["record"]["assembly"], refinement["fine"]
        row.update(
            status="completed",
            metrics=dict(
                apogee_m=fine["apogee_m"],
                incidence_deg=fine["ascent_incidence_deg"],
                static_margin_cal=(a["cp_mm"] - a["wet_cg_mm"]) / spec.geometry.body_diameter_mm,
                dry_mass_g=a["dry_mass_g"],
                cg_mm=a["wet_cg_mm"],
                cp_mm=a["cp_mm"],
            ),
            temporal_pass=refinement["metrics"]["temporal_pass"],
            time_step_difference_m=refinement["altitude_change_m"],
            drag_plus_10pct_height_m=refinement["sensitivity_flight"]["apogee_m"],
            aero_domain_pass=all(
                read(artifacts["screen"])["aero_domain_pass"] and f["aero_domain_pass"]
                for f in (fine, refinement["sensitivity_flight"])
            ),
            detailed_cfd_available=spec.geometry.fin_count == 4,
            phase_diagnostics=flight_phases.diagnose(a, fine),
        )
    except (OSError, ValueError, RuntimeError) as exc:
        row["error"] = str(exc)[-2000:]
    row.update(
        completed_methods=statuses,
        elapsed_s=time.monotonic() - start,
        source_hash=source,
        physical_qualification=False,
    )
    write_json(folder / "result.json", row)
    manifest = {
        p.relative_to(folder).as_posix(): sha(p)
        for p in folder.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    write_json(folder / "manifest.json", manifest)
    row["evidence"] = dict(directory=folder.name, manifest_sha256=sha(folder / "manifest.json"))
    return row


def run(template, root, *, workers=2, budget_s=1800, precision=None, emit=print):
    """A fixed candidate batch, no LLM calls, no learning updates, no design acceptance.

    Budget is divided before dispatch: parallelism never multiplies available solver time.
    Each worker has separate paths and a process-tree timeout. GPU CFD/FEM stay outside
    this batch. Results are merged in input order, independent of completion order.
    """
    if not 1 <= workers <= 4 or not 0 < budget_s <= 86400:
        raise ValueError("Use 1–4 workers and a positive budget up to 86400 s")
    if template.requirement is None:
        raise ValueError("An unchanged altitude requirement is required")
    precision = precision or Precision()
    candidates, aliases = comparable_starts(template)
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    jobs = [
        (
            label,
            spec,
            root / f"s{i:02}",
            source,
            precision,
            budget_s / len(candidates),
            begin + budget_s,
        )
        for i, (label, spec) in enumerate(candidates.items())
    ]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(_case, jobs):
            rows.append(row)
            emit(
                dict(
                    seed=row["label"],
                    status=row["status"],
                    elapsed_s=row["elapsed_s"],
                    metrics=row.get("metrics"),
                )
            )
            write_json(root / "progress.json", dict(source_hash=source, results=rows))
    unchanged = code_hash() == source
    valid = [
        r
        for r in rows
        if unchanged and r["status"] == "completed" and r["aero_domain_pass"] and r["temporal_pass"]
    ]
    target = template.requirement.target_altitude_m
    ranking = sorted(valid, key=lambda r: (rank(r, precision, target), r["label"]))
    for row in ranking:
        row["joint_violation"] = rank(row, precision, target)
    selected = ranking[0] if ranking else None
    ready = next((r for r in ranking if r["detailed_cfd_available"]), None)
    for name, row in (("selected", selected), ("selected-cfd-compatible", ready)):
        if row:
            write_json(root / f"{name}.json", row["spec"])
    report = dict(
        source_hash=source,
        source_unchanged=unchanged,
        workers=workers,
        budget_s=budget_s,
        elapsed_s=time.monotonic() - begin,
        charged_case_s=sum(r["elapsed_s"] for r in rows),
        requirement=template.requirement.model_dump(mode="json"),
        precision=precision.model_dump(),
        controlled_fields=list(CONTROLLED),
        aliases=aliases,
        candidate_count=len(rows),
        results=rows,
        ranked_ids=[r["label"] for r in ranking],
        selected=selected["label"] if selected else None,
        selected_cfd_compatible=ready["label"] if ready else None,
        registered_sources=seeds.catalog(),
        physical_qualification=False,
        acceptance_performed=False,
        scope="Provisional small-angle screening; fresh CAD and mass, thermal, discharge, "
        "6DOF, step-halving and drag sensitivity. No CFD/FEM or model validation. "
        "Variants of one source are correlated; source flight scores are not imported.",
    )
    write_json(root / "report.json", report)
    return report
