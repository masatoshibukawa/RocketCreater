"""Lumped heat network for waiting, including a sealed-gas pressure scenario."""

import numpy as np
from scipy.integrate import solve_ivp

from .schema import AnalysisConfig


def wait(design, cfg: AnalysisConfig, *, ambient_c=35.0, initial_c=25.0, sealed=False):
    # Capacities/contact conductances are exposed assumptions, not material measurements.
    initial_pressure = (
        cfg.loads.ambient_pa + design.initial_gauge_pressure_pa if sealed else cfg.loads.ambient_pa
    )
    gas_mass = initial_pressure * design.bottle_volume_m3 * (1 - design.water_fill_frac)
    gas_mass /= cfg.loads.gas_r * (initial_c + 273.15)
    capacity = np.array(
        [
            gas_mass * cfg.loads.gas_r / (cfg.loads.gamma - 1),
            cfg.loads.wall_capacity_j_k,
            cfg.contact.support_kg * 1200,
            max(design.payload_mass_kg, 0.001) * 3170,
            12.0,
        ]
    )  # gas, skin, mount, payload, exposed fin
    conductance = np.zeros((5, 5))
    for i, j, k in [(0, 1, 0.3), (1, 2, 0.08), (2, 3, 0.06)]:
        conductance[i, j] = conductance[j, i] = k
    convection = np.array([0.0, 0.8, 0.0, 0.0, 0.24])
    projected = np.array([0.0, 0.018, 0.0, 0.0, 0.006])
    radiation_area = np.array([0.0, 0.08, 0.0, 0.0, 0.024])
    ambient = ambient_c + 273.15
    solar = cfg.surface_absorptivity * cfg.solar_w_m2 * projected

    def rhs(_, y):
        t = y[:5]
        outside = (
            convection * (ambient - t)
            + 0.9 * 5.670374419e-8 * radiation_area * (ambient**4 - t**4)
            + solar
        )
        exchange = np.sum(conductance * (t[None, :] - t[:, None]), axis=1)
        return np.r_[(exchange + outside) / capacity, outside.sum()]

    initial = np.r_[np.full(5, initial_c + 273.15), 0.0]
    if cfg.warm_wait_s == 0:
        times = np.array([0.0])
        temperatures = initial[None, :]
    else:
        s = solve_ivp(
            rhs,
            (0, cfg.warm_wait_s),
            initial,
            rtol=1e-9,
            atol=1e-10,
            t_eval=np.linspace(0, cfg.warm_wait_s, 301),
        )
        if not s.success:
            raise RuntimeError(s.message)
        times = s.t
        temperatures = s.y.T
    energy = (temperatures[:, :5] - initial[:5]) @ capacity
    initial_pressure = (
        cfg.loads.ambient_pa + design.initial_gauge_pressure_pa if sealed else cfg.loads.ambient_pa
    )
    pressure = (
        initial_pressure * temperatures[:, 0] / initial[0]
        if sealed
        else np.full(len(times), initial_pressure)
    )
    return {
        "completed": True,
        "scope": "five-node heat network; assumed contact/convection properties",
        "sealed": sealed,
        "final_c": dict(
            zip(
                ["gas", "skin", "mount", "payload", "fin"],
                (temperatures[-1, :5] - 273.15).tolist(),
                strict=True,
            )
        ),
        "peak_absolute_pressure_pa": float(max(pressure)),
        "energy_balance_relative": float(
            np.max(abs(energy - temperatures[:, 5])) / max(abs(energy).max(), 1)
        ),
        "capacities_j_k": capacity.tolist(),
        "conductances_w_k": conductance.tolist(),
        "trace": {
            "time_s": times.tolist(),
            "temperature_c": (temperatures[:, :5] - 273.15).tolist(),
            "absolute_pressure_pa": pressure.tolist(),
        },
    }
