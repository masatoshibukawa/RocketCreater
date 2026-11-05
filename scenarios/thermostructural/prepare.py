"""Export the existing prototype's loads without interpreting its proxy pass as qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rocketwright.physics import atmosphere, recovery, water  # noqa: E402
from rocketwright.physics.stability import trapezoidal_fin_force  # noqa: E402
from rocketwright.schema import BottleDesign, Env, FinSet  # noqa: E402


def prepare(packet: Path, out: Path) -> dict:
    source = {
        name: (packet / f"{name}.json").read_bytes() for name in ("assembly", "design", "run")
    }
    assembly, design_data, run = (json.loads(source[name]) for name in source)
    design, env = BottleDesign(**design_data), Env(**run["environment"])
    assert design.payload_mass_kg > 0 and design.has_parachute and design.has_fins
    flight = water.run_flight(design, env)
    assert flight.left_rail and flight.thrust_end_time_s > 0
    assert np.all(np.diff(flight.t_s) > 0)
    # SIMPLIFICATION: the underlying flight assumes zero incidence and an instantaneous
    # residual-air impulse. Do not differentiate its velocity jump into a finite load.
    wind_e, wind_n = recovery.wind_vector_mps(env)
    speed = np.sqrt(
        (flight.vx_mps - wind_e) ** 2 + (flight.vy_mps - wind_n) ** 2 + flight.vz_mps**2
    )
    atmos = np.array(
        [
            atmosphere.state_scalar(env.launch_altitude_m + z, env.temperature_offset_k)
            for z in flight.z_m
        ]
    )
    q = 0.5 * atmos[:, 2] * speed**2
    d = assembly["dimensions_mm"]
    cn, cp = trapezoidal_fin_force(
        d["body_diameter"] / 1000,
        FinSet(
            count=4,
            root_chord_m=d["fin_root"] / 1000,
            tip_chord_m=d["fin_tip"] / 1000,
            span_m=d["fin_span"] / 1000,
            sweep_m=d["fin_sweep"] / 1000,
        ),
        (d["overall"] - d["fin_tail_inset"] - d["fin_root"]) / 1000,
    )
    descent = recovery.descend(
        float(flight.mass_kg[-1]),
        design.parachute_diameter_m,
        env,
        start_altitude_m=flight.apogee_m,
    )
    result = {
        "source_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in source.items()},
        "physical_status": "conditional_analysis_not_qualified",
        "design": design_data,
        "environment": run["environment"],
        "assembly": assembly,
        "fin_set_CNalpha_per_rad": cn,
        "fin_cp_m": cp,
        "ambient_pressure_pa": float(atmos[0, 1]),
        "max_dynamic_pressure_pa": float(q.max()),
        "max_speed_mps": float(speed.max()),
        "water_peak_proper_accel_mps2": float(
            flight.accel_mps2[flight.t_s < flight.thrust_end_time_s].max()
        ),
        "water_end_s": flight.thrust_end_time_s,
        "air_impulse_ns": flight.air_impulse_ns,
        "landing_speed_mps": descent.descent_speed_mps,
        "apogee_m": flight.apogee_m,
        "trace": {
            "time_s": flight.t_s.tolist(),
            "q_pa": q.tolist(),
            "mass_kg": flight.mass_kg.tolist(),
            "thrust_n": flight.thrust_n.tolist(),
            "proper_accel_mps2": flight.accel_mps2.tolist(),
        },
        "limitations": [
            "Unvalidated constant Cd; previous 3D CFD failed absolute-drag validation.",
            "Air impulse duration unresolved; opening and landing shocks use separate scenarios.",
            "No measured strength, stiffness, thermal properties, contact or bond allowables.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("assembly", "design", "trace", "source_sha256")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    prepare(args.packet, args.out)
