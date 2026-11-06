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


def run(
    design,
    assembly,
    loads,
    cfg: FlightConfig,
    *,
    cd_scale=1.0,
    cn_scale=1.0,
    max_step=0.02,
    aero_model=None,
    mass_model=None,
    record_loads=False,
):
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
    rho = cfg.air_density_kg_m3  # constant launch-site density, not a vertical profile

    def mass_properties(t):
        if mass_model is not None:
            return mass_model.properties(t)
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
        azimuth = np.deg2rad(cfg.wind_to_azimuth_deg)
        wind[:2] = (
            np.array([[np.cos(azimuth), -np.sin(azimuth)], [np.sin(azimuth), np.cos(azimuth)]])
            @ wind[:2]
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
        if aero_model is None:
            aero_force = normal + drag
            aero_moment = np.cross([0, 0, cg - cp], normal)
        else:
            aero = aero_model.evaluate(vb, q, cg)
            aero_force, aero_moment = aero["force_n"], aero["moment_nm"]
        f_body = aero_force + np.array([0.0, 0.0, thrust])
        torque = aero_moment.copy()
        damping = np.zeros(3)
        damping[:2] = -q * area * length**2 / (2 * max(speed, 0.1)) * cfg.pitch_damping * omega[:2]
        arm = radius + g["fin_span"] / 2000
        damping[2] = (
            q
            * area
            * assembly["fin_set_CNalpha_per_rad"]
            * arm
            * (np.deg2rad(cfg.cant_deg) - omega[2] * arm / (2 * max(speed, 0.1)))
        )
        torque += damping
        inflation = 0.0
        if deployment is not None and design.has_parachute:
            inflation = np.clip((t - deployment) / cfg.opening_s, 0, 1)
            inflation = inflation * inflation * (3 - 2 * inflation)
        canopy_area = np.pi * (design.parachute_diameter_m or 0) ** 2 / 4
        canopy = -q * canopy_area * 0.75 * inflation * vb / max(speed, 1e-9)
        f_body += canopy
        # Canopy line attaches at the nose; stretch/pendulum fluid effects are unresolved.
        torque += np.cross([0, 0, cg], canopy)
        detail = {
            "air_velocity_body_mps": vb,
            "aero_force_n": aero_force,
            "aero_moment_nm": aero_moment,
            "thrust_n": thrust,
            "canopy_body_n": canopy,
            "damping_moment_nm": damping,
        }
        return (
            r @ f_body,
            torque,
            (m, cg, moment, q, alpha, inflation, np.linalg.norm(canopy)),
            detail,
        )

    def angular_state(t, omega, torque, inertia_now, cg):
        di = np.array([np.interp(t, time, idot[:, j], right=0) for j in range(3)])
        mdot = np.interp(t, time, tr["mass_flow_kg_s"], right=0)
        outlet = length - cg
        rn = design.nozzle_diameter_m / 2
        flux = mdot * np.array([outlet**2 + rn**2 / 4, outlet**2 + rn**2 / 4, rn**2 / 2])
        transport = -(di + flux) * omega
        angular = (torque - np.cross(omega, inertia_now * omega) + transport) / inertia_now
        return angular, transport

    evaluations = 0

    def rhs(rail, deployment):
        def derivative(t, y):
            nonlocal evaluations
            evaluations += 1
            if evaluations > cfg.maximum_rhs_evaluations:
                raise RuntimeError(
                    "6DOF integration evaluation limit; possible stiff/invalid scenario"
                )
            f, torque, (m, cg, inertia_now, *_), _ = forces(t, y, deployment)
            acceleration = f / m - np.array([0, 0, G])
            if rail:
                a = float(np.dot(acceleration, axis))
                if np.dot(y[:3], axis) <= 0 and np.dot(y[3:6], axis) <= 0 and a < 0:
                    a = 0
                return np.r_[axis * np.dot(y[3:6], axis), axis * a, np.zeros(7)]
            omega = y[10:13]
            angular, _ = angular_state(t, omega, torque, inertia_now, cg)
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
    load_samples = []
    for t, y in zip(times, states, strict=True):
        f, torque, info, detail = forces(t, y, deployment)
        m, cg, inertia_now, q, alpha, inflation, canopy = info
        if record_loads:
            r = rotation(y[6:10])
            rail_force = np.zeros(3)
            rail_moment = np.zeros(3)
            angular, transport = angular_state(t, y[10:13], torque, inertia_now, cg)
            if t <= rail.t[-1]:
                actual = rhs(True, None)(t, y)[3:6]
                rail_force = r.T @ (m * (actual + [0, 0, G]) - f)
                rail_moment = -torque
                angular = np.zeros(3)
            detail.update(
                time_s=t,
                mass_kg=m,
                inertia_kg_m2=inertia_now,
                cg_m=cg,
                proper_body_mps2=r.T @ f / m + rail_force / m,
                angular_acceleration_rad_s2=angular,
                transport_moment_nm=transport,
                rail_force_n=rail_force,
                rail_moment_nm=rail_moment,
                external_moment_nm=torque + rail_moment,
                omega_rad_s=y[10:13],
            )
            load_samples.append(
                {
                    k: v.tolist() if isinstance(v, np.ndarray) else float(v)
                    for k, v in detail.items()
                }
            )
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
    result = {
        "completed": bool(len(descent.t_events[0])),
        "qualified": False,
        "scope": "6DOF, rigid surrogate inertia, dry gas, constant launch-site density",
        "air_density_kg_m3": rho,
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
    if record_loads:
        result["load_samples"] = load_samples
    if aero_model is not None:
        result["aero_source"] = aero_model.metadata
        result["aero_domain_pass"] = (
            all(
                np.linalg.norm(s["air_velocity_body_mps"]) <= aero_model.speeds[-1]
                for s in load_samples
            )
            if record_loads
            else False
        )
        result["scope"] = "quaternion 6DOF with numerical wind-tunnel lookup; conditional model"
        result["limitations"] = [
            "unvalidated CFD and mass distribution",
            "velocity clamped to simulated range; pressure still scales with actual speed squared",
            "fixed-density flow, no slosh, prescribed canopy inflation",
            "fourfold-fin azimuth dependence approximated by meridional data",
            "rotational damping and nozzle angular-momentum transport are engineering models",
        ]
    return result
