"""Compile one saved design into the common geometry/mass/material physics record."""

import math

import numpy as np

from rocketwright.adaptive import digest
from rocketwright.analysis.schema import MOUNTS, STOCKS
from rocketwright.physics.atmosphere import state_scalar
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig, FlightConfig, Material
from rocketwright.physics.concrete_fin import polygon_moments
from rocketwright.physics.stability import trapezoidal_fin_force
from rocketwright.schema import FinSet


def compile_record(spec, cad_metrics):
    """CAD volumes are supplied by the host's real geometry adapter, never by the LLM."""
    g, a = spec.geometry, spec.assumptions
    if spec.env.earth_rotation:
        raise ValueError("Earth rotation is not supported by this local 6DOF adapter")
    stock, mount = STOCKS[spec.material], MOUNTS[a.mount]
    length, diameter = g.overall_mm / 1000, g.body_diameter_mm / 1000
    area = math.pi * diameter**2 / 4
    if spec.design.bottle_volume_m3 / area >= length - g.nose_length_mm / 1000 - 0.01:
        raise ValueError("The declared liquid reservoir does not fit the analysis envelope")
    if (
        not spec.design.has_fins
        or not spec.design.has_parachute
        or spec.design.payload_mass_kg <= 0
    ):
        raise ValueError("This campaign requires fins, positive payload and parachute recovery")
    volumes = {k: float(cad_metrics[k]["volume_mm3"]) for k in ("fin", "nose")}
    if any(not math.isfinite(v) or v <= 0 for v in volumes.values()):
        raise ValueError("CAD solid volumes must be finite and positive")
    fin_g = volumes["fin"] * g.fin_count * stock["density"] * 1e-6
    nose_g = volumes["nose"] * stock["density"] * 1e-6
    measured = spec.measured_printed_mass_g
    scale = measured / (fin_g + nose_g) if measured is not None else 1
    fin_g, nose_g = fin_g * scale, nose_g * scale
    start = length - (g.fin_tail_inset_mm + g.fin_root_mm) / 1000
    points = (
        np.array(
            [
                [0, 0],
                [g.fin_root_mm, 0],
                [g.fin_sweep_mm + g.fin_tip_mm, g.fin_span_mm],
                [g.fin_sweep_mm, g.fin_span_mm],
            ]
        )
        / 1000
    )
    _, centroid, _ = polygon_moments(points)
    fin_station = start + centroid[0]
    bill = [
        dict(
            id="other_dry",
            mass_g=spec.other_dry_mass_g,
            station_mm=1000 * length * a.other_mass_station_fraction,
        ),
        dict(id="printed_nose", mass_g=nose_g, station_mm=g.nose_length_mm * 0.65),
        dict(id="printed_fins", mass_g=fin_g, station_mm=fin_station * 1000),
    ]
    if mount["additional_mass_g"]:
        bill.append(
            dict(
                id="mount_increment",
                mass_g=mount["additional_mass_g"],
                station_mm=1000 * fin_station,
            )
        )
    dry = sum(r["mass_g"] for r in bill) / 1000
    moment = sum(r["mass_g"] * r["station_mm"] for r in bill) / 1e6
    payload = spec.design.payload_mass_kg
    liquid = spec.design.bottle_volume_m3 * spec.design.water_fill_frac * 1000
    bottom = length - 0.01
    loaded = (moment + payload * length * a.payload_station_fraction) / (dry + payload)
    wet = (dry + payload) * loaded + liquid * (bottom - liquid / (2000 * area))
    wet /= dry + payload + liquid
    fins = FinSet(
        count=g.fin_count,
        root_chord_m=g.fin_root_mm / 1000,
        tip_chord_m=g.fin_tip_mm / 1000,
        span_m=g.fin_span_mm / 1000,
        sweep_m=g.fin_sweep_mm / 1000,
        thickness_m=g.fin_thickness_mm / 1000,
    )
    cn, cp = trapezoidal_fin_force(diameter, fins, start)
    cp = (2 * g.nose_length_mm / 1500 + cn * cp) / (2 + cn)
    dimensions = dict(
        overall=g.overall_mm,
        body_diameter=g.body_diameter_mm,
        nose_length=g.nose_length_mm,
        bottle_length=g.body_height_mm,
        fin_root=g.fin_root_mm,
        fin_tip=g.fin_tip_mm,
        fin_span=g.fin_span_mm,
        fin_sweep=g.fin_sweep_mm,
        fin_tail_inset=g.fin_tail_inset_mm,
        fin_count=g.fin_count,
        fin_thickness=g.fin_thickness_mm,
        fin_tab=a.root_capture_mm,
        fin_root_offset=0,
        fin_shoe_width=0,
        skirt_length=0,  # flat CFD base; no recessed skirt is inferred
    )
    assembly = dict(
        key="design-" + digest(spec.model_dump(mode="json"))[:16],
        axial_cd=spec.design.axial_drag_coefficient or 0.55,
        dimensions_mm=dimensions,
        bill=bill,
        dry_mass_g=dry * 1000,
        dry_cg_mm=moment / dry * 1000,
        loaded_cg_mm=loaded * 1000,
        wet_cg_mm=wet * 1000,
        cp_mm=cp * 1000,
        fin_set_CNalpha_per_rad=cn,
        physical_qualification=False,
    )
    config = AnalysisConfig(
        fin_material=Material(**stock, evidence_id="assumed-printed-constitutive-scenario"),
        fin_thickness_m=g.fin_thickness_mm / 1000,
        fin_root_k_n_m=mount["root_k_n_m"],
        solar_w_m2=a.solar_w_m2,
        warm_wait_s=a.warm_wait_s,
        flight=FlightConfig(
            wind_mps=spec.env.wind_speed_mps,
            gust_mps=a.gust_mps,
            cant_deg=0,
            initial_tilt_deg=a.initial_tilt_deg,
            pitch_damping=a.pitch_damping,
            rail_m=spec.env.rail_length_m,
            opening_s=a.opening_s,
        ),
    )
    temperature, pressure, density = state_scalar(
        spec.env.launch_altitude_m, spec.env.temperature_offset_k
    )
    config.loads.ambient_pa = pressure
    config.loads.initial_k = temperature
    config.loads.ambient_k = temperature
    config.loads.initial_wall_k = temperature
    config.flight.air_density_kg_m3 = density
    config.flight.wind_to_azimuth_deg = (spec.env.wind_direction_deg + 180) % 360
    design = spec.design.model_copy(update={"dry_mass_kg": dry, "geometry": g})
    return dict(
        design=design.model_dump(mode="json"),
        assembly=assembly,
        config=config.model_dump(mode="json"),
        material=spec.material,
        mass_basis="measured total; CAD proportions" if measured else "solid CAD estimate",
        dimensions_measured=g.dimensions_measured,
        evidence=a.evidence,
        limitations=[
            "attachment and constitutive properties are assumptions",
            "CFD/FEM envelopes omit printed clip/slot detail",
            "BOM local inertias are surrogates",
            "not physical qualification",
        ],
    )


def scopes(spec, *, precision, code_hash):
    """Canonical scopes: every editable field enters an applicable dependency hash."""
    d = spec.design.model_dump(mode="json", exclude={"dry_mass_kg", "geometry"})
    return {
        k: digest(v)
        for k, v in dict(
            geometry=spec.geometry.model_dump(),
            material=spec.material,
            mass=dict(
                other=spec.other_dry_mass_g,
                measured=spec.measured_printed_mass_g,
                payload=spec.design.payload_mass_kg,
                stations=spec.assumptions.model_dump(
                    include={"other_mass_station_fraction", "payload_station_fraction"}
                ),
            ),
            assumptions=spec.assumptions.model_dump(),
            operation=d,
            environment=spec.env.model_dump(),
            requirements=dict(
                requirement=spec.requirement.model_dump() if spec.requirement else None,
                precision=precision.model_dump(),
            ),
            code=code_hash,
        ).items()
    }
