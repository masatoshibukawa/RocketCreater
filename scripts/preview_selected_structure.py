"""Separate structural diagnostic under analytic flight loads; no CFD acceptance."""

import argparse
import sys
import time
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.runtime import run as run_process
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.tradeoff import environment
from rocketwright.analysis.worker import read


def run(parent, output):
    protocol = read(parent / "protocol.json")
    source = code_hash()
    if protocol["source_hash"] != source:
        raise ValueError("Changed numerical source")
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {
        m: str((parent / m / "data.json").resolve())
        for m in ("geometry", "thermal", "propulsion", "screen")
    }
    parent_hashes = {k: sha(Path(p)) for k, p in artifacts.items()}
    report = dict(
        source_hash=source,
        protocol_sha256=sha(parent / "protocol.json"),
        spec=protocol["spec"],
        parent_hashes=parent_hashes,
        results=[],
        load_scope="analytic flight envelope; not CFD loads",
        physical_qualification=False,
        acceptance_performed=False,
    )
    start = time.monotonic()
    for method in ("modes", "fem_coarse", "fem_fine"):
        folder = output / method
        folder.mkdir()
        remaining = 300 - (time.monotonic() - start)
        write_json(
            folder / "input.json",
            dict(
                spec=protocol["spec"],
                precision=protocol["precision"],
                runtime=protocol["runtime"],
                artifacts=dict(artifacts),
                timeout_s=remaining,
            ),
        )
        row = dict(method=method, status="failed")
        begin = time.monotonic()
        try:
            run_process(
                [
                    sys.executable,
                    "-m",
                    "rocketwright.analysis.worker",
                    str(folder / "input.json"),
                    str(folder / "data.json"),
                    method,
                ],
                cwd=Path(__file__).resolve().parents[1],
                log=folder / "worker.log",
                timeout=remaining,
                env=environment(),
            )
            artifacts[method] = str((folder / "data.json").resolve())
            row.update(status="completed", data=read(folder / "data.json"))
        except (ValueError, RuntimeError, OSError) as error:
            row["error"] = str(error)[-2000:]
        row["elapsed_s"] = time.monotonic() - begin
        report["results"].append(row)
        print(
            dict(method=method, status=row["status"], metrics=row.get("data", {}).get("metrics")),
            flush=True,
        )
        if row["status"] != "completed":
            break
    report.update(
        complete=len(report["results"]) == 3
        and all(r["status"] == "completed" for r in report["results"]),
        elapsed_s=time.monotonic() - start,
        source_unchanged=code_hash() == source
        and parent_hashes == {m: sha(parent / m / "data.json") for m in parent_hashes},
    )
    write_json(output / "report.json", report)
    write_json(
        output / "manifest.json",
        {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()},
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.parent, a.output)
