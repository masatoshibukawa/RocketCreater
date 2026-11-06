#!/usr/bin/env python
"""One-off helper: evaluate candidate amateur / bottle demo designs with the real physics.

    uv run python scripts/tune_suborbital_demo.py --tier amateur
    uv run python scripts/tune_suborbital_demo.py --tier bottle

Runs every candidate in `CANDIDATES[tier]` through the agent's `_simulate_dispatch` (so the
budget and requirement rules apply exactly as in the demo) with the environment and requirement
of the matching scenario, prints the verdict, and scans one design variable so a human can pick
values that sit inside the passing window. The numbers hard-coded in
`rocketwright/agent/fake_client.py` (DEMO_DESIGNS["amateur"] / ["bottle"]) came from this script.
"""

from __future__ import annotations

import argparse
from typing import Any

from rocketwright.agent.fake_client import DEMO_REQUIREMENTS
from rocketwright.agent.tools import _simulate_dispatch
from rocketwright.schema import DesignAdapter, Env, Requirement

# Same environments as scenarios/demo_amateur.yaml and scenarios/demo_bottle.yaml.
ENVS: dict[str, Env] = {
    "amateur": Env(
        launch_latitude_deg=36.0, launch_altitude_m=300, wind_speed_mps=3.0, wind_direction_deg=270
    ),
    "bottle": Env(
        launch_latitude_deg=35.0, launch_altitude_m=20, wind_speed_mps=2.0, wind_direction_deg=270
    ),
}

_FINS = {"count": 4, "root_chord_m": 0.10, "tip_chord_m": 0.05, "span_m": 0.05, "sweep_m": 0.03}


def _amateur(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tier": "amateur",
        "body_diameter_m": 0.054,
        "body_length_m": 0.9,
        "nose_shape": "ogive",
        "nose_length_m": 0.15,
        "fins": _FINS,
        "motor_id": "dummy_J420",
        "dry_mass_kg": 1.5,
        "payload_mass_kg": 1.0,
        "parachute_diameter_m": 1.2,
        "deploy_delay_s": 1.0,
    }
    base.update(kw)
    return base


def _bottle(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tier": "bottle",
        "bottle_volume_m3": 0.0015,
        "water_fill_frac": 0.4,
        "initial_gauge_pressure_pa": 500_000,
        "nozzle_diameter_m": 0.022,
        "dry_mass_kg": 0.12,
        "payload_mass_kg": 0.06,
        "has_fins": True,
        "has_parachute": True,
        "parachute_diameter_m": 0.5,
    }
    base.update(kw)
    return base


# (label, design, scan variable, scan values)
CANDIDATES: dict[str, list[tuple[str, dict[str, Any], str, list[float]]]] = {
    "amateur": [
        (
            "I200, small chute (expected FAIL)",
            _amateur(motor_id="dummy_I200", dry_mass_kg=1.0, parachute_diameter_m=0.6),
            "dry_mass_kg",
            [0.8, 1.0, 1.2],
        ),
        (
            "J420 66 mm body",
            _amateur(body_diameter_m=0.066, body_length_m=1.1, nose_length_m=0.2, dry_mass_kg=1.4),
            "dry_mass_kg",
            [1.2, 1.3, 1.4, 1.5, 1.6],
        ),
        (
            "J420 54 mm body, heavier",
            _amateur(dry_mass_kg=1.9),
            "dry_mass_kg",
            [1.7, 1.8, 1.9, 2.0],
        ),
    ],
    "bottle": [
        (
            "no parachute (expected FAIL)",
            _bottle(has_parachute=False, parachute_diameter_m=None),
            "initial_gauge_pressure_pa",
            [300e3, 400e3, 500e3],
        ),
        (
            "parachute, pressure scan",
            _bottle(),
            "initial_gauge_pressure_pa",
            [250e3, 300e3, 350e3, 400e3, 450e3],
        ),
        (
            "1.5 L bottle, fill scan",
            _bottle(initial_gauge_pressure_pa=300e3),
            "water_fill_frac",
            [0.30, 0.35, 0.40, 0.45],
        ),
    ],
}

_KEYS = {
    "amateur": ("apogee_m", "rail_exit_speed_mps", "stability_margin_cal", "descent_speed_mps"),
    "bottle": ("apogee_m", "max_speed_mps", "descent_speed_mps", "landing_distance_m"),
}


def verdict(tier: str, raw: dict[str, Any], req: Requirement) -> str:
    design = DesignAdapter.validate_python(raw)
    res = _simulate_dispatch(design, ENVS[tier], 42, req)
    nums = " ".join(f"{k}={res.metrics[k]:.3g}" for k in _KEYS[tier])
    status = "PASS" if res.success else "FAIL " + "; ".join(res.failure_reasons)
    return f"{nums} cost={res.cost_jpy:.0f} -> {status}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("amateur", "bottle"), required=True)
    args = parser.parse_args(argv)
    req = Requirement.model_validate(DEMO_REQUIREMENTS[args.tier])
    for label, raw, var, values in CANDIDATES[args.tier]:
        print(f"{label}: {var}={raw[var]}")
        print(f"  {verdict(args.tier, raw, req)}")
        for value in values:
            print(f"    {var}={value:g}: {verdict(args.tier, {**raw, var: value}, req)}")


if __name__ == "__main__":
    main()
