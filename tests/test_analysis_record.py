import copy

import pytest

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.record import compile_record, scopes
from rocketwright.analysis.schema import Precision
from rocketwright.manufacturing import PrintGeometry
from rocketwright.schema import BottleDesign, Requirement


def spec():
    d = BottleDesign(
        bottle_volume_m3=0.0015,
        water_fill_frac=0.25,
        initial_gauge_pressure_pa=300000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.15,
        payload_mass_kg=0.06,
        has_parachute=True,
        parachute_diameter_m=0.7,
    )
    geometry = PrintGeometry.from_design(d).model_copy(
        update={"body_diameter_mm": 90, "body_height_mm": 400}
    )
    return DesignSpec(
        design=d,
        geometry=geometry,
        other_dry_mass_g=100,
        requirement=Requirement(goal_kind="altitude", target_altitude_m=30),
    )


VOLUMES = {"fin": {"volume_mm3": 5000}, "nose": {"volume_mm3": 9000}}


def test_common_record_mass_closes_and_material_changes_inertia_inputs():
    s = spec()
    p = compile_record(s, VOLUMES)
    assert p["design"]["dry_mass_kg"] == pytest.approx(0.13596)
    assert sum(b["mass_g"] for b in p["assembly"]["bill"]) == pytest.approx(135.96)
    assert p["assembly"]["loaded_cg_mm"] < p["assembly"]["wet_cg_mm"]
    s.material = "Prusament PETG"
    q = compile_record(s, VOLUMES)
    assert q["design"]["dry_mass_kg"] > p["design"]["dry_mass_kg"]
    assert q["config"]["fin_material"]["young_pa"] < p["config"]["fin_material"]["young_pa"]
    assert not q["assembly"]["physical_qualification"]


def test_measured_mass_and_mount_increment_are_not_silently_discarded():
    s = spec()
    s.measured_printed_mass_g = 28
    s.assumptions.mount = "reinforced"
    p = compile_record(s, VOLUMES)
    assert p["design"]["dry_mass_kg"] == pytest.approx(0.133)
    assert p["config"]["fin_root_k_n_m"] == 2e6
    assert p["mass_basis"].startswith("measured total")


def test_scoped_invalidation_covers_editable_inputs_and_requirements():
    s, precision = spec(), Precision()
    initial = scopes(s, precision=precision, code_hash="v1")
    changed = copy.deepcopy(s)
    changed.name = "only a label"
    assert initial == scopes(changed, precision=precision, code_hash="v1")
    changed.assumptions.root_capture_mm = 12
    other = scopes(changed, precision=precision, code_hash="v1")
    assert other["assumptions"] != initial["assumptions"]
    assert other["geometry"] == initial["geometry"]
    precision.altitude_error_m = 0.2
    assert scopes(s, precision=precision, code_hash="v1")["requirements"] != initial["requirements"]


def test_no_fabricated_geometry_or_invalid_volume_enters_record():
    with pytest.raises(KeyError):
        compile_record(spec(), {})
    with pytest.raises(ValueError):
        compile_record(spec(), {"fin": {"volume_mm3": -1}, "nose": {"volume_mm3": 2}})
