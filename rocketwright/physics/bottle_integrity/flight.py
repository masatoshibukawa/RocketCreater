"""Conditional 6-DOF rigid-body flight with changing water mass and finite canopy inflation.

Aerodynamics are low-angle engineering approximations, not validated CFD. Large
incidence, liquid slosh and flexible modes require additional models/evidence.
"""

import numpy as np
from scipy.integrate import solve_ivp

from .schema import FlightConfig

G = 9.80665


def rotation(q):
    """Scalar-first unit quaternion, body to world."""
    w, x, y, z = np.asarray(q) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def qrate(q, omega):
    omega = np.asarray(omega)
    w, v = q[0], q[1:]
    return 0.5 * np.r_[-np.dot(v, omega), w * omega + np.cross(v, omega)]


def run(design, assembly, loads, cfg: FlightConfig, *, cd_scale=1.0, cn_scale=1.0, max_step=0.02):
    tr = loads["trace"]
    time = np.asarray(tr["time_s"])
    g = assembly["dimensions_mm"]
    length, radius = g["overall"] / 1000, g["body_diameter"] / 2000
    area = np.pi * radius**2
    dry = design.dry_mass_kg + design.payload_mass_kg
    dry_cg = assembly["loaded_cg_mm"] / 1000
    mw0 = tr["water_kg"][0]
    water_station = (assembly["wet_cg_mm"] / 1000 * (dry + mw0) - dry * dry_cg) / mw0
    liquid_bottom = water_station + mw0 / (2000 * area)
    cp = assembly["cp_mm"] / 1000
    slope = assembly["fin_set_CNalpha_per_rad"] + 2
    tilt = np.deg2rad(cfg.initial_tilt_deg)
    quaternion = np.array([np.cos(tilt / 2), 0, np.sin(tilt / 2), 0])
    axis = rotation(quaternion)[:, 2]
    last_mass = tr["mass_kg"][-1]
    cd = (design.axial_drag_coefficient or 0.55) * cd_scale
    rho = 1.204  # fixed reference atmosphere, documented in scope

    def mass_properties(t):
        m = np.interp(t, time, tr["mass_kg"], right=last_mass)
        water = np.interp(t, time, tr["water_kg"], right=tr["water_kg"][-1])
        height = water / (1000 * area)
        station = liquid_bottom - height / 2
        cg = (dry * dry_cg + (m - dry) * station) / m
        # Dry inertia surrogate: uniform axial extent, calibrated CG; no measured inertia.
        it = dry * (length**2 / 12 + radius**2 / 4 + (dry_cg - cg) ** 2)
        it += (m - dry) * (height**2 / 12 + radius**2 / 4 + (station - cg) ** 2)
        iz = 0.5 * m * radius**2
        return m, cg, np.array([it, it, iz])

    inertia = np.array([mass_properties(t)[2] for t in time])
    idot = np.gradient(inertia, time, axis=0)

    def forces(t, y, deployment):
        r = rotation(y[6:10])
        omega = y[10:13]
        wind = np.array(
            [
                cfg.wind_mps + cfg.gust_mps * np.sin(2 * np.pi * 0.7 * t),
                cfg.gust_mps * 0.4 * np.sin(2 * np.pi * 1.1 * t),
                0,
            ]
        )
        air = y[3:6] - wind
        vb = r.T @ air
        speed = float(np.linalg.norm(vb))
        q = 0.5 * rho * speed**2
        alpha = np.arctan2(np.linalg.norm(vb[:2]), vb[2]) if speed > 0.1 else 0.0
        cross = np.linalg.norm(vb[:2])
        normal = np.zeros(3)
        if cross > 1e-12:
            normal[:2] = -q * area * slope * cn_scale * alpha * vb[:2] / cross
        # Beyond the angle limit this remains an extrapolated scenario, not accepted aero.
        drag = -q * area * cd * vb / max(speed, 1e-9)
        thrust = np.interp(t, time, tr["thrust_n"], right=0.0)
        m, cg, moment = mass_properties(t)
        f_body = normal + drag + np.array([0.0, 0.0, thrust])
        torque = np.cross([0, 0, cg - cp], normal)
        torque[:2] -= q * area * length**2 / (2 * max(speed, 0.1)) * cfg.pitch_damping * omega[:2]
        arm = radius + g["fin_span"] / 2000
        torque[2] += (
            q
            * area
            * assembly["fin_set_CNalpha_per_rad"]
            * arm
            * (np.deg2rad(cfg.cant_deg) - omega[2] * arm / (2 * max(speed, 0.1)))
        )
        inflation = 0.0
        if deployment is not None and design.has_parachute:
            inflation = np.clip((t - deployment) / cfg.opening_s, 0, 1)
            inflation = inflation * inflation * (3 - 2 * inflation)
        canopy_area = np.pi * (design.parachute_diameter_m or 0) ** 2 / 4
        canopy = -q * canopy_area * 0.75 * inflation * vb / max(speed, 1e-9)
        f_body += canopy
        # Canopy line attaches at the nose; stretch/pendulum fluid effects are unresolved.
        torque += np.cross([0, 0, cg], canopy)
        return r @ f_body, torque, (m, cg, moment, q, alpha, inflation, np.linalg.norm(canopy))

    def rhs(rail, deployment):
        def derivative(t, y):
            f, torque, (m, cg, inertia_now, *_) = forces(t, y, deployment)
            acceleration = f / m - np.array([0, 0, G])
            if rail:
                a = float(np.dot(acceleration, axis))
                if np.dot(y[:3], axis) <= 0 and np.dot(y[3:6], axis) <= 0 and a < 0:
                    a = 0
                return np.r_[axis * np.dot(y[3:6], axis), axis * a, np.zeros(7)]
            di = np.array([np.interp(t, time, idot[:, j], right=0) for j in range(3)])
            mdot = np.interp(t, time, tr["mass_flow_kg_s"], right=0)
            # Exhaust co-rotates at an axial outlet: angular momentum carried out.
            outlet = length - cg
            rn = design.nozzle_diameter_m / 2
            flux = mdot * np.array([outlet**2 + rn**2 / 4, outlet**2 + rn**2 / 4, rn**2 / 2])
            omega = y[10:13]
            angular = (
                torque - np.cross(omega, inertia_now * omega) - (di + flux) * omega
            ) / inertia_now
            return np.r_[y[3:6], acceleration, qrate(y[6:10], omega), angular]

        return derivative

    def rail_exit(t, y):
        return np.dot(y[:3], axis) - cfg.rail_m

    def apex(t, y):
        return y[5]

    def ground(t, y):
        return y[2]

    rail_exit.terminal = apex.terminal = ground.terminal = True
    rail_exit.direction = 1
    apex.direction = ground.direction = -1
    y0 = np.r_[np.zeros(6), quaternion, np.zeros(3)]

    def integrate(fun, interval, initial, events):
        s = solve_ivp(
            fun, interval, initial, events=events, rtol=2e-7, atol=1e-9, max_step=max_step
        )
        if not s.success or not np.all(np.isfinite(s.y)):
            raise RuntimeError(s.message)
        return s

    rail = integrate(rhs(True, None), (0, min(5, cfg.maximum_time_s)), y0, rail_exit)
    if not len(rail.t_events[0]):
        return {"completed": False, "reason": "did_not_leave_rail", "qualified": False}
    ascent = integrate(rhs(False, None), (rail.t[-1], cfg.maximum_time_s), rail.y[:, -1], apex)
    if not len(ascent.t_events[0]):
        return {"completed": False, "reason": "apogee_not_reached", "qualified": False}
    deployment = ascent.t[-1] + cfg.deployment_delay_s
    descent = integrate(
        rhs(False, deployment), (ascent.t[-1], cfg.maximum_time_s), ascent.y[:, -1], ground
    )
    times = np.r_[rail.t, ascent.t[1:], descent.t[1:]]
    states = np.c_[rail.y, ascent.y[:, 1:], descent.y[:, 1:]].T
    samples = []
    for t, y in zip(times, states, strict=True):
        f, torque, info = forces(t, y, deployment)
        m, cg, _, q, alpha, inflation, canopy = info
        # Aerodynamic incidence limits apply to ascent; descent still exposes extrapolation.
        samples.append(
            [
                q,
                np.rad2deg(alpha),
                np.linalg.norm(f) / m,
                np.dot(rotation(y[6:10])[:, 2], f) / m,
                canopy,
                cg,
                inflation,
            ]
        )
    values = np.array(samples)
    free_ascent = (times > rail.t[-1]) & (times <= ascent.t[-1])
    active = free_ascent & (values[:, 0] > 10)
    angle_max = float(values[active, 1].max()) if active.any() else 0.0
    return {
        "completed": bool(len(descent.t_events[0])),
        "qualified": False,
        "scope": "6DOF, rigid axisymmetric surrogate inertia, dry gas, fixed density 1.204 kg/m3",
        "limitations": [
            "unvalidated aero and inertia",
            "no liquid slosh",
            "canopy inflation prescribed; line/cloth dynamics unresolved",
            "high-angle aerodynamic continuation is unqualified",
        ],
        "rail_exit_s": float(rail.t[-1]),
        "rail_exit_speed_mps": float(np.linalg.norm(rail.y[3:6, -1])),
        "apogee_m": float(ascent.y[2, -1]),
        "apogee_s": float(ascent.t[-1]),
        "impact_speed_mps": float(np.linalg.norm(descent.y[3:6, -1])),
        "vertical_impact_mps": float(abs(descent.y[5, -1])),
        "drift_m": float(np.linalg.norm(descent.y[:2, -1])),
        "max_q_pa": float(values[:, 0].max()),
        "max_canopy_force_n": float(values[:, 4].max()),
        "ascent_incidence_deg": angle_max,
        "aero_domain_pass": angle_max <= cfg.aero_angle_limit_deg,
        "peak_roll_rad_s": float(abs(states[:, 12]).max()),
        "quaternion_norm_error": float(abs(np.linalg.norm(states[:, 6:10], axis=1) - 1).max()),
        "trace": {
            "time_s": times.tolist(),
            "position_m": states[:, :3].tolist(),
            "velocity_mps": states[:, 3:6].tolist(),
            "quaternion": states[:, 6:10].tolist(),
            "omega_rad_s": states[:, 10:13].tolist(),
            "q_pa": values[:, 0].tolist(),
            "incidence_deg": values[:, 1].tolist(),
            "proper_mps2": values[:, 2].tolist(),
            "axial_proper_mps2": values[:, 3].tolist(),
            "canopy_force_n": values[:, 4].tolist(),
            "cg_m": values[:, 5].tolist(),
        },
    }
