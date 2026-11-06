"""One bounded subprocess per analysis. Only host-registered methods reach this module."""

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.agent.project_equipment import procurement_summary
from rocketwright.analysis import aero_accuracy
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.schema import Precision
from rocketwright.manufacturing import PrintRequest, prepare_geometry
from rocketwright.physics import fin_candidates, fin_load_map, stability_theorems
from rocketwright.physics.bottle_integrity import fem, flight, loads, thermal
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.physics.concrete_fin import polygon_moments
from rocketwright.physics.flight_loads import MassDistribution, TunnelDatabase, recover
from rocketwright.schema import BottleDesign

ROOT = Path(__file__).resolve().parents[2]


def integrated_coefficients(values, stations, diameter, cg):
    """Raw tunnel axes: x goes from nose to tail. Include force arms about the same CG."""
    arms = np.column_stack(
        [(np.asarray(stations) - cg) / diameter, np.zeros(len(stations)), np.zeros(len(stations))]
    )
    forces = values[..., :3]
    moments = values[..., 3:] + np.cross(arms, forces)
    return np.concatenate([forces.sum(axis=-2), moments.sum(axis=-2)], axis=-1)


def free_ascent_margin(trajectory, cp_m, diameter_m):
    trace = trajectory["trace"]
    times = np.asarray(trace["time_s"])
    active = (
        (times > trajectory["rail_exit_s"])
        & (times <= trajectory["apogee_s"])
        & (np.asarray(trace["q_pa"]) > 10)
    )
    if not active.any():
        return None
    return float(np.min((cp_m - np.asarray(trace["cg_m"])[active]) / diameter_m))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


class AnalyticAero:
    """Small-angle surrogate, with a distributed force contract for load recovery."""

    def __init__(self, record, scale=1):
        a = record["assembly"]
        self.area = math.pi * (a["dimensions_mm"]["body_diameter"] / 2000) ** 2
        self.cp = a["cp_mm"] / 1000
        self.stations = np.array([self.cp])
        self.speeds = np.array([0.1, 35.0])
        self.cn = a["fin_set_CNalpha_per_rad"] + 2
        self.cd = (record["design"].get("axial_drag_coefficient") or 0.55) * scale
        self.metadata = dict(method="small-angle analytic surrogate", physical_validation=False)

    def evaluate(self, vb, q, cg):
        vb = np.asarray(vb)
        speed, cross = np.linalg.norm(vb), np.linalg.norm(vb[:2])
        alpha = math.atan2(cross, vb[2]) if speed > 0.1 else 0
        force = -q * self.area * self.cd * vb / max(speed, 1e-9)
        # Smooth sine continuation avoids a discontinuous transverse force at reverse flow.
        # Acceptance still uses the declared small-angle limit; this is not high-angle evidence.
        force[:2] -= q * self.area * self.cn * math.sin(alpha) * vb[:2] / max(cross, 1e-9)
        moment = np.cross([0, 0, cg - self.cp], force)
        return dict(
            force_n=force,
            moment_nm=moment,
            station_m=self.stations,
            line_force_n=force[None, :],
            line_couple_nm=np.zeros((1, 3)),
        )


