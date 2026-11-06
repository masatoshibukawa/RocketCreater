#!/usr/bin/env python
"""Size a launcher for a satellite: uv run python scripts/from_satellite.py launch_request.json"""

from __future__ import annotations

import argparse
from pathlib import Path

from rocketwright.launch_request import load_launch_request, size_launcher


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path, help="write the full result as JSON")
    args = parser.parse_args()
    result = size_launcher(load_launch_request(args.request))
    m = result.metrics
    print(f"{result.satellite_name}: {result.reference_id} based, {result.engine_count} engines")
    print(f"liftoff mass {m['total_liftoff_mass_kg']:,.0f} kg")
    print(f"orbit {m['perigee_m'] / 1000:.1f} x {m['apogee_m'] / 1000:.1f} km")
    print(f"payload margin {m['payload_margin_kg']:.1f} kg, max q {m['max_q_pa'] / 1000:.1f} kPa")
    print(f"cost {result.cost_jpy:,.0f} JPY, success rate {result.success_rate:.2f}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    if args.output:
        args.output.write_text(result.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
