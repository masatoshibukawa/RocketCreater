"""Publish a verified analytic-load structural diagnostic without claiming CFD acceptance."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read


def export(search, old, new, destination):
    campaign = read(search / "report.json")
    output = dict(
        source_hash=campaign["source_hash"],
        search_report_sha256=sha(search / "report.json"),
        load_scope="maximum dynamic pressure times maximum incidence; not concurrent CFD",
        deflection_limit_ratio=0.05,
        physical_qualification=False,
        methods=[],
    )
    for method, folder in (("wide-old", old), ("wide-new", new)):
        report = read(folder / "report.json")
        selected = next(
            r for r in campaign["results"] if r["label"] == campaign["detailed_candidates"][method]
        )
        if (
            not report["complete"]
            or not report["source_unchanged"]
            or report["source_hash"] != campaign["source_hash"]
            or report["spec"] != selected["spec"]
        ):
            raise ValueError("Structural diagnostic differs from selected source/candidate")
        manifest = read(folder / "manifest.json")
        for name, value in manifest.items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or sha(path) != value:
                raise ValueError("Structural evidence changed")
        rows = {r["method"]: r["data"] for r in report["results"]}
        for name, data in rows.items():
            if data != read(folder / name / "data.json"):
                raise ValueError("Structural report differs from sealed worker output")
        beam, fem = rows["modes"], rows["fem_fine"]
        ratio = fem["metrics"]["fem_deflection_ratio"]
        output["methods"].append(
            dict(
                method=method,
                label=selected["label"],
                report_sha256=sha(folder / "report.json"),
                manifest_sha256=sha(folder / "manifest.json"),
                verified_files=len(manifest),
                beam_deflection_ratio=beam["metrics"]["fin_deflection_ratio"],
                modes_hz=beam["first_modes_hz"],
                fin_temperature_c=beam["temperature_c"],
                assumed_force_n=beam["root_force_n"],
                fem_displacement_m=fem["max_displacement_m"],
                fem_deflection_ratio=ratio,
                mesh_relative_change=fem["metrics"]["fem_mesh_change"],
                deflection_check=ratio <= 0.05,
                linear_solution_caution=(
                    "Large deformation: displacement/stress are not validated predictions"
                ),
                elapsed_s=report["elapsed_s"],
            )
        )
    write_json(destination, output)
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("search", "old", "new", "destination"):
        p.add_argument(field, type=Path)
    a = p.parse_args()
    print(export(a.search, a.old, a.new, a.destination))
