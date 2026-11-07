"""Audit rejected CAD transitions without altering the frozen search outcome."""

import argparse
import math
import runpy
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "3d model/prototypes/pet-rocket-coke-2l/verify_stl.py"


def export(search, probes, destination):
    campaign = read(search / "report.json")
    if campaign["source_hash"] != code_hash():
        raise ValueError("CAD source differs from frozen search")
    verifier = runpy.run_path(str(VERIFIER))
    rows = []
    for label, folder in zip(("core-old-2", "wide-new-2"), probes, strict=True):
        source = search / label / "geometry/cad"
        probe, audit = read(folder / "probe.json"), read(folder / "sat.json")
        params = read(source / "parameters.json")
        if (
            probe["parameter_sha256"] != sha(source / "parameters.json")
            or sha(source / "fin-assembly-mm.stl") != sha(folder / "assembly.stl")
            or audit["verifier_sha256"] != sha(VERIFIER)
            or any(sha(folder / f["file"]) != f["sha256"] for f in audit["files"])
        ):
            raise ValueError("Changed CAD diagnostic evidence")
        dtype = np.dtype(
            [("normal", "<f4", (3,)), ("triangle", "<f4", (3, 3)), ("attribute", "<u2")]
        )
        tri = np.frombuffer((folder / "assembly.stl").read_bytes(), dtype=dtype, offset=84)[
            "triangle"
        ].astype(float)
        _, indices = np.unique(tri.reshape(-1, 3), axis=0, return_inverse=True)
        faces = indices.reshape(-1, 3)
        angle = math.radians(params["fin"]["print_rotation_y_deg"])
        c, s = math.cos(angle), math.sin(angle)
        rotated = tri @ np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]).T
        rotated -= rotated.min(axis=(0, 1))
        epsilon = audit["tolerances"]["intersection_epsilon_mm"]
        # Diagnostic only: no alternate transformed mesh is accepted or exported for printing.
        arithmetic = {}
        for name, values in (
            ("float64_rigid_transform", rotated),
            ("float64_transform_then_float32", rotated.astype(np.float32).astype(float)),
        ):
            _, pairs = verifier["nonadjacent_intersections"](values, faces, epsilon)
            arithmetic[name] = dict(intersection_count=len(pairs), pairs=pairs)
        rows.append(
            dict(
                label=label,
                original_rejection_preserved=True,
                probe=probe,
                independent_stl_audit=audit,
                arithmetic_probe=arithmetic,
                input_hashes={p.name: sha(p) for p in folder.iterdir() if p.is_file()},
            )
        )
    result = dict(
        source_hash=campaign["source_hash"],
        search_report_sha256=sha(search / "report.json"),
        candidates=rows,
        physical_qualification=False,
        limitations=[
            "No repair or replacement of either rejected candidate",
            "Float64 arithmetic probe checks intersections only, not complete CAD acceptance",
            "STL verifier skips triangles sharing vertices; no complete exact-predicate proof",
        ],
    )
    write_json(destination, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("search", "old", "new", "destination"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    result = export(a.search, (a.old, a.new), a.destination)
    print([(r["label"], r["arithmetic_probe"]) for r in result["candidates"]])
