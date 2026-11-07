"""Render one finished, unrotated CFD case from its sealed numeric fields."""

import argparse
import sys
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read


def render(case, output):
    from scenarios.cfd.flow_preview import FlowPreview

    data = read(case / "case.json")
    if data["angle_deg"] != 0 or data["cant_deg"] != 0:
        raise ValueError("This fixed body overlay is restricted to zero incidence and cant")
    assembly = case.parent.parent / "assembly.json"
    if sha(assembly) != data["geometry_sha256"]:
        raise ValueError("CFD assembly binding differs")
    names = ("case.json", "volume.npz", "slice.npz", "history.csv")
    hashes = {name: sha(case / name) for name in names}
    volume, section = np.load(case / "volume.npz"), np.load(case / "slice.npz")
    history = np.genfromtxt(case / "history.csv", names=True, delimiter=",")
    output.mkdir(parents=True, exist_ok=False)
    preview = FlowPreview(
        output,
        data["dimensions_mm"],
        data["shape"],
        data["angle_deg"],
        data["cant_deg"],
        data["speed_mps"],
        data["Re"],
        data["d"],
        data["upstream_D"],
    )
    preview.snapshot(
        100,
        volume["ux_U"],
        volume["solid"],
        int(volume["stride"]),
        section["ux_U"],
        section["solid"],
        history["tU_D"],
        history["Cd"],
    )
    if hashes != {name: sha(case / name) for name in names}:
        raise ValueError("Observed CFD fields changed during rendering")
    write_json(
        output / "source.json",
        dict(
            case_files=hashes,
            geometry_sha256=data["geometry_sha256"],
            solver_sources=data["source_sha256"],
            speed_mps=data["speed_mps"],
            cells_per_d=data["d"],
            width_d=data["width_D"],
            snapshot="end of this single CFD case",
            render_sha256=sha(output / "frame-100.png"),
            renderer_sha256=sha(Path(__file__)),
            physical_qualification=False,
            limitations=[
                "Simplified body overlay",
                "100% is case progress, not accuracy or acceptance",
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--preview-libraries", type=Path, required=True)
    a = p.parse_args()
    sys.path.append(str(a.preview_libraries.resolve()))
    render(a.case, a.output)
