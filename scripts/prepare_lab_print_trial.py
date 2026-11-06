"""Prepare verified PET v2 meshes for a laboratory fit trial; never start a printer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "3d model/prototypes/pet-rocket-coke-2l"
PARTS = (
    ("fit_ring.stl", "01-fit-ring.stl", 1, "fit_check"),
    ("mount_gauge.stl", "02-mount-gauge.stl", 1, "fit_check"),
    ("fin.stl", "03-fin-print-orientation.stl", 3, "after_fit_check"),
    ("nose_cone.stl", "04-nose-cone.stl", 1, "after_fit_check"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(output: Path) -> dict:
    report_path = SOURCE / "reports/geometry-verification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["valid"]:
        raise ValueError("The source geometry report did not pass")
    verified = {row["file"]: row for row in report["files"]}
    rows = []
    for source_name, target_name, final_count, stage in PARTS:
        source = SOURCE / "improved" / source_name
        row = verified[source_name]
        data = source.read_bytes()
        triangles = struct.unpack_from("<I", data, 80)[0]
        if not row["valid"] or sha256(source) != row["sha256"] or len(data) != 84 + 50 * triangles:
            raise ValueError(f"Verified binary STL changed: {source_name}")
        rows.append(
            {
                "source": source.relative_to(ROOT).as_posix(),
                "file": target_name,
                "sha256": row["sha256"],
                "dimensions_mm": row["dimensions_mm"],
                "triangles": triangles,
                "final_assembly_quantity": final_count,
                "first_trial_quantity": 1,
                "stage": stage,
            }
        )
    output.mkdir(parents=True, exist_ok=True)
    for row in rows:
        destination = output / row["file"]
        if destination.exists():
            if sha256(destination) != row["sha256"]:
                raise ValueError(f"Refusing to replace a different trial mesh: {destination.name}")
        else:
            shutil.copyfile(ROOT / row["source"], destination)
    manifest = {
        "case_id": "pet-coke-2l-v2",
        "trial_date": "2026-11-06",
        "requested_by": "2026-11-07",
        "units": "mm",
        "purpose": "Non-pressurized fit and shape trial; not a flight-qualified assembly",
        "state": "meshes_verified_waiting_for_slicing_and_printer_power",
        "geometry_report_sha256": sha256(report_path),
        "saved_profile_candidate": {
            "machine": "UltiMaker S5",
            "extruder": 0,
            "print_core": "AA 0.4",
            "material": "UltiMaker Black Tough PLA",
            "layer_height_mm": 0.2,
            "physical_configuration_verified": False,
        },
        "hardware": {
            "reachable": False,
            "power_and_network_verified": False,
            "plate_clear_verified": False,
            "material_remaining_verified": False,
            "print_started": False,
            "print_completed": False,
        },
        "bottle": {
            "diameter_assumption_mm": 110,
            "ring_inner_diameter_mm": 110.8,
            "fit_measured": False,
        },
        "parts": rows,
    }
    manifest_path = output / "mesh-manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise ValueError("Trial record changed; use a new output directory to preserve it")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log = output / "observations.csv"
    if not log.exists():
        with log.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "part",
                    "printed",
                    "actual_material",
                    "actual_mass_g",
                    "actual_time_min",
                    "fit_observation",
                    "defects",
                ]
            )
            writer.writerows([[row["file"], "not_started", "", "", "", "", ""] for row in rows])
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "output/print-trial-lab1")
    arguments = parser.parse_args()
    result = prepare(arguments.out)
    print(
        json.dumps(
            {
                "case_id": result["case_id"],
                "parts": len(result["parts"]),
                "print_started": result["hardware"]["print_started"],
            }
        )
    )
