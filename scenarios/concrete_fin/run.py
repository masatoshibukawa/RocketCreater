"""Reproduce one concrete candidate's tunnel, flight, load transfer and FEM study."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rocketwright.physics import fin_load_map, stability_theorems  # noqa: E402
from rocketwright.physics.bottle_integrity import fem, flight, loads, thermal  # noqa: E402
from rocketwright.physics.bottle_integrity.harness import write_json  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig  # noqa: E402
from rocketwright.physics.concrete_fin import write_candidate  # noqa: E402
from rocketwright.physics.fin_candidates import beam  # noqa: E402
from rocketwright.physics.flight_loads import MassDistribution, TunnelDatabase, recover  # noqa: E402
from rocketwright.schema import BottleDesign  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tunnel(folder, cells):
    target = folder / "tunnel"
    target.mkdir(exist_ok=False)
    spec = dict(speeds_mps=[8, 30], angles_deg=[0, 5, 10, 15, 45, 90, 135, 180])
    write_json(target / "table-config.json", spec)
    for speed in spec["speeds_mps"]:
        for angle in spec["angles_deg"]:
            command = [
                sys.executable,
                "-X",
                "utf8",
                str(ROOT / "scenarios/cfd/run_flow.py"),
                str(folder / "assembly.json"),
                str(target / f"v{speed:02}-a{angle:03}"),
                "--shape",
                "flat",
                "--wall",
                "interpolated",
                "--fin-thickness-mm",
                "1",
                "--cells",
                str(cells),
                "--width",
                "10",
                "--upstream",
                "3",
                "--times",
                "40",
                "--speed",
                str(speed),
                "--angle",
                str(angle),
                "--rotate-geometry",
                "--surface-loads",
                "--no-preview",
            ]
            if speed == 30 and angle == 5:
                command.append("--volume")
            subprocess.run(command, check=True, cwd=ROOT, timeout=2400)
    return target


def components(case):
    return np.array([case["mean"][k] for k in ("Cx", "Cy", "Cm_z")])


def aero_checks(folder, table):
    rows = [read(folder / f"grid-d{d}-a005/case.json") for d in (16, 24, 28)]
    floor = np.array([0.05, 0.05, 0.1])
    differences = [
        abs(components(a) - components(b)) / np.maximum(abs(components(b)), floor)
        for a, b in zip(rows[:-1], rows[1:], strict=True)
    ]
    case = rows[1]
    values = table.coefficients(18, 5)
    xyz = np.column_stack([table.stations - case["cg_mm"] / 1000, np.zeros((len(values), 2))])
    force = values[:, :3].sum(0)
    moment = (np.cross(xyz, values[:, :3]) / table.diameter + values[:, 3:]).sum(0)
    predicted = np.array([force[0], force[1], moment[2]])
    interpolation = abs(predicted - components(case)) / np.maximum(abs(components(case)), floor)
    return dict(
        observables=["Cx", "Cy", "Cm_z"],
        grid16_to24=differences[0].tolist(),
        grid24_to28=differences[1].tolist(),
        heldout_v18_a5=interpolation.tolist(),
        numerical_pass=bool(max(differences[1]) <= 0.05 and max(interpolation) <= 0.10),
        scope="component checks at one incidence; no global error bound, no physical validation",
        further_checks=[
            "other-angle grid study",
            "domain and duration checks",
            "independent validation",
        ],
    )


def fin_coefficients(folder, table):
    return np.array(
        [
            [
                read(folder / "tunnel" / f"v{s:02.0f}-a{a:03.0f}/case.json")["fin_coefficients"]
                for a in table.angles
            ]
            for s in table.speeds
        ]
    )


def interpolate_fin(data, table, speed, angle):
    speed, angle = np.clip(speed, table.speeds[0], table.speeds[-1]), np.clip(angle, 0, 180)
    i = min(max(np.searchsorted(table.speeds, speed) - 1, 0), len(table.speeds) - 2)
    j = min(max(np.searchsorted(table.angles, angle) - 1, 0), len(table.angles) - 2)
    u = (speed - table.speeds[i]) / (table.speeds[i + 1] - table.speeds[i])
    v = (angle - table.angles[j]) / (table.angles[j + 1] - table.angles[j])
    return (
        (1 - u) * (1 - v) * data[i, j]
        + u * (1 - v) * data[i + 1, j]
        + (1 - u) * v * data[i, j + 1]
        + u * v * data[i + 1, j + 1]
    )


def assess(folder, solver):
    output = folder / "assessment"
    output.mkdir(exist_ok=False)
    packet = read(folder / "input.json")
    design, assembly = BottleDesign(**packet["design"]), packet["assembly"]
    cfg = AnalysisConfig(**packet["config"])
    table = TunnelDatabase(folder / "tunnel")
    if (
        hashlib.sha256((folder / "assembly.json").read_bytes()).hexdigest()
        != table.metadata["geometry_sha256"]
    ):
        raise ValueError("CFD and structural assembly differ")
    checks = aero_checks(folder, table)
    write_json(output / "aero-checks.json", checks)
    prop = loads.propulsion(design, cfg.loads)
    warm = thermal.wait(design, cfg, sealed=True)
    warm["scope"] = (
        "unchanged lumped thermal network; scenario only, not validated for new laminate/shoes"
    )
    write_json(output / "thermal.json", warm)
    mass = MassDistribution(design, assembly, prop)
    fin_data = fin_coefficients(folder, table)
    summaries, events, trajectories = {}, [], {}
    conditions = {
        "nominal": {},
        "calm": {"wind_mps": 0, "gust_mps": 0},
        "crosswind": {"wind_mps": 4, "gust_mps": 2},
        "low_damping": {"pitch_damping": 2},
        "tilt_plus2": {"initial_tilt_deg": cfg.flight.initial_tilt_deg + 2},
    }
    for name, changes in conditions.items():
        print("FLIGHT", name, flush=True)
        trajectory = flight.run(
            design,
            assembly,
            prop,
            cfg.flight.model_copy(update=changes),
            aero_model=table,
            mass_model=mass,
            record_loads=True,
        )
        if not trajectory["completed"]:
            raise RuntimeError(f"Incomplete flight: {name}")
        trajectories[name] = trajectory
        write_json(output / f"{name}-flight.json", trajectory)
        section = recover(trajectory, table, mass, prop)
        residual = float(np.max(abs(section["equilibrium_residual"])))
        if residual > 1e-6:
            raise ValueError("Unbalanced recovered loads")
        np.savez_compressed(
            output / f"{name}-sections.npz",
            **{k: section[k] for k in ("cuts_m", "time_s", "resultants", "equilibrium_residual")},
        )
        summaries[name] = {
            k: trajectory[k]
            for k in (
                "apogee_m",
                "impact_speed_mps",
                "max_q_pa",
                "ascent_incidence_deg",
                "peak_roll_rad_s",
                "drift_m",
                "rail_exit_speed_mps",
            )
        }
        summaries[name]["section_equilibrium_residual"] = residual
        for sample in trajectory["load_samples"]:
            if not trajectory["rail_exit_s"] <= sample["time_s"] <= trajectory["apogee_s"]:
                continue
            velocity = np.asarray(sample["air_velocity_body_mps"])
            speed = np.linalg.norm(velocity)
            angle = np.degrees(np.arctan2(np.linalg.norm(velocity[:2]), velocity[2]))
            q = 0.5 * 1.204 * speed**2
            value = interpolate_fin(fin_data, table, speed, angle)
            for blade, row in enumerate(value):
                normal = (row[2], -row[1], -row[2], row[1])[blade]
                radial_moment = (row[4], row[5], -row[4], -row[5])[blade]
                if abs(normal) < 1e-6:
                    continue
                events.append(
                    dict(
                        condition=name,
                        time_s=sample["time_s"],
                        blade=blade,
                        force_n=abs(q * table.area * normal),
                        root_bending_nm=abs(q * table.area * table.diameter * row[3]),
                        centroid_m=[
                            -radial_moment / normal * table.diameter,
                            row[3] / normal * table.diameter,
                        ],
                        q_pa=q,
                        incidence_deg=angle,
                        speed_mps=speed,
                    )
                )
    write_json(output / "flights.json", summaries)
    baseline, perturbed = trajectories["nominal"], trajectories["tilt_plus2"]
    shared = np.linspace(
        max(baseline["rail_exit_s"], perturbed["rail_exit_s"]),
        min(baseline["apogee_s"], perturbed["apogee_s"]),
        201,
    )
    axes = []
    for item in (baseline, perturbed):
        trace = item["trace"]
        directions = np.array([flight.rotation(quat)[:, 2] for quat in trace["quaternion"]])
        values = np.column_stack(
            [np.interp(shared, trace["time_s"], directions[:, j]) for j in range(3)]
        )
        axes.append(values / np.linalg.norm(values, axis=1)[:, None])
    difference = np.degrees(np.arccos(np.clip((axes[0] * axes[1]).sum(1), -1, 1)))
    write_json(
        output / "finite-perturbation.json",
        dict(
            initial_tilt_change_deg=2,
            time_s=shared.tolist(),
            axis_difference_deg=difference.tolist(),
            entry_difference_deg=float(difference[0]),
            final_difference_deg=float(difference[-1]),
            peak_difference_deg=float(difference.max()),
            final_to_entry_ratio=float(difference[-1] / max(difference[0], 1e-9)),
            scope="one finite nonlinear perturbation on common ascent times; not asymptotic proof",
        ),
    )
    stability = stability_theorems.flight_screen(
        assembly, trajectories["nominal"], table, mass, cfg.flight
    )
    write_json(output / "stability-theorems.json", stability)
    if stability["completed"]:
        row = stability["frozen_checks"][len(stability["frozen_checks"]) // 2]
        stability_theorems.campaign(
            output / "frozen-selection",
            dict(
                kind="frozen_pitch",
                unforced=True,
                scope="one frozen air-aligned operating point",
                parameters=dict(
                    inertia=row["inertia_kg_m2"],
                    stiffness=row["stiffness_nm_rad"],
                    damping=row["damping_nm_s_rad"],
                ),
            ),
        )
        stability_theorems.campaign(
            output / "scheduled-selection",
            dict(
                kind="piecewise_affine_pitch",
                parameters=stability["scheduled_model"],
                scope="finite ascent reduction; not the full nonlinear rocket",
            ),
        )
    # Retain both force- and moment-governing actual simultaneous resultants.
    governing = [max(events, key=lambda e: e[k]) for k in ("force_n", "root_bending_nm")]
    write_json(output / "fin-events.json", governing)
    results = []
    temperature = max(45.0, warm["final_c"]["fin"])
    g = assembly["dimensions_mm"]
    material = cfg.fin_material
    modulus = material.young_pa * np.interp(
        temperature, [material.reference_c, material.warm_c], [1, material.warm_ratio]
    )
    modes = []
    for factor in (0.25, 1, 4):
        response = beam(
            g["fin_span"] / 1000,
            g["fin_root"] / 1000,
            g["fin_tip"] / 1000,
            cfg.fin_thickness_m,
            modulus,
            material.density,
            cfg.fin_root_k_n_m * factor,
            governing[0]["force_n"],
            tab=g["fin_tab"] / 1000,
            n=40,
        )
        modes.append(
            dict(
                root_stiffness_factor=factor,
                first_modes_hz=response["first_modes_hz"],
                linear_deflection_m=response["max_deflection_m"],
            )
        )
    write_json(
        output / "modal-screen.json",
        dict(
            cases=modes,
            temperature_c=temperature,
            scope="bending beam with root compliance; no torsion, flight damping, flutter or slosh",
        ),
    )
    for number, event in enumerate(governing):
        if number and event == governing[0]:
            continue
        history = []
        for resolution in (2, 3, 4):
            print("FEM", number, resolution, flush=True)
            lines, nodes, elements, meta = fin_load_map.deck(
                assembly,
                cfg,
                event["force_n"],
                event["centroid_m"],
                resolution=resolution,
                temperature_c=temperature,
            )
            result = fem.run_deck(solver, output / f"fin{number}-mesh{resolution}", "fin", lines)
            write_json(output / f"fin{number}-mesh{resolution}/result.json", result)
            write_json(output / f"fin{number}-mesh{resolution}/mapping.json", meta)
            history.append(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("node_displacements_m", "integration_stress_pa")
                }
            )
            if len(history) > 1:
                error = {
                    k: abs(history[-2][k] / result[k] - 1)
                    for k in ("max_displacement_m", "p95_integration_vm_pa")
                }
                if max(error.values()) < 0.05:
                    break
        results.append(
            dict(
                event=event,
                meshes=history,
                mesh_change=error,
                numerical_pass=max(error.values()) < 0.05,
                temperature_c=temperature,
                material_allowable=None,
            )
        )
    write_json(output / "structure.json", results)
    write_json(
        output / "status.json",
        dict(
            executed=True,
            numerical_aero_pass=checks["numerical_pass"],
            altitude_target_m=30,
            nominal_altitude_pass=summaries["nominal"]["apogee_m"] >= 30,
            hardware_qualification=False,
            source_input_sha256=hashlib.sha256((folder / "input.json").read_bytes()).hexdigest(),
            limitations=[
                "CFD remains unvalidated",
                "normal-load structural surrogate, not full FSI",
                "joint stiffness is geometric estimate; bolt/contact/strap strength unknown",
                "thin-sheet and warm material properties unverified",
                "other hardware unchanged and unqualified",
            ],
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["prepare", "tunnel", "assess"])
    p.add_argument("folder", type=Path)
    p.add_argument("--input", type=Path)
    p.add_argument("--cells", type=int, default=24)
    p.add_argument("--solver", type=Path)
    args = p.parse_args()
    if args.phase == "prepare":
        write_candidate(read(args.input), args.folder)
    elif args.phase == "tunnel":
        tunnel(args.folder.resolve(), args.cells)
    else:
        assess(args.folder.resolve(), args.solver.resolve())


if __name__ == "__main__":
    main()
