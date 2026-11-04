import pytest

from rocketwright.bottle_assembly import BenchRecord, Workshop
from rocketwright.bottle_search import Action, Search


def test_mount_and_wet_stability_drive_rework_before_flight():
    run = Search("references", Workshop())
    plain = Action("component", "D02", 9, 300, 35, "carton_plain")
    damped = plain.change(variant="carton_damped")
    wide = plain.change(variant="carton_wide")
    assert wide.id not in run.options()
    _, first = run.step(plain.id, "inspect the reference fins")
    assert not first["eligible"] and first["mount_bound"] > 0.1
    _, second = run.step(damped.id, "test a damped mount")
    assert second["mount_bound"] < 0.1 and not second["checks"]["static_restoring_dry_and_wet"]
    assert damped.change(method="flight").id not in run.options()
    _, third = run.step(wide.id, "move the pressure center aft")
    assert third["eligible"] and third["wet_cg_mm"] < third["cp_mm"]
    assert run.design(wide).dry_mass_kg == pytest.approx(third["dry_mass_g"] / 1000)
    assert run.design(wide).axial_drag_coefficient > run.design(damped).axial_drag_coefficient
    assert wide.change(method="flight").id in run.options()
    assert wide.change(method="confirm").id not in run.options()


def test_specimen_record_is_specific_to_mount_and_airframe():
    key = "D02/9/carton_wide"
    record = BenchRecord(
        article_id="fixture-test",
        record="synthetic",
        dry_mass_g=170,
        dry_cg_from_tip_mm=305,
        modal_zeta_lower=0.01,
    )
    run = Search("references", Workshop(articles={key: record}, nozzle_options_mm=[9]))
    baseline = Action("component", "D02", 9, 300, 35, "carton_damped")
    run.step(baseline.id, "establish reference")
    wide = baseline.change(variant="carton_wide")
    _, result = run.step(wide.id, "apply fixture data")
    assert result["dry_mass_g"] == 170 and not result["checks"]["mount_settles"]
    assert wide.change(method="flight").id not in run.options()
    assert run.design(baseline).dry_mass_kg != 0.170
    assert all(a.nozzle_mm == 9 for a in run.options().values())
    with pytest.raises(ValueError, match="unknown workshop"):
        Search("references", Workshop(unavailable={"typo"}))
