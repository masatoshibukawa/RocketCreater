"""Source-pinned fixed-candidate CFD/FEM confirmation; no implicit planner or gate changes."""

import argparse
import sys
import time
from pathlib import Path

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.runtime import run as run_process
from rocketwright.analysis.schema import Precision
from rocketwright.analysis.service import code_hash
from rocketwright.analysis.tradeoff import environment
from rocketwright.analysis.worker import read

ROOT = Path(__file__).resolve().parents[1]
METHODS = (
    "geometry",
    "thermal",
    "propulsion",
    "screen",
    "benchmarks",
    "cfd_coarse",
    "cfd_fine",
    "cfd_audit",
    "flight",
    "refine",
    "modes",
    "stability",
    "fem_coarse",
    "fem_fine",
    "confirm",
)


def verify(spec, runtime, root, budget=10800):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source, script = code_hash(), sha(Path(__file__))
    start = time.monotonic()
    precision = Precision()
    protocol = dict(
        source_hash=source,
        script_sha256=script,
        spec=spec.model_dump(mode="json"),
        runtime=runtime.model_dump(),
        precision=precision.model_dump(),
        budget_s=budget,
        acceptance_unchanged=True,
        methods=METHODS,
        planner="fixed host verification",
    )
    write_json(root / "protocol.json", protocol)
    artifacts, rows = {}, []
    for method in METHODS:
        if code_hash() != source or sha(Path(__file__)) != script:
            raise ValueError("Source changed during fixed verification")
        remaining = budget - (time.monotonic() - start)
        folder = root / method
        folder.mkdir()
        write_json(
            folder / "input.json",
            dict(
                spec=protocol["spec"],
                precision=precision.model_dump(),
                runtime=runtime.model_dump(),
                artifacts=artifacts,
                timeout_s=max(0.1, remaining),
            ),
        )
        begin = time.monotonic()
        row = dict(method=method, status="failed")
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
                cwd=ROOT,
                log=folder / "worker.log",
                timeout=remaining,
                env=environment(),
            )
            data = read(folder / "data.json")
            artifacts[method] = str(folder / "data.json")
            row.update(status="completed", metrics=data.get("metrics", {}))
        except (OSError, ValueError, RuntimeError) as error:
            row["error"] = str(error)[-2000:]
        row["elapsed_s"] = time.monotonic() - begin
        write_json(
            folder / "manifest.json",
            {
                p.relative_to(folder).as_posix(): sha(p)
                for p in folder.rglob("*")
                if p.is_file() and p.name != "manifest.json"
            },
        )
        row["manifest_sha256"] = sha(folder / "manifest.json")
        rows.append(row)
        write_json(root / "progress.json", rows)
        print(row, flush=True)
        if row["status"] != "completed":
            break  # Retain partial evidence; never fabricate missing dependencies.
    result = dict(
        **protocol,
        results=rows,
        source_unchanged=code_hash() == source,
        complete=len(artifacts) == len(METHODS),
        elapsed_s=time.monotonic() - start,
        physical_qualification=False,
        confirmation=read(artifacts["confirm"]) if "confirm" in artifacts else None,
    )
    write_json(root / "report.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("runtime", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--budget", type=float, default=10800)
    a = p.parse_args()
    if not 300 <= a.budget <= 86400:
        p.error("Use a 300–86400 second budget")
    verify(
        DesignSpec.model_validate(read(a.input)),
        Runtime.model_validate(read(a.runtime)),
        a.output,
        a.budget,
    )
