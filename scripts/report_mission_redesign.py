"""Audit completed redesign evidence without promoting screening into CFD acceptance."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.preview_coarse_flight import verify_folder


def audit_run(folder):
    report = read(folder / "report.json")
    if report["source_hash"] != code_hash() or not report["source_unchanged"]:
        raise ValueError("Changed physical source")
    for path, expected in report.get("inputs", report.get("input_hashes", {})).items():
        if sha(Path(path)) != expected:
            raise ValueError("Changed input/recipe: " + path)
    return report


def native_rows(folder, rows):
    results, count = [], 0
    for row in rows:
        path = folder / row["label"]
        if sha(path / "manifest.json") != row["evidence"]["manifest_sha256"]:
            raise ValueError("Changed native manifest")
        count += verify_folder(path)
        result = {key: row[key] for key in ("label", "status", "spec")}
        if row["status"] == "completed":
            result.update(
                {key: row[key] for key in ("metrics", "temporal_pass", "aero_domain_pass")}
            )
        else:
            result["error"] = row["error"]
        if "modal_probe" in row:
            probe = path / "modal-probe/data.json"
            if sha(probe) != row["modal_probe_sha256"]:
                raise ValueError("Changed modal probe")
            result["modal_probe"] = row["modal_probe"]
            result["modal_probe_sha256"] = sha(probe)
            count += 1
        result["manifest_sha256"] = row["evidence"]["manifest_sha256"]
        results.append(result)
    return results, count


def structure(folder):
    report = audit_run(folder)
    verified = 0
    for row in report["results"]:
        path = folder / row["method"]
        if sha(path / "manifest.json") != row["manifest_sha256"]:
            raise ValueError("Changed structural manifest")
        verified += verify_folder(path)
    return dict(
        results=report["results"],
        verified_files=verified,
        load_scope=report["load_scope"],
        report_sha256=sha(folder / "report.json"),
    )


def run(root, destination):
    search_folder, refine_folder = root / "mission40-redesign2", root / "m40-refine1"
    search, refine = audit_run(search_folder), audit_run(refine_folder)
    if search["precision"] != Precision().model_dump() or not search["input_unchanged"]:
        raise ValueError("Changed acceptance/input contract")
    if sha(search_folder / "evaluations.jsonl") != search["evaluations_sha256"]:
        raise ValueError("Changed evaluations")
    native, count1 = native_rows(search_folder, search["results"])
    variants, count2 = native_rows(refine_folder, refine["results"])
    early = read(root / "mission40-redesign1/interruption.json")
    if (
        sha(root / "mission40-redesign1/evaluations.jsonl") != early["evaluations_sha256"]
        or sha(root / "mission40-redesign1/executed-script.py") != early["script_sha256"]
    ):
        raise ValueError("Changed interrupted attempt")
    probes = []
    for cells in (20, 24):
        folder = root / f"m40-de0-flow{cells}"
        case = read(folder / "case.json")
        for name, expected in case["source_sha256"].items():
            if sha(Path("scenarios/cfd") / name) != expected:
                raise ValueError("Changed CFD recipe")
        if case["geometry_sha256"] != sha(root / "m40-de0-pre1/assembly.json"):
            raise ValueError("Changed CFD geometry")
        probes.append(
            dict(
                cells=cells,
                case=case,
                artifacts={p.name: sha(p) for p in folder.iterdir() if p.is_file()},
            )
        )
    public = dict(
        schema="fixed-mission-redesign-results-v1",
        mission=search["mission"],
        source_hash=code_hash(),
        precision=search["precision"],
        search_reserves=search["reserves"],
        interrupted_attempt=early,
        search=dict(
            unique_attempts=search["unique_attempts"],
            objective_calls=sum(r["nfev"] for r in search["runs"]),
            predicted_candidates=search["predictor_candidates"],
            elapsed_s=search["elapsed_s"],
            native=native,
            report_sha256=sha(search_folder / "report.json"),
        ),
        refinement=dict(
            screen_count=refine["screen_count"],
            native=variants,
            elapsed_s=refine["elapsed_s"],
            report_sha256=sha(refine_folder / "report.json"),
        ),
        preliminary_structure=structure(root / "m40-de0-structure1"),
        refined_structure=structure(root / "m40-final-structure1"),
        preliminary_cfd=probes,
        verified_native_files=count1 + count2,
        acceptance_performed=False,
        criteria_met=False,
        physical_qualification=False,
        scope=(
            "Native analytic-flight redesign and CFD convergence probes; "
            "no complete new tunnel table"
        ),
    )
    probe_folder = root / "m40-cfd-refine1"
    if (probe_folder / "report.json").exists():
        probe = audit_run(probe_folder)
        public["refined_cfd"] = dict(
            results=probe["results"],
            grid_differences=probe["grid_differences"],
            elapsed_s=probe["elapsed_s"],
            verified_files=verify_folder(probe_folder),
            report_sha256=sha(probe_folder / "report.json"),
        )
    write_json(destination, public)
    print(
        dict(
            native_files=public["verified_native_files"],
            search_attempts=search["unique_attempts"],
            refinement_cases=refine["screen_count"],
            accepted=False,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    run(a.root, a.destination)
