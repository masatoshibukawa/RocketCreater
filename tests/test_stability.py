"""Tests for the Barrowman centre-of-pressure / static-margin model (CLAUDE.md section 7).

The reference CP in `test_textbook_four_fin_rocket` is computed in the test with an independent
transcription of the Barrowman equations (J. S. Barrowman, "The Practical Calculation of the
Aerodynamic Characteristics of Slender Finned Vehicles", 1967; summarised in the OpenRocket
technical documentation, https://openrocket.info/documentation.html).
"""

from __future__ import annotations

import math

import pytest

from rocketwright.physics import stability
from rocketwright.schema import AmateurDesign, FinSet


def design(**overrides: object) -> AmateurDesign:
    base: dict[str, object] = {
        "body_diameter_m": 0.05,
        "body_length_m": 0.80,
        "nose_shape": "conical",
        "nose_length_m": 0.15,
        "fins": FinSet(count=4, root_chord_m=0.10, tip_chord_m=0.05, span_m=0.06, sweep_m=0.04),
        "motor_id": "dummy_G80",
        "dry_mass_kg": 0.6,
        "payload_mass_kg": 0.2,
        "parachute_diameter_m": 0.6,
    }
    base.update(overrides)
    return AmateurDesign(**base)  # type: ignore[arg-type]


def _barrowman_cp_by_hand(d: AmateurDesign) -> float:
    """Independent transcription of the Barrowman equations for a cone + tube + N trapezoidal
    fins mounted flush with the aft end. Lengths measured from the nose tip."""
    radius = d.body_diameter_m / 2.0
    # nose cone: C_N = 2, CP at 2/3 of the cone length
    cn_nose = 2.0
    x_nose = 2.0 / 3.0 * d.nose_length_m
    # fins
    f = d.fins
    cr, ct, s, xt, n = f.root_chord_m, f.tip_chord_m, f.span_m, f.sweep_m, f.count
    mid_chord = math.sqrt(s**2 + (xt + ct / 2.0 - cr / 2.0) ** 2)
    cn_fins = (
        (1.0 + radius / (s + radius))
        * (4.0 * n * (s / d.body_diameter_m) ** 2)
        / (1.0 + math.sqrt(1.0 + (2.0 * mid_chord / (cr + ct)) ** 2))
    )
    x_fin_le = d.nose_length_m + d.body_length_m - cr
    x_fins = (
        x_fin_le + xt * (cr + 2.0 * ct) / (3.0 * (cr + ct)) + (cr + ct - cr * ct / (cr + ct)) / 6.0
    )
    return (cn_nose * x_nose + cn_fins * x_fins) / (cn_nose + cn_fins)


def test_textbook_four_fin_rocket_matches_hand_calculation() -> None:
    d = design()
    assert stability.center_of_pressure_m(d) == pytest.approx(_barrowman_cp_by_hand(d), rel=1e-9)
    # sanity: the CP sits behind the nose cone and ahead of the tail
    assert d.nose_length_m < stability.center_of_pressure_m(d) < d.nose_length_m + d.body_length_m


@pytest.mark.parametrize(
    ("shape", "fraction"), [("conical", 2.0 / 3.0), ("ogive", 0.466), ("elliptical", 1.0 / 3.0)]
)
def test_nose_cp_fraction_per_shape(shape: str, fraction: float) -> None:
    d = design(nose_shape=shape)
    cn, x = stability.nose_normal_force(d)
    assert cn == pytest.approx(2.0)
    assert x == pytest.approx(fraction * d.nose_length_m)


def test_margin_increases_with_fin_span() -> None:
    small = design(fins=FinSet(count=4, root_chord_m=0.10, tip_chord_m=0.05, span_m=0.04))
    large = design(fins=FinSet(count=4, root_chord_m=0.10, tip_chord_m=0.05, span_m=0.09))
    m_small = stability.static_margin_cal(small, motor_mass_kg=0.125)
    m_large = stability.static_margin_cal(large, motor_mass_kg=0.125)
    assert m_large > m_small


def test_margin_decreases_when_payload_moves_aft() -> None:
    d = design(payload_mass_kg=0.5)
    forward = stability.static_margin_cal(d, motor_mass_kg=0.125, payload_station_m=0.10)
    aft = stability.static_margin_cal(d, motor_mass_kg=0.125, payload_station_m=0.80)
    assert aft < forward


def test_margin_is_cp_minus_cg_in_calibers() -> None:
    d = design()
    cp = stability.center_of_pressure_m(d)
    cg = stability.center_of_gravity_m(d, motor_mass_kg=0.125)
    assert stability.static_margin_cal(d, motor_mass_kg=0.125) == pytest.approx(
        (cp - cg) / d.body_diameter_m
    )


def test_cg_is_mass_weighted_station_average() -> None:
    d = design(dry_mass_kg=1.0, payload_mass_kg=1.0)
    total_length = d.nose_length_m + d.body_length_m
    # SIMPLIFICATION in the model: airframe at mid-length, payload at the nose base, motor at
    # the aft end (motor_length_m = 0 puts its CG exactly at the tail).
    expected = (1.0 * total_length / 2.0 + 1.0 * d.nose_length_m + 1.0 * total_length) / 3.0
    assert stability.center_of_gravity_m(d, motor_mass_kg=1.0) == pytest.approx(expected)


def test_margin_without_motor_mass_uses_the_catalog_motor() -> None:
    d = design(motor_id="dummy_G80")
    m_catalog = stability.static_margin_cal(d)
    assert math.isfinite(m_catalog)
    # heavier motor at the tail -> CG moves aft -> margin drops
    assert stability.static_margin_cal(d, motor_mass_kg=10.0) < m_catalog
