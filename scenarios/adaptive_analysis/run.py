"""Execute registered adaptive follow-up analyses on the existing bottle candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rocketwright.adaptive import Campaign, Requirements, digest  # noqa: E402
from rocketwright.physics.bottle_integrity import aeroelastic, fem, flight, loads  # noqa: E402
from rocketwright.physics.bottle_integrity.harness import write_json  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig, Material  # noqa: E402
from rocketwright.physics.fin_candidates import PROFILES, beam, reconcile_mass  # noqa: E402
from rocketwright.physics.flight_loads import MassDistribution, TunnelDatabase  # noqa: E402
from rocketwright.schema import BottleDesign  # noqa: E402

COMPONENTS = ("Cx", "Cy", "Cz", "Croll", "Cpitch_y", "Cm_z")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vector(case):
    return np.array([case["mean"][k] for k in COMPONENTS])


def comparison(value, reference):
    # Absolute floors avoid relative noise at symmetry-zero coefficients.
    floor = np.array([0.1, 0.1, 0.1, 0.05, 0.05, 0.1])
    return dict(
        norm=float(np.linalg.norm(value - reference) / max(np.linalg.norm(reference), 1e-9)),
        components=dict(
            zip(
                COMPONENTS,
                (abs(value - reference) / np.maximum(abs(reference), floor)).tolist(),
                strict=True,
            )
        ),
    )


class ComponentAero:
    """Scale force components and moment about the instantaneous CG independently.

    Used only for sensitivity; no claim of a realizable pressure distribution.
    """

    def __init__(self, base, axial=1, normal=1, moment=1):
        self.base, self.axial, self.normal, self.moment = base, axial, normal, moment
        self.speeds = base.speeds
        self.metadata = dict(
            base.metadata,
            component_scales=[axial, normal, moment],
            scope="independent force/moment sensitivity only",
        )

    def evaluate(self, velocity, q, cg):
        result = self.base.evaluate(velocity, q, cg)
        result["force_n"] = result["force_n"] * [self.normal, self.normal, self.axial]
        result["moment_nm"] = result["moment_nm"] * self.moment
        return result


class Adapters:
    def __init__(self, packet, tunnel, prior, solver, assembly_path):
        self.packet, self.tunnel, self.prior = packet, tunnel, prior
        self.design = BottleDesign(**packet["design"])
        self.assembly = packet["assembly"]
        self.config = AnalysisConfig(**packet["config"])
        self.config.flight.cant_deg = 0
        self.solver, self.assembly_path = solver, assembly_path
        self.table = TunnelDatabase(tunnel)
        self.propulsion = loads.propulsion(self.design, self.config.loads)
        self.baseline = None

    def run_flight(self, output, name, *, design=None, assembly=None, aero=None, config=None):
        design, assembly = design or self.design, assembly or self.assembly
        prop = (
            self.propulsion
            if design == self.design
            else loads.propulsion(design, self.config.loads)
        )
        result = flight.run(
            design,
            assembly,
            prop,
            config or self.config.flight,
            aero_model=aero or self.table,
            mass_model=MassDistribution(design, assembly, prop),
        )
        if not result["completed"]:
            raise RuntimeError(f"Incomplete trajectory: {name}")
        write_json(output / (name + "-flight.json"), result)
        return result

    def audit(self, params, output, host):
        summary = read(self.prior / "summary.json")
        rows = {}
        for angle in (0, 5, 90):
            cases = [read(self.tunnel / f"mesh{n}-a{angle:03}/case.json") for n in (24, 32)]
            rows[str(angle)] = comparison(vector(cases[0]), vector(cases[1]))
        windows = {}
        for name in ("v18-a005", "holdout-v24-a012", "mesh32-a005"):
            case = read(self.tunnel / name / "case.json")
            values = np.genfromtxt(self.tunnel / name / "history.csv", delimiter=",", names=True)
            selected = values[values["tU_D"] > max(values["tU_D"]) / 2]
            blocks = np.array_split(np.column_stack([selected[k] for k in COMPONENTS]), 4)
            windows[name] = dict(
                block_means=[b.mean(0).tolist() for b in blocks],
                split_drift=comparison(
                    vector(case)
                    + np.array([case["split_window_difference"][k] for k in COMPONENTS]),
                    vector(case),
                ),
            )
        g = self.assembly["dimensions_mm"]
        volume = (
            4
            * self.config.fin_thickness_m
            * (
                (g["fin_root"] + g["fin_tip"]) * g["fin_span"] / 2e6
                + g["fin_root"] * g["fin_tab"] / 1e6
            )
        )
        solid_mass = volume * (self.config.fin_material or self.config.material).density
        bom_mass = next(
            b["mass_g"] / 1000 for b in self.assembly["bill"] if b["id"] == "carton_fin"
        )
        return dict(
            grid_components=rows,
            window_diagnostics=windows,
            fin_mass_reconciliation=dict(
                solid_assumption_kg=solid_mass, bom_kg=bom_mass, difference_kg=solid_mass - bom_mass
            ),
            metrics=dict(
                aero_error=max(summary["tunnel_checks"]["grid24_to32"].values())
                / host.requirements.grid_relative_limit,
                altitude_shortfall=max(
                    0, host.requirements.altitude_target_m - summary["cases"]["nominal"]["apogee_m"]
                ),
                fin_flexibility=5,
                stability_unknown=1,
            ),
            scope=(
                "Component comparisons and block drift are diagnostics, not "
                "statistical confidence bounds"
            ),
        )

    def cfd(self, params, output, host):
        records = []
        for angle in params["angles"]:
            folder = output / f"a{angle:03}"
            command = [
                sys.executable,
                str(ROOT / "scenarios/cfd/run_flow.py"),
                str(self.assembly_path),
                str(folder),
                "--shape",
                "flat",
                "--cells",
                str(params["cells"]),
                "--speed",
                str(params["speed"]),
                "--angle",
                str(angle),
                "--width",
                "10",
                "--times",
                str(params["times"]),
                "--lattice-speed",
                str(params["lattice_speed"]),
                "--rotate-geometry",
                "--surface-loads",
                "--no-preview",
            ]
            print("CFD", params["kind"], angle, flush=True)
            try:
                subprocess.run(command, cwd=ROOT, check=True, timeout=1800)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise RuntimeError(f"CFD case failed: {folder.name}") from error
            case = read(folder / "case.json")
            records.append(
                dict(
                    angle=angle,
                    case=case,
                    file=str(folder.relative_to(host.output) / "case.json"),
                    sha256=file_hash(folder / "case.json"),
                )
            )
        return dict(cases=records, parameters=params, physical_validation=False)

    def sensitivity(self, params, output, host):
        self.baseline = self.run_flight(output, "baseline")
        base = self.baseline["apogee_m"]
        rows, derivatives = [], []
        for component in ("axial", "normal", "moment"):
            samples = {}
            for change in (-0.1, -0.05, 0.05, 0.1):
                result = self.run_flight(
                    output,
                    f"{component}-{change:+.2f}",
                    aero=ComponentAero(self.table, **{component: 1 + change}),
                )
                samples[change] = result["apogee_m"]
            d5 = (samples[0.05] - samples[-0.05]) / 0.1
            d10 = (samples[0.1] - samples[-0.1]) / 0.2
            derivatives.append(max(abs(d5), abs(d10)))
            rows.append(
                dict(
                    component=component,
                    apogees={str(k): v for k, v in samples.items()},
                    derivative_5pct_m=d5,
                    derivative_10pct_m=d10,
                    central_curvature_m=(samples[0.1] + samples[-0.1] - 2 * base) / 0.01,
                )
            )
        sensitivity = sum(derivatives)
        allowance = host.requirements.aero_relative_tolerance(sensitivity)
        return dict(
            baseline_apogee_m=base,
            components=rows,
            l1_sensitivity_m_per_relative_error=sensitivity,
            allocated_aero_error_m=host.requirements.altitude_numerical_budget_m
            * host.requirements.aero_budget_fraction,
            local_coefficient_tolerance=allowance,
            scope="Local worst-sign sum of component sensitivities, not a global error bound",
            metrics={
                "required_aero_tolerance": allowance,
                "altitude_shortfall": max(0, host.requirements.altitude_target_m - base),
            },
        )

    def aero_compare(self, params, output, host):
        def result(key):
            return host.results[key]["value"]

        stencil = {r["angle"]: vector(r["case"]) for r in result("angle-stencil")["cases"]}
        # Lock even training stations; odd stations never enter fitting or threshold tuning.
        train, holdout = [6, 8, 10, 12, 14], [7, 9, 11, 13]
        checks = []
        for angle in holdout:
            predicted = (stencil[angle - 1] + stencil[angle + 1]) / 2
            checks.append(dict(angle=angle, **comparison(predicted, stencil[angle])))
        baseline = stencil[12]
        time_check = comparison(vector(result("longer-average")["cases"][0]["case"]), baseline)
        mach_check = comparison(vector(result("lower-mach")["cases"][0]["case"]), baseline)
        grid = {
            str(row["angle"]): comparison(stencil[row["angle"]], vector(row["case"]))
            for row in result("angle-grid24")["cases"]
        }
        limits = host.requirements
        tolerance = result("aero-sensitivity")["local_coefficient_tolerance"]
        # Componentwise (with declared zero floors), not just an aggregate force norm.
        worst_interp = max(max(c["components"].values()) for c in checks)
        worst_grid = max(max(c["components"].values()) for c in grid.values())
        return dict(
            training_angles=train,
            holdout_angles=holdout,
            interpolation=checks,
            duration40_to160=time_check,
            lattice_speed075_to050=mach_check,
            grid16_to24=grid,
            requested_local_tolerance=tolerance,
            next_method=(
                "boundary-fitted geometry or interpolated wall treatment; retain "
                "current diagnostics"
            ),
            metrics=dict(
                aero_error=max(
                    worst_interp / limits.interpolation_relative_limit,
                    worst_grid / (tolerance or limits.grid_relative_limit),
                ),
                aero_numerical_pass=False,
            ),
            reason=(
                "Higher-grid convergence, absolute validation and off-plane "
                "coverage remain unresolved; no automatic promotion"
            ),
            scope=(
                "Lattice-speed comparison also changes time step; Mach and "
                "temporal effects are not isolated"
            ),
        )

    def governing_fin_load(self):
        candidates = []
        for path in self.prior.glob("*-flight.json"):
            r = read(path)
            tr = r["trace"]
            t, q, alpha = (np.array(tr[k]) for k in ("time_s", "q_pa", "incidence_deg"))
            ids = np.flatnonzero((t >= r["rail_exit_s"]) & (t <= r["apogee_s"]))
            i = ids[np.argmax(q[ids] * alpha[ids])]
            candidates.append(
                dict(
                    case=path.stem,
                    time_s=float(t[i]),
                    q_pa=float(q[i]),
                    incidence_deg=float(alpha[i]),
                    product=float(q[i] * alpha[i]),
                )
            )
        event = max(candidates, key=lambda r: r["product"])
        area = np.pi * (self.assembly["dimensions_mm"]["body_diameter"] / 2000) ** 2
        event["force_one_fin_n"] = (
            event["q_pa"]
            * area
            * self.assembly["fin_set_CNalpha_per_rad"]
            / 2
            * np.deg2rad(event["incidence_deg"])
        )
        event["aero_load_domain_pass"] = event["incidence_deg"] <= 15
        return event

    def fin_screen(self, params, output, host):
        g, event = self.assembly["dimensions_mm"], self.governing_fin_load()
        temperature = read(self.prior / "thermal.json")["final_c"]["fin"]
        rows = []
        for profile, properties in PROFILES.items():
            ratio = np.interp(temperature, [20, 55], [1, properties["warm_ratio"]])
            for thickness in (0.00075, 0.001, 0.0015, 0.002, 0.0025, 0.003):
                for root_k in (5e4, 5e5, 5e6):
                    value = beam(
                        g["fin_span"] / 1000,
                        g["fin_root"] / 1000,
                        g["fin_tip"] / 1000,
                        thickness,
                        properties["young_pa"] * ratio,
                        properties["density"],
                        root_k,
                        event["force_one_fin_n"],
                        tab=g["fin_tab"] / 1000,
                    )
                    value.update(
                        id=f"{profile}-t{thickness * 1000:g}-k{root_k:g}",
                        profile=profile,
                        properties=properties,
                        thickness_m=thickness,
                        root_k_n_m=root_k,
                    )
                    value["deflection_span_ratio"] = value["max_deflection_m"] / (
                        g["fin_span"] / 1000
                    )
                    value["screen_pass"] = (
                        value["deflection_span_ratio"]
                        <= host.requirements.fin_deflection_span_ratio
                    )
                    value["mass_four_fins_kg"] = 4 * value["mass_one_fin_kg"]
                    rows.append(value)
        shortlist = []
        for profile in PROFILES:
            eligible = [r for r in rows if r["profile"] == profile and r["screen_pass"]]
            if eligible:
                shortlist.append(
                    min(eligible, key=lambda r: (r["mass_four_fins_kg"], r["root_k_n_m"]))
                )
        shortlist.sort(key=lambda r: (r["mass_four_fins_kg"], r["root_k_n_m"]))
        return dict(
            candidates=rows,
            shortlist=shortlist[:2],
            load_event=event,
            temperature_c=temperature,
            allowable_status="unknown for every assumed profile",
            scope=(
                "Large linear deflections only identify failures; load at 15+ deg "
                "is an extrapolated demand scenario"
            ),
            metrics=dict(
                fin_flexibility=max(r["deflection_span_ratio"] for r in rows)
                / host.requirements.fin_deflection_span_ratio
            ),
        )

    def fin_nonlinear(self, params, output, host):
        screen = host.results["fin-candidates"]["value"]
        baseline = dict(
            id="reference-t1-k500000",
            properties=PROFILES["reference_assumption"],
            thickness_m=0.001,
            root_k_n_m=5e5,
        )
        rows = []
        event = screen["load_event"]
        for candidate in [baseline, *screen["shortlist"]]:
            cfg = self.config.model_copy(deep=True)
            cfg.fin_material = Material(**candidate["properties"])
            cfg.fin_thickness_m = candidate["thickness_m"]
            cfg.fin_root_k_n_m = candidate["root_k_n_m"]
            history = []
            for resolution in (2, 3, 4):
                print("FEM", candidate["id"], resolution, flush=True)
                deck, nodes, elements, meta = fem.fin_deck(
                    self.assembly,
                    cfg,
                    event["q_pa"],
                    resolution=resolution,
                    temperature_c=screen["temperature_c"],
                    incidence_deg=event["incidence_deg"],
                )
                result = fem.run_deck(
                    self.solver, output / candidate["id"] / f"mesh{resolution}", "fin", deck
                )
                twist, peak = aeroelastic.mean_twist(nodes, result["node_displacements_m"])
                result.update(resolution=resolution, twist_deg=twist, peak_twist_deg=peak)
                write_json(output / candidate["id"] / f"mesh{resolution}" / "result.json", result)
                history.append(
                    {
                        k: v
                        for k, v in result.items()
                        if k not in ("node_displacements_m", "integration_stress_pa")
                    }
                )
                if len(history) >= 2:
                    changes = {
                        k: abs(history[-2][k] / result[k] - 1)
                        for k in ("max_displacement_m", "p95_integration_vm_pa")
                    }
                    if max(changes.values()) <= host.requirements.grid_relative_limit:
                        break
            row = dict(
                candidate=candidate,
                meshes=history,
                mesh_change=changes,
                numerical_pass=max(changes.values()) <= host.requirements.grid_relative_limit,
                deflection_span_ratio=history[-1]["max_displacement_m"]
                / (self.assembly["dimensions_mm"]["fin_span"] / 1000),
                aero_load_domain_pass=event["aero_load_domain_pass"],
                strength_status="unknown: no applicable material/joint allowable",
            )
            rows.append(row)
        return dict(
            cases=rows,
            load_event=event,
            temperature_c=screen["temperature_c"],
            scope=(
                "Nonlinear structural response to frozen follower pressure, no "
                "fluid re-solve; twist requests FSI"
            ),
            metrics=dict(structure_numerical_pass=all(r["numerical_pass"] for r in rows)),
        )

    def reflight(self, params, output, host):
        screen = host.results["fin-candidates"]["value"]
        cases = []
        for candidate in screen["shortlist"]:
            design, assembly = reconcile_mass(
                self.design, self.assembly, candidate["mass_four_fins_kg"]
            )
            write_json(output / (candidate["id"] + "-assembly.json"), assembly)
            result = self.run_flight(output, candidate["id"], design=design, assembly=assembly)
            cases.append(
                dict(
                    candidate=candidate["id"],
                    dry_mass_kg=design.dry_mass_kg,
                    apogee_m=result["apogee_m"],
                    impact_speed_mps=result["impact_speed_mps"],
                    loaded_cg_mm=assembly["loaded_cg_mm"],
                    wet_cg_mm=assembly["wet_cg_mm"],
                    wet_static_margin_calibers=(assembly["cp_mm"] - assembly["wet_cg_mm"])
                    / assembly["dimensions_mm"]["body_diameter"],
                    geometry_aero_invalidated=True,
                )
            )
        return dict(
            cases=cases,
            scope=(
                "Isolated mass/inertia diagnostic using prior rigid "
                "zero-thickness aero; not accepted new designs"
            ),
        )

    def perturbation(self, params, output, host):
        baseline = self.baseline or self.run_flight(output, "baseline")
        rows = []
        for damping in (2, 10):
            for delta in (-0.5, 0.5, 2.0):
                cfg = self.config.flight.model_copy(
                    update={
                        "initial_tilt_deg": self.config.flight.initial_tilt_deg + delta,
                        "pitch_damping": damping,
                    }
                )
                result = self.run_flight(output, f"tilt{delta:+g}-damping{damping}", config=cfg)
                # At changed damping use a matching unperturbed baseline.
                reference = (
                    baseline
                    if damping == 10
                    else self.run_flight(
                        output,
                        f"reference-damping{damping}-delta{delta:+g}",
                        config=self.config.flight.model_copy(update={"pitch_damping": damping}),
                    )
                )
                t0 = max(reference["rail_exit_s"], result["rail_exit_s"])
                t1 = min(reference["apogee_s"], result["apogee_s"])
                t = np.linspace(t0, t1, 201)

                def axes(r, t=t):
                    tr = r["trace"]
                    axes = np.array([flight.rotation(q)[:, 2] for q in tr["quaternion"]])
                    v = np.column_stack([np.interp(t, tr["time_s"], axes[:, j]) for j in range(3)])
                    return v / np.linalg.norm(v, axis=1)[:, None]

                angle = np.rad2deg(
                    np.arccos(np.clip(np.sum(axes(reference) * axes(result), axis=1), -1, 1))
                )
                rows.append(
                    dict(
                        delta_tilt_deg=delta,
                        damping=damping,
                        time_s=t.tolist(),
                        attitude_difference_deg=angle.tolist(),
                        peak_difference_deg=float(max(angle)),
                        final_difference_deg=float(angle[-1]),
                        final_to_initial_input_ratio=float(angle[-1] / abs(delta)),
                        apogee_difference_m=result["apogee_m"] - reference["apogee_m"],
                    )
                )
        return dict(
            cases=rows,
            scope=(
                "Finite-time nonlinear trajectory comparisons over common "
                "free-ascent interval; not an exponential/Lyapunov certificate"
            ),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("tunnel", type=Path)
    parser.add_argument("prior", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--memory-gib", type=float, default=8)
    parser.add_argument("--budget-s", type=float, default=2400)
    parser.add_argument("--altitude-error-m", type=float, default=1.5)
    args = parser.parse_args()
    packet = read(args.input)
    # The CFD assembly hash must be the identical source file used by the prior tunnel.
    assembly_path = ROOT.parent / "bottle-generation/output/bottle-prototype/assembly.json"
    if file_hash(assembly_path) != read(args.tunnel / "v18-a000/case.json")["geometry_sha256"]:
        raise ValueError("CFD geometry source differs from prior table")
    if read(assembly_path)["dimensions_mm"] != packet["assembly"]["dimensions_mm"]:
        raise ValueError("Assembly dimensions differ")
    requirements = Requirements(altitude_numerical_budget_m=args.altitude_error_m)
    adapter = Adapters(
        packet, args.tunnel.resolve(), args.prior.resolve(), args.solver.resolve(), assembly_path
    )
    code_paths = [
        Path(__file__),
        ROOT / "rocketwright/adaptive.py",
        ROOT / "rocketwright/physics/fin_candidates.py",
        ROOT / "rocketwright/physics/flight_loads.py",
        ROOT / "scenarios/cfd/run_flow.py",
        ROOT / "scenarios/cfd/bottle_flow.cu",
        *sorted((ROOT / "rocketwright/physics/bottle_integrity").glob("*.py")),
    ]
    inputs = dict(
        prior=digest({p.name: file_hash(p) for p in sorted(args.prior.glob("*.json"))}),
        geometry=digest(packet["assembly"]),
        mass=digest(packet["design"]),
        material=digest(packet["config"]),
        operation=digest(packet["config"]["flight"]),
        code=digest({str(p.relative_to(ROOT)): file_hash(p) for p in code_paths}),
        requirements=digest(requirements.model_dump()),
        fin_span_m=packet["assembly"]["dimensions_mm"]["fin_span"] / 1000,
    )
    runners = {
        name: getattr(adapter, name)
        for name in (
            "audit",
            "cfd",
            "aero_compare",
            "fin_screen",
            "fin_nonlinear",
            "reflight",
            "sensitivity",
            "perturbation",
        )
    }
    campaign = Campaign(
        args.output,
        inputs=inputs,
        runners=runners,
        capabilities=["cuda", "calculix"],
        memory_gib=args.memory_gib,
        budget_s=args.budget_s,
        requirements=requirements,
    )
    write_json(
        args.output / "provenance.json",
        dict(
            inputs=inputs,
            source_sha256={str(p.relative_to(ROOT)): file_hash(p) for p in code_paths},
            solver_sha256=file_hash(args.solver),
            environment={k: os.environ.get(k) for k in ["CUDA_PATH", "CFD_CUDA_DLL_DIR"]},
        ),
    )
    campaign.run()
    print(
        json.dumps({k: v["execution_status"] for k, v in campaign.results.items()}, indent=2),
        flush=True,
    )


if __name__ == "__main__":
    main()
