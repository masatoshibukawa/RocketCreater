"""Audit and export the assumed-drag redesign; preserve its original executed source."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.preview_coarse_flight import verify_folder


def run(root, output):
    report = read(root / "report.json")
    if not report["source_unchanged"] or not report["input_unchanged"]:
        raise ValueError("Changed experiment source/input")
    if report["source_hash"] != code_hash():
        raise ValueError("Use the experiment's frozen numerical source")
    for name, expected in report["input_hashes"].items():
        path = (
            root / "executed-script.py"
            if Path(name).name == "search_drag_reserve.py"
            else Path(name)
        )
        if sha(path) != expected:
            raise ValueError(f"Changed input: {name}")
    if sha(root / "evaluations.jsonl") != report["evaluations_sha256"]:
        raise ValueError("Changed physical evaluations")
    verified = 0
    for row in read(root / "anchors.json") + report["results"]:
        folder = root / row["label"]
        if sha(folder / "manifest.json") != row["evidence"]["manifest_sha256"]:
            raise ValueError("Changed native manifest")
        verified += verify_folder(folder)
    result = {
        k: report[k]
        for k in (
            "source_hash",
            "parent_source",
            "mission",
            "drag_assumption",
            "reserves",
            "precision",
            "population",
            "generations",
            "aerodynamic_scope",
            "imported_information",
            "predictor_used",
            "acceptance_performed",
            "physical_qualification",
            "elapsed_s",
            "evaluations_sha256",
        )
    }
    result.update(
        source_unchanged=True,
        input_unchanged=True,
        verified_native_files=verified,
        report_sha256=sha(root / "report.json"),
        executed_script_sha256=sha(root / "executed-script.py"),
        objective_calls=sum(r["nfev"] for r in report["search"]),
        unique_attempts=sum(r["unique_attempts"] for r in report["search"]),
        results=report["results"],
        limitations=[
            "Constant Cd=1.4 is a sensitivity assumption, not computed CFD for these shapes",
            "All native candidates remain below 20 m under that assumption",
            "These bounded searches do not prove design infeasibility",
            "Only old specifications are reused; current-source CAD and physical labels are new",
        ],
    )
    write_json(output, result)
    print(
        dict(
            calls=result["objective_calls"],
            unique=result["unique_attempts"],
            verified_native_files=verified,
            seconds=result["elapsed_s"],
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.root, a.output)
