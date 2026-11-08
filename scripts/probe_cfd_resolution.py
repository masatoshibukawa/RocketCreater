"""Source-bound independent CFD probes before paying for an entire wind-tunnel table."""

import argparse
import time
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.aero_accuracy import relative_change
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.worker import Worker, read
from scripts.preview_coarse_flight import verify_folder


def run(parent, output, *, cells=(20, 24, 28), times=80, lattice_speed=0.05, budget=7200):
    output.mkdir(parents=True, exist_ok=False)
    begin, source = time.monotonic(), code_hash()
    saved = read(parent / "result.json")
    if saved["status"] != "completed" or saved["source_hash"] != source:
        raise ValueError("Completed current-source native candidate required")
    verified = verify_folder(parent)
    assembly = read(parent / "geometry/data.json")["record"]["assembly"]
    rt = Runtime(
        cfd_enabled=True,
        cfd_cells_coarse=cells[0],
        cfd_cells_fine=cells[1],
        cfd_times=times,
        cfd_width=12.5,
        cfd_lattice_speed=lattice_speed,
    )
    context = dict(
        spec=saved["spec"],
        precision=Precision().model_dump(),
        runtime=rt.model_dump(),
        artifacts={},
        timeout_s=budget,
    )
    hashes = {
        str(p): sha(p)
        for p in (
            Path(__file__),
            parent / "manifest.json",
            parent / "result.json",
            parent / "geometry/data.json",
        )
    }
    plan = dict(
        source_hash=source,
        inputs=hashes,
        verified_parent_files=verified,
        context=context,
        cells=list(cells),
        speed_mps=18,
        angle_deg=10,
        acceptance_performed=False,
        physical_qualification=False,
    )
    write_json(output / "protocol.json", plan)
    write_json(output / "assembly.json", assembly)
    worker = Worker(context, output)
    rows = []
    for n in cells:
        if code_hash() != source or any(sha(Path(p)) != value for p, value in hashes.items()):
            raise ValueError("Input/source changed during CFD probes")
        row = dict(cells=n, status="failed")
        t = time.monotonic()
        try:
            case = worker.run_case(output / "assembly.json", output / f"grid-{n}", 18, 10, n)
            row.update(
                status="completed",
                case=case,
                averaging=max(
                    abs(v) / max(abs(case["mean"][k]), 0.05)
                    for k, v in case["split_window_difference"].items()
                ),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            row["error"] = str(exc)
        row["elapsed_s"] = time.monotonic() - t
        rows.append(row)
        write_json(output / "progress.json", rows)
        print({k: v for k, v in row.items() if k != "case"}, flush=True)
        if row["status"] != "completed":
            break
    completed = [r for r in rows if r["status"] == "completed"]
    vectors = [[r["case"]["mean"][k] for k in ("Cx", "Cy", "Cm_z")] for r in completed]
    differences = [relative_change(a, b) for a, b in zip(vectors[:-1], vectors[1:], strict=True)]
    write_json(
        output / "report.json",
        dict(
            **plan,
            results=rows,
            grid_differences=differences,
            source_unchanged=code_hash() == source,
            elapsed_s=time.monotonic() - begin,
        ),
    )
    write_json(
        output / "manifest.json",
        {
            p.relative_to(output).as_posix(): sha(p)
            for p in output.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--cells", type=int, nargs=3, default=(20, 24, 28))
    p.add_argument("--times", type=float, default=80)
    p.add_argument("--lattice-speed", type=float, default=0.05)
    p.add_argument("--budget", type=float, default=7200)
    a = p.parse_args()
    if not 6 <= a.cells[0] < a.cells[1] < a.cells[2] <= 48 or not 300 <= a.budget <= 86400:
        p.error("Use three increasing grid sizes and a bounded 300–86400 second budget")
    run(
        a.parent,
        a.output,
        cells=a.cells,
        times=a.times,
        lattice_speed=a.lattice_speed,
        budget=a.budget,
    )
