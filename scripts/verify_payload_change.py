"""Recompute a payload-only mission change with sealed, unchanged-geometry CFD."""

import argparse
import copy
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, integrated_coefficients, read, serial
from rocketwright.physics.flight_loads import TunnelDatabase
from scripts.preview_coarse_flight import verify_folder
from scripts.report_joint_confirmation import export
from scripts.verify_joint_candidate import METHODS


def payload_spec(original, payload_g, altitude_m):
    updated = copy.deepcopy(original)
    updated["design"]["payload_mass_kg"] = payload_g / 1000
    updated["requirement"].update(payload_mass_kg=payload_g / 1000, target_altitude_m=altitude_m)
    result = DesignSpec.model_validate(updated)
    if not np.isfinite([payload_g, altitude_m]).all() or min(payload_g, altitude_m) <= 0:
        raise ValueError("Positive finite mission values required")
    return result.model_dump(mode="json")


def check_payload_only(before, after):
    expected = payload_spec(
        before,
        after["design"]["payload_mass_kg"] * 1000,
        after["requirement"]["target_altitude_m"],
    )
    if expected != after:
        raise ValueError("CFD reuse permits only payload and matching mission changes")


def rebase_case(case, cg_mm):
    """Move coefficient moment reference; retain original simulated grid/rotation center."""
    result = copy.deepcopy(case)
    old = case.get("moment_reference_cg_mm", case["cg_mm"])
    offset = (old - cg_mm) / case["dimensions_mm"]["body_diameter"]
    for key in ("mean", "split_window_difference"):
        values = result[key]
        values["Cpitch_y"] -= offset * values["Cz"]
        values["Cm_z"] += offset * values["Cy"]
    result.update(moment_reference_cg_mm=cg_mm, simulation_reused=True)
    return result


def dependencies(parent):
    report = read(parent / "report.json")
    if (
        not report["complete"]
        or not report["source_unchanged"]
        or report["source_hash"] != code_hash()
    ):
        raise ValueError("A complete source-identical parent is required")
    ancestor = report.get("resumed_from")
    if ancestor and sha(Path(ancestor["root"]) / "report.json") != ancestor["report_sha256"]:
        raise ValueError("Parent ancestry changed")
    folders, proof = {}, {}
    for row in report["results"]:
        method = row["method"]
        folder = Path(row.get("reused_from", parent / method)).resolve()
        expected = (Path(ancestor["root"]) if row.get("reused_from") else parent) / method
        if folder != expected.resolve() or row["status"] != "completed":
            raise ValueError("Invalid parent stage")
        if sha(folder / "manifest.json") != row["manifest_sha256"]:
            raise ValueError("Parent manifest changed")
        proof[method] = dict(manifest_sha256=row["manifest_sha256"], files=verify_folder(folder))
        folders[method] = folder
    if set(folders) != set(METHODS):
        raise ValueError("Incomplete parent stages")
    # Tables are deliberately retained in the source run, never redirected silently.
    for method in ("cfd_coarse", "cfd_fine"):
        data = read(folders[method] / "data.json")
        if Path(data["table_folder"]).resolve() != folders[method] / "tunnel":
            raise ValueError("CFD table is outside the sealed dependency")
    return report, folders, proof


class PayloadWorker(Worker):
    def __init__(self, context, folder, sources):
        super().__init__(context, folder)
        self.sources = sources

    def geometry(self):
        metrics = read(self.sources["geometry"] / "data.json")["cad_metrics"]
        return dict(
            cad_metrics=metrics,
            record=compile_record(self.spec, metrics),
            metrics={"geometry_valid": True},
            cad_reused=True,
        )

    def benchmarks(self):
        return dict(read(self.sources["benchmarks"] / "data.json"), benchmark_reused=True)

    def cfd(self, fine):
        method = "cfd_fine" if fine else "cfd_coarse"
        result = read(self.sources[method] / "data.json")
        table = TunnelDatabase(result["table_folder"])
        cg = self.assembly["loaded_cg_mm"] / 1000
        cases = [
            rebase_case(read(p), cg * 1000)
            for p in sorted(Path(result["table_folder"]).glob("*/case.json"))
        ]
        result["averaging_relative_change"] = max(
            abs(delta) / max(abs(case["mean"][name]), 0.05)
            for case in cases
            for name, delta in case["split_window_difference"].items()
        )
        if fine:
            prior = np.asarray(self.data["cfd_coarse"]["coefficients"])
            now = integrated_coefficients(table.table, table.stations, table.diameter, cg)
            old = integrated_coefficients(prior, table.stations, table.diameter, cg)
            result["grid_relative_change"] = float(
                np.max(
                    np.max(abs(now - old), axis=(0, 1))
                    / np.maximum(np.max(abs(now), axis=(0, 1)), 0.01)
                )
            )
            result["metrics"] = dict(cfd_grid_change=result["grid_relative_change"])
        result.update(
            simulation_reused=True,
            moment_reference_cg_mm=cg * 1000,
            source_manifest_sha256=sha(self.sources[method] / "manifest.json"),
        )
        return result

    def run_case(self, assembly, out, speed, angle, cells, **changes):
        # Worker.cfd_audit recomputes every diagnostic using rebased independent cases.
        path = self.sources["cfd_audit"] / out.name / "case.json"
        case = read(path)
        if (case["speed_mps"], case["angle_deg"], case["d"]) != (speed, angle, cells):
            raise ValueError("Independent CFD condition differs from requested audit")
        result = rebase_case(case, self.assembly["loaded_cg_mm"])
        result["source_case_sha256"] = sha(path)
        out.mkdir()
        write_json(out / "case.json", result)
        return result


