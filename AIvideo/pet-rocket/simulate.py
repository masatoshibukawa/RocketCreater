"""Continuous water/air blowdown and conditional vertical ascent for the v2 PET design."""

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent
G, R, GAMMA, RHO_W = 9.80665, 287.05, 1.4, 1000.0


def gas_nozzle(pressure, temperature, ambient, effective_area):
    """Isentropic reservoir-to-convergent-nozzle discharge, including pressure thrust."""
    if pressure <= ambient:
        return 0.0, 0.0, 0.0, ambient
    ratio = ambient / pressure
    critical = (2 / (GAMMA + 1)) ** (GAMMA / (GAMMA - 1))
    if ratio <= critical:
        exit_pressure = pressure * critical
        exit_temperature = temperature * 2 / (GAMMA + 1)
        velocity = math.sqrt(GAMMA * R * exit_temperature)
        flow = effective_area * pressure / math.sqrt(R * temperature) * math.sqrt(GAMMA) * (2 / (GAMMA + 1)) ** ((GAMMA + 1) / (2 * (GAMMA - 1)))
    else:
        exit_pressure = ambient
        velocity = math.sqrt(2 * GAMMA / (GAMMA - 1) * R * temperature * (1 - ratio ** ((GAMMA - 1) / GAMMA)))
        flow = effective_area * pressure / math.sqrt(R * temperature) * math.sqrt(2 * GAMMA / (GAMMA - 1) * (ratio ** (2 / GAMMA) - ratio ** ((GAMMA + 1) / GAMMA)))
    thrust = flow * velocity + (exit_pressure - ambient) * effective_area
    return flow, thrust, velocity, exit_pressure


def design_values():
    parameters = json.loads((ROOT / "source-data/parameters.json").read_text())
    geometry = json.loads((ROOT / "source-data/geometry.json").read_text())
    assembly = json.loads((ROOT / "source-data/assembly.json").read_text())
    parts = geometry["parts"]
    part_mass = (parts["nose_cone"]["solid_mass_g_at_assumed_density"] + parameters["fin"]["count"] * parts["fin"]["solid_mass_g_at_assumed_density"]) / 1000
    return {
        "bottle_diameter_m": parameters["bottle"]["body_diameter"] / 1000,
        "max_body_diameter_m": geometry["nose_analytic"]["outer_diameter_mm"] / 1000,
        "bottle_height_m": parameters["bottle"]["height"] / 1000,
        "height_m": (assembly["nose_base_z_mm"] + geometry["nose_analytic"]["height_mm"]) / 1000,
        "span_m": 2 * parts["fin"]["bounds_mm"][1][0] / 1000,
        "cad_parts_mass_kg": part_mass,
        "nose_mass_kg": parts["nose_cone"]["solid_mass_g_at_assumed_density"] / 1000,
        "one_fin_mass_kg": parts["fin"]["solid_mass_g_at_assumed_density"] / 1000,
        "fin_count": parameters["fin"]["count"],
        "fin_azimuth_deg": [item["azimuth_deg"] for item in assembly["fins"]],
        "nose_base_z_m": assembly["nose_base_z_mm"] / 1000,
    }


