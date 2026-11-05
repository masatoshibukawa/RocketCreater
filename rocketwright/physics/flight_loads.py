"""CFD -> trajectory -> self-equilibrated section loads for a bottle rocket.

Axes in flight are body z toward the nose. Section axial force is positive in
compression. The mass distribution, damping and internal transport are models,
not measurements. Design envelopes retain the condition causing each maximum.
"""

import hashlib
import json
from pathlib import Path

import numpy as np


class TunnelDatabase:
    def __init__(self, folder, *, scale=1.0):
        folder = Path(folder)
        config_path = folder / "table-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        self.speeds = np.array(config.get("speeds_mps", [8.0, 18.0, 30.0]))
        self.angles = np.array(config.get("angles_deg", [0.0, 5.0, 15.0, 45.0, 90.0, 135.0, 180.0]))
        if (
            len(self.speeds) < 2
            or len(self.angles) < 2
            or not np.isfinite(self.speeds).all()
            or not np.isfinite(self.angles).all()
            or np.any(np.diff(self.speeds) <= 0)
            or np.any(np.diff(self.angles) <= 0)
            or self.speeds[0] <= 0
            or self.angles[0] != 0
            or self.angles[-1] != 180
        ):
            raise ValueError("Invalid tunnel interpolation axes")
        self.scale = scale
        rows, hashes, geometry = [], {}, set()
        removed = []
        for speed in self.speeds:
            row = []
            for angle in self.angles:
                name = f"v{speed:02.0f}-a{angle:03.0f}"
                directory = folder / name
                case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
                path = directory / "line-loads.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                if (
                    case["speed_mps"] != speed
                    or case["angle_deg"] != angle
                    or not case["rotated_geometry"]
                    or case["cant_deg"] != 0
                    or data["integration_relative_residual"] > 2e-4
                ):
                    raise ValueError(f"Invalid numerical tunnel input: {name}")
                geometry.add(case["geometry_sha256"])
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.stations = np.asarray(data["station_m"])
                self.diameter = data["ref_diameter_m"]
                self.area = data["ref_area_m2"]
                values = np.column_stack([data["force_coeff"], data["couple_coeff_at_station"]])
                projected = values.copy()
                # Reflection symmetry of the uncanted four-fin meridional geometry.
                # Preserve raw CFD data; remove sampled cross-plane mean noise only here.
                projected[:, [2, 3, 4]] = 0
                if angle in (0, 180):
                    projected[:, [1, 5]] = 0
                removed.append(float(np.linalg.norm(values - projected)))
                row.append(projected)
            rows.append(row)
        if len(geometry) != 1:
            raise ValueError("Tunnel table mixes geometries")
        self.table = np.asarray(rows)
        self.metadata = {
            "method": "bilinear numerical-tunnel load table",
            "case_hashes": hashes,
            "geometry_sha256": geometry.pop(),
            "speeds_mps": self.speeds.tolist(),
            "incidence_deg": self.angles.tolist(),
            "symmetry": "reflection projection; raw loads retained",
            "max_removed_coefficient_norm": max(removed),
            "scale": scale,
            "physical_validation": False,
        }

    def coefficients(self, speed, angle):
        speed = np.clip(speed, self.speeds[0], self.speeds[-1])
        angle = np.clip(angle, self.angles[0], self.angles[-1])
        i = min(max(np.searchsorted(self.speeds, speed) - 1, 0), len(self.speeds) - 2)
        j = min(max(np.searchsorted(self.angles, angle) - 1, 0), len(self.angles) - 2)
        a = (speed - self.speeds[i]) / (self.speeds[i + 1] - self.speeds[i])
        b = (angle - self.angles[j]) / (self.angles[j + 1] - self.angles[j])
        return self.scale * (
            (1 - a) * (1 - b) * self.table[i, j]
            + a * (1 - b) * self.table[i + 1, j]
            + (1 - a) * b * self.table[i, j + 1]
            + a * b * self.table[i + 1, j + 1]
        )

    def evaluate(self, air_velocity_body, q, cg):
        vb = np.asarray(air_velocity_body)
        speed = np.linalg.norm(vb)
        cross = np.linalg.norm(vb[:2])
        alpha = np.degrees(np.arctan2(cross, vb[2])) if speed > 1e-10 else 0.0
        e1 = np.r_[vb[:2] / cross, 0] if cross > 1e-10 else np.array([1.0, 0, 0])
        ez = np.array([0.0, 0, 1])
        transform = np.column_stack([-ez, -e1, np.cross(ez, e1)])
        coefficients = self.coefficients(speed, alpha)
        force = q * self.area * coefficients[:, :3] @ transform.T
        couple = q * self.area * self.diameter * coefficients[:, 3:] @ transform.T
        r = np.column_stack([np.zeros((len(force), 2)), cg - self.stations])
        return {
            "force_n": force.sum(0),
            "moment_nm": (np.cross(r, force) + couple).sum(0),
            "station_m": self.stations,
            "line_force_n": force,
            "line_couple_nm": couple,
            "speed_clamped": bool(speed < self.speeds[0] or speed > self.speeds[-1]),
        }


