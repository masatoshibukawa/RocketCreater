"""Integrate actual solid CAD mass properties and compare with flight's lumped surrogates."""

import argparse
import copy
import struct
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read
from rocketwright.physics.flight_loads import MassDistribution
from scripts.preview_coarse_flight import verify_folder


def moments(triangles):
    """Closed outward triangles: signed tetrahedral integrals, in input length units."""
    t = np.asarray(triangles, float)
    if t.ndim != 3 or t.shape[1:] != (3, 3) or not np.isfinite(t).all():
        raise ValueError("Finite triangles required")
    # Translation improves conditioning for small parts far from the coordinate origin.
    origin = t.mean(axis=(0, 1))
    v = t - origin
    volumes = np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])) / 6
    volume = volumes.sum()
    if volume <= 0:
        raise ValueError("Positive outward-oriented volume required")
    sums = v.sum(axis=1)
    center = np.einsum("i,ij->j", volumes, sums) / (4 * volume)
    second = np.einsum("i,ij,ik->jk", volumes, sums, sums)
    second += np.einsum("i,iaj,iak->jk", volumes, v, v)
    covariance = second / (20 * volume) - np.outer(center, center)
    inertia_per_mass = np.trace(covariance) * np.eye(3) - covariance
    if np.linalg.eigvalsh(inertia_per_mass).min() <= 0:
        raise ValueError("Nonpositive solid inertia")
    return dict(
        volume=float(volume),
        centroid=(center + origin).tolist(),
        inertia_per_mass=inertia_per_mass.tolist(),
    )


def stl_moments(path):
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * n or n < 4:
        raise ValueError("Expected a nonempty binary STL")
    dtype = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    return moments(np.frombuffer(data, dtype=dtype, offset=84)["v"])


def run(parent, output):
    output.mkdir(parents=True, exist_ok=False)
    saved, source = read(parent / "result.json"), code_hash()
    if saved["status"] != "completed" or saved["source_hash"] != source:
        raise ValueError("Current-source completed parent required")
    verified = verify_folder(parent)
    cad = parent / "geometry/cad"
    files = {"fin": cad / "fin-assembly-mm.stl", "nose": cad / "nose-mm.stl"}
    props = {name: stl_moments(path) for name, path in files.items()}
    metrics = read(parent / "geometry/data.json")["cad_metrics"]
    for name, prop in props.items():
        if not np.isclose(prop["volume"], metrics[name]["volume_mm3"], rtol=1e-5):
            raise ValueError("STL volume differs from inspected CAD")
    context = dict(
        spec=saved["spec"],
        precision=Precision().model_dump(),
        runtime=Runtime().model_dump(),
        timeout_s=300,
        artifacts={
            m: str(parent / m / "data.json")
            for m in ("geometry", "thermal", "propulsion", "screen")
        },
    )
    baseline = Worker(context, output)
    baseline.setup()
    assembly = copy.deepcopy(baseline.assembly)
    g = assembly["dimensions_mm"]
    comparison = []
    for item in assembly["bill"]:
        name = {"printed_fins": "fin", "printed_nose": "nose"}.get(item["id"])
        if name is None:
            continue
        prop = props[name]
        per_mass = np.array(prop["inertia_per_mass"])
        center = np.array(prop["centroid"])
        if name == "fin":
            # Four rotations around the vehicle axis cancel transverse products.
            # Include each blade's radial offset from the axis of the assembled set.
            radius2 = center[0] ** 2 + center[1] ** 2
            transverse = (per_mass[0, 0] + per_mass[1, 1] + radius2) / 2
            diag = np.array([transverse, transverse, per_mass[2, 2] + radius2])
            station = g["overall"] - g["fin_tail_inset"] - center[2]
        else:
            diag = np.diag(per_mass)
            station = g["nose_length"] - center[2]
        comparison.append(
            dict(id=item["id"], prior_station_mm=item["station_mm"], cad_station_mm=float(station))
        )
        item["local_inertia_kg_m2"] = (diag * item["mass_g"] / 1000 * 1e-6).tolist()
        item["station_mm"] = float(station)
    old = baseline.assembly
    shift = sum(r["mass_g"] * r["station_mm"] for r in assembly["bill"]) - sum(
        r["mass_g"] * r["station_mm"] for r in old["bill"]
    )
    dry_g, payload_g = assembly["dry_mass_g"], baseline.design.payload_mass_kg * 1000
    water_g = baseline.design.bottle_volume_m3 * baseline.design.water_fill_frac * 1e6
    for key, mass_g in (
        ("dry_cg_mm", dry_g),
        ("loaded_cg_mm", dry_g + payload_g),
        ("wet_cg_mm", dry_g + payload_g + water_g),
    ):
        assembly[key] += shift / mass_g
    write_json(output / "cad-assembly.json", assembly)
    rows = []
    for label, body in (("legacy", old), ("cad_mass_properties", assembly)):
        worker = Worker(context, output)
        worker.setup()
        worker.assembly = body
        worker.record["assembly"] = body
        t = time.monotonic()
        trajectory = worker.trajectory(dt=0.01)
        worker.data["screen"] = trajectory
        modes = worker.modes()
        mass = MassDistribution(worker.design, body, worker.data["propulsion"])
        row = dict(
            label=label,
            apogee_m=trajectory["apogee_m"],
            incidence_deg=trajectory["ascent_incidence_deg"],
            static_margin_cal=(body["cp_mm"] - body["wet_cg_mm"]) / g["body_diameter"],
            beam_ratio=modes["metrics"]["fin_deflection_ratio"],
            initial_inertia_kg_m2=mass.properties(0)[2].tolist(),
            dry_inertia_kg_m2=mass.properties(60)[2].tolist(),
            elapsed_s=time.monotonic() - t,
        )
        write_json(output / f"{label}-flight.json", trajectory)
        rows.append(row)
        print(row, flush=True)
    if not np.isclose(rows[0]["apogee_m"], saved["metrics"]["apogee_m"], rtol=1e-9):
        raise ValueError("Legacy baseline does not reproduce saved flight")
    write_json(
        output / "report.json",
        dict(
            production_source_hash=source,
            diagnostic_source_sha256=sha(Path(__file__)),
            inputs={str(p): sha(p) for p in [parent / "manifest.json", *files.values()]},
            verified_parent_files=verified,
            cad_properties=props,
            station_comparison=comparison,
            results=rows,
            source_unchanged=source == code_hash(),
            acceptance_performed=False,
            physical_qualification=False,
            scope="Diagnostic assembly override from solid CAD; production compiler unchanged",
            limitations=[
                "Uniform material density",
                "Other components retain assumed inertias",
                "Analytic aerodynamics; no full nonlinear-flight stability proof",
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
