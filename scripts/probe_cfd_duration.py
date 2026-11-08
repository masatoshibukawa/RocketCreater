"""Escalate time averaging on one current-source candidate without changing its gates."""

import argparse
import subprocess
import time
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.aero_accuracy import relative_change
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read
from scripts.preview_coarse_flight import verify_folder


def run(parent, output):
    output.mkdir(parents=True, exist_ok=False)
    source, begin = code_hash(), time.monotonic()
    saved = read(parent / "result.json")
    if saved["status"] != "completed" or saved["source_hash"] != source:
        raise ValueError("Fresh current-source candidate required")
    verified = verify_folder(parent)
    assembly = read(parent / "geometry/data.json")["record"]["assembly"]
    precision = Precision()
    runtime = Runtime(
        cfd_enabled=True,
        cfd_cells_coarse=16,
        cfd_cells_fine=20,
        cfd_times=80,
        cfd_width=12.5,
        cfd_lattice_speed=0.05,
    )
    context = dict(
        spec=saved["spec"],
        precision=precision.model_dump(),
        runtime=runtime.model_dump(),
        artifacts={},
        timeout_s=7200,
    )
    jobs = [
        ("axial-80", 0, 80),
        ("ascent-80", 10, 80),
        ("ascent-320", 10, 320),
        ("ascent-800", 10, 800),
    ]
    hashes = {
        str(p): sha(p)
        for p in (
            Path(__file__),
            parent / "manifest.json",
            parent / "result.json",
            parent / "geometry/data.json",
        )
    }
    plan = dict(
        source_hash=source,
        inputs=hashes,
        context=context,
        jobs=jobs,
        verified_parent_files=verified,
        acceptance_performed=False,
        scope="Single-grid, single-speed diagnostics; never full-design acceptance",
    )
    write_json(output / "protocol.json", plan)
    write_json(output / "assembly.json", assembly)
    worker = Worker(context, output)
    results, previous = [], None
    for label, angle, duration in jobs:
        if code_hash() != source or any(sha(Path(k)) != v for k, v in hashes.items()):
            raise ValueError("Changed source/input during duration probe")
        row = dict(label=label, status="failed", angle_deg=angle, duration_D_U=duration)
        t = time.monotonic()
        try:
            case = worker.run_case(
                output / "assembly.json", output / label, 18, angle, 20, cfd_times=duration
            )
            averaging = max(
                abs(delta) / max(abs(case["mean"][key]), 0.05)
                for key, delta in case["split_window_difference"].items()
            )
            vector = [case["mean"][key] for key in ("Cx", "Cy", "Cm_z")]
            change = relative_change(previous, vector) if angle == 10 and previous else None
            row.update(
                status="completed",
                case=case,
                averaging=averaging,
                duration_change=change,
                point_time_checks_pass=(
                    angle == 10
                    and change is not None
                    and averaging <= precision.temporal_relative_limit
                    and change <= precision.temporal_relative_limit
                ),
            )
            if angle == 10:
                previous = vector
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            row["error"] = str(error)
        row["elapsed_s"] = time.monotonic() - t
        results.append(row)
        write_json(output / "progress.json", results)
        print({k: v for k, v in row.items() if k != "case"}, flush=True)
        if row["status"] == "failed" or row["point_time_checks_pass"]:
            break
    write_json(
        output / "report.json",
        dict(
            **plan,
            results=results,
            source_unchanged=source == code_hash(),
            elapsed_s=time.monotonic() - begin,
        ),
    )
    write_json(
        output / "manifest.json",
        {
            p.relative_to(output).as_posix(): sha(p)
            for p in output.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
