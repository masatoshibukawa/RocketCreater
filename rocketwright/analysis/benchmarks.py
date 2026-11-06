"""Independent exact cases and published flight comparisons, with explicit scope limits."""

import math

import numpy as np

from rocketwright.analysis.screening import axial_flight
from rocketwright.physics.bottle_integrity import loads, thermal
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig, LoadConfig
from rocketwright.physics.fin_candidates import beam
from rocketwright.schema import BottleDesign

SOURCE = "https://arxiv.org/html/2001.08828"
# Fischer et al., Table 2, launches 1–4 and 6. Pressures in the paper are ABSOLUTE.
# The first, second and fourth flights were previously used by the legacy water model.
# No parameters are fitted in this module, including on the two additional cases.
FLIGHTS = (
    (1, 17, 0.350, 3.5, 17.5, "legacy calibration overlap"),
    (2, 17, 0.325, 3.5, 17.1, "legacy calibration overlap"),
    (3, 17, 0.255, 3.0, 14.1, "additional fixed audit"),
    (4, 17, 0.255, 3.5, 17.4, "legacy calibration overlap"),
    (6, 35, 0.250, 2.5, 7.6, "off-nominal launch stress case"),
)


def run():
    rows = []
    for number, temp, fill, absolute_bar, observed, split in FLIGHTS:
        d = BottleDesign(
            bottle_volume_m3=0.001,
            water_fill_frac=fill,
            initial_gauge_pressure_pa=absolute_bar * 100000 - 100000,
            nozzle_diameter_m=0.009,
            dry_mass_kg=0.143,
            axial_drag_coefficient=0.6,
        )
        cfg = LoadConfig(
            ambient_pa=100000,
            initial_k=temp + 273.15,
            ambient_k=temp + 273.15,
            initial_wall_k=temp + 273.15,
        )
        p = loads.propulsion(d, cfg)
        nominal = axial_flight(d, p, area=math.pi * 0.04**2, cd=0.6)
        band = [axial_flight(d, p, area=math.pi * 0.04**2, cd=cd)["apogee_m"] for cd in (0.4, 0.8)]
        error = nominal["apogee_m"] - observed
        rows.append(
            dict(
                launch=number,
                split=split,
                observed_m=observed,
                measurement_error_m=0.5,
                predicted_m=nominal["apogee_m"],
                error_m=error,
                relative_error=error / observed,
                within_measurement=abs(error) <= 0.5,
                cd_scenario_height_m=[min(band), max(band)],
                completed=p["completed"],
                mass_balance_relative=p["mass_balance_relative"],
                energy_balance_relative=p["energy_balance_relative"],
            )
        )

    # Independent analytic constant-thrust / vacuum coast reference.
    prop = {"trace": {"time_s": [0, 1], "mass_kg": [1, 1], "thrust_n": [20, 20]}}
    g = 9.80665
    exact = (20 - g) / 2 + (20 - g) ** 2 / (2 * g)
    computed = axial_flight(None, prop, area=0, cd=0, max_step=0.001)["apogee_m"]

    # Constant rectangular beam with a finite distributed foundation: closed form.
    length, chord, thickness, young, force, root_k, tab = 0.12, 0.06, 0.002, 2e9, 1, 5e5, 0.01
    root_matrix = root_k * np.array([[1, -tab / 2], [-tab / 2, tab**2 / 3]])
    root = np.linalg.solve(root_matrix, [force, force * length / 2])
    exact_tip = (
        force * length**3 / (8 * young * chord * thickness**3 / 12) + root[0] + root[1] * length
    )
    calculated = beam(length, chord, chord, thickness, young, 1240, root_k, force, tab=tab)

    # With no heat exchange during liquid expulsion, p V^gamma is invariant.
    cfg = LoadConfig(gas_wall_h=0, outside_h=0)
    d = BottleDesign(
        bottle_volume_m3=0.001,
        water_fill_frac=0.3,
        initial_gauge_pressure_pa=250000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.143,
    )
    p = loads.propulsion(d, cfg)
    tr = p["trace"]
    liquid = np.asarray(tr["time_s"]) <= p["liquid_end"]["time_s"]
    volume = d.bottle_volume_m3 - np.asarray(tr["water_kg"])[liquid] / 1000
    invariant = np.asarray(tr["pressure_pa"])[liquid] * volume**cfg.gamma
    pv_error = float(np.max(abs(invariant / invariant[0] - 1)))
    heat = thermal.wait(
        d, AnalysisConfig(solar_w_m2=0, warm_wait_s=120), ambient_c=20, initial_c=20, sealed=True
    )
    thermal_error = max(abs(v - 20) for v in heat["final_c"].values())
    verification = dict(
        axial_relative_error=abs(computed - exact) / exact,
        beam_relative_error=abs(calculated["tip_m"] - exact_tip) / exact_tip,
        gas_pv_relative_error=pv_error,
        thermal_equilibrium_error_c=thermal_error,
    )
    checks = dict(
        axial=verification["axial_relative_error"] < 1e-4,
        beam=verification["beam_relative_error"] < 1e-6,
        gas=pv_error < 1e-6,
        thermal=thermal_error < 1e-6,
    )
    return dict(
        verification=verification,
        verification_checks=checks,
        reference_flights=rows,
        source=SOURCE,
        source_location="Section 9, Table 2",
        fit_performed=False,
        coefficients_changed=False,
        reference_rms_relative_error=float(
            np.sqrt(np.mean([r["relative_error"] ** 2 for r in rows]))
        ),
        scope="Production discharge plus vertical axial model; not the complete 6DOF/CFD airframe",
        limitations=[
            "0.9 discharge and heat exchange coefficients remain assumptions",
            "launch 6 includes reported launch friction/leakage and is kept separate",
            "no CFD surface-geometry or printed-strength experimental validation",
            "small-grid differences are not bounds on physical model error",
        ],
        physical_qualification=False,
        aircraft_validation=False,
        metrics={"exact_benchmarks_pass": all(checks.values())},
    )
