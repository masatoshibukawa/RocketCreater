"""Reproduce the bottle CFD study and compare forces against the flight-model input."""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import savemat
from scipy.optimize import brentq

from rocketwright.physics.water import simulate
from rocketwright.schema import BottleDesign, Env

# GPU cases run serially. Names identify the exact runs used in the report.
R03_OPTIONS = "--shape rounded_flat --speed 20 --nu 1.5382e-5 --cells 24 --times 48"
CASES = {
    "empty": "--shape empty --cells 8 --times 3",
    "sphere16": "--shape sphere --cells 16 --times 40",
    "sphereWide": "--shape sphere --cells 16 --width 14 --upstream 7 --times 40",
    "sphereHigh": "--shape sphere --sphere-re 90000 --cells 24 --times 32",
    "r03": R03_OPTIONS,
    "r03Paired": R03_OPTIONS + " --paired-samples",
    "rocket10": "--cells 10 --times 32",
    "rocket16": "--cells 16 --times 48",
    "rocket24": "--cells 24 --times 48",
    "rocket32": "--cells 32 --times 48",
    "rocket40": "--cells 40 --times 48 --volume",
    "wide": "--cells 16 --width 12 --times 48",
    "flat": "--shape flat --cells 16 --times 48",
    "flat24": "--shape flat --cells 24 --times 48",
    "paired24": "--cells 24 --times 48 --paired-samples",
    "plus5": "--cells 16 --angle 5 --times 48",
    "minus5": "--cells 16 --angle -5 --times 48",
    "plus5fine": "--cells 24 --angle 5 --times 48",
    "minus5fine": "--cells 24 --angle -5 --times 48",
    "cantPlus": "--cells 16 --cant 3 --times 48",
    "cantMinus": "--cells 16 --cant -3 --times 48",
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prototype", type=Path, help="completed manufacturing packet")
    p.add_argument("root", type=Path, help="new case root for --run, or a completed case root")
    p.add_argument("--run", action="store_true", help="compute all cases before analysis")
    p.add_argument("--no-preview", action="store_true", help="skip live images during the suite")
    args = p.parse_args()
    assembly = json.loads((args.prototype / "assembly.json").read_text(encoding="utf-8"))
    design = BottleDesign.model_validate_json((args.prototype / "design.json").read_bytes())
    flight = json.loads((args.prototype / "run.json").read_text(encoding="utf-8"))
    env = Env.model_validate(flight["environment"])
    reference_file = Path(__file__).with_name("r03_reference.json")
    reference = json.loads(reference_file.read_text(encoding="utf-8"))
    if args.run:
        args.root.mkdir(parents=True, exist_ok=False)
        for position, (name, options) in enumerate(CASES.items(), 1):
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("run_flow.py")),
                    str(
                        reference_file
                        if name.startswith("r03")
                        else args.prototype / "assembly.json"
                    ),
                    str(args.root / name),
                    *(
                        ["--no-preview"]
                        if args.no_preview
                        else ["--study-position", str(position), str(len(CASES))]
                    ),
                    *options.split(),
                    *([] if "--paired-samples" in options.split() else ["--no-paired-samples"]),
                ],
                check=True,
            )
    rows = {k: json.loads((args.root / k / "case.json").read_text(encoding="utf-8")) for k in CASES}

    def height(cd):
        candidate = design.model_copy(update={"axial_drag_coefficient": float(cd)})
        return simulate(candidate, env).metrics["apogee_m"]

    with (args.root / "coefficients.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case",
                "cells_per_D",
                "Re",
                "angle_deg",
                "cant_deg",
                "width_D",
                "Cd",
                "Cl",
                "Cy",
                "Croll",
                "Cm_z",
                "Cd_window_shift",
                "nominal_height_m_if_constant_Cd",
            ]
        )
        for name, r in rows.items():
            m = r["mean"]
            expected = reference if name.startswith("r03") else assembly
            if r["assembly"] != expected["key"] or r["dimensions_mm"] != expected["dimensions_mm"]:
                raise ValueError(f"{name} does not match the supplied assembly")
            if r["cg_mm"] != expected["loaded_cg_mm"] or r["prior_cd"] != expected["axial_cd"]:
                raise ValueError(f"{name} has a different moment reference or nominal design")
            writer.writerow(
                [
                    name,
                    r["d"],
                    r["Re"],
                    r["angle_deg"],
                    r["cant_deg"],
                    r["width_D"],
                    m["Cd"],
                    m["Cl"],
                    m["Cy"],
                    m["Croll"],
                    m["Cm_z"],
                    r["split_window_difference"]["Cd"],
                    height(m["Cd"]) if name.startswith("rocket") else "",
                ]
            )
    fine = rows["rocket40"]
    drag = fine["mean"]["Cd"]
    grid_delta = abs(rows["rocket32"]["mean"]["Cd"] - drag) / drag
    width_delta = abs(rows["wide"]["mean"]["Cd"] / rows["rocket16"]["mean"]["Cd"] - 1)
    window_delta = abs(fine["split_window_difference"]["Cd"]) / drag
    sphere_error = abs(rows["sphereWide"]["mean"]["Cd"] / 1.0917 - 1)
    empty = np.load(args.root / "empty" / "slice.npz")
    uniform_error = float(np.max(np.abs(empty["ux_U"] - 1)))
    sphere = rows["sphereWide"]
    center = np.load(args.root / "sphereWide" / "slice.npz")["ux_U"][sphere["grid"][1] // 2]
    x = (np.arange(len(center)) + 0.5) / sphere["d"] - sphere["upstream_D"]
    roots = np.flatnonzero((x[:-1] > 1) & (center[:-1] < 0) & (center[1:] >= 0))
    wake_length = None
    if len(roots):
        j = roots[0]
        wake_length = float(x[j] - 1 - center[j] * (x[j + 1] - x[j]) / (center[j + 1] - center[j]))
    cp_estimates = {}
    for label, plus, minus in [("16", "plus5", "minus5"), ("24", "plus5fine", "minus5fine")]:
        pos, neg = rows[plus]["mean"], rows[minus]["mean"]
        delta_m = pos["Cm_z"] - neg["Cm_z"]
        delta_f = pos["Cy"] - neg["Cy"]
        cp_estimates[label] = (
            assembly["loaded_cg_mm"] + fine["dimensions_mm"]["body_diameter"] * delta_m / delta_f
        )
    gates = dict(
        sample_parity_at_24=abs(rows["paired24"]["mean"]["Cd"] / rows["rocket24"]["mean"]["Cd"] - 1)
        <= 0.05,
        uniform_flow=uniform_error < 1e-4 and rows["empty"]["mean"]["Cd"] == 0,
        sphere_control=sphere_error <= 0.10,
        grid=grid_delta <= 0.05,
        width_at_16=width_delta <= 0.05,
        time_at_finest=window_delta <= 0.03,
    )
    audit = dict(
        fixed_flat_geometry_change_16_to_24=rows["flat"]["mean"]["Cd"]
        / rows["flat24"]["mean"]["Cd"]
        - 1,
        tunnel_reference_cd=reference["measured_cd"],
        tunnel_single_sample_cd=rows["r03"]["mean"]["Cd"],
        tunnel_reconstruction_cd=rows["r03Paired"]["mean"]["Cd"],
        tunnel_relative_error=rows["r03Paired"]["mean"]["Cd"] / reference["measured_cd"] - 1,
        model_cd=design.axial_drag_coefficient,
        model_height_m=height(design.axial_drag_coefficient),
        finest_cd=drag,
        finest_height_if_constant_cd_m=height(drag),
        constant_cd_at_mission_floor=brentq(lambda c: height(c) - 27, 0.01, 3),
        relative_change_grid=grid_delta,
        relative_change_width=width_delta,
        relative_change_time=window_delta,
        sphere_relative_error=sphere_error,
        sphere_wake_length_D=wake_length,
        empty_velocity_error=uniform_error,
        effective_cp_mm=cp_estimates,
        checks=gates,
        numerical_checks_pass=all(gates.values()),
        tunnel_within_20_percent=abs(rows["r03Paired"]["mean"]["Cd"] / reference["measured_cd"] - 1)
        <= 0.20,
        transfer_to_flight="diagnostic_only",
        hardware_validation="not_measured",
    )
    (args.root / "assessment.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    field = np.load(args.root / "rocket40" / "slice.npz")
    volume = np.load(args.root / "rocket40" / "volume.npz")
    savemat(
        args.root / "plot-data.mat",
        dict(
            ux=field["ux_U"],
            solid=field["solid"],
            volume=volume["ux_U"],
            interior=volume["solid"],
            stride=float(volume["stride"]),
            d=float(fine["d"]),
            upstream=fine["upstream_D"],
            grid=fine["grid"],
            prior=design.axial_drag_coefficient,
            grids=[rows[f"rocket{n}"]["mean"]["Cd"] for n in [10, 16, 24, 32, 40]],
            dims=fine["dimensions_mm"],
        ),
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