def verify(parent, root, payload_g=50, altitude_m=30, budget=1800):
    parent, root = parent.resolve(), root.resolve()
    before, sources, proof = dependencies(parent)
    source, script = code_hash(), sha(Path(__file__))
    spec = payload_spec(before["spec"], payload_g, altitude_m)
    check_payload_only(before["spec"], spec)
    root.mkdir(parents=True, exist_ok=False)
    protocol = dict(
        source_hash=source,
        script_sha256=script,
        spec=spec,
        precision=before["precision"],
        runtime=before["runtime"],
        methods=METHODS,
        parent_report_sha256=sha(parent / "report.json"),
        dependency_proof=proof,
        cfd_cases_reused=sum(
            len(list(sources[m].rglob("case.json")))
            for m in ("cfd_coarse", "cfd_fine", "cfd_audit")
        ),
        payload_only=True,
        acceptance_unchanged=True,
        reuse_scope="CAD and stationary CFD only; original grid position retained",
        planner="fixed payload comparison",
        budget_s=budget,
    )
    write_json(root / "protocol.json", protocol)
    write_json(root / "spec.json", spec)
    artifacts, rows = {}, []
    start = time.monotonic()
    for method in METHODS:
        if code_hash() != source or sha(Path(__file__)) != script:
            raise ValueError("Source changed during payload study")
        remaining = budget - (time.monotonic() - start)
        if remaining <= 0:
            break
        folder = root / method
        folder.mkdir()
        context = dict(
            spec=spec,
            precision=protocol["precision"],
            runtime=protocol["runtime"],
            artifacts=dict(artifacts),
            timeout_s=remaining,
        )
        write_json(folder / "input.json", context)
        begin = time.monotonic()
        row = dict(method=method, status="failed")
        try:
            data = serial(PayloadWorker(context, folder, sources).run(method))
            write_json(folder / "data.json", data)
            artifacts[method] = str(folder / "data.json")
            row.update(status="completed", metrics=data.get("metrics", {}))
        except (ValueError, RuntimeError, OSError) as error:
            row["error"] = str(error)[-2000:]
        row["elapsed_s"] = time.monotonic() - begin
        write_json(
            folder / "manifest.json",
            {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file()},
        )
        row["manifest_sha256"] = sha(folder / "manifest.json")
        rows.append(row)
        write_json(root / "progress.json", rows)
        print(row, flush=True)
        if row["status"] != "completed":
            break
    _, _, after_proof = dependencies(parent)
    result = dict(
        **protocol,
        results=rows,
        complete=len(artifacts) == len(METHODS),
        source_unchanged=code_hash() == source and after_proof == proof,
        elapsed_s=time.monotonic() - start,
        physical_qualification=False,
        confirmation=read(artifacts["confirm"]) if "confirm" in artifacts else None,
    )
    write_json(root / "report.json", result)
    return result


def portable(root, destination):
    report = read(root / "report.json")
    result = export(root, destination)
    result.update(
        gpu_cases=0,
        cfd_cases_reused=report["cfd_cases_reused"],
        cad_reused=True,
        parent_report_sha256=report["parent_report_sha256"],
        dependency_proof=report["dependency_proof"],
        payload_only=True,
        reuse_scope=report["reuse_scope"],
        dependency_files_verified=sum(v["files"] for v in report["dependency_proof"].values()),
    )
    write_json(destination, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--payload-g", type=float, default=50)
    p.add_argument("--altitude-m", type=float, default=30)
    p.add_argument("--export", type=Path)
    a = p.parse_args()
    report = verify(a.parent, a.output, a.payload_g, a.altitude_m)
    if not report["complete"]:
        raise SystemExit("Incomplete payload verification; see progress.json")
    if a.export:
        portable(a.output, a.export)
