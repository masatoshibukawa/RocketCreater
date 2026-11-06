import pytest

from rocketwright.agent.tools import execute_tool
from rocketwright.bottle_stability import bottle_stability
from rocketwright.parts import load_parts as load_parts
from rocketwright.schema import BottleDesign

DESIGN = BottleDesign(
    bottle_volume_m3=0.0015,
    water_fill_frac=0.4,
    initial_gauge_pressure_pa=250000,
    nozzle_diameter_m=0.015,
    dry_mass_kg=0.09,
    payload_mass_kg=0.06,
    has_fins=True,
    has_parachute=True,
    parachute_diameter_m=0.5,
)


def test_water_at_the_tail_moves_the_cg_aft_and_lowers_the_margin():
    result = bottle_stability(DESIGN)
    assert result.wet_cg_from_nose_m > result.dry_cg_from_nose_m
    assert result.wet_margin_cal < result.dry_margin_cal


def test_margin_matches_the_definition():
    result = bottle_stability(DESIGN)
    aero_diameter = (result.x_cp_from_nose_m - result.wet_cg_from_nose_m) / result.wet_margin_cal
    dry = (result.x_cp_from_nose_m - result.dry_cg_from_nose_m) / aero_diameter
    assert result.dry_margin_cal == pytest.approx(dry)


def test_a_longer_catalog_fin_moves_the_centre_of_pressure_aft():
    catalog = load_parts()
    fin_set = catalog.get("bottle_fin_set_pp_sheet_4", "bottle_fin_set")
    small = bottle_stability(DESIGN, fin_set.model_copy(update={"span_m": 0.04}))
    large = bottle_stability(DESIGN, fin_set.model_copy(update={"span_m": 0.16}))
    assert large.x_cp_from_nose_m > small.x_cp_from_nose_m
    assert large.wet_margin_cal > small.wet_margin_cal


def test_no_fins_gives_no_margin():
    assert bottle_stability(DESIGN.model_copy(update={"has_fins": False})) is None


def test_negative_margin_is_warned_in_words():
    text = " ".join(bottle_stability(DESIGN).warnings())
    assert "does not restore itself at liftoff" in text


def test_simulate_design_reports_the_margin_for_a_bottle():
    out = execute_tool(
        "simulate_design",
        {"design": DESIGN.model_dump(mode="json"), "env": {}, "seed": None, "requirement": None},
        "t",
    )
    assert "stability_margin_cal" in out["metrics"]
    assert "dry_stability_margin_cal" in out["metrics"]
    assert any(w.startswith("stability:") for w in out["warnings"])


def test_design_from_parts_uses_the_chosen_fin_set():
    build = {
        "tier": "bottle",
        "bottle_id": "pet_bottle_1p5l",
        "water_fill_frac": 0.4,
        "initial_gauge_pressure_pa": 250000.0,
        "nozzle_id": "bottle_nozzle_15mm",
        "fin_set_id": "bottle_fin_set_pp_sheet_4",
        "payload_mass_kg": 0.06,
    }
    out = execute_tool("design_from_parts", {"build": build, "env": {}}, "t")
    assert out["sim"] is not None, out
    assert any("bottle_fin_set_pp_sheet_4" in w for w in out["sim"]["warnings"])