class MassDistribution:
    """BOM masses at stated stations, finite local inertia, 16 axial water slices."""

    def __init__(self, design, assembly, propulsion):
        self.design, self.assembly = design, assembly
        self.trace = {k: np.asarray(v) for k, v in propulsion["trace"].items()}
        self.radius = assembly["dimensions_mm"]["body_diameter"] / 2000
        self.length = assembly["dimensions_mm"]["overall"] / 1000
        bill = assembly["bill"]
        masses = np.array([b["mass_g"] / 1000 for b in bill])
        masses *= design.dry_mass_kg / masses.sum()
        stations = np.array([b["station_mm"] / 1000 for b in bill])
        dry = design.dry_mass_kg + design.payload_mass_kg
        payload_station = (
            dry * assembly["loaded_cg_mm"] / 1000 - masses @ stations
        ) / design.payload_mass_kg
        self.dry_mass = np.r_[masses, design.payload_mass_kg]
        self.dry_station = np.r_[stations, payload_station]
        # Local gyration lengths: explicit surrogates, not measured inertia tensors.
        extents = {
            "coke_jp_1500": 0.305,
            "sleeve": 0.182,
            "nose_paper": 0.1,
            "carton_fin": 0.07,
            "pad_damped": 0.06,
            "canopy_film": 0.08,
        }
        axial_span = np.array([extents.get(b["id"], 0.025) for b in bill] + [0.06])
        radial2 = np.full(len(self.dry_mass), self.radius**2 / 2)
        for i, b in enumerate(bill):
            if b["id"] == "carton_fin":
                span = assembly["dimensions_mm"]["fin_span"] / 1000
                radial2[i] = self.radius**2 + self.radius * span + span**2 / 3
        self.local_dry = self.dry_mass[:, None] * np.column_stack(
            [axial_span**2 / 12 + radial2 / 2, axial_span**2 / 12 + radial2 / 2, radial2]
        )
        mw0 = self.trace["water_kg"][0]
        water_cg = (
            (dry + mw0) * assembly["wet_cg_mm"] / 1000 - dry * assembly["loaded_cg_mm"] / 1000
        ) / mw0
        self.area = np.pi * self.radius**2
        self.bottom = water_cg + mw0 / (2000 * self.area)
        self.top = self.bottom - design.bottle_volume_m3 / self.area
        if not 0 < self.top < self.bottom < self.length:
            raise ValueError("Liquid reservoir falls outside the body")

    def sample(self, time):
        trace = self.trace
        mw = max(0.0, np.interp(time, trace["time_s"], trace["water_kg"]))
        mg = np.interp(time, trace["time_s"], trace["gas_kg"])
        height = mw / (1000 * self.area)
        stations = np.r_[
            self.dry_station,
            self.bottom - (np.arange(16) + 0.5) * height / 16,
            (self.top + self.bottom - height) / 2,
        ]
        masses = np.r_[self.dry_mass, np.full(16, mw / 16), mg]
        fluid = masses[-17:]
        span = np.r_[np.full(16, height / 16), self.bottom - height - self.top]
        local = np.vstack(
            [
                self.local_dry,
                fluid[:, None]
                * np.column_stack(
                    [
                        span**2 / 12 + np.full(17, self.radius**2 / 4),
                        span**2 / 12 + np.full(17, self.radius**2 / 4),
                        np.full(17, self.radius**2 / 2),
                    ]
                ),
            ]
        )
        return stations, masses, local

    def properties(self, time):
        station, mass, local = self.sample(time)
        total = mass.sum()
        cg = float(mass @ station / total)
        inertia = local.sum(0) + [mass @ (station - cg) ** 2, mass @ (station - cg) ** 2, 0]
        return total, cg, inertia


def section_resultants(stations, forces, couples, cuts):
    """Force and moment on the fore segment from the aft segment, at each cut."""
    stations, forces, couples = np.asarray(stations), np.asarray(forces), np.asarray(couples)
    result = np.zeros((len(cuts), 6))
    for i, cut in enumerate(cuts):
        selected = stations < cut
        r = np.column_stack([np.zeros((selected.sum(), 2)), cut - stations[selected]])
        result[i, :3] = -forces[selected].sum(0)
        result[i, 3:] = -(np.cross(r, forces[selected]) + couples[selected]).sum(0)
    return result


