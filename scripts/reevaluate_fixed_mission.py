"""Reevaluate sealed candidate pools at 400 kPa / 40 g / 20 m without redesign."""

import argparse
import copy
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.seed_survey import _case
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.expanded_screening import measure
from scripts.preview_coarse_flight import verify_folder

MISSION = dict(initial_gauge_pressure_pa=400000.0, payload_mass_kg=0.04, target_altitude_m=20.0)


def mission_spec(original):
    data = copy.deepcopy(original)
    data["design"].update({k: MISSION[k] for k in ("initial_gauge_pressure_pa", "payload_mass_kg")})
    data["requirement"].update(
        payload_mass_kg=MISSION["payload_mass_kg"], target_altitude_m=MISSION["target_altitude_m"]
    )
    return DesignSpec.model_validate(data)


def violation(metrics):
    return sum(
        (
            max(0, (20 - metrics["scenario_height_m"][0]) / 20),
            max(0, (1.12 - metrics["static_margin_cal"]) / 1.12),
            max(0, (metrics["conservative_beam_ratio"] - 0.05) / 0.05),
        )
    )


def run(parents, output):
    output.mkdir(parents=True, exist_ok=False)
    start, source = time.monotonic(), code_hash()
    scripts = [Path(__file__), Path(__file__).with_name("expanded_screening.py")]
    script_hashes = {p.name: sha(p) for p in scripts}
    inputs, rows, excluded, aliases, seen = {}, [], [], [], {}
    verified = 0
    for index, parent in enumerate(parents):
        report = read(parent / "report.json")
        if not report["source_unchanged"] or report["source_hash"] != source:
            raise ValueError("Pool source differs from current physics")
        inputs[parent.name] = sha(parent / "report.json")
        for case in report["results"]:
            folder = (parent / case["evidence"]["directory"]).resolve()
            if (
                not folder.is_relative_to(parent.resolve())
                or sha(folder / "manifest.json") != case["evidence"]["manifest_sha256"]
            ):
                raise ValueError("Candidate evidence changed")
            verified += verify_folder(folder)
            label = f"pool{index}-{case['label']}"
            if case["status"] != "completed":
                excluded.append(dict(label=label, reason="Parent native CAD/analysis incomplete"))
                continue
            spec = mission_spec(case["spec"])
            fingerprint = digest(spec.model_dump(mode="json"))
            if fingerprint in seen:
                aliases.append(dict(label=label, identical_to=seen[fingerprint]))
                continue
            seen[fingerprint] = label
            cad = read(folder / "geometry" / "data.json")["cad_metrics"]
            metrics = measure(spec, spec, cad)
            row = dict(
                label=label,
                anchor=int(case["label"].rsplit("-", 1)[1]),
                spec=spec.model_dump(mode="json"),
                spec_sha256=fingerprint,
                parent_manifest_sha256=case["evidence"]["manifest_sha256"],
                cad_data_sha256=sha(folder / "geometry" / "data.json"),
                metrics=metrics,
                violation=violation(metrics),
            )
            rows.append(row)
            write_json(output / "screen-progress.json", rows)
            print(dict(label=label, violation=row["violation"]), flush=True)
    selected = [
        min(
            (r for r in rows if r["anchor"] == anchor),
            key=lambda r: (r["violation"], -r["metrics"]["scenario_height_m"][0]),
        )
        for anchor in range(3)
    ]
    jobs = [
        (
            r["label"], DesignSpec.model_validate(r["spec"]), output / r["label"], source,
            Precision(), 240, time.monotonic() + 900,
        )
        for r in selected
    ]
    native = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(_case, jobs):
            native.append(row)
            write_json(output / "native-progress.json", native)
            print(dict(native=row["label"], status=row["status"]), flush=True)
    unchanged = (
        code_hash() == source
        and script_hashes == {p.name: sha(p) for p in scripts}
        and all(sha(p / "report.json") == inputs[p.name] for p in parents)
    )
    result = dict(
        source_hash=source, script_hashes=script_hashes, inputs=inputs, mission=MISSION,
        rows=rows, excluded=excluded, aliases=aliases, selected=[r["label"] for r in selected],
        native=native, parent_files_verified=verified, source_unchanged=unchanged,
        elapsed_s=time.monotonic() - start, redesign=False, physical_qualification=False,
        note="Sealed CAD used for screening; fresh CAD/analytic-aero 6DOF for three finalists",
    )
    write_json(output / "report.json", result)
    if not unchanged:
        raise ValueError("Source or inputs changed during evaluation")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("parents", type=Path, nargs="+")
    args = parser.parse_args()
    run(args.parents, args.output)