class Worker:
    def __init__(self, context, folder):
        self.ctx, self.folder = context, Path(folder).resolve()
        self.spec = DesignSpec.model_validate(context["spec"])
        self.precision = Precision.model_validate(context["precision"])
        self.data = {k: read(v) for k, v in context["artifacts"].items()}
        self.deadline = time.monotonic() + context["timeout_s"]

    def setup(self):
        self.record = compile_record(self.spec, self.data["geometry"]["cad_metrics"])
        self.design = BottleDesign.model_validate(self.record["design"])
        self.assembly = self.record["assembly"]
        self.cfg = AnalysisConfig.model_validate(self.record["config"])
        self.cfg.flight.aero_angle_limit_deg = self.precision.maximum_incidence_deg
        self.record["config"] = self.cfg.model_dump(mode="json")
        write_json(self.folder / "record.json", self.record)

    def geometry(self):
        d = self.spec.design.model_copy(update={"geometry": self.spec.geometry})
        _, metrics = prepare_geometry(PrintRequest(design=d), self.folder / "cad")
        # Validate reservoir and mass before any downstream calculation.
        record = compile_record(self.spec, metrics)
        return dict(cad_metrics=metrics, record=record, metrics={"geometry_valid": True})

    def thermal(self):
        temp = self.cfg.loads.ambient_k - 273.15
        result = thermal.wait(self.design, self.cfg, ambient_c=temp, initial_c=temp, sealed=True)
        result["metrics"] = {"thermal_balance": result["energy_balance_relative"] < 1e-6}
        return result

    def propulsion(self):
        warm = self.data["thermal"]
        self.cfg.loads.initial_k = warm["final_c"]["gas"] + 273.15
        self.cfg.loads.initial_wall_k = warm["final_c"]["skin"] + 273.15
        warmed = self.design.model_copy(
            update={
                "initial_gauge_pressure_pa": warm["trace"]["absolute_pressure_pa"][-1]
                - self.cfg.loads.ambient_pa
            }
        )
        result = loads.propulsion(warmed, self.cfg.loads)
        if not result["completed"]:
            raise RuntimeError("Discharge did not finish within the modeled duration")
        result["metrics"] = dict(
            propulsion_balance=max(
                result["energy_balance_relative"], result["mass_balance_relative"]
            )
            < 0.01
        )
        return result

    def aero(self, scale=1):
        if "cfd_fine" in self.data:
            return TunnelDatabase(self.data["cfd_fine"]["table_folder"], scale=scale)
        return AnalyticAero(self.record, scale=scale)

    def trajectory(self, *, dt=None, scale=1, tilt=None, use_cfd=True, aero_model=None):
        dt = dt or self.ctx["runtime"].get("flight_step_s", 0.02)
        cfg = self.cfg.flight.model_copy()
        if tilt is not None:
            cfg.initial_tilt_deg = tilt
        propulsion = self.data["propulsion"]
        mass = MassDistribution(self.design, self.assembly, propulsion)
        aero = aero_model or (self.aero(scale) if use_cfd else AnalyticAero(self.record, scale))
        result = flight.run(
            self.design,
            self.assembly,
            propulsion,
            cfg,
            max_step=dt,
            aero_model=aero,
            mass_model=mass,
            record_loads=True,
        )
        if not result["completed"]:
            raise RuntimeError(
                "Flight integration incomplete: " + result.get("reason", "no landing")
            )
        speed = np.array(
            [np.linalg.norm(s["air_velocity_body_mps"]) for s in result["load_samples"]]
        )
        t = np.asarray(result["trace"]["time_s"])
        active = (
            (t > result["rail_exit_s"])
            & (t < result["apogee_s"])
            & (np.asarray(result["trace"]["q_pa"]) > 10)
        )
        result["aero_domain_pass"] = bool(
            (
                not active.any()
                or (
                    speed[active].min() >= aero.speeds[0] and speed[active].max() <= aero.speeds[-1]
                )
            )
            and (
                isinstance(aero, TunnelDatabase)
                or result["ascent_incidence_deg"] <= self.precision.maximum_incidence_deg
            )
        )
        result["max_air_speed_mps"] = float(speed.max())
        recovered = recover(result, aero, mass, propulsion, ambient_pa=self.cfg.loads.ambient_pa)
        result["section_loads"] = serial(recovered)
        result["max_section_equilibrium_residual"] = float(
            abs(recovered["equilibrium_residual"]).max()
        )
        result["metrics"] = dict(
            apogee_m=result["apogee_m"],
            max_air_speed_mps=result["max_air_speed_mps"],
            incidence_deg=result["ascent_incidence_deg"],
            aero_domain_pass=result["aero_domain_pass"],
        )
        return result

    def screen(self):
        return self.trajectory(use_cfd=False)

    def flight(self):
        return self.trajectory()

    def run_case(self, assembly, out, speed, angle, cells, **changes):
        r = dict(self.ctx["runtime"], **changes)
        command = [
            r.get("cfd_python") or sys.executable,
            str(ROOT / "scenarios/cfd/run_flow.py"),
            str(assembly),
            str(out),
            "--shape",
            "flat",
            "--wall",
            "interpolated",
            "--fin-thickness-mm",
            str(self.spec.geometry.fin_thickness_mm),
            "--cells",
            str(cells),
            "--width",
            str(r.get("cfd_width", 10)),
            "--upstream",
            "3",
            "--times",
            str(r["cfd_times"]),
            "--speed",
            str(speed),
            "--angle",
            str(angle),
            "--lattice-speed",
            str(r.get("cfd_lattice_speed", 0.075)),
            "--rotate-geometry",
            "--surface-loads",
            "--paired-samples",
            "--volume",
            "--no-preview",
        ]
        with out.with_suffix(".log").open("w", encoding="utf-8") as log:
            p = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=max(0.1, self.deadline - time.monotonic()),
            )
        if p.returncode:
            raise RuntimeError(f"CFD case {out.name} failed; inspect its log")
        return read(out / "case.json")

    def cfd_audit(self):
        r = self.ctx["runtime"]
        table = self.aero()
        speed, angle = aero_accuracy.holdout(table.speeds, table.angles)
        assembly = self.folder / "assembly.json"
        write_json(assembly, self.assembly)
        levels = [r["cfd_cells_coarse"], r["cfd_cells_fine"], r["cfd_cells_fine"] + 4]
        cases = {
            str(n): self.run_case(assembly, self.folder / f"grid-{n}", speed, angle, n)
            for n in levels
        }
        cases["wide"] = self.run_case(
            assembly,
            self.folder / "wide",
            speed,
            angle,
            levels[1],
            cfd_width=r.get("cfd_width", 10) + 2,
        )
        cases["time"] = self.run_case(
            assembly,
            self.folder / "time",
            speed,
            angle,
            levels[1],
            cfd_lattice_speed=r.get("cfd_lattice_speed", 0.075) / 2,
        )
        cases["duration"] = self.run_case(
            assembly,
            self.folder / "duration",
            speed,
            angle,
            levels[1],
            cfd_times=r["cfd_times"] * 2,
        )
        names = ["Cx", "Cy", "Cm_z"]
        vectors = {k: [v["mean"][n] for n in names] for k, v in cases.items()}
        reference = vectors[str(levels[1])]
        coeff = integrated_coefficients(
            table.coefficients(speed, angle),
            table.stations,
            table.diameter,
            self.assembly["loaded_cg_mm"] / 1000,
        )[[0, 1, 5]]
        differences = {
            k: aero_accuracy.relative_change(reference, vectors[k])
            for k in ("wide", "time", "duration")
        }
        differences["interpolation"] = aero_accuracy.relative_change(coeff, reference)
        differences["third_grid"] = aero_accuracy.relative_change(
            reference, vectors[str(levels[2])]
        )
        return dict(
            condition=dict(speed_mps=speed, angle_deg=angle),
            cells=levels,
            differences=differences,
            observed_orders={
                n: aero_accuracy.grid_order(levels, [vectors[str(level)][i] for level in levels])
                for i, n in enumerate(names)
            },
            cases=cases,
            metrics={"aero_" + k: v for k, v in differences.items()},
            scope="One independent ascent condition; finite differences, not a global error bound",
        )

    def cfd(self, fine):
        runtime = self.ctx["runtime"]
        cells = runtime["cfd_cells_fine" if fine else "cfd_cells_coarse"]
        speeds = runtime.get("cfd_speeds", [1, 35])
        angles = runtime.get("cfd_angles", [0, 5, 15, 45, 90, 135, 180])
        folder = self.folder / "tunnel"
        folder.mkdir()
        write_json(folder / "table-config.json", dict(speeds_mps=speeds, angles_deg=angles))
        assembly_file = self.folder / "assembly.json"
        write_json(assembly_file, self.assembly)
        for speed in speeds:
            for angle in angles:
                out = folder / f"v{speed:02.0f}-a{angle:03.0f}"
                self.run_case(assembly_file, out, speed, angle, cells)
        table = TunnelDatabase(folder)
        cases = [read(p) for p in folder.glob("*/case.json")]
        averaging = max(
            abs(delta) / max(abs(case["mean"][name]), 0.05)
            for case in cases
            for name, delta in case["split_window_difference"].items()
        )
        result = dict(
            table_folder=str(folder),
            cells=cells,
            metadata=table.metadata,
            coefficients=table.table.tolist(),
            averaging_relative_change=averaging,
            maximum_density_departure=max(c["max_abs_density_departure"] for c in cases),
            metrics={},
        )
        if fine:
            old = np.asarray(self.data["cfd_coarse"]["coefficients"])
            # Compare integrated force/couple and distributed loads, not drag alone.
            cg = self.assembly["loaded_cg_mm"] / 1000
            total = integrated_coefficients(table.table, table.stations, table.diameter, cg)
            prior = integrated_coefficients(old, table.stations, table.diameter, cg)
            diff = np.max(abs(total - prior), axis=(0, 1))
            denominator = np.maximum(np.max(abs(total), axis=(0, 1)), 0.01)
            result["grid_relative_change"] = float(max(diff / denominator))
            result["distributed_relative_change"] = float(
                np.linalg.norm(table.table - old) / max(np.linalg.norm(table.table), 1e-9)
            )
            result["metrics"]["cfd_grid_change"] = result["grid_relative_change"]
        return result

    def base_flight(self):
        return self.data.get("flight", self.data["screen"])

    def refine(self):
        base = self.base_flight()
        step = self.ctx["runtime"].get("flight_step_s", 0.02) / 2
        fine = self.trajectory(dt=step)
        sensitivity = self.trajectory(dt=step, scale=1.1)
        change = abs(fine["apogee_m"] - base["apogee_m"])
        slope = abs(sensitivity["apogee_m"] - fine["apogee_m"]) / 0.1
        allowed = (
            min(
                self.precision.grid_relative_limit,
                self.precision.altitude_error_m * self.precision.aero_allocation / slope,
            )
            if slope > 1e-9
            else None
        )
        propagation = None
        if "cfd_coarse" in self.data:
            coarse = self.trajectory(
                dt=step, aero_model=TunnelDatabase(self.data["cfd_coarse"]["table_folder"])
            )
            propagation = dict(
                coarse_flight=coarse,
                altitude_difference_m=abs(coarse["apogee_m"] - fine["apogee_m"]),
                incidence_difference_deg=abs(
                    coarse["ascent_incidence_deg"] - fine["ascent_incidence_deg"]
                ),
                max_q_difference_pa=abs(coarse["max_q_pa"] - fine["max_q_pa"]),
                scope="Same integration step, different CFD grids; not a bound on model error",
            )
        return dict(
            fine=fine,
            grid_propagation=propagation,
            sensitivity_flight=sensitivity,
            altitude_change_m=change,
            aero_sensitivity_m_per_relative_coefficient=slope,
            allowed_aero_relative_change=allowed,
            scope="Local finite perturbation and two-level difference, not an error bound",
            metrics=dict(
                temporal_pass=(
                    change <= self.precision.altitude_error_m * (1 - self.precision.aero_allocation)
                    and change / max(fine["apogee_m"], 1) <= self.precision.temporal_relative_limit
                )
            ),
        )

    def fin_force(self):
        f = self.base_flight()
        if "cfd_fine" in self.data:
            return max(
                abs(row["local_resultant"][2]) for row in aero_accuracy.fin_envelope(self.aero(), f)
            )
        # A screening distribution when individual CFD resultants are unavailable.
        q = f["max_q_pa"]
        alpha = math.radians(min(90, f["ascent_incidence_deg"]))
        area = math.pi * (self.spec.geometry.body_diameter_mm / 2000) ** 2
        return q * area * self.assembly["fin_set_CNalpha_per_rad"] * alpha / 2

    def modes(self):
        g, cfg = self.spec.geometry, self.cfg
        mat = cfg.fin_material
        temp = self.data["thermal"]["final_c"]["fin"]
        ratio = np.clip((temp - mat.reference_c) / (mat.warm_c - mat.reference_c), 0, 1)
        young = mat.young_pa * (1 - ratio * (1 - mat.warm_ratio))
        result = fin_candidates.beam(
            g.fin_span_mm / 1000,
            g.fin_root_mm / 1000,
            g.fin_tip_mm / 1000,
            g.fin_thickness_mm / 1000,
            young,
            mat.density,
            cfg.fin_root_k_n_m,
            self.fin_force(),
            tab=self.spec.assumptions.root_capture_mm / 1000,
        )
        result["load_scope"] = (
            "CFD concurrent fin force envelope; beam load shape remains assumed"
            if "cfd_fine" in self.data
            else "max-q times max-incidence envelope; two loaded fins, assumed distribution"
        )
        result["temperature_c"] = temp
        result["metrics"] = dict(
            fin_deflection_ratio=result["max_deflection_m"] / (g.fin_span_mm / 1000),
            positive_modes=min(result["first_modes_hz"]) > 0,
        )
        return result

    def structure(self, fine):
        g = self.spec.geometry
        _, center, _ = polygon_moments(
            np.array(
                [
                    [0, 0],
                    [g.fin_root_mm, 0],
                    [g.fin_sweep_mm + g.fin_tip_mm, g.fin_span_mm],
                    [g.fin_sweep_mm, g.fin_span_mm],
                ]
            )
            / 1000
        )
        temp = self.data["thermal"]["final_c"]["fin"]
        level = self.ctx["runtime"].get("fem_level", 2) - (0 if fine else 1)
        cases = (
            aero_accuracy.fin_envelope(self.aero(), self.base_flight())
            if "cfd_fine" in self.data
            else [dict(analytic_envelope=True)]
        )
        outputs = []
        for i, condition in enumerate(cases):
            if "local_resultant" in condition:
                deck, _, _, mapping = fin_load_map.resultant_deck(
                    self.assembly,
                    self.cfg,
                    condition["local_resultant"],
                    resolution=level,
                    temperature_c=temp,
                )
            else:
                deck, _, _, mapping = fin_load_map.deck(
                    self.assembly,
                    self.cfg,
                    self.fin_force(),
                    center,
                    resolution=level,
                    temperature_c=temp,
                )
            result = fem.run_deck(
                self.ctx["runtime"]["calculix"],
                self.folder,
                f"fin-{i}",
                deck,
                timeout_s=max(0.1, self.deadline - time.monotonic()),
            )
            result.update(mapping=mapping, condition=condition)
            outputs.append(result)
        result = dict(
            cases=outputs,
            load_scope=(
                (
                    "CFD Fn and both root moments at concurrent extrema; "
                    "reconstructed pressure, not local traction; tangential load omitted"
                )
                if "cfd_fine" in self.data
                else "analytic flight envelope"
            ),
        )
        for key in ("max_displacement_m", "p95_integration_vm_pa", "max_integration_vm_pa"):
            if key in outputs[0]:
                result[key] = max(r[key] for r in outputs)
        result["metrics"] = dict(
            fem_deflection_ratio=result["max_displacement_m"] / (g.fin_span_mm / 1000)
        )
        if fine:
            old = self.data["fem_coarse"]
            change = max(
                abs(result[k] - old[k]) / max(abs(result[k]), 1e-12)
                for k in ["max_displacement_m", "p95_integration_vm_pa"]
            )
            if len(old["cases"]) != len(outputs):
                raise ValueError("FEM grids used different load cases")
            change = max(
                change,
                max(
                    abs(after[k] - before[k]) / max(abs(after[k]), 1e-12)
                    for before, after in zip(old["cases"], outputs, strict=True)
                    for k in ("max_displacement_m", "p95_integration_vm_pa")
                ),
            )
            result["metrics"]["fem_mesh_change"] = change
        return result

    def stability(self):
        aero = self.aero()
        mass = MassDistribution(self.design, self.assembly, self.data["propulsion"])
        result = stability_theorems.flight_screen(
            self.assembly, self.base_flight(), aero, mass, self.cfg.flight
        )
        perturbed = self.trajectory(tilt=min(10, self.spec.assumptions.initial_tilt_deg + 1))
        result["perturbed_flight"] = perturbed
        result["metrics"] = dict(
            frozen_pitch_pass=(
                result.get("analyzed_points", 0) > 0
                and result.get("frozen_asymptotic_count") == result.get("analyzed_points")
            ),
            perturbation_incidence_deg=perturbed["ascent_incidence_deg"],
        )
        return result

    def confirm(self):
        # Independent tighter integration and perturbed initial condition, never an existence test.
        result = self.trajectory(
            dt=self.ctx["runtime"].get("flight_step_s", 0.02) / 4,
            tilt=min(10, self.spec.assumptions.initial_tilt_deg + 0.5),
        )
        precision, base = self.precision, self.base_flight()
        target = self.spec.requirement.target_altitude_m if self.spec.requirement else None
        liftoff_static = (
            self.assembly["cp_mm"] - self.assembly["wet_cg_mm"]
        ) / self.spec.geometry.body_diameter_mm
        margins = [
            free_ascent_margin(
                t, self.assembly["cp_mm"] / 1000, self.spec.geometry.body_diameter_mm / 1000
            )
            for t in (base, result)
        ]
        static = min(margins) if all(m is not None for m in margins) else None
        checks = dict(
            altitude=target is not None
            and (
                min(base["apogee_m"], result["apogee_m"]) >= target
                if self.spec.altitude_rule == "minimum"
                else max(abs(base["apogee_m"] - target), abs(result["apogee_m"] - target))
                <= 0.1 * target
            ),
            attitude=max(
                base["ascent_incidence_deg"],
                result["ascent_incidence_deg"],
                self.data["stability"]["metrics"]["perturbation_incidence_deg"],
            )
            <= precision.maximum_incidence_deg,
            static_margin=static is not None and static >= precision.minimum_static_margin_cal,
            temporal=self.data["refine"]["metrics"]["temporal_pass"],
            fin_deformation=self.data["modes"]["metrics"]["fin_deflection_ratio"]
            <= precision.deflection_span_limit,
            modes=self.data["modes"]["metrics"]["positive_modes"],
            frozen_pitch=self.data["stability"]["metrics"]["frozen_pitch_pass"],
            aero_domain=result["aero_domain_pass"] and base["aero_domain_pass"],
            thermal_balance=self.data["thermal"]["metrics"]["thermal_balance"],
            propulsion_balance=self.data["propulsion"]["metrics"]["propulsion_balance"],
            payload_mass=self.design.payload_mass_kg >= self.spec.requirement.payload_mass_kg,
            recovery=(
                not self.spec.requirement.recovery_required
                or (self.design.has_parachute and result["impact_speed_mps"] <= 5)
            ),
            cost_evidence=(
                self.spec.requirement.budget_jpy is None
                or (
                    procurement_summary(self.spec)["total_jpy"] is not None
                    and procurement_summary(self.spec)["total_jpy"]
                    <= self.spec.requirement.budget_jpy
                )
            ),
        )
        if precision.require_cfd:
            allowed = self.data["refine"]["allowed_aero_relative_change"]
            checks["aero_grid"] = (
                allowed is not None and self.data["cfd_fine"]["grid_relative_change"] <= allowed
            )
            checks["aero_averaging"] = (
                self.data["cfd_fine"]["averaging_relative_change"]
                <= precision.temporal_relative_limit
            )
            propagation = self.data["refine"]["grid_propagation"]
            checks["aero_trajectory"] = (
                propagation["altitude_difference_m"]
                <= precision.altitude_error_m * precision.aero_allocation
                and propagation["incidence_difference_deg"] <= precision.attitude_error_deg
            )
            if precision.require_aero_audit:
                audit = self.data["cfd_audit"]["differences"]
                checks.update(
                    aero_interpolation=audit["interpolation"] <= precision.grid_relative_limit,
                    aero_domain_size=audit["wide"] <= precision.grid_relative_limit,
                    aero_lattice=audit["time"] <= precision.temporal_relative_limit,
                    aero_duration=audit["duration"] <= precision.temporal_relative_limit,
                    aero_third_grid=allowed is not None and audit["third_grid"] <= allowed,
                )
        if precision.require_fem:
            fm = self.data["fem_fine"]["metrics"]
            checks["fem_mesh"] = fm["fem_mesh_change"] <= precision.structure_relative_limit
            checks["fin_deformation"] &= (
                fm["fem_deflection_ratio"] <= precision.deflection_span_limit
            )
        return dict(
            flight=result,
            checks=checks,
            unmet=[k for k, v in checks.items() if not v],
            static_margin_cal=static,
            liftoff_static_margin_cal=liftoff_static,
            static_margin_scope=("fixed analytic CP; free ascent after rail exit at q>10 Pa; "
                                 "liftoff recorded separately"),
            metrics=dict(criteria_met=all(checks.values())),
            physical_qualification=False,
            full_flight_stability_proved=False,
            scope="Declared conditional numerical criteria only; strength allowables unresolved",
        )

    def run(self, kind):
        if kind != "geometry":
            self.setup()
        if kind in {"cfd_coarse", "cfd_fine"}:
            return self.cfd(kind.endswith("fine"))
        if kind in {"fem_coarse", "fem_fine"}:
            return self.structure(kind.endswith("fine"))
        allowed = {
            "geometry",
            "cfd_audit",
            "thermal",
            "propulsion",
            "screen",
            "flight",
            "refine",
            "modes",
            "stability",
            "confirm",
        }
        if kind not in allowed:
            raise ValueError("Unregistered analysis method")
        return getattr(self, kind)()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("kind")
    args = parser.parse_args()
    result = serial(Worker(read(args.input), args.output.parent).run(args.kind))
    write_json(args.output, result)
    # Include raw solver evidence, so an edited deck/table cannot silently remain current.
    manifest = {
        p.relative_to(args.output.parent).as_posix(): sha(p)
        for p in args.output.parent.rglob("*")
        if p.is_file() and p.name not in {"manifest.json", "worker.log"}
    }
    write_json(args.output.parent / "manifest.json", manifest)


if __name__ == "__main__":
    main()