def recover(flight, aero, mass_model, propulsion, *, cuts=65, pressure=True):
    """Recover balanced loads, retaining rail, canopy, pressure and transport terms."""
    # Resolve both sides of fixed point loads/couples instead of skipping jumps
    # between regularly spaced section samples. Water slices remain distributed.
    fixed = np.r_[
        aero.stations,
        mass_model.dry_station,
        mass_model.top,
        mass_model.bottom,
        0.38,
        mass_model.length - 0.04,
    ]
    cut_stations = np.unique(
        np.clip(
            np.r_[np.linspace(0, mass_model.length, cuts), fixed - 1e-8, fixed + 1e-8],
            0,
            mass_model.length,
        )
    )
    traces, residuals = [], []
    for sample in flight["load_samples"]:
        t, cg = sample["time_s"], sample["cg_m"]
        q = 0.5 * 1.204 * np.linalg.norm(sample["air_velocity_body_mps"]) ** 2
        air = aero.evaluate(sample["air_velocity_body_mps"], q, cg)
        station = list(air["station_m"])
        force = list(air["line_force_n"])
        couple = list(air["line_couple_nm"])

        def point(s, f=(0, 0, 0), m=(0, 0, 0), station=station, force=force, couple=couple):
            station.append(s)
            force.append(np.asarray(f))
            couple.append(np.asarray(m))

        # A cut at the tail includes the force at the nozzle's upstream face.
        point(mass_model.length - 1e-9, [0, 0, sample["thrust_n"]], sample["transport_moment_nm"])
        point(0, sample["canopy_body_n"])
        if "ground_force_n" in sample:
            point(mass_model.length - 1e-9, sample["ground_force_n"])
        point(mass_model.length - 0.04, m=sample["damping_moment_nm"])
        guide = 0.38
        point(
            guide,
            sample["rail_force_n"],
            np.asarray(sample["rail_moment_nm"])
            - np.cross([0, 0, cg - guide], sample["rail_force_n"]),
        )
        if pressure:
            tr = propulsion["trace"]
            gauge = max(0.0, np.interp(t, tr["time_s"], tr["pressure_pa"]) - 101085)
            pressure_force = gauge * mass_model.area
            point(mass_model.top, [0, 0, pressure_force])
            point(mass_model.bottom, [0, 0, -pressure_force])
        s, m, local = mass_model.sample(t)
        r = np.column_stack([np.zeros((len(s), 2)), cg - s])
        omega = np.asarray(sample["omega_rad_s"])
        alpha = np.asarray(sample["angular_acceleration_rad_s2"])
        acceleration = (
            np.asarray(sample["proper_body_mps2"])
            + np.cross(alpha, r)
            + np.cross(omega, np.cross(omega, r))
        )
        inertia_force = -m[:, None] * acceleration
        inertia_couple = -(local * alpha + np.cross(omega, local * omega))
        station += list(s)
        force += list(inertia_force)
        couple += list(inertia_couple)
        station, force, couple = np.asarray(station), np.asarray(force), np.asarray(couple)
        r_all = np.column_stack([np.zeros((len(station), 2)), cg - station])
        residuals.append(np.r_[force.sum(0), (np.cross(r_all, force) + couple).sum(0)])
        traces.append(section_resultants(station, force, couple, cut_stations))
    return {
        "cuts_m": cut_stations,
        "time_s": np.array([s["time_s"] for s in flight["load_samples"]]),
        "resultants": np.asarray(traces),
        "equilibrium_residual": np.asarray(residuals),
        "sign": "body z toward nose; axial Rz positive compression, negative tension",
        "pressure": "self-equilibrated reservoir end loads; membrane approximation"
        if pressure
        else False,
        "transport": "variable-mass angular momentum correction lumped at nozzle",
        "scope": "quasi-static section loads; no flexible transient amplification or liquid slosh",
    }


def envelopes(cases, *, design_factor=1.5):
    """Separate component envelopes; retain concurrent vectors at every governing event."""
    if design_factor < 1:
        raise ValueError("Design factor must be >= 1")
    metrics = {
        "compression_n": lambda a: np.maximum(a[..., 2], 0),
        "tension_n": lambda a: np.maximum(-a[..., 2], 0),
        "shear_n": lambda a: np.linalg.norm(a[..., :2], axis=-1),
        "bending_nm": lambda a: np.linalg.norm(a[..., 3:5], axis=-1),
        "torsion_nm": lambda a: abs(a[..., 5]),
    }
    output = {}
    for name, metric in metrics.items():
        candidates = []
        for case_id, result in cases.items():
            value = metric(result["resultants"])
            at = np.argmax(value, axis=0)
            candidates.append((case_id, result, value[at, np.arange(value.shape[1])], at))
        winner = np.argmax([c[2] for c in candidates], axis=0)
        rows = []
        for station, k in enumerate(winner):
            case_id, result, values, at = candidates[k]
            i = at[station]
            rows.append(
                {
                    "station_m": float(result["cuts_m"][station]),
                    "limit": float(values[station]),
                    "design": float(design_factor * values[station]),
                    "case": case_id,
                    "time_s": float(result["time_s"][i]),
                    "concurrent_vector": result["resultants"][i, station].tolist(),
                }
            )
        output[name] = rows
    return {
        "factor": design_factor,
        "factor_basis": "declared scenario margin; not a prescribed standard",
        "envelopes": output,
        "combination": "component maxima need not occur simultaneously",
        "physical_qualification": False,
    }
