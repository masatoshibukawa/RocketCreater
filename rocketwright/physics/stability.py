"""Barrowman centre of pressure and static margin for the amateur tier (CLAUDE.md section 7).

Barrowman's equations (J. S. Barrowman, "The Practical Calculation of the Aerodynamic
Characteristics of Slender Finned Vehicles", M.S. thesis, Catholic University of America, 1967;
summarised in the OpenRocket technical documentation, https://openrocket.info/documentation.html)
give the subsonic, small-angle-of-attack normal-force coefficient `C_N` and its centre of
pressure for a nose cone, a cylindrical body (zero contribution) and a set of trapezoidal fins
with body interference. Stations are measured in metres from the nose tip.

Geometry convention (shared with drawing.py): `nose_length_m` is the cone, `body_length_m` is
the cylindrical tube behind it, so the overall length is `nose_length_m + body_length_m` and the
fins sit flush with the aft end.

Every approximation is marked with `# SIMPLIFICATION:`.
"""

from __future__ import annotations

import math

from rocketwright.schema import AmateurDesign, FinSet

__all__ = [
    "NOSE_CP_FRACTION",
    "center_of_gravity_m",
    "center_of_pressure_m",
    "fin_normal_force",
    "nose_normal_force",
    "overall_length_m",
    "static_margin_cal",
]

# CP of the nose cone as a fraction of its length (Barrowman: X = L - V / (pi R^2)).
NOSE_CP_FRACTION: dict[str, float] = {
    "conical": 2.0 / 3.0,
    "ogive": 0.466,
    "elliptical": 1.0 / 3.0,
}
NOSE_CN = 2.0  # every nose shape has C_N_alpha = 2 (per unit reference area pi R^2)


def overall_length_m(design: AmateurDesign) -> float:
    return design.nose_length_m + design.body_length_m


def nose_normal_force(design: AmateurDesign) -> tuple[float, float]:
    """(C_N, CP station) of the nose cone."""
    return NOSE_CN, NOSE_CP_FRACTION[design.nose_shape] * design.nose_length_m


def fin_normal_force(design: AmateurDesign) -> tuple[float, float]:
    """(C_N, CP station) of the fin set, including the body-interference factor."""
    return trapezoidal_fin_force(
        design.body_diameter_m, design.fins, overall_length_m(design) - design.fins.root_chord_m
    )


def trapezoidal_fin_force(diameter_m: float, f: FinSet, x_root_le: float) -> tuple[float, float]:
    """Normal-force slope and CP for fins with a specified root leading-edge station."""
    radius = diameter_m / 2.0
    cr, ct, s, xt = f.root_chord_m, f.tip_chord_m, f.span_m, f.sweep_m
    # Mid-chord line length from root mid-chord to tip mid-chord.
    mid_chord = math.sqrt(s * s + (xt + ct / 2.0 - cr / 2.0) ** 2)
    interference = 1.0 + radius / (s + radius)
    # SIMPLIFICATION: Barrowman's `N` is used as is for 3-8 fins. His derivation assumes at most
    # two fins are effective in any plane; OpenRocket applies a reduction for 5+ fins.
    cn = (
        interference
        * (4.0 * f.count * (s / diameter_m) ** 2)
        / (1.0 + math.sqrt(1.0 + (2.0 * mid_chord / (cr + ct)) ** 2))
    )
    x_cp = (
        x_root_le + xt * (cr + 2.0 * ct) / (3.0 * (cr + ct)) + (cr + ct - cr * ct / (cr + ct)) / 6.0
    )
    return cn, x_cp


def center_of_pressure_m(design: AmateurDesign) -> float:
    """Barrowman CP station from the nose tip (C_N-weighted mean of the components)."""
    cn_n, x_n = nose_normal_force(design)
    cn_f, x_f = fin_normal_force(design)
    # SIMPLIFICATION: a constant-diameter body tube contributes no normal force (Barrowman).
    return (cn_n * x_n + cn_f * x_f) / (cn_n + cn_f)


def center_of_gravity_m(
    design: AmateurDesign,
    motor_mass_kg: float,
    *,
    motor_length_m: float = 0.0,
    payload_station_m: float | None = None,
) -> float:
    """Lumped-mass CG station from the nose tip.

    SIMPLIFICATION: the airframe dry mass is spread uniformly along the overall length (CG at
    mid-length), the payload is a point mass at the base of the nose cone unless
    `payload_station_m` is given, and the motor is a point mass at the centre of its case,
    which sits flush with the aft end (`motor_length_m = 0` puts it exactly at the tail).
    """
    length = overall_length_m(design)
    x_payload = design.nose_length_m if payload_station_m is None else payload_station_m
    x_motor = length - motor_length_m / 2.0
    moment = (
        design.dry_mass_kg * length / 2.0
        + design.payload_mass_kg * x_payload
        + motor_mass_kg * x_motor
    )
    return moment / (design.dry_mass_kg + design.payload_mass_kg + motor_mass_kg)


def static_margin_cal(
    design: AmateurDesign,
    motor_mass_kg: float | None = None,
    *,
    motor_length_m: float | None = None,
    payload_station_m: float | None = None,
) -> float:
    """Static margin (CP - CG) in calibers (body diameters).

    With `motor_mass_kg` omitted the motor is looked up in the catalog and its LOADED mass and
    case length are used: the liftoff condition (full motor, CG furthest aft) is the least
    stable one. With an explicit mass and no length the motor CG sits at the tail.
    """
    if motor_mass_kg is None:
        from rocketwright.physics import solid  # local import: solid imports this module

        motor = solid.load_motor(design.motor_id)
        motor_mass_kg = motor.total_mass_kg
        if motor_length_m is None:
            motor_length_m = motor.length_m
    cg = center_of_gravity_m(
        design,
        motor_mass_kg,
        motor_length_m=motor_length_m or 0.0,
        payload_station_m=payload_station_m,
    )
    return (center_of_pressure_m(design) - cg) / design.body_diameter_m
