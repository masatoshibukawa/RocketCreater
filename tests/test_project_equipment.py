import pytest

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.agent.project_equipment import Equipment, Purchase, procurement_summary
from rocketwright.manufacturing import PrintGeometry, PrintRequest, parameters
from rocketwright.schema import BottleDesign


def spec():
    d = BottleDesign(
        bottle_volume_m3=0.002,
        water_fill_frac=0.3,
        initial_gauge_pressure_pa=300000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.1,
        payload_mass_kg=0.06,
    )
    return DesignSpec(design=d, geometry=PrintGeometry.from_design(d), other_dry_mass_g=80)


def test_unknown_estimated_or_wrong_quantity_cost_cannot_pass_budget():
    s = spec()
    cost = procurement_summary(s)
    assert cost["total_jpy"] is None
    s.equipment.procurement = [
        Purchase(
            part=r["part"],
            quantity=r["required_quantity"],
            unit_price_jpy=100,
            basis="quote",
            source="recorded quote",
            checked_on="2026-11-06",
        )
        for r in cost["rows"]
    ]
    assert procurement_summary(s)["total_jpy"] == 1000
    s.equipment.procurement[0].basis = "estimate"
    assert procurement_summary(s)["total_jpy"] is None
    s.equipment.procurement[0].basis = "paid"
    s.equipment.procurement[0].quantity = 2
    assert procurement_summary(s)["total_jpy"] is None
    with pytest.raises(ValueError):
        Equipment(procurement=[Purchase(part="fin", quantity=4)] * 2)


def test_saved_clearance_and_slots_enter_actual_cad_parameters():
    s = spec()
    g = s.geometry.model_copy(update={"radial_clearance_mm": 0.8, "fin_slot_width_mm": 4.2})
    d = s.design.model_copy(update={"geometry": g})
    actual = parameters(PrintRequest(design=d))
    assert actual["bottle"]["radial_clearance"] == 0.8
    assert actual["fin"]["slot_width"] == 4.2
    assert Equipment().printer_profile == "s5-gray-aa04"