def integrate(config, design, step=0.001, drag_override=None):
    volume = config["volume_m3"]
    water0 = volume * config["fill_fraction"] * RHO_W
    gas_volume0 = volume - water0 / RHO_W
    pressure0 = config["ambient_pressure_pa"] + config["gauge_pressure_pa"]
    if pressure0*(gas_volume0/volume)**GAMMA <= config["ambient_pressure_pa"]:
        raise ValueError("This ascent recipe requires complete water expulsion; residual-water scenarios need a separate model")
    gas_mass0 = pressure0 * gas_volume0 / (R * config["temperature_k"])
    dry = design["cad_parts_mass_kg"] + config["bottle_mass_kg"] + config["nozzle_mass_kg"] + config["retention_mass_kg"]
    area = math.pi * (config["nozzle_diameter_m"] / 2) ** 2 * config["discharge_coefficient"]
    # Use the actual maximum nose diameter, not a volume-derived bottle diameter.
    frontal_area = math.pi * (design["max_body_diameter_m"] / 2) ** 2
    cd = config["drag_coefficient"] if drag_override is None else drag_override
    phases = []
    state = np.array([0.0, 0.0, water0, gas_mass0, 0.0, 0.0, 0.0])
    t = 0.0
    gas_reference = None

    def quantities(y, phase):
        water = max(float(y[2]), 0.0)
        gas_mass = max(float(y[3]), 1e-12)
        if phase == "water":
            gas_volume = volume - water / RHO_W
            pressure = pressure0 * (gas_volume0 / gas_volume) ** GAMMA
            temperature = config["temperature_k"] * (gas_volume0 / gas_volume) ** (GAMMA - 1)
            velocity = math.sqrt(max(0, 2 * (pressure - config["ambient_pressure_pa"]) / RHO_W))
            water_flow = RHO_W * area * velocity
            return pressure, temperature, water_flow * velocity, water_flow, 0.0, velocity
        if phase == "air":
            ref_mass, ref_temperature = gas_reference
            temperature = ref_temperature * (gas_mass / ref_mass) ** (GAMMA - 1)
            pressure = gas_mass * R * temperature / volume
            flow, thrust, velocity, _ = gas_nozzle(pressure, temperature, config["ambient_pressure_pa"], area)
            return pressure, temperature, thrust, 0.0, flow, velocity
        ref_mass, ref_temperature = gas_reference
        temperature = ref_temperature * (gas_mass / ref_mass) ** (GAMMA - 1)
        return gas_mass * R * temperature / volume, temperature, 0.0, 0.0, 0.0, 0.0

    for phase in ("water", "air", "coast"):
        if phase == "air":
            state[2] = max(state[2], 0.0)
            gas_reference = (state[3], config["temperature_k"] * (gas_volume0 / volume) ** (GAMMA - 1))
        def rhs(_t, y):
            pressure, temperature, thrust, mw, ma, velocity = quantities(y, phase)
            mass = dry + max(y[2], 0.0) + max(y[3], 0.0)
            drag = -0.5 * config["air_density_kg_m3"] * cd * frontal_area * y[1] * abs(y[1])
            acceleration = (thrust + drag) / mass - G
            if y[0] <= 0 and y[1] <= 0 and acceleration < 0:
                acceleration = 0.0
            return [y[1], acceleration, -mw, -ma, thrust, mw, ma]
        if phase == "water":
            def event(_t, y):
                return min(y[2], (quantities(y, phase)[0] - config["ambient_pressure_pa"]) * 1e-6)
        elif phase == "air":
            def event(_t, y):
                return quantities(y, phase)[0] - config["ambient_pressure_pa"] - 0.01
        else:
            def event(_t, y):
                return y[1]
        event.terminal, event.direction = True, -1
        sol = solve_ivp(rhs, (t, t + 20), state, rtol=2e-9, atol=1e-10, max_step=step if phase != "coast" else step * 10, dense_output=True, events=event)
        if not sol.success or not sol.t_events[0].size:
            raise RuntimeError(f"Phase did not finish: {phase}")
        phases.append((phase, t, float(sol.t[-1]), sol.sol, quantities))
        state = sol.y[:, -1].copy()
        t = float(sol.t[-1])
    # Quantities are recomputed independently of the closure's final phase reference.
    times = np.unique(np.concatenate([np.arange(0, t, 1 / 240), np.array([item[2] for item in phases]), [t]]))
    rows = []
    for sample in times:
        phase, start, end, solution, _ = next(item for item in phases if sample <= item[2] + 1e-10)
        y = solution(sample)
        p, temperature, thrust, mw, ma, jet = quantities(y, phase)
        mass = dry + max(y[2], 0.0) + max(y[3], 0.0)
        drag = -0.5 * config["air_density_kg_m3"] * cd * frontal_area * y[1] * abs(y[1])
        rows.append([sample, y[0], y[1], mass, max(y[2], 0.0), max(y[3], 0.0), p, temperature, thrust, mw, ma, jet, (thrust + drag) / mass - G])
    data = np.asarray(rows)
    jumps=[abs(phases[i][3](phases[i][2])[1]-phases[i+1][3](phases[i+1][1])[1]) for i in range(len(phases)-1)]
    return {"data": data, "phase_ends": {name: end for name, start, end, solution, q in phases}, "phase_transition_velocity_jump_m_s":max(jumps), "dry_mass_kg": dry, "initial_water_mass_kg": water0, "initial_air_mass_kg": gas_mass0, "apogee_m": float(state[0]), "apogee_time_s": t, "impulse_ns": float(state[4]), "integrated_water_out_kg": float(state[5]), "integrated_air_out_kg": float(state[6]), "final_air_mass_kg": float(state[3]), "frontal_area_m2": frontal_area, "effective_nozzle_area_m2": area}


