#!/usr/bin/env python
"""One-off helper: tune the pitch program of the commercial demo designs with the real physics.

    uv run python scripts/tune_demo_design.py

Prints, for each candidate in `CANDIDATES`, the design returned by
`rocketwright.physics.multistage.tune_pitch_program`, the SimResult verdict and a small
neighbourhood scan (pitch_start_s +-0.5 s, initial_pitch_deg +-0.2 deg) so a human can pick a
pitch program that sits inside the passing window rather than on its edge. The numbers hard-coded
in `rocketwright/agent/fake_client.py` (DEMO_DESIGNS["commercial"]) came from this script.

With the coast-and-circularize insertion the perigee is set by the circularization burn, so the
kick mainly decides the apogee overshoot and the leftover propellant; the scan shows how wide
the passing window is (it used to be a tenth of a degree).
"""

from __future__ import annotations

import time
from typing import Any

from rocketwright.cost import estimate_cost_jpy
from rocketwright.physics import multistage as ms
from rocketwright.schema import Env, MultistageDesign, Requirement, Stage

# Same environment and requirement as scenarios/demo_commercial.yaml. Orbit goals are flown with
# Earth rotation on by the agent's dispatch (rocketwright.agent.tools._orbit_env), so it is on
# here too.
ENV = Env(
    launch_latitude_deg=31.25,
    launch_altitude_m=20,
    wind_speed_mps=5.0,
    wind_direction_deg=200,
    earth_rotation=True,
)
REQUIREMENT = Requirement(
    goal_kind="orbit", target_altitude_m=400_000, payload_mass_kg=150, budget_jpy=2.0e9
)

# (label, stage-1 propellant, stage-1 engines, stage-2 propellant, initial pitch guess)
# Electron-class vehicle: 9-10 Rutherford on stage 1, one on stage 2. A merlin_1d first stage
# is physically too strong for a 150 kg payload under the 2e9 JPY budget: with a liftoff mass
# capped at ~25 t by cost it lifts off at TWR > 3 and exceeds the 60 kPa max-Q limit.
CANDIDATES: list[tuple[str, float, int, float, tuple[float, float]]] = [
    ("under-fuelled (expected to FAIL)", 9_250.0, 9, 1_500.0, (12.0, 4.0)),
    ("design A", 9_250.0, 9, 2_500.0, (12.0, 4.0)),
    ("design C", 9_250.0, 10, 3_500.0, (25.0, 8.0)),
]


def make_design(
    prop1_kg: float, engines1: int, prop2_kg: float, pitch: tuple[float, float]
) -> MultistageDesign:
    return MultistageDesign(
        tier="commercial",
        stages=[
            Stage(
                propellant_mass_kg=prop1_kg,
                structural_fraction=0.08,
                engine_id="rutherford",
                engine_count=engines1,
            ),
            Stage(
                propellant_mass_kg=prop2_kg,
                structural_fraction=0.10,
                engine_id="rutherford",
                engine_count=1,
            ),
        ],
        fairing_mass_kg=50.0,
        payload_mass_kg=REQUIREMENT.payload_mass_kg,
        pitch_start_s=pitch[0],
        initial_pitch_deg=pitch[1],
    )


def verdict(design: MultistageDesign) -> tuple[bool, dict[str, Any]]:
    result = ms.simulate(design, ENV, target_perigee_m=REQUIREMENT.target_altitude_m)
    m = result.metrics
    return result.success, {
        "perigee_km": round(m["perigee_m"] / 1e3, 1),
        "apogee_km": round(min(m["apogee_m"], 1e8) / 1e3),
        "max_q_kpa": round(m["max_q_pa"] / 1e3, 1),
        "propellant_margin_kg": round(m["propellant_margin_kg"]),
        "payload_margin_kg": round(m["payload_margin_kg"]),
        "reasons": result.failure_reasons,
    }


def neighbourhood(design: MultistageDesign) -> None:
    print("    neighbourhood (ps, pa -> perigee km, * = pass):")
    for dps in (-2.0, 0.0, 2.0):
        cells = []
        for dpa in (-1.0, -0.5, 0.0, 0.5, 1.0):
            candidate = design.model_copy(
                update={
                    "pitch_start_s": design.pitch_start_s + dps,
                    "initial_pitch_deg": design.initial_pitch_deg + dpa,
                }
            )
            ok, info = verdict(candidate)
            cells.append(f"{info['perigee_km']:7.1f}{'*' if ok else ' '}")
        print(f"      ps{dps:+.1f}: " + " ".join(cells))


def main() -> None:
    for label, prop1, engines1, prop2, guess in CANDIDATES:
        start = make_design(prop1, engines1, prop2, guess)
        ok, info = verdict(start)
        print(f"{label}: liftoff cost {estimate_cost_jpy(start):.3g} JPY")
        print(f"  as guessed (ps={guess[0]}, pa={guess[1]}): {'PASS' if ok else 'FAIL'} {info}")
        t0 = time.perf_counter()
        tuned = ms.tune_pitch_program(start, ENV, target_perigee_m=REQUIREMENT.target_altitude_m)
        dt = time.perf_counter() - t0
        rounded = tuned.model_copy(
            update={
                "pitch_start_s": round(tuned.pitch_start_s, 2),
                "initial_pitch_deg": round(tuned.initial_pitch_deg, 2),
            }
        )
        ok, info = verdict(rounded)
        print(
            f"  tuned in {dt:.1f} s: pitch_start_s={rounded.pitch_start_s}, "
            f"initial_pitch_deg={rounded.initial_pitch_deg} -> {'PASS' if ok else 'FAIL'} {info}"
        )
        neighbourhood(rounded)


if __name__ == "__main__":
    main()
