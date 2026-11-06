"""Run the flight -> CFD -> Cd -> flight -> design loop (docs/aero.md section 7) and print it.

    # a workbench candidate, on its assembled airframe (real fins, real CG)
    uv run python scripts/aero_loop.py --action D02/9/325/25/carton_wide \
        --backend openfoam_pipeline
    # any bottle design JSON, on the representative airframe
    uv run python scripts/aero_loop.py examples/designs/bottle.json --target 30 --backend barrowman

CFD results are cached per shape and speed under $ROCKETWRIGHT_AERO_CACHE, so repeating a run
is immediate. --json writes the whole result. The design files are not changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rocketwright import aero
from rocketwright.bottle_assembly import Workshop
from rocketwright.bottle_candidates import ENV, PRESSURE_KPA
from rocketwright.bottle_search import TARGET, Action, Search
from rocketwright.geometry import assembled_shape
from rocketwright.schema import DesignAdapter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSHOP = ROOT / "scenarios" / "bottle_empty_workshop.json"


def _candidate(key: str, workshop_path: Path) -> dict:
    """Loop inputs of `start/nozzle/pressure/fill/variant`, as the workbench builds them."""
    try:
        start, nozzle, pressure, fill, variant = key.split("/")
        action = Action("confirm", start, int(nozzle), int(pressure), int(fill), variant)
    except ValueError:
        raise SystemExit(
            f"--action must be start/nozzle/pressure/fill/variant, got {key}"
        ) from None
    workshop = Workshop.model_validate_json(workshop_path.read_bytes())
    search = Search("references", workshop)
    design = search.design(action)
    plan = search.plan(action, design)
    return {
        "design": design,
        "env": search.env,
        "shape": assembled_shape(plan["dimensions_mm"]),
        "cg_from_nose_m": plan["wet_cg_mm"] / 1000,
        "pressures_kpa": [p for p in PRESSURE_KPA if p <= workshop.pressure_ceiling_kpa],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("design", nargs="?", type=Path, help="bottle design JSON")
    source.add_argument("--action", help="workbench candidate: start/nozzle/pressure/fill/variant")
    p.add_argument("--workshop", type=Path, default=DEFAULT_WORKSHOP, help="with --action")
    p.add_argument("--target", type=float, default=TARGET, help="target apogee, m")
    p.add_argument("--backend", default="auto", choices=aero.BACKEND_NAMES)
    p.add_argument("--pressures", type=float, nargs="+", help="candidate pressures, kPa")
    p.add_argument("--max-rounds", type=int, default=6)
    p.add_argument("--mesh-preset", choices=["coarse", "medium", "fine"])
    p.add_argument("--json", type=Path, help="also write the whole result here")
    args = p.parse_args(argv)
    if args.action:
        inputs = _candidate(args.action, args.workshop)
    else:
        design = DesignAdapter.validate_python(json.loads(args.design.read_text(encoding="utf-8")))
        inputs = {"design": design, "env": ENV, "pressures_kpa": PRESSURE_KPA}
    if args.pressures:
        inputs["pressures_kpa"] = args.pressures
    result = aero.run_aero_loop(
        inputs.pop("design"),
        inputs.pop("env"),
        target_apogee_m=args.target,
        backend=args.backend,
        max_rounds=args.max_rounds,
        extra={"mesh_preset": args.mesh_preset} if args.mesh_preset else None,
        **inputs,
    )
    for r in result.rounds:
        x_cp = "n/a" if r.x_cp_from_nose_m is None else f"{r.x_cp_from_nose_m * 1000:.0f} mm"
        margin = "n/a" if r.static_margin_cal is None else f"{r.static_margin_cal:+.2f} cal"
        print(
            f"round {r.round}: {r.flight_pressure_kpa:.0f} kPa, Cd {r.flight_cd:.3f} -> "
            f"apogee {r.flight_apogee_m:.2f} m, top speed {r.max_speed_mps:.1f} m/s | "
            f"{r.backend} at {r.cfd_speed_mps:.0f} m/s: Cd {r.cd:.3f}, x_cp {x_cp}, "
            f"margin {margin} ({r.elapsed_s:.0f} s{', cached' if r.cached else ''}) | "
            f"{r.pressure_kpa:.0f} kPa -> apogee {r.apogee_m:.2f} m, "
            f"descent {r.descent_speed_mps:.2f} m/s",
            flush=True,
        )
    print("converged" if result.converged else "NOT converged")
    for note in result.notes:
        print(f"note: {note}")
    if result.artifacts_dir:
        print(f"artifacts: {result.artifacts_dir}")
    if args.json:
        args.json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return 0 if result.converged else 1


if __name__ == "__main__":
    sys.exit(main())
