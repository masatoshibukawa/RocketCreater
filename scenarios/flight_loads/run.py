"""Execute the numerical wind-tunnel -> flight -> section/design load chain."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rocketwright.physics.bottle_integrity import flight, loads, thermal  # noqa: E402
from rocketwright.physics.bottle_integrity.harness import write_json  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig  # noqa: E402
from rocketwright.physics.flight_loads import (  # noqa: E402
    MassDistribution,
    TunnelDatabase,
    envelopes,
    recover,
)
from rocketwright.schema import BottleDesign  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tunnel_checks(folder, table):
    def coeff(name):
        c = read(folder / name / "case.json")["mean"]
        return np.array([c[k] for k in ("Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z")])

    def change(a, b):
        return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-9))

    grid, table_error = {}, {}
    for angle in (0, 5, 90):
        fine = coeff(f"mesh32-a{angle:03}")
        grid[str(angle)] = change(coeff(f"mesh24-a{angle:03}"), fine)
        table_error[str(angle)] = change(coeff(f"v18-a{angle:03}"), fine)
    domain = change(coeff("width-a005"), coeff("v18-a005"))
    duration = change(coeff("long-a005"), coeff("v18-a005"))
    spec = read(folder / "table-config.json") if (folder / "table-config.json").exists() else {}
    holdout_speed = spec.get("holdout_speed_mps", 24)
    holdout_angle = spec.get("holdout_angle_deg", 10)
    holdout_case = spec.get("holdout_case", "holdout-v24-a010")
    value = table.coefficients(holdout_speed, holdout_angle)
    f = value[:, :3].sum(0)
    station = np.column_stack([table.stations, np.zeros((len(table.stations), 2))])
    cg = read(folder / "v18-a005/case.json")["cg_mm"] / 1000
    m = (np.cross(station - [cg, 0, 0], value[:, :3]) / table.diameter + value[:, 3:]).sum(0)
    interpolation = change(np.r_[f, m], coeff(holdout_case))
    integration = max(
        read(p)["integration_relative_residual"] for p in folder.glob("*/line-loads.json")
    )
    return {
        "grid24_to32": grid,
        "table16_to32": table_error,
        "width10_to14": domain,
        "duration40_to80": duration,
        "held_out_interpolation": interpolation,
        "held_out_case": holdout_case,
        "max_surface_integration_residual": integration,
        "criteria": {"grid": 0.05, "domain": 0.05, "duration": 0.03, "interpolation": 0.1},
        "pass": max(grid.values()) < 0.05
        and domain < 0.05
        and duration < 0.03
        and interpolation < 0.1,
        "scope": "six-component coefficient norm; numerical sensitivity, no physical validation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="Prior integrity input.json containing design/assembly/config"
    )
    parser.add_argument("tunnel", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--design-factor", type=float, default=1.5)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    packet = read(args.input)
    design, assembly = BottleDesign(**packet["design"]), packet["assembly"]
    config = AnalysisConfig(**packet["config"])
    config.flight.cant_deg = 0  # matches the simulated uncanted four-fin geometry
    table = TunnelDatabase(args.tunnel)
    representative = read(args.tunnel / "v18-a000/case.json")
    if representative["dimensions_mm"] != assembly["dimensions_mm"]:
        raise ValueError("Flight and CFD geometry do not match")
    checks = tunnel_checks(args.tunnel, table)
    write_json(args.output / "tunnel-checks.json", checks)
    warm = thermal.wait(design, config, sealed=True)
    warm_design = design.model_copy(
        update={
            "initial_gauge_pressure_pa": warm["peak_absolute_pressure_pa"] - config.loads.ambient_pa
        }
    )
    warm_config = config.loads.model_copy(
        update={
            "initial_k": warm["final_c"]["gas"] + 273.15,
            "initial_wall_k": warm["final_c"]["skin"] + 273.15,
            "ambient_k": 308.15,
        }
    )
    prop = {
        "nominal": loads.propulsion(design, config.loads),
        "warm": loads.propulsion(warm_design, warm_config),
    }
    write_json(args.output / "thermal.json", warm)
    write_json(args.output / "propulsion.json", prop)
    spread = max(
        *checks["table16_to32"].values(),
        checks["held_out_interpolation"],
        checks["width10_to14"],
        checks["duration40_to80"],
    )
    conditions = [
        ("nominal", design, prop["nominal"], {}, 1.0),
        ("calm", design, prop["nominal"], {"wind_mps": 0, "gust_mps": 0}, 1.0),
        ("crosswind", design, prop["nominal"], {"wind_mps": 4, "gust_mps": 2}, 1.0),
        ("warm", warm_design, prop["warm"], {}, 1.0),
        ("aero_upper", design, prop["nominal"], {}, 1 + spread),
        ("aero_lower", design, prop["nominal"], {}, max(0.05, 1 - spread)),
        ("low_damping", design, prop["nominal"], {"pitch_damping": 2}, 1.0),
        ("delayed_canopy", design, prop["nominal"], {"deployment_delay_s": 0.25}, 1.0),
    ]
    recovered, summaries = {}, {}
    for name, article, discharge, changes, scale in conditions:
        print("FLIGHT", name, flush=True)
        model = TunnelDatabase(args.tunnel, scale=scale)
        mass = MassDistribution(article, assembly, discharge)
        flight_cfg = config.flight.model_copy(update=changes)
        trajectory = flight.run(
            article,
            assembly,
            discharge,
            flight_cfg,
            aero_model=model,
            mass_model=mass,
            record_loads=True,
        )
        if not trajectory["completed"]:
            raise RuntimeError(f"Flight incomplete: {name}: {trajectory}")
        result = recover(trajectory, model, mass, discharge)
        residual = np.max(np.abs(result["equilibrium_residual"]), axis=0)
        if residual.max() > 1e-6:
            raise RuntimeError(f"Unbalanced section loads: {name}: {residual}")
        np.savez_compressed(
            args.output / f"{name}-sections.npz",
            **{k: result[k] for k in ("cuts_m", "time_s", "resultants", "equilibrium_residual")},
        )
        write_json(args.output / f"{name}-flight.json", trajectory)
        recovered[name] = result
        speed = np.array(
            [np.linalg.norm(s["air_velocity_body_mps"]) for s in trajectory["load_samples"]]
        )
        summaries[name] = {
            k: trajectory[k]
            for k in (
                "apogee_m",
                "apogee_s",
                "max_q_pa",
                "max_canopy_force_n",
                "impact_speed_mps",
                "ascent_incidence_deg",
                "drift_m",
            )
        }
        summaries[name].update(
            max_equilibrium_residual=residual.tolist(),
            max_mach=float(speed.max() / 343),
            max_acceleration_g=float(
                max(np.linalg.norm(s["proper_body_mps2"]) for s in trajectory["load_samples"])
                / 9.80665
            ),
            speed_clamped_samples=int(
                ((speed < model.speeds[0]) | (speed > model.speeds[-1])).sum()
            ),
            max_speed_mps=float(speed.max()),
            scale=scale,
        )
        if name == "nominal":
            finer = flight.run(
                article,
                assembly,
                discharge,
                flight_cfg,
                max_step=0.01,
                aero_model=model,
                mass_model=mass,
                record_loads=True,
            )
            finer_load = recover(finer, model, mass, discharge)
            coarse_envelope = envelopes({name: result})["envelopes"]
            fine_envelope = envelopes({name: finer_load})["envelopes"]
            difference = {
                key: abs(
                    max(r["limit"] for r in coarse_envelope[key])
                    / max(max(r["limit"] for r in fine_envelope[key]), 1e-8)
                    - 1
                )
                for key in coarse_envelope
            }
            # Zero torsion is exact by the imposed reflection symmetry.
            difference = {k: v for k, v in difference.items() if k != "torsion_nm"}
            summaries[name]["time_refinement"] = difference
    # Axial landing envelope: all impact velocity stopped over 5/15/30 mm.
    # This is an explicitly prescribed contact scenario, not a resolved tumbling impact.
    worst = max(summaries, key=lambda k: summaries[k]["impact_speed_mps"])
    velocity = summaries[worst]["impact_speed_mps"]
    mass = MassDistribution(design, assembly, prop["nominal"])
    t = float(prop["nominal"]["trace"]["time_s"][-1] + 60)
    total, cg, inertia = mass.properties(t)
    for distance in (0.005, 0.015, 0.03):
        acceleration = velocity**2 / (2 * distance) + 9.80665
        sample = {
            "time_s": t,
            "mass_kg": total,
            "cg_m": cg,
            "inertia_kg_m2": inertia,
            "air_velocity_body_mps": [0, 0, 0],
            "proper_body_mps2": [0, 0, acceleration],
            "angular_acceleration_rad_s2": [0, 0, 0],
            "omega_rad_s": [0, 0, 0],
            "thrust_n": 0,
            "canopy_body_n": [0, 0, 0],
            "rail_force_n": [0, 0, 0],
            "rail_moment_nm": [0, 0, 0],
            "transport_moment_nm": [0, 0, 0],
            "damping_moment_nm": [0, 0, 0],
            "ground_force_n": [0, 0, total * acceleration],
        }
        name = f"axial_landing_{1000 * distance:.0f}mm"
        result = recover({"load_samples": [sample]}, table, mass, prop["nominal"])
        recovered[name] = result
        np.savez_compressed(
            args.output / f"{name}-sections.npz",
            **{k: result[k] for k in ("cuts_m", "time_s", "resultants", "equilibrium_residual")},
        )
        summaries[name] = {
            "source_case": worst,
            "impact_speed_mps": velocity,
            "stop_distance_m": distance,
            "proper_acceleration_mps2": acceleration,
        }
    design_loads = envelopes(recovered, design_factor=args.design_factor)
    write_json(args.output / "design-loads.json", design_loads)
    sources = [
        args.input,
        Path(__file__),
        Path(flight.__file__),
        Path(__file__).parents[2] / "rocketwright/physics/flight_loads.py",
    ]
    summary = {
        "cases": summaries,
        "tunnel_checks": checks,
        "assumed_aero_spread": spread,
        "design_factor": args.design_factor,
        "units": "SI; forces N, moments N*m",
        "sources_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "maxima": {
            k: max(v, key=lambda r: r["limit"]) for k, v in design_loads["envelopes"].items()
        },
        "status": "conditional_simulations_complete",
        "physical_safety": "not_qualified",
        "limits": [
            "CFD numerical checks are independent of actual-material qualification",
            "mean rigid-geometry aero; no resolved moving-fin FSI or turbulent buffet",
            "azimuthal symmetry surrogate and engineering rotational damping",
            "BOM-based surrogate inertia; no slosh; nozzle-lumped angular transport",
            "pressure end-resultants use uniform reservoir membrane approximation",
            "canopy inflation prescribed; landing axis-aligned prescribed stopping distance",
            "assumed design margin; separate component maxima are not a concurrent load case",
        ],
    }
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary["maxima"], indent=2), flush=True)


if __name__ == "__main__":
    main()
