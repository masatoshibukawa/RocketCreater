"""Finite-duration water expulsion and compressible air discharge with gas/wall energy."""

import math

import numpy as np
from scipy.integrate import simpson, solve_ivp

from .schema import LoadConfig


def gas_nozzle(p, temperature, area, cfg: LoadConfig):
    if p <= cfg.ambient_pa:
        return 0.0, 0.0, False
    g, R = cfg.gamma, cfg.gas_r
    ratio = cfg.ambient_pa / p
    critical = (2 / (g + 1)) ** (g / (g - 1))
    pe = p * critical if ratio < critical else cfg.ambient_pa
    mach2 = 2 / (g - 1) * ((p / pe) ** ((g - 1) / g) - 1)
    te = temperature / (1 + (g - 1) * mach2 / 2)
    speed = math.sqrt(max(0, g * R * te * mach2))
    effective_area = cfg.discharge_coefficient * area
    mdot = pe / (R * te) * speed * effective_area
    return mdot, mdot * speed + (pe - cfg.ambient_pa) * effective_area, ratio < critical


def propulsion(design, cfg: LoadConfig):
    """State also integrates work and outgoing gas enthalpy for independent energy accounting.

    Dry ideal gas, uniform reservoir, no evaporation/condensation or liquid slosh.
    The manufacturer's bottle/launcher restrictions are not established by this model.
    """
    volume = design.bottle_volume_m3
    mw0 = volume * design.water_fill_frac * 1000
    va0 = volume - mw0 / 1000
    area = math.pi * (design.nozzle_diameter_m / 2) ** 2
    cv = cfg.gas_r / (cfg.gamma - 1)
    cp = cv + cfg.gas_r
    mg0 = (cfg.ambient_pa + design.initial_gauge_pressure_pa) * va0 / (cfg.gas_r * cfg.initial_k)
    initial = np.array([mw0, mg0, cfg.initial_k, cfg.initial_wall_k, 0.0, 0.0, 0.0])

    def values(y, liquid):
        mw, mg, tg, tw = y[:4]
        va = volume - max(mw, 0) / 1000
        p = mg * cfg.gas_r * tg / va
        if liquid:
            jet = math.sqrt(2 * max(p - cfg.ambient_pa, 0) / 1000)
            water_out = cfg.discharge_coefficient * area * 1000 * jet
            gas_out, thrust = 0.0, water_out * jet
        else:
            gas_out, thrust, _ = gas_nozzle(p, tg, area, cfg)
            water_out = 0.0
        return p, water_out, gas_out, thrust

    def rhs(liquid):
        def f(_, y):
            p, water_out, gas_out, _ = values(y, liquid)
            _, mg, tg, tw = y[:4]
            qgas = cfg.gas_wall_h * cfg.wall_area_m2 * (tw - tg)
            qambient = cfg.outside_h * cfg.wall_area_m2 * (cfg.ambient_k - tw)
            work = p * water_out / 1000
            enthalpy = gas_out * cp * tg
            return [
                -water_out,
                -gas_out,
                (qgas - work - gas_out * cfg.gas_r * tg) / (mg * cv),
                (qambient - qgas) / cfg.wall_capacity_j_k,
                work,
                enthalpy,
                qambient,
            ]

        return f

    def empty(_, y):
        return y[0]

    def depressurised(_, y):
        return y[1] * cfg.gas_r * y[2] / (volume - max(y[0], 0) / 1000) - cfg.ambient_pa - 50

    empty.terminal = depressurised.terminal = True
    empty.direction = depressurised.direction = -1
    water = solve_ivp(
        rhs(True),
        (0, cfg.max_time_s),
        initial,
        events=[empty, depressurised],
        rtol=2e-9,
        atol=1e-11,
        max_step=0.001,
    )
    if not water.success:
        raise RuntimeError(water.message)
    end = water.y[:, -1].copy()
    time = water.t[-1]
    end_values = values(end, True)
    stages = [(water, True)]
    exhausted = bool(len(water.t_events[0]))
    if exhausted:
        end[0] = 0
        air = solve_ivp(
            rhs(False),
            (time, time + cfg.max_time_s),
            end,
            events=depressurised,
            rtol=2e-9,
            atol=1e-11,
            max_step=0.001,
        )
        if not air.success:
            raise RuntimeError(air.message)
        stages.append((air, False))
    rows = []
    for s, liquid in stages:
        for k, t in enumerate(s.t):
            if rows and t <= rows[-1][0]:
                continue
            y = s.y[:, k]
            p, water_out, gas_out, thrust = values(y, liquid)
            mass = design.dry_mass_kg + design.payload_mass_kg + max(y[0], 0) + y[1]
            rows.append([t, thrust, mass, p, y[2], y[3], max(y[0], 0), y[1], water_out + gas_out])
    trace = np.array(rows)
    final = stages[-1][0].y[:, -1]
    initial_energy = mg0 * cv * cfg.initial_k + cfg.wall_capacity_j_k * cfg.initial_wall_k
    final_energy = final[1] * cv * final[2] + cfg.wall_capacity_j_k * final[3]
    energy_error = final_energy - initial_energy + final[4] + final[5] - final[6]
    # Integrate each side of the phase transition separately, without smearing its jump.
    mass_out = sum(
        simpson([sum(values(y, liquid)[1:3]) for y in s.y.T], x=s.t) for s, liquid in stages
    )
    pressure_end = trace[-1, 3]
    return {
        "completed": pressure_end <= cfg.ambient_pa + 50.1,
        "scope": "dry ideal gas, lumped heat exchange, quasi-steady convergent discharge",
        "liquid_end": {"time_s": time, "pressure_pa": end_values[0], "temperature_k": end[2]},
        "air_duration_s": trace[-1, 0] - time if exhausted else 0,
        "peak_thrust_n": float(trace[:, 1].max()),
        "impulse_ns": float(np.trapezoid(trace[:, 1], trace[:, 0])),
        "energy_balance_relative": abs(energy_error) / (mg0 * cv * cfg.initial_k),
        "mass_balance_relative": abs(mass_out - (mw0 + mg0 - final[0] - final[1])) / (mw0 + mg0),
        "trace": dict(
            zip(
                [
                    "time_s",
                    "thrust_n",
                    "mass_kg",
                    "pressure_pa",
                    "gas_k",
                    "wall_k",
                    "water_kg",
                    "gas_kg",
                    "mass_flow_kg_s",
                ],
                trace.T.tolist(),
                strict=True,
            )
        ),
    }
