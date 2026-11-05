"""Run a traceable numeric wind tunnel; never substitute simulation for measured evidence."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cells", type=int, default=16)
    parser.add_argument("--times", type=float, default=40)
    parser.add_argument("--checks-only", action="store_true")
    parser.add_argument("--refine-incidence", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    driver = root / "scenarios/cfd/run_flow.py"
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = []
    if not args.checks_only:
        for speed in (8, 18, 30):
            for angle in (0, 5, 15, 45, 90, 135, 180):
                jobs.append((f"v{speed:02}-a{angle:03}", args.cells, speed, angle, 10, args.times))
    # Independent discretization/domain/time/velocity interpolation checks.
    for cells in (24, 32):
        for angle in (0, 5, 90):
            jobs.append((f"mesh{cells}-a{angle:03}", cells, 18, angle, 10, args.times))
    jobs += [
        ("width-a005", 16, 18, 5, 14, args.times),
        ("long-a005", 16, 18, 5, 10, 2 * args.times),
        ("holdout-v24-a010", 16, 24, 10, 10, args.times),
    ]
    if args.refine_incidence:
        jobs = [
            (f"v{speed:02}-a010", args.cells, speed, 10, 10, args.times) for speed in (8, 18, 30)
        ]
        jobs.append(("holdout-v24-a012", args.cells, 24, 12, 10, args.times))
    fingerprint = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (driver, driver.with_name("bottle_flow.cu"), args.assembly)
    }
    manifest_file = args.output / "tunnel-run.json"
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest["source_hashes"] != fingerprint:
            raise ValueError("Source/input changed; use a new run directory")
    else:
        manifest = {"source_hashes": fingerprint, "cases": {}, "physical_validation": False}
    for name, cells, speed, angle, width, duration in jobs:
        target = args.output / name
        if name in manifest["cases"]:
            expected = manifest["cases"][name]["case_sha256"]
            if hashlib.sha256((target / "case.json").read_bytes()).hexdigest() != expected:
                raise ValueError(f"Cached result changed: {name}")
            continue
        command = [
            sys.executable,
            str(driver),
            str(args.assembly.resolve()),
            str(target.resolve()),
            "--shape",
            "flat",
            "--cells",
            str(cells),
            "--width",
            str(width),
            "--times",
            str(duration),
            "--speed",
            str(speed),
            "--angle",
            str(angle),
            "--rotate-geometry",
            "--surface-loads",
            "--no-preview",
        ]
        print(f"TUNNEL {name} ({cells} cells/D)", flush=True)
        subprocess.run(command, cwd=root, check=True, timeout=1800)
        result = json.loads((target / "case.json").read_text(encoding="utf-8"))
        manifest["cases"][name] = {
            "case_sha256": hashlib.sha256((target / "case.json").read_bytes()).hexdigest(),
            "seconds": result["seconds"],
        }
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.refine_incidence:
        angles = [0, 5, 10, 15, 45, 90, 135, 180]
        for speed in (8, 18, 30):
            for angle in angles:
                if not (args.output / f"v{speed:02}-a{angle:03}/case.json").exists():
                    raise ValueError("Refined table has missing base cases")
        (args.output / "table-config.json").write_text(
            json.dumps(
                {
                    "speeds_mps": [8, 18, 30],
                    "angles_deg": angles,
                    "holdout_case": "holdout-v24-a012",
                    "holdout_speed_mps": 24,
                    "holdout_angle_deg": 12,
                    "reason": "25.2% held-out error at 10 degrees triggered incidence refinement",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print("TUNNEL COMPLETE", flush=True)


if __name__ == "__main__":
    main()
