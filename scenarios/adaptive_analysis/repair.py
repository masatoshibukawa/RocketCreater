"""Return from failed mission tradeoffs to geometry, with old aero explicitly invalidated."""

import argparse
import copy
import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rocketwright.adaptive import Campaign, Requirements, digest  # noqa: E402
from rocketwright.physics.bottle_integrity import aeroelastic, fem  # noqa: E402
from rocketwright.physics.bottle_integrity.harness import write_json  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig, Material  # noqa: E402
from rocketwright.physics.fin_candidates import PROFILES, beam, reconcile_mass  # noqa: E402
from rocketwright.physics.stability import trapezoidal_fin_force  # noqa: E402
from rocketwright.schema import BottleDesign, FinSet  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def geometry_candidates(packet, prior, requirements):
    design = BottleDesign(**packet["design"])
    original = packet["assembly"]
    event = prior["fin-candidates"]["value"]["load_event"]
    temperature = prior["fin-candidates"]["value"]["temperature_c"]
    rows = []
    choices = itertools.product(
        (80, 100, 120, 140),
        (70, 90),
        (0.75, 1, 1.5, 2, 2.5, 3),
        ("reference_assumption", "stiff_assumption"),
        (5e5, 5e6),
    )
    for span, root, thickness, profile, spring in choices:
        article = copy.deepcopy(original)
        g = article["dimensions_mm"]
        g.update(fin_span=span, fin_root=root, fin_tip=root / 2)
        fin = FinSet(
            count=4,
            root_chord_m=root / 1000,
            tip_chord_m=root / 2000,
            span_m=span / 1000,
            sweep_m=g["fin_sweep"] / 1000,
        )
        start = (g["overall"] - g["fin_tail_inset"] - root) / 1000
        cn, cp_fin = trapezoidal_fin_force(g["body_diameter"] / 1000, fin, start)
        article["cp_mm"] = (2 * g["nose_length"] * 2 / 3 + cn * cp_fin * 1000) / (2 + cn)
        article["fin_set_CNalpha_per_rad"] = cn
        prop = PROFILES[profile]
        warm_ratio = 1 + (prop["warm_ratio"] - 1) * (temperature - 20) / 35
        force = event["force_one_fin_n"] * cn / original["fin_set_CNalpha_per_rad"]
        result = beam(
            span / 1000,
            root / 1000,
            root / 2000,
            thickness / 1000,
            prop["young_pa"] * warm_ratio,
            prop["density"],
            spring,
            force,
            n=20,
        )
        mass = 4 * result["mass_one_fin_kg"]
        changed, article = reconcile_mass(design, article, mass)
        # Exact trapezoidal area centroid in the axial direction; add the rectangular tab.
        cr, ct, sweep, tab = root / 1000, root / 2000, g["fin_sweep"] / 1000, g["fin_tab"] / 1000
        xplate = (
            start
            + sweep * (cr + 2 * ct) / (3 * (cr + ct))
            + (cr * cr + cr * ct + ct * ct) / (3 * (cr + ct))
        )
        plate_area, tab_area = span / 1000 * (cr + ct) / 2, cr * tab
        station = (plate_area * xplate + tab_area * (start + cr / 2)) / (plate_area + tab_area)
        bill = next(b for b in article["bill"] if b["id"] == "carton_fin")
        moment_shift = mass * (station - bill["station_mm"] / 1000)
        water = 1000 * changed.bottle_volume_m3 * changed.water_fill_frac
        loaded = changed.dry_mass_kg + changed.payload_mass_kg
        for key, total in (
            ("dry_cg_mm", changed.dry_mass_kg),
            ("loaded_cg_mm", loaded),
            ("wet_cg_mm", loaded + water),
        ):
            article[key] += 1000 * moment_shift / total
        bill["station_mm"] = 1000 * station
        # Reuse the existing project screen: 15 mm adverse water-centroid shift.
        wet_margin = article["cp_mm"] - article["wet_cg_mm"] - 15 * water / (loaded + water)
        dry_margin = article["cp_mm"] - article["loaded_cg_mm"]
        ratio = result["max_deflection_m"] / (span / 1000)
        passed = min(wet_margin, dry_margin) > 0 and ratio <= requirements.fin_deflection_span_ratio
        rows.append(
            dict(
                id=f"s{span}-r{root}-t{thickness}-{profile}-k{spring:g}",
                span_mm=span,
                root_mm=root,
                thickness_mm=thickness,
                profile=profile,
                root_k_n_m=spring,
                fin_mass_kg=mass,
                dry_mass_kg=changed.dry_mass_kg,
                deflection_span_ratio=ratio,
                first_mode_hz=result["first_modes_hz"][0],
                wet_margin_with_water_shift_mm=wet_margin,
                dry_margin_mm=dry_margin,
                screen_pass=passed,
                CFD_invalidated=True,
                nonlinear_FEM_required=True,
                design=changed.model_dump(),
                assembly=article,
            )
        )
    feasible = [r for r in rows if r["screen_pass"]]

    def dominates(a, b):
        av = (a["dry_mass_kg"], a["deflection_span_ratio"], -a["wet_margin_with_water_shift_mm"])
        bv = (b["dry_mass_kg"], b["deflection_span_ratio"], -b["wet_margin_with_water_shift_mm"])
        return all(x <= y for x, y in zip(av, bv, strict=True)) and any(
            x < y for x, y in zip(av, bv, strict=True)
        )

    frontier = [r for r in feasible if not any(dominates(other, r) for other in feasible)]
    frontier.sort(key=lambda r: (r["dry_mass_kg"], r["root_k_n_m"]))
    return dict(
        candidates=rows,
        pareto_ids=[r["id"] for r in frontier],
        lightest=frontier[0] if frontier else None,
        criteria=dict(
            deflection_span_limit=requirements.fin_deflection_span_ratio,
            positive_dry_and_adverse_wet_CP_minus_CG=True,
        ),
        scope=(
            "Conditional structural/static screen only. "
            "New geometry cannot reuse old CFD as qualified evidence."
        ),
        next_required=[
            "geometry-specific CFD with wall/grid verification",
            "nonlinear FEM and joint data",
            "recomputed flight loads and mission evaluation",
        ],
        metrics=dict(
            geometry_screen_feasible_count=len(feasible), geometry_candidate_exists=bool(feasible)
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("campaign", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--solver", type=Path, required=True)
    args = p.parse_args()
    packet, prior = read(args.input), read(args.campaign / "results.json")
    requirements = Requirements(**read(args.campaign / "requirements.json"))
    # Import results as immutable prior evidence, never as a current cache entry.
    for key in ("fin-candidates", "mass-reflight"):
        result = prior[key]
        payload = {k: v for k, v in result.items() if k != "artifact_hash"}
        if result["execution_status"] != "completed" or digest(payload) != result["artifact_hash"]:
            raise ValueError("Prior artifact incomplete or modified")

    def review(params, output, host):
        flights = prior["mass-reflight"]["value"]["cases"]
        needed = all(c["apogee_m"] < requirements.altitude_target_m for c in flights)
        return dict(
            rejected_thickness_only_candidates=[c["candidate"] for c in flights],
            metrics=dict(
                geometry_repair_needed=needed,
                altitude_shortfall=max(
                    requirements.altitude_target_m - c["apogee_m"] for c in flights
                ),
            ),
            reason="stiffness-only choices lost mission performance; reopen low-layer geometry",
        )

    def screen(params, output, host):
        result = geometry_candidates(packet, prior, requirements)
        for row in result["candidates"]:
            if row["id"] in result["pareto_ids"]:
                write_json(output / (row["id"] + ".json"), row)
        return result

    def structural(params, output, host):
        row = host.results["geometry-candidates"]["value"]["lightest"]
        cfg = AnalysisConfig(**packet["config"])
        cfg.fin_material = Material(**PROFILES[row["profile"]])
        cfg.fin_thickness_m = row["thickness_mm"] / 1000
        cfg.fin_root_k_n_m = row["root_k_n_m"]
        event = prior["fin-candidates"]["value"]["load_event"]
        temperature = prior["fin-candidates"]["value"]["temperature_c"]
        history = []
        for level in (2, 3, 4):
            deck, nodes, elements, meta = fem.fin_deck(
                row["assembly"],
                cfg,
                event["q_pa"],
                resolution=level,
                temperature_c=temperature,
                incidence_deg=event["incidence_deg"],
            )
            result = fem.run_deck(args.solver, output / f"mesh{level}", "fin", deck)
            twist, peak = aeroelastic.mean_twist(nodes, result["node_displacements_m"])
            result.update(
                twist_deg=twist,
                peak_twist_deg=peak,
                geometry={"nodes": nodes, "elements": [e[0] for e in elements]},
            )
            write_json(output / f"mesh{level}" / "result.json", result)
            history.append(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("geometry", "node_displacements_m", "integration_stress_pa")
                }
            )
            if len(history) > 1:
                change = {
                    k: abs(history[-2][k] / result[k] - 1)
                    for k in ("max_displacement_m", "p95_integration_vm_pa")
                }
                if max(change.values()) < requirements.grid_relative_limit:
                    break
        return dict(
            candidate=row["id"],
            meshes=history,
            mesh_change=change,
            numerical_pass=max(change.values()) < requirements.grid_relative_limit,
            aero_load_domain_pass=event["aero_load_domain_pass"],
            strength_status="unknown",
            temperature_c=temperature,
            reference_load_event=event,
            applied_force_one_fin_n=meta["force_target_n"],
        )

    def aero(params, output, host):
        row = host.results["geometry-candidates"]["value"]["lightest"]
        article_path = output / "assembly.json"
        write_json(article_path, row["assembly"])
        cases = []
        for cells, angle in ((16, 0), (16, 5), (16, 10), (16, 15), (24, 5)):
            directory = output / f"d{cells}-a{angle:03}"
            print("REPAIR CFD", cells, angle, flush=True)
            try:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scenarios/cfd/run_flow.py"),
                        str(article_path.resolve()),
                        str(directory.resolve()),
                        "--shape",
                        "flat",
                        "--cells",
                        str(cells),
                        "--speed",
                        "18",
                        "--angle",
                        str(angle),
                        "--width",
                        "10",
                        "--times",
                        "40",
                        "--rotate-geometry",
                        "--surface-loads",
                        "--no-preview",
                    ],
                    check=True,
                    cwd=ROOT,
                    timeout=900,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise RuntimeError("New geometry CFD failed") from error
            cases.append(read(directory / "case.json"))
        keys = ("Cx", "Cy", "Cm_z")
        coarse = next(c for c in cases if c["d"] == 16 and c["angle_deg"] == 5)
        fine = next(c for c in cases if c["d"] == 24 and c["angle_deg"] == 5)
        differences = {k: abs(coarse["mean"][k] / fine["mean"][k] - 1) for k in keys}
        return dict(
            candidate=row["id"],
            cases=cases,
            grid16_to24=differences,
            numerical_pass=False,
            scope=(
                "Geometry-specific diagnostic probes; incomplete full-angle table and grid evidence"
            ),
            metrics={"new_geometry_aero_qualified": False},
        )

    host = Campaign(
        args.output,
        inputs=dict(
            repair_evidence=digest(prior),
            geometry=digest(packet["assembly"]),
            material=digest(PROFILES),
            requirements=digest(requirements.model_dump()),
            code=digest(
                {
                    str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
                    for p in (
                        Path(__file__),
                        ROOT / "rocketwright/physics/fin_candidates.py",
                        ROOT / "rocketwright/physics/stability.py",
                        ROOT / "rocketwright/physics/bottle_integrity/fem.py",
                        ROOT / "scenarios/cfd/run_flow.py",
                        ROOT / "scenarios/cfd/bottle_flow.cu",
                    )
                }
            ),
        ),
        runners={
            "repair_audit": review,
            "geometry_screen": screen,
            "fin_nonlinear": structural,
            "cfd": aero,
        },
        capabilities=["cuda", "calculix"],
        memory_gib=8,
        budget_s=600,
        requirements=requirements,
    )
    host.run()
    if "geometry-candidates" not in host.results:
        print("No geometry repair selected", flush=True)
        return
    result = host.results["geometry-candidates"]["value"]
    print(
        json.dumps(
            dict(
                count=len(result["candidates"]),
                feasible=result["metrics"],
                pareto=len(result["pareto_ids"]),
                lightest=result["lightest"]["id"] if result["lightest"] else None,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
