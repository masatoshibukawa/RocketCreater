"""Independent conservation and analytic-limit checks on a completed MATLAB study."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.linalg import eigvalsh


def verify(folder: Path) -> dict:
    def read(name):
        return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))

    assert read("run-status")["state"] == "complete"
    data, source = read("results"), read("input")
    cfg = data["assumptions"]
    assert data["physical_status"] == "not_qualified"
    assert data["source_sha256"] == source["source_sha256"]
    d, g = source["design"], source["assembly"]["dimensions_mm"]
    p = cfg["thermal"]
    for row in data["thermal"]["cooling"]:
        expected = (p["gas_initial_C"] + 273.15) * (1 - d["water_fill_frac"]) ** (
            row["polytropic_exponent"] - 1
        ) - 273.15
        assert abs(row["gas_end_C"] - expected) < 1e-7
        assert row["refinement_delta_K"] < 0.01
        if row["polytropic_exponent"] == 1.4:
            assert abs(row["water_end_s"] - source["water_end_s"]) < 1e-4
    # External heat integrated independently equals total sensible energy increase.
    heat_errors = []
    capacities = np.array(
        [
            p["skin_mass_kg"] * p["skin_cp_j_kg_k"],
            source["assembly"]["print_parts"]["pair_solid_pla_g"]
            / 1000
            * cfg["collar"]["cp_j_kg_k"],
            d["payload_mass_kg"] * p["payload_cp_j_kg_k"],
            p["exposed_fin_mass_kg"] * p["fin_cp_j_kg_k"],
        ]
    )
    area = math.pi * g["body_diameter"] * g["egg_bay_length"] / 1e6
    projection = area / math.pi
    fin_area = (g["fin_root"] + g["fin_tip"]) * g["fin_span"] / 2e6
    for sun in data["thermal"]["sun"]:
        temps = np.array([sun[k] for k in ("skin_C", "mount_C", "payload_C", "fin_C")]).T
        rad = (
            p["emissivity"]
            * 5.670374419e-8
            * ((temps + 273.15) ** 4 - (p["ambient_C"] + 273.15) ** 4)
        )
        losses = p["outside_h_w_m2_k"] * (temps - p["ambient_C"]) + rad
        external = sun["absorptivity"] * p["solar_w_m2"] * (projection + fin_area)
        external = external - area * losses[:, 0] - 2 * fin_area * losses[:, 3]
        heat = np.trapezoid(external, sun["time_s"])
        stored = (temps[-1] - temps[0]) @ capacities
        error = abs(heat - stored) / abs(stored)
        assert error < 0.002
        heat_errors.append(error)
    # Compare distributed-load deflection to an independent virtual-work integral.
    beam_errors = []
    p = cfg["fin"]
    L, c0, c1 = (g[k] / 1000 for k in ("fin_span", "fin_root", "fin_tip"))
    b = (c1 - c0) / L
    for a in data["fin"]["cases"]:
        if not a["applicable"]:
            assert a["pitch"] == []
        if not a["static_equilibrium_exists"]:
            assert a["tip_deflection_m"] is None
        if a["offset_chord_fraction"] != 0:
            continue
        coeff = (
            a["dynamic_pressure_pa"]
            * source["fin_set_CNalpha_per_rad"]
            / 2
            * math.pi
            * (g["body_diameter"] / 2000) ** 2
            * math.radians(p["incidence_deg"])
            / ((c0 + c1) * L / 2)
        )

        def moment(x, coeff=coeff):
            return coeff * (c0 * (L - x) ** 2 / 2 + b * (L**3 / 3 - x * L**2 / 2 + x**3 / 6))

        E = p["E_pa"] * a["stiffness_ratio"]
        integral = quad(
            lambda x, E=E: (L - x) * moment(x) / (E * (c0 + b * x) * p["thickness_m"] ** 3 / 12),
            0,
            L,
        )[0]
        root_ratio = {
            "bonded": 1,
            "two_slipping_plies": 1,
            "stiffer_root": 10,
            "warm_bonded": a["stiffness_ratio"],
        }[a["case_name"]]
        expected = integral + moment(0) * L / (p["root_bend_stiffness_nm_rad"] * root_ratio)
        error = abs(a["tip_deflection_m"] - expected) / abs(expected)
        assert error < 0.001
        beam_errors.append(error)
    p = cfg["mount"]
    K = np.array(
        [
            [p["wall_stiffness_n_m"] + p["pad_stiffness_n_m"], -p["pad_stiffness_n_m"]],
            [-p["pad_stiffness_n_m"], p["pad_stiffness_n_m"]],
        ]
    )
    freq = np.sqrt(eigvalsh(K, np.diag([p["support_mass_kg"], d["payload_mass_kg"]]))) / (2 * np.pi)
    assert np.allclose(freq, data["payload"]["mode_hz"], rtol=1e-10)
    for case in data["payload"]["cases"]:
        if case["linear_response_applicable"]:
            assert case["first_travel_limit_s"] is None
        else:
            assert case["peak_pad_travel_mm"] >= p["available_stroke_m"] * 1000
    body = data["body"]["wall"]
    force = d["initial_gauge_pressure_pa"] * math.pi * (g["body_diameter"] / 2000) ** 2
    axial = np.array(body["axial_MPa"]) * 1e6
    assert np.allclose(axial * 2 * math.pi * g["body_diameter"] / 2000 * body["thickness_m"], force)
    collar = data["collar"]
    assert collar["displacement_grid_check"] and collar["interior_stress_grid_check"]
    assert collar["force_balance_check"]
    assert collar["load_integration_check"]
    assert max(x["superposition_relative"] for x in collar["mesh"]) < 1e-6
    summary = {
        "numerical_verification": "passed_for_reported_observables",
        "physical_validation": "not_performed",
        "solar_energy_balance_max_relative": max(heat_errors),
        "fin_virtual_work_max_relative": max(beam_errors),
        "collar_final_force_balance_relative": collar["mesh"][-1]["force_balance_relative"],
        "payload_time_refinement_relative": data["payload"]["refinement_relative"],
        "unresolved_numerical_checks": [
            "clamp point stress and stress-recovered boundary traction"
        ],
    }
    (folder / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    print(json.dumps(verify(parser.parse_args().folder), indent=2))