def main():
    config = json.loads((ROOT / "scenario.json").read_text())
    design = design_values()
    nominal = integrate(config, design)
    refined = integrate(config, design, step=0.0005)
    data = nominal.pop("data")
    checks = {
        "water_mass_balance_error_kg": abs(nominal["integrated_water_out_kg"] - nominal["initial_water_mass_kg"]),
        "air_mass_balance_error_kg": abs(nominal["integrated_air_out_kg"] - nominal["initial_air_mass_kg"] + nominal["final_air_mass_kg"]),
        "apogee_step_halving_difference_m": abs(nominal["apogee_m"] - refined["apogee_m"]),
        "all_finite": bool(np.isfinite(data).all()),
        "water_mass_monotone": bool(np.max(np.diff(data[:,4])) < 1e-8),
        "phase_transition_velocity_jump_m_s": nominal["phase_transition_velocity_jump_m_s"],
    }
    assert checks["water_mass_balance_error_kg"] < 1e-7
    assert checks["air_mass_balance_error_kg"] < 1e-7
    assert checks["apogee_step_halving_difference_m"] < 1e-4
    assert checks["all_finite"] and checks["water_mass_monotone"]
    assert checks["phase_transition_velocity_jump_m_s"]<1e-9
    sensitivity = []
    for drag in (0.35, 0.5, 0.7):
        for pressure_factor in (0.85, 1.0, 1.15):
            trial = integrate({**config, "drag_coefficient":drag, "gauge_pressure_pa":config["gauge_pressure_pa"] * pressure_factor}, design)
            sensitivity.append({"cd":drag, "pressure_factor":pressure_factor, "apogee_m":trial["apogee_m"]})
    out = ROOT / "renders"
    out.mkdir(exist_ok=True)
    np.savez_compressed(out / "trajectory.npz", data=data)
    header = ["time_s","altitude_m","velocity_m_s","mass_kg","water_mass_kg","air_mass_kg","pressure_abs_pa","temperature_k","thrust_n","water_flow_kg_s","air_flow_kg_s","jet_speed_m_s","acceleration_m_s2"]
    with (ROOT / "trajectory-keyframes.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(header)
        for index in np.unique(np.linspace(0,len(data)-1,121).round().astype(int)):
            writer.writerow([f"{number:.8g}" for number in data[index]])
    report = {"scenario":config, "design":design, "nominal":nominal, "checks":checks, "sensitivity_cases":sensitivity, "sensitivity_apogee_range_m":[min(x["apogee_m"] for x in sensitivity),max(x["apogee_m"] for x in sensitivity)], "sensitivity_interpretation":"Scenario sensitivity only, not an experimental confidence interval.", "model":"Quasi-steady effective-area water jet; dry adiabatic reservoir; choked/unchoked gas discharge; continuous variable-mass vertical ODE; axial quadratic drag.", "limitations":["Unmeasured bottle envelope and assumed initial conditions.","No slosh, transient liquid inertance, heat transfer, condensation, flex or attitude dynamics.","Perfect vertical alignment and still air; no stability or retention qualification.","Ascent only; recovery system is not designed."]}
    (ROOT / "simulation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"nominal":nominal,"checks":checks,"sensitivity_apogee_range_m":report["sensitivity_apogee_range_m"]},indent=2))


if __name__ == "__main__":
    main()
