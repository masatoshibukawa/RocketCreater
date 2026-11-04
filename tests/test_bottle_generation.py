import pytest

from rocketwright.bottle_candidates import VOLUME_M3, design_at, starts
from rocketwright.bottle_search import Action, Search


def test_harness_rejects_skipping_and_reusing_lower_layer_evidence():
    search = Search("references")
    action = Action("component", "D02", 9, 300, 35)
    with pytest.raises(ValueError, match="listed ID"):
        search.step(action.change(method="screen").id, "skip the nominal flight")
    search.step(action.id, "test the original octagonal canopy")
    _, result = search.step(action.change(method="flight").id, "establish altitude")
    assert result["apogee_m"] < 27
    raised = action.change(pressure_kpa=375)
    assert raised.id in search.options()
    assert raised.change(method="flight").id not in search.options()
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
