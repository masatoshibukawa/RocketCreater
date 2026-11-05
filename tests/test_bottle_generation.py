import pytest

from rocketwright import bottle_candidates, bottle_search
from rocketwright.bottle_candidates import REQUIREMENT, VOLUME_M3, design_at, starts
from rocketwright.bottle_search import Action, Search


def test_harness_rejects_skipping_and_reusing_lower_layer_evidence(monkeypatch):
    # A 30 m fixture keeps this 300 kPa flight short of target, whatever the demo target is.
    short_flight = REQUIREMENT.model_copy(update={"target_altitude_m": 30})
    monkeypatch.setattr(bottle_candidates, "REQUIREMENT", short_flight)
    monkeypatch.setattr(bottle_search, "TARGET", 30)
    search = Search("references")
    action = Action("component", "D02", 9, 300, 35)
    with pytest.raises(ValueError, match="listed ID"):
        search.step(action.change(method="screen").id, "skip the nominal flight")
    search.step(action.id, "test the original octagonal canopy")
    _, result = search.step(action.change(method="flight").id, "establish altitude")
    assert result["apogee_m"] < 27
    # A short flight must offer a raised-pressure component re-screen, never a direct flight.
    # The exact step depends on the calibrated water model (it was 375 kPa before the drag /
    # air-impulse calibration), so check the behaviour rather than one pressure value.
    options = search.options()
    raised = [
        act
        for act in options.values()
        if act.method == "component"
        and (act.start, act.nozzle_mm, act.fill_pct) == ("D02", 9, 35)
        and act.pressure_kpa > action.pressure_kpa
    ]
    assert raised
    assert all(r.change(method="flight").id not in options for r in raised)
    assert action.change(method="screen").id not in search.options()


def test_nozzle_substitution_updates_mass_without_relaxing_payload_or_capacity():
    seed = starts()["D01"]
    open_neck = design_at(seed, 22, 300, 35)
    insert = design_at(seed, 9, 300, 35)
    assert insert.dry_mass_kg - open_neck.dry_mass_kg == pytest.approx(0.010)
    assert insert.payload_mass_kg == open_neck.payload_mass_kg == 0.060
    assert insert.bottle_volume_m3 == open_neck.bottle_volume_m3 == VOLUME_M3
    with pytest.raises(ValueError, match="domain"):
        design_at(seed, 17, 300, 35)
