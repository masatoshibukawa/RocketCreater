"""Fit a shared CFD domain to both fixed finalists before spending GPU work."""

import argparse
import math
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.worker import read


def transverse_envelope(assembly):
    """Maximum of a*|sin(angle)| + b*|cos(angle)| over all in-plane angles."""
    dims = assembly["dimensions_mm"]
    diameter, cg = dims["body_diameter"], assembly["loaded_cg_mm"]
    if diameter <= 0 or not 0 <= cg <= dims["overall"]:
        raise ValueError("Positive diameter and an internal rotation center required")
    a = max(cg, dims["overall"] - cg) / diameter
    b = 0.5 + (dims["fin_span"] + dims.get("fin_root_offset", 0)) / diameter
    return math.hypot(a, b)


def select_runtime(runtime, assemblies):
    if len(assemblies) != 2:
        raise ValueError("Two fixed finalists are required")
    envelopes = [transverse_envelope(a) for a in assemblies]
    # Match run_flow.py's 0.75-D wall clearance. Round up in 0.5-D increments and leave
    # room for the independent +2-D domain audit (run_flow permits up to 16 D).
    required = 2 * (max(envelopes) + 0.75)
    width = max(runtime.cfd_width, math.ceil(required * 2) / 2)
    levels = (runtime.cfd_cells_coarse, runtime.cfd_cells_fine, runtime.cfd_cells_fine + 4)
    while min(2 * round(width * cells / 2) / cells for cells in levels) < required:
        width += 0.5
    if width > 14:
        raise ValueError("Geometry cannot fit the registered audited CFD domain")
    data = runtime.model_dump()
    data["cfd_width"] = width
    selected = Runtime.model_validate(data)
    grids = [(selected.cfd_cells_fine + 4, width), (selected.cfd_cells_fine, width + 2)]
    # Conservative allocation estimate: 152 B distributions, mask/lookup and auxiliary reserve.
    bytes_per_case = max(
        round(18 * cells) * (2 * round(w * cells / 2)) ** 2 * 200 for cells, w in grids
    )
    return selected, dict(
        transverse_envelope_d=envelopes,
        required_width_d=required,
        selected_width_d=width,
        domain_audit_width_d=width + 2,
        clearance_d=[width / 2 - e for e in envelopes],
        estimated_peak_bytes_per_case=bytes_per_case,
        memory_is_estimate=True,
        acceptance_unchanged=True,
    )


def prepare(runtime_path, assembly_paths, destination):
    runtime = Runtime.model_validate(read(runtime_path))
    selected, evidence = select_runtime(runtime, [read(p) for p in assembly_paths])
    evidence.update(
        original_runtime=runtime.model_dump(),
        selected_runtime=selected.model_dump(),
        assembly_hashes={p.as_posix(): sha(p) for p in assembly_paths},
        runtime_sha256=sha(runtime_path),
        reason="Rotated-body clearance at all in-plane angles",
    )
    if destination.exists():
        raise ValueError("Use a new runtime file; preserve the first attempted configuration")
    write_json(destination, selected.model_dump())
    write_json(destination.with_suffix(".preflight.json"), evidence)
    return evidence


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runtime", type=Path)
    p.add_argument("old_assembly", type=Path)
    p.add_argument("new_assembly", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    print(prepare(a.runtime, [a.old_assembly, a.new_assembly], a.destination))
