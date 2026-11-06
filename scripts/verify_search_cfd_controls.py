"""Run the production GPU kernels on wall-unit and Re=100 sphere controls."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json

ROOT = Path(__file__).resolve().parents[1]


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    control = subprocess.run(
        [sys.executable, str(ROOT / "scenarios/cfd/check_wall.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    write_json(root / "wall.json", json.loads(control.stdout.strip().splitlines()[-1]))
    cases = []
    for cells in (12, 16, 20):
        folder = root / f"sphere-{cells}"
        command = [
            sys.executable,
            str(ROOT / "scenarios/cfd/run_flow.py"),
            str(ROOT / "scenarios/cfd/r03_reference.json"),
            str(folder),
            "--shape",
            "sphere",
            "--sphere-re",
            "100",
            "--wall",
            "interpolated",
            "--cells",
            str(cells),
            "--width",
            "12",
            "--upstream",
            "6",
            "--times",
            "60",
            "--surface-loads",
            "--no-preview",
        ]
        with (root / f"sphere-{cells}.log").open("w", encoding="utf-8") as log:
            subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=True
            )
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        cases.append(case)
        print(json.dumps(dict(cells=cells, cd=case["mean"]["Cd"])), flush=True)
    reference = 24 / 100 * (1 + 0.15 * 100**0.687)
    cd = [r["mean"]["Cd"] for r in cases]
    report = dict(
        wall=json.loads(control.stdout.strip().splitlines()[-1]),
        source="https://mfix.netl.doe.gov/doc/mfix-exa/guide/latest/tutorials/fluid/steady-flow-around-sphere.html",
        reference_kind="Schiller-Naumann correlation; not an exact solution or rocket experiment",
        reference_cd=reference,
        limits=dict(correlation_relative=0.05, successive_grid_relative=0.05),
        cases=cases,
        correlation_relative_error=[abs(v / reference - 1) for v in cd],
        successive_grid_relative=[abs(a - b) / abs(b) for a, b in zip(cd, cd[1:], strict=False)],
        elapsed_s=time.monotonic() - start,
        rocket_validation=False,
        limitations=[
            "Periodic transverse boundaries differ from the reference tutorial",
            "Only the low-Re sphere and wall implementation are checked",
            "No high-Re rocket wall-layer accuracy or experimental agreement is inferred",
        ],
    )
    write_json(root / "report.json", report)
    write_json(
        root / "manifest.json",
        {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*") if p.is_file()},
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = run(args.output.resolve())
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}))


if __name__ == "__main__":
    main()
