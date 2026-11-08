"""Audit an inlet-clearance correction separately from design acceptance."""

from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import read
from scripts.preview_coarse_flight import verify_folder


def run(root, destination):
    old_folder = root / "esc-new2/cfd_fine"
    before_path = old_folder / "tunnel/v35-a180/case.json"
    after_folder = root / "m40-domain-corrected"
    before, after = read(before_path), read(after_folder / "case.json")
    count = verify_folder(old_folder)
    fields = [
        "shape",
        "wall_scheme",
        "fin_thickness_mm",
        "dimensions_mm",
        "cg_mm",
        "d",
        "width_D",
        "Re",
        "lattice_Ma",
        "Cs",
        "tau",
        "speed_mps",
        "angle_deg",
        "rotated_geometry",
        "cant_deg",
        "steps",
        "paired_samples",
        "averaging_tU_D",
        "geometry_sha256",
    ]
    if any(before[k] != after[k] for k in fields):
        raise ValueError("Inlet comparison changed other numerical inputs")
    for name in ("bottle_flow.cu", "interpolated_wall.cuh"):
        if before["source_sha256"][name] != after["source_sha256"][name]:
            raise ValueError("CUDA equations changed")
    for name, expected in after["source_sha256"].items():
        if sha(Path("scenarios/cfd") / name) != expected:
            raise ValueError("Changed corrected CFD source")
    old_native = root / "m40-refine1/thickness-2.4"
    new_native = root / "m40-corrected-pre1"
    a, b = read(old_native / "result.json"), read(new_native / "result.json")
    if a["spec"] != b["spec"] or a["metrics"] != b["metrics"] or b["source_hash"] != code_hash():
        raise ValueError("Candidate replay changed inputs or analytic metrics")
    native_count = verify_folder(old_native) + verify_folder(new_native)
    if (root / "m40-domain-rejected").exists():
        raise ValueError("Invalid-domain test unexpectedly created a case")
    write_json(
        destination,
        dict(
            schema="rotated-cfd-boundary-correction-v1",
            source_hash=code_hash(),
            previous_source_hash=a["source_hash"],
            before=before,
            after=after,
            matched_fields=fields,
            cuda_equations_unchanged=True,
            verified_old_cfd_files=count,
            verified_native_replay_files=native_count,
            before_case_sha256=sha(before_path),
            after_artifacts={p.name: sha(p) for p in after_folder.iterdir() if p.is_file()},
            rejection_log_sha256=sha(root / "m40-domain-rejected.log"),
            native_replay=dict(
                metrics=b["metrics"],
                spec_sha256=sha(new_native / "spec.json"),
                old_manifest_sha256=sha(old_native / "manifest.json"),
                new_manifest_sha256=sha(new_native / "manifest.json"),
            ),
            criteria_met=False,
            acceptance_performed=False,
            physical_qualification=False,
            scope=(
                "Old-geometry boundary control and identical current-candidate analytic replay; "
                "no completed corrected tunnel table"
            ),
        ),
    )


if __name__ == "__main__":
    run(Path("output"), Path("scenarios/adaptive_design/mission40-cfd-boundary.json"))
