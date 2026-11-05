"""Dependency-gated analysis pool with immutable artifacts for assembled bottle candidates.

The host supplies the executable and output root. A planner/LLM can only select
listed method IDs; it cannot supply shell commands or promote physical validity.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from rocketwright.physics.stability import trapezoidal_fin_force
from rocketwright.schema import BottleDesign, FinSet

from . import aeroelastic, contact, evidence, fem, flight, loads, stability, thermal, verification
from .schema import AnalysisConfig


def contract(layer, category, phase, target, method, inputs, outputs, evaluation, depends=()):
    return dict(
        layer=layer,
        category=category,
        phase=phase,
        target=target,
        method=method,
        inputs=inputs,
        outputs=outputs,
        evaluation=evaluation,
        depends=list(depends),
    )


POOL = {
    "evidence": contract(
        "low",
        "identification",
        "before analysis",
        "actual article and material",
        "hash/provenance/applicability audit",
        ["manifest", "source records"],
        ["missing evidence"],
        "no synthetic or unreviewed record promoted",
    ),
    "thermal": contract(
        "low/middle",
        "thermal",
        "wait and pressure hold",
        "gas/skin/mount/payload/fin",
        "five-node heat/pressure network",
        ["thermal properties", "solar exposure"],
        ["temperature", "pressure"],
        "energy residual and temperature coverage",
        ("evidence",),
    ),
    "propulsion": contract(
        "middle",
        "fluid/thermal",
        "liquid and air discharge",
        "mass/thrust/temperature",
        "finite-duration compressible nozzle and energy ODE",
        ["geometry", "pressure", "thermal"],
        ["mass/thrust/temperature traces"],
        "mass/energy residual; missing phase is not a pass",
        ("thermal",),
    ),
    "flight": contract(
        "middle/high",
        "rigid-body motion",
        "rail to landing",
        "trajectory/attitude/rotation",
        "quaternion 6DOF with finite canopy inflation",
        ["propulsion", "aero", "inertia"],
        ["flight trace", "loads", "aero-domain flags"],
        "events/norm/refinement; validity separate",
        ("propulsion",),
    ),
    "contact": contract(
        "low/middle",
        "impact",
        "launch/opening/landing",
        "payload pad and stop",
        "two-DOF cubic pad plus unilateral compliant contact",
        ["flight loads", "pad/contact properties"],
        ["penetration", "force", "work balance"],
        "time-step refinement and missing fracture allowable",
        ("flight",),
    ),
    "structure": contract(
        "low/middle",
        "nonlinear FEM",
        "thermal and load envelope",
        "fin/collar/body/sleeve",
        "CalculiX NLGEOM, contact foundation and pressure-twist iteration",
        ["loads", "geometry", "material", "temperature", "solver"],
        ["deformation", "stress", "mesh change"],
        "benchmarks/refinement; compare strength only with matching evidence",
        ("contact", "thermal"),
    ),
    "stability": contract(
        "middle/high",
        "stability",
        "free ascent",
        "local pitch and elastic modes",
        "Lyapunov/common-P screen and bending-torsion lag model",
        ["flight", "structural applicability"],
        ["decay certificate scope", "mode/instability sensitivity"],
        "never equate frozen poles with whole-flight proof",
        ("structure", "flight"),
    ),
    "uncertainty": contract(
        "high",
        "robustness",
        "flight and recovery",
        "mission variations",
        "seeded stratified scenario ensemble",
        ["pressure/wind/Cd/CN/opening variation"],
        ["conditional envelopes", "invalid-domain count"],
        "not a probability of safety",
        ("flight",),
    ),
    "verdict": contract(
        "high",
        "evidence synthesis",
        "handoff",
        "whole article",
        "separate numerical/model/evidence gates",
        ["all lower results"],
        ["status", "next analyses/tests"],
        "missing or invalid evidence prevents physical qualification",
        (
            "evidence",
            "thermal",
            "propulsion",
            "flight",
            "contact",
            "structure",
            "stability",
            "uncertainty",
        ),
    ),
}


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(path, value):
    Path(path).write_text(
        json.dumps(jsonable(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


class IntegrityHarness:
    def __init__(
        self,
        design,
        assembly,
        output,
        *,
        config=None,
        solver=None,
        evidence_records=(),
        evidence_root=None,
        cfd_assessment=None,
    ):
        self.design = BottleDesign.model_validate(design)
        self.assembly = copy.deepcopy(assembly)
        self.config = config or AnalysisConfig()
        self.output = Path(output).resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise FileExistsError("Use a new run directory; previous results are immutable")
        self.output.mkdir(parents=True, exist_ok=True)
        self.solver = solver
        self.evidence_records = evidence_records
        self.evidence_root = Path(evidence_root or self.output)
        self.cfd = cfd_assessment
        self.results = {}
        self.history = []
        g = self.assembly["dimensions_mm"]
        cn, _ = trapezoidal_fin_force(
            g["body_diameter"] / 1000,
            FinSet(
                count=4,
                root_chord_m=g["fin_root"] / 1000,
                tip_chord_m=g["fin_tip"] / 1000,
                span_m=g["fin_span"] / 1000,
                sweep_m=g["fin_sweep"] / 1000,
            ),
            (g["overall"] - g["fin_tail_inset"] - g["fin_root"]) / 1000,
        )
        self.assembly["fin_set_CNalpha_per_rad"] = cn
        packet = {
            "design": self.design.model_dump(),
            "assembly": self.assembly,
            "config": self.config.model_dump(),
            "pool": POOL,
            "prior_cfd": self.cfd,
            "implementation_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(__file__).parent.glob("*.py")
            },
        }
        write_json(self.output / "input.json", packet)
        self.input_hash = hashlib.sha256((self.output / "input.json").read_bytes()).hexdigest()

    def options(self):
        return {
            k: v
            for k, v in POOL.items()
            if k not in self.results
            and all(
                d in self.results and self.results[d]["execution_status"] == "completed"
                for d in v["depends"]
            )
        }

    def step(self, method_id, reason):
        if method_id not in self.options() or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Select an available method ID and provide a reason")
        try:
            result = getattr(self, "_" + method_id)()
            result.setdefault("execution_status", "completed")
        except (RuntimeError, ValueError, FileNotFoundError, KeyError) as error:
            result = {"execution_status": "failed", "error": str(error), "qualified": False}
        result["source_id"] = f"{self.input_hash[:12]}:{method_id}"
        self.results[method_id] = jsonable(result)
        write_json(self.output / f"{method_id}.json", result)
        self.history.append(
            {
                "method_id": method_id,
                "reason": reason,
                "source_id": result["source_id"],
                "execution_status": result["execution_status"],
            }
        )
        write_json(self.output / "history.json", self.history)
        self._propagate_blocks()
        return self.results[method_id]

    def _propagate_blocks(self):
        changed = True
        while changed:
            changed = False
            for key, spec in POOL.items():
                if key in self.results or key == "verdict":
                    continue
                failed = [
                    d
                    for d in spec["depends"]
                    if d in self.results and self.results[d]["execution_status"] != "completed"
                ]
                if failed:
                    result = {
                        "execution_status": "blocked",
                        "failed_dependencies": failed,
                        "qualified": False,
                        "source_id": f"{self.input_hash[:12]}:{key}",
                    }
                    self.results[key] = result
                    write_json(self.output / f"{key}.json", result)
                    changed = True
        if (
            len(self.results) == len(POOL) - 1
            and "verdict" not in self.results
            and not self.options()
        ):
            result = self._verdict()
            result.update(execution_status="completed", source_id=f"{self.input_hash[:12]}:verdict")
            self.results["verdict"] = result
            write_json(self.output / "verdict.json", result)

    def run_all(self, progress=None):
        while self.options():
            key = next(iter(self.options()))
            if progress:
                progress(key, "running")
            self.step(key, "Dependency inputs are available; execute the required integrity check")
            if progress:
                progress(key, self.results[key]["execution_status"])
        write_json(self.output / "results.json", self.results)
        return self.results

    def _evidence(self):
        return evidence.audit(self.evidence_records, self.evidence_root)

    def _thermal(self):
        return {
            "vented": thermal.wait(self.design, self.config),
            "sealed": thermal.wait(self.design, self.config, sealed=True),
        }

    def _propulsion(self):
        warm = self.results["thermal"]["sealed"]
        design = self.design.model_copy(
            update={
                "initial_gauge_pressure_pa": warm["peak_absolute_pressure_pa"]
                - self.config.loads.ambient_pa
            }
        )
        cfg = self.config.loads.model_copy(
            update={
                "initial_k": warm["final_c"]["gas"] + 273.15,
                "initial_wall_k": warm["final_c"]["skin"] + 273.15,
                "ambient_k": 308.15,
            }
        )
        return {
            "nominal": loads.propulsion(self.design, self.config.loads),
            "warm_sealed_scenario": loads.propulsion(design, cfg),
            "warm_design": design.model_dump(),
            "scope": "nominal and assumed sealed warm wait; no pressure approval inferred",
        }

    def _flight(self):
        p = self.results["propulsion"]
        if not p["nominal"]["completed"]:
            raise RuntimeError("Propulsion did not complete")
        nominal = flight.run(self.design, self.assembly, p["nominal"], self.config.flight)
        refined = flight.run(
            self.design, self.assembly, p["nominal"], self.config.flight, max_step=0.01
        )
        if not nominal["completed"] or not refined["completed"]:
            raise RuntimeError("Flight did not reach all required events")
        changes = {
            k: abs(nominal[k] - refined[k]) / max(abs(refined[k]), 1e-9)
            for k in ["apogee_m", "max_q_pa", "impact_speed_mps", "max_canopy_force_n"]
        }
        warm = flight.run(
            BottleDesign(**p["warm_design"]),
            self.assembly,
            p["warm_sealed_scenario"],
            self.config.flight,
        )
        return {
            "nominal": nominal,
            "warm_sealed_scenario": warm,
            "time_refinement": changes,
            "numerical_pass": max(changes.values()) < self.config.observable_relative_tolerance,
        }

    def _contact(self):
        f = self.results["flight"]["nominal"]
        tr = f["trace"]
        p = self.config.contact
        cases = {}
        for name, lo, hi in [
            ("launch", 0, 1.2),
            (
                "opening",
                max(0, f["apogee_s"] - 0.05),
                f["apogee_s"] + self.config.flight.deployment_delay_s + 1,
            ),
        ]:
            t = np.linspace(lo, hi, int((hi - lo) / 0.0005) + 1)
            acc = np.interp(t, tr["time_s"], tr["proper_mps2"])
            cases[name] = contact.response(
                t,
                acc,
                self.design.payload_mass_kg,
                p,
                initial_proper=9.80665 if name == "launch" else acc[0],
            )
        landing = []
        for distance in [0.005, self.config.flight.stop_distance_m, 0.03]:
            velocity = f["impact_speed_mps"]
            duration = 2 * distance / velocity
            t = np.linspace(0, 0.3, 3001)
            pulse = np.where(
                t < duration, np.pi * velocity / (2 * duration) * np.sin(np.pi * t / duration), 0
            )
            r = contact.response(t, 9.80665 + pulse, self.design.payload_mass_kg, p)
            r.update(stop_distance_m=distance, assumption="full impact speed along mount axis")
            landing.append(r)
        worst = landing[0]
        distance = 0.005
        velocity = f["impact_speed_mps"]
        duration = 2 * distance / velocity
        t = np.linspace(0, 0.3, 6001)
        pulse = np.where(
            t < duration, np.pi * velocity / (2 * duration) * np.sin(np.pi * t / duration), 0
        )
        fine = contact.response(
            t,
            9.80665 + pulse,
            self.design.payload_mass_kg,
            p.model_copy(update={"max_step_s": p.max_step_s / 2}),
        )
        change = abs(fine["peak_contact_force_n"] / worst["peak_contact_force_n"] - 1)
        return {
            "cases": cases,
            "landing": landing,
            "landing_time_refinement": change,
            "numerical_pass": change < self.config.observable_relative_tolerance,
            "scope": "scalar load-magnitude envelope; separate event equilibrium assumptions",
        }

    def _structure(self):
        if self.solver is None:
            raise FileNotFoundError(
                "CalculiX executable required for nonlinear structural analysis"
            )
        cfg = self.config
        out = self.output / "fem"
        check = verification.fem_limits(self.solver, out / "verification")
        if not check["passed"]:
            raise RuntimeError("FEM analytical-limit verification failed")
        f = self.results["flight"]["nominal"]
        warm = self.results["thermal"]["sealed"]["final_c"]
        mounts = (
            list(self.results["contact"]["cases"].values()) + self.results["contact"]["landing"]
        )
        force = max(r["peak_wall_reaction_n"] for r in mounts)
        q = max(f["max_q_pa"], self.results["flight"]["warm_sealed_scenario"]["max_q_pa"])
        results = {
            "benchmarks": check,
            "load_envelope": {"q_pa": q, "collar_force_n": force},
            "cases": {},
        }
        for label, temp in [("nominal", 20.0), ("warm", warm["fin"])]:
            history = []
            for level in range(1, cfg.maximum_mesh_level + 1):
                r = aeroelastic.coupled_fin(
                    self.solver,
                    out / f"fin-{label}-{level}",
                    self.assembly,
                    cfg,
                    q,
                    temperature_c=temp,
                    resolution=level,
                )
                history.append(r)
                if len(history) >= 2 and self._mesh_change(history[-2]["fem"], r["fem"])["pass"]:
                    break
            change = self._mesh_change(history[-2]["fem"], history[-1]["fem"])
            results["cases"]["fin-" + label] = {"meshes": history, "mesh_check": change}
        for label, temp in [("nominal", 20.0), ("warm", warm["mount"])]:
            history = []
            for level in range(1, cfg.maximum_mesh_level + 1):
                deck = fem.collar_deck(
                    self.assembly, cfg, force, temperature_c=temp, resolution=level
                )
                history.append(self._fem_case(out / f"collar-{label}-{level}", "collar", deck))
                if len(history) >= 2 and self._mesh_change(history[-2], history[-1])["pass"]:
                    break
            results["cases"]["collar-" + label] = {
                "meshes": history,
                "mesh_check": self._mesh_change(*history[-2:]),
            }
        for label, temp, pressure in [
            ("nominal", 20.0, self.design.initial_gauge_pressure_pa),
            (
                "warm",
                warm["skin"],
                self.results["thermal"]["sealed"]["peak_absolute_pressure_pa"]
                - cfg.loads.ambient_pa,
            ),
        ]:
            history = []
            for level in range(1, cfg.maximum_mesh_level + 1):
                deck = fem.body_deck(
                    self.assembly,
                    cfg,
                    pressure,
                    temperature_c=temp,
                    resolution=level,
                    axial_compression_n=force,
                    transverse_n=force * 0.1,
                    ovality=0.003,
                )
                history.append(self._fem_case(out / f"body-{label}-{level}", "body", deck))
                if len(history) >= 2 and self._mesh_change(history[-2], history[-1])["pass"]:
                    break
            results["cases"]["body-" + label] = {
                "meshes": history,
                "mesh_check": self._mesh_change(*history[-2:]),
            }
        # Explicit exploratory material alternatives, not assigned physical properties.
        ortho = cfg.model_copy(deep=True)
        ortho.collar_material = (cfg.collar_material or cfg.material).model_copy(deep=True)
        ortho.collar_material.engineering_constants = (
            2e9,
            1.4e9,
            0.8e9,
            0.25,
            0.25,
            0.25,
            0.6e9,
            0.3e9,
            0.3e9,
        )
        results["orthotropy_sensitivity"] = self._fem_case(
            out / "collar-orthotropic",
            "collar",
            fem.collar_deck(self.assembly, ortho, force, temperature_c=warm["mount"], resolution=2),
        )
        creep = cfg.model_copy(deep=True)
        creep.creep_reference_rate_per_s = 1e-7
        results["creep_sensitivity"] = self._fem_case(
            out / "body-creep",
            "body",
            fem.body_deck(
                self.assembly,
                creep,
                self.design.initial_gauge_pressure_pa,
                temperature_c=warm["skin"],
                resolution=2,
            ),
        )
        sleeve = copy.deepcopy(self.assembly)
        sleeve["dimensions_mm"]["bottle_length"] = sleeve["dimensions_mm"]["egg_bay_length"]
        length = sleeve["dimensions_mm"]["bottle_length"] / 1000
        radius = sleeve["dimensions_mm"]["body_diameter"] / 2000
        results["sleeve_compression"] = self._fem_case(
            out / "sleeve",
            "sleeve",
            fem.body_deck(
                sleeve,
                cfg,
                0.0,
                temperature_c=warm["mount"],
                profile=[[0, radius], [length, radius]],
                axial_compression_n=force,
                transverse_n=force * 0.1,
                ovality=0.003,
                resolution=2,
            ),
        )
        # Demand screens expose unsupported joint strength rather than guessing an allowable.
        overlap = 0.02
        width = self.assembly["dimensions_mm"]["fin_root"] / 1000
        finforce = max(
            results["cases"][key]["meshes"][-1]["metadata"]["force_target_n"]
            for key in ("fin-nominal", "fin-warm")
        )
        results["joint_demands"] = {
            "collar_axial_n": force,
            "fin_assumed_bond_shear_pa": finforce / (width * overlap),
            "fin_assumed_bond_peel_pa": 6 * finforce * 0.07 / (width * overlap**2),
            "scope": "assumed overlap 20 mm, peel from 70 mm lever; no joint allowable",
        }
        results["strength_status"] = "unknown: actual geometry/material/support allowables required"
        return results

    def _fem_case(self, folder, name, deck):
        lines, nodes, elements, meta = deck
        r = fem.run_deck(self.solver, folder, name, lines)
        r["metadata"] = meta
        r["geometry"] = {"nodes": nodes, "elements": [e[0] for e in elements]}
        return r

    def _mesh_change(self, coarse, fine):
        changes = {
            k: abs(coarse[k] / fine[k] - 1) for k in ["max_displacement_m", "p95_integration_vm_pa"]
        }
        return {
            "observables": changes,
            "pass": max(changes.values()) < self.config.observable_relative_tolerance,
            "scope": "displacement and 95th-percentile stress; peak stress not qualified",
        }

    def _stability(self):
        return {
            "pitch": stability.pitch(
                self.assembly, self.results["flight"]["nominal"], self.design, self.config.flight
            ),
            "flutter": stability.flutter(self.assembly, self.config),
            "warm_flutter": stability.flutter(
                self.assembly,
                self.config,
                temperature_c=self.results["thermal"]["sealed"]["final_c"]["fin"],
            ),
        }

    def _uncertainty(self):
        rng = np.random.default_rng(self.config.flight.seed)
        n = self.config.flight.sample_count
        strata = np.array([(rng.permutation(n) + rng.random(n)) / n for _ in range(5)]).T
        samples = []
        for i, row in enumerate(strata):
            pressure = self.design.initial_gauge_pressure_pa * (0.9 + 0.2 * row[0])
            d = self.design.model_copy(update={"initial_gauge_pressure_pa": pressure})
            fcfg = self.config.flight.model_copy(
                update={
                    "wind_mps": 4 * row[1],
                    "gust_mps": 2 * row[2],
                    "opening_s": 0.05 + 0.25 * row[3],
                }
            )
            p = loads.propulsion(d, self.config.loads)
            f = flight.run(
                d, self.assembly, p, fcfg, cd_scale=0.7 + 0.8 * row[4], cn_scale=0.8 + 0.4 * row[2]
            )
            f.pop("trace", None)
            samples.append(
                {
                    "sample": i,
                    "pressure_pa": pressure,
                    "wind_mps": fcfg.wind_mps,
                    "opening_s": fcfg.opening_s,
                    "result": f,
                }
            )
        return {
            "seed": self.config.flight.seed,
            "samples": samples,
            "scope": "assumed stratified ranges; not measured probability distributions",
            "qualified": False,
        }

    def _verdict(self):
        failed = [k for k, v in self.results.items() if v["execution_status"] != "completed"]
        missing = self.results["evidence"].get("missing", list(evidence.REQUIRED))
        structure = self.results.get("structure", {})
        cases = structure.get("cases", {})
        mesh_pass = bool(cases) and all(r["mesh_check"]["pass"] for r in cases.values())
        coupling_pass = bool(cases) and all(
            cases[k]["meshes"][-1]["completed"] and cases[k]["meshes"][-1]["aero_domain_pass"]
            for k in ("fin-nominal", "fin-warm")
            if k in cases
        )
        return {
            "physical_status": "not_qualified",
            "qualified": False,
            "failed_methods": failed,
            "missing_evidence": missing,
            "cfd_transfer": "diagnostic_only",
            "required_followup": evidence.REQUIRED,
            "conclusion": "Executed conditional analyses do not establish actual article safety",
            "numerical_checks": {
                "all_structural_mesh_observables": mesh_pass,
                "fin_load_deformation_fixed_point": coupling_pass,
                "propulsion_conservation": all(
                    r["energy_balance_relative"] < 1e-5 and r["mass_balance_relative"] < 1e-5
                    for r in self.results.get("propulsion", {}).values()
                    if isinstance(r, dict) and "energy_balance_relative" in r
                ),
                "flight": self.results.get("flight", {}).get("numerical_pass", False),
                "contact": self.results.get("contact", {}).get("numerical_pass", False),
                "fem_benchmarks": self.results.get("structure", {})
                .get("benchmarks", {})
                .get("passed", False),
            },
        }
