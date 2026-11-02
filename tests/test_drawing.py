"""Tests for rocketwright.drawing: well-formed, deterministic SVG side views per tier."""

import xml.etree.ElementTree as ET

import pytest

from rocketwright.drawing import render_side_view_svg
from rocketwright.schema import DesignAdapter

AMATEUR = DesignAdapter.validate_python(
    {
        "tier": "amateur",
        "body_diameter_m": 0.08,
        "body_length_m": 1.2,
        "nose_shape": "ogive",
        "nose_length_m": 0.3,
        "fins": {
            "count": 4,
            "root_chord_m": 0.15,
            "tip_chord_m": 0.06,
            "span_m": 0.09,
            "sweep_m": 0.05,
        },
        "motor_id": "dummy-H128",
        "dry_mass_kg": 1.2,
        "payload_mass_kg": 0.5,
        "parachute_diameter_m": 0.9,
        "deploy_delay_s": 3.0,
    }
)

BOTTLE = DesignAdapter.validate_python(
    {
        "tier": "bottle",
        "bottle_volume_m3": 0.0015,
        "water_fill_frac": 0.35,
        "initial_gauge_pressure_pa": 500_000,
        "nozzle_diameter_m": 0.009,
        "dry_mass_kg": 0.12,
        "payload_mass_kg": 0.06,
        "has_fins": True,
        "has_parachute": True,
        "parachute_diameter_m": 0.4,
    }
)

COMMERCIAL = DesignAdapter.validate_python(
    {
        "tier": "commercial",
        "stages": [
            {
                "propellant_mass_kg": 9250,
                "structural_fraction": 0.08,
                "engine_id": "rutherford",
                "engine_count": 9,
            },
            {
                "propellant_mass_kg": 3500,
                "structural_fraction": 0.10,
                "engine_id": "rutherford",
                "engine_count": 1,
            },
        ],
        "fairing_mass_kg": 50,
        "payload_mass_kg": 150,
        "pitch_start_s": 25.0,
        "initial_pitch_deg": 8.0,
    }
)

HEAVY = DesignAdapter.validate_python(
    {
        "tier": "heavy",
        "stages": [
            {
                "propellant_mass_kg": 400_000,
                "structural_fraction": 0.06,
                "engine_id": "merlin_1d",
                "engine_count": 9,
            },
            {
                "propellant_mass_kg": 100_000,
                "structural_fraction": 0.07,
                "engine_id": "merlin_1d_vacuum",
                "engine_count": 1,
            },
        ],
        "boosters": [{"booster_id": "gem_63", "count": 2}],
        "fairing_mass_kg": 1_900,
        "payload_mass_kg": 8_000,
        "pitch_start_s": 20.0,
        "initial_pitch_deg": 5.0,
    }
)


def _parse(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"].startswith("0 0 800 ")
    assert root.find("{http://www.w3.org/2000/svg}title") is not None
    return root


def _texts(root: ET.Element) -> list[str]:
    return ["".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text")]


@pytest.mark.parametrize("design", [AMATEUR, BOTTLE, COMMERCIAL, HEAVY], ids=lambda d: d.tier)
def test_svg_is_well_formed_and_deterministic(design):
    a = render_side_view_svg(design)
    b = render_side_view_svg(design)
    assert a == b
    root = _parse(a)
    assert root.attrib["width"] == "800"
    assert any("Scale" in t or "scale" in t for t in _texts(root))


def test_amateur_dimensions_and_parts():
    root = _parse(render_side_view_svg(AMATEUR))
    texts = _texts(root)
    assert "1500 mm" in texts  # total length = nose + body
    assert "1200 mm" in texts  # body length
    assert "300 mm" in texts  # nose length
    assert "80 mm" in texts  # diameter
    assert "150 mm" in texts  # fin root chord
    assert "60 mm" in texts  # fin tip chord
    assert "90 mm" in texts  # fin span
    assert any("dummy-H128" in t for t in texts)  # motor mount legend
    assert any("0.90 m" in t and "arachute" in t for t in texts)
    assert any("x4" in t for t in texts)  # fin count


@pytest.mark.parametrize("shape", ["conical", "ogive", "elliptical"])
def test_amateur_nose_shapes_differ(shape):
    d = AMATEUR.model_copy(update={"nose_shape": shape})
    svg = render_side_view_svg(d)
    _parse(svg)
    assert shape in svg
    others = [s for s in ("conical", "ogive", "elliptical") if s != shape]
    for o in others:
        assert render_side_view_svg(AMATEUR.model_copy(update={"nose_shape": o})) != svg


def test_bottle_dimensions_and_features():
    root = _parse(render_side_view_svg(BOTTLE))
    texts = _texts(root)
    assert "9 mm" in texts  # nozzle diameter
    assert any(t.endswith(" mm") for t in texts)
    assert any("35 %" in t for t in texts)  # water level label
    assert any("arachute" in t for t in texts)
    # fins and parachute toggle visible elements
    no_extras = BOTTLE.model_copy(
        update={"has_fins": False, "has_parachute": False, "parachute_diameter_m": None}
    )
    assert render_side_view_svg(no_extras) != render_side_view_svg(BOTTLE)
    assert 'class="fin"' not in render_side_view_svg(no_extras)
    assert 'class="parachute"' not in render_side_view_svg(no_extras)
    assert 'class="fin"' in render_side_view_svg(BOTTLE)


def test_commercial_is_concept_level_with_stage_lengths():
    root = _parse(render_side_view_svg(COMMERCIAL))
    texts = _texts(root)
    assert any("Concept sketch" in t and "not for manufacturing" in t for t in texts)
    assert any(t.startswith("Stage 1") for t in texts)
    assert any(t.startswith("Stage 2") for t in texts)
    assert any(t.startswith("Total length") for t in texts)
    assert any(t.startswith("Diameter") for t in texts)
    assert any(t.endswith(" m") for t in texts)
    assert any("x9" in t for t in texts)  # engine count


def test_heavy_draws_boosters():
    svg = render_side_view_svg(HEAVY)
    root = _parse(svg)
    texts = _texts(root)
    assert any("gem_63" in t and "x2" in t for t in texts)
    assert "booster" in svg
    assert any("Concept sketch" in t for t in texts)


def test_width_parameter_scales_viewbox():
    svg = render_side_view_svg(AMATEUR, width_px=400)
    root = ET.fromstring(svg)
    assert root.attrib["width"] == "400"
    assert root.attrib["viewBox"].startswith("0 0 400 ")
