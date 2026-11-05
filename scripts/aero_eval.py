"""Evaluate the aerodynamics of a design JSON with one aero backend and print the AeroResult.

    uv run python scripts/aero_eval.py examples/designs/bottle.json --backend openfoam_pipeline \
        --speed 15 --aoa 0 4
    uv run python scripts/aero_eval.py examples/designs/amateur.json --backend barrowman
    uv run python scripts/aero_eval.py --status          # which backends are usable here
    uv run python scripts/aero_eval.py d.json --stl out.stl   # also write the airframe STL (m)

CFD results are cached per shape under $ROCKETWRIGHT_AERO_CACHE (~/.cache/rocketwright/aero).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rocketwright import aero
from rocketwright.geometry import airframe, write_stl
from rocketwright.schema import DesignAdapter


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("design", nargs="?", type=Path, help="design JSON (bottle or amateur)")
    p.add_argument("--backend", default="auto", choices=aero.BACKEND_NAMES)
    p.add_argument("--speed", type=float, default=15.0, help="free-stream speed, m/s")
    p.add_argument("--aoa", type=float, nargs="+", default=[0.0, 4.0], help="angles, deg")
    p.add_argument("--cg", type=float, default=None, help="CG from the nose, m (default: estimate)")
    p.add_argument(
        "--mesh-preset", choices=["coarse", "medium", "fine"], help="openfoam_pipeline mesh"
    )
    p.add_argument("--stl", type=Path, help="also write the airframe STL (metres) here")
    p.add_argument("--status", action="store_true", help="list backends and availability")
    args = p.parse_args(argv)
    if args.status:
        print(json.dumps(aero.status(), indent=2))
        return 0
    if args.design is None:
        p.error("design is required unless --status")
    design = DesignAdapter.validate_python(json.loads(args.design.read_text(encoding="utf-8")))
    if args.stl:
        write_stl(args.stl, airframe(design))
    query = aero.AeroQuery(
        design=design,
        speed_mps=args.speed,
        alphas_deg=tuple(args.aoa),
        cg_from_nose_m=args.cg,
        extra={"mesh_preset": args.mesh_preset} if args.mesh_preset else {},
    )
    result = aero.evaluate(query, backend=args.backend)
    out = result.model_dump(mode="json")
    out["cd_for_flight_model"] = aero.cd_for_physics(result, design)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
