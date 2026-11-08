"""Propagate observed CFD split-window differences as deterministic load-bias scenarios."""

import argparse
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import AnalyticAero, Worker, read
from scripts.preview_coarse_flight import verify_folder

KEYS = ("Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z")


class BiasedAero(AnalyticAero):
    def __init__(self, record, bias):
        super().__init__(record)
        self.bias = np.asarray(bias, float)
        if self.bias.shape != (6,) or not np.isfinite(self.bias).all():
            raise ValueError("Six finite raw tunnel coefficients required")
        self.reference_station = record["assembly"]["loaded_cg_mm"] / 1000
        self.diameter = record["assembly"]["dimensions_mm"]["body_diameter"] / 1000
        self.stations = np.r_[self.cp, self.reference_station]
        self.metadata = dict(
            method="analytic aero plus deterministic CFD-scale bias scenarios",
            physical_validation=False,
        )

    def evaluate(self, vb, q, cg):
        base = super().evaluate(vb, q, cg)
        vb = np.asarray(vb, float)
        cross = np.linalg.norm(vb[:2])
        e1 = np.r_[vb[:2] / cross, 0] if cross > 1e-10 else np.array([1.0, 0, 0])
        ez = np.array([0.0, 0, 1.0])
        transform = np.column_stack([-ez, -e1, np.cross(ez, e1)])
        force = q * self.area * (transform @ self.bias[:3])
        couple = q * self.area * self.diameter * (transform @ self.bias[3:])
        return dict(
            force_n=base["force_n"] + force,
            moment_nm=base["moment_nm"]
            + couple
            + np.cross([0, 0, cg - self.reference_station], force),
            station_m=self.stations,
            line_force_n=np.vstack([base["line_force_n"], force]),
            line_couple_nm=np.vstack([base["line_couple_nm"], couple]),
        )


def run(parent, cfd, output):
    output.mkdir(parents=True, exist_ok=False)
    source, begin = code_hash(), time.monotonic()
    saved, case = read(parent / "result.json"), read(cfd / "case.json")
    if saved["status"] != "completed" or saved["source_hash"] != source:
        raise ValueError("Current-source completed parent required")
    verified = verify_folder(parent)
    assembly = read(parent / "geometry/data.json")["record"]["assembly"]
    if case["dimensions_mm"] != assembly["dimensions_mm"] or not np.isclose(
        case["cg_mm"], assembly["loaded_cg_mm"]
    ):
        raise ValueError("CFD geometry/reference differs")
    deltas = np.array([case["split_window_difference"][k] for k in KEYS])
    jobs = [("baseline", np.zeros(6))]
    for i, key in enumerate(KEYS):
        for sign in (-1, 1):
            bias = np.zeros(6)
            bias[i] = sign * abs(deltas[i])
            jobs.append((f"{key}-{sign:+d}", bias))
    for sign in (-1, 1):
        jobs.append((f"joint-{sign:+d}", sign * deltas))
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
    worker = Worker(context, output)
    worker.setup()
    rows = []
    for label, bias in jobs:
        flight = worker.trajectory(dt=0.01, aero_model=BiasedAero(worker.record, bias))
        t = np.asarray(flight["trace"]["time_s"])
        ascent = t <= flight["apogee_s"]
        roll = np.asarray(flight["trace"]["omega_rad_s"])[ascent, 2]
        row = dict(
            label=label,
            bias=dict(zip(KEYS, bias.tolist(), strict=True)),
            apogee_m=flight["apogee_m"],
            incidence_deg=flight["ascent_incidence_deg"],
            peak_ascent_roll_rad_s=float(np.max(np.abs(roll))),
            aero_domain_pass=flight["aero_domain_pass"],
            equilibrium_residual=flight["max_section_equilibrium_residual"],
        )
        write_json(output / f"{label}.json", flight)
        rows.append(row)
        write_json(output / "progress.json", rows)
    if not np.isclose(rows[0]["apogee_m"], saved["metrics"]["apogee_m"], rtol=1e-9):
        raise ValueError("Zero bias does not reproduce native baseline")
    write_json(
        output / "report.json",
        dict(
            production_source_hash=source,
            diagnostic_source_sha256=sha(Path(__file__)),
            parent_manifest_sha256=sha(parent / "manifest.json"),
            verified_parent_files=verified,
            cfd_case_sha256=sha(cfd / "case.json"),
            results=rows,
            altitude_max_change_m=max(abs(r["apogee_m"] - rows[0]["apogee_m"]) for r in rows),
            incidence_max_change_deg=max(
                abs(r["incidence_deg"] - rows[0]["incidence_deg"]) for r in rows
            ),
            elapsed_s=time.monotonic() - begin,
            source_unchanged=source == code_hash(),
            acceptance_performed=False,
            physical_qualification=False,
            limitations=[
                "A single-speed/incidence observed difference is not a global confidence bound",
                "Constant coefficient biases across the trajectory are diagnostic scenarios",
                "Analytic nominal aerodynamics, not a complete CFD flight prediction",
                "All production averaging/precision gates remain unchanged",
            ],
        ),
    )
    write_json(output / "manifest.json", {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    print(dict(cases=len(rows), elapsed_s=time.monotonic() - begin), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("cfd", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.cfd, a.output)
