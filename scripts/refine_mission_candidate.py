"""Measured failure -> bounded thickness/fill/nozzle alternatives -> fresh CAD checks."""

import argparse
import copy
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read
from scripts.expanded_screening import measure
from scripts.preview_coarse_flight import verify_folder


def run(parent, output):
    output.mkdir(parents=True, exist_ok=False)
    source, start = code_hash(), time.monotonic()
    saved = read(parent / "summary.json")
    if saved["status"] != "completed" or saved["source_hash"] != source:
        raise ValueError("Completed current-source parent required")
    checked = verify_folder(parent)
    anchor = DesignSpec.model_validate(saved["spec"])
    if (
        anchor.design.initial_gauge_pressure_pa != 400000
        or anchor.design.payload_mass_kg != 0.04
        or anchor.requirement.target_altitude_m != 20
    ):
        raise ValueError("Fixed mission changed")
    cad = read(parent / "geometry/data.json")["cad_metrics"]
    hashes = {
        str(p): sha(p)
        for p in (
            Path(__file__),
            parent / "summary.json",
            parent / "manifest.json",
            Path("scripts/expanded_screening.py"),
        )
    }
    rows, selected = [], []
    for thickness in (2.2, 2.3, 2.4):
        group = []
        for fill in np.arange(0.22, 0.3001, 0.005):
            for nozzle in (18, 20, 22, 25, 32.817):
                data = copy.deepcopy(saved["spec"])
                data["geometry"]["fin_thickness_mm"] = thickness
                data["design"].update(
                    geometry=data["geometry"],
                    water_fill_frac=round(float(fill), 4),
                    nozzle_diameter_m=nozzle / 1000,
                )
                spec = DesignSpec.model_validate(data)
                metrics = measure(spec, anchor, cad)
                group.append(
                    dict(
                        spec=spec.model_dump(mode="json"),
                        metrics=metrics,
                        spec_sha256=digest(spec.model_dump(mode="json")),
                    )
                )
        # A 0.04-caliber screening reserve; final Precision's 1-caliber gate is unchanged.
        eligible = [r for r in group if r["metrics"]["static_margin_cal"] >= 1.04]
        if not eligible:
            raise ValueError("No static-margin-eligible refinement")
        # First retain the <=22 mm nozzle group; larger bores are measured sensitivity cases.
        eligible = [r for r in eligible if r["spec"]["design"]["nozzle_diameter_m"] <= 0.022]
        chosen = max(eligible, key=lambda r: r["metrics"]["scenario_height_m"][0])
        selected.append(dict(chosen, label=f"thickness-{thickness:g}"))
        rows.extend(group)
    write_json(
        output / "screen.json",
        dict(
            source_hash=source,
            inputs=hashes,
            verified_parent_files=checked,
            rows=rows,
            selected=selected,
            acceptance_performed=False,
        ),
    )
    jobs = [
        (
            r["label"],
            DesignSpec.model_validate(r["spec"]),
            output / r["label"],
            source,
            Precision(),
            300,
            time.monotonic() + 900,
        )
        for r in selected
    ]
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(_case, jobs):
            if row["status"] == "completed":
                folder = output / row["label"]
                destination = folder / "modal-probe"
                destination.mkdir()
                context = dict(
                    spec=row["spec"],
                    precision=Precision().model_dump(),
                    runtime=Runtime().model_dump(),
                    artifacts={m: str(folder / m / "data.json") for m in row["completed_methods"]},
                    timeout_s=60,
                )
                worker = Worker(context, destination)
                worker.setup()
                modes = worker.modes()
                write_json(destination / "data.json", modes)
                row["modal_probe"] = modes["metrics"]
                row["modal_probe_sha256"] = sha(destination / "data.json")
            results.append(row)
            write_json(output / "progress.json", results)
            print(
                dict(
                    label=row["label"],
                    status=row["status"],
                    metrics=row.get("metrics"),
                    modes=row.get("modal_probe"),
                ),
                flush=True,
            )
    unchanged = code_hash() == source and all(sha(Path(p)) == value for p, value in hashes.items())
    write_json(
        output / "report.json",
        dict(
            source_hash=source,
            source_unchanged=unchanged,
            inputs=hashes,
            results=results,
            screen_count=len(rows),
            elapsed_s=time.monotonic() - start,
            acceptance_performed=False,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
