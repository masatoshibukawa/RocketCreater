import math

import pytest

from rocketwright.geometry import airframe
from rocketwright.manufacturing import PrintGeometry, PrintRequest, parameters
from rocketwright.physics.water import _Dynamics
from rocketwright.schema import BottleDesign, Env


def bottle():
    return BottleDesign(bottle_volume_m3=0.002, water_fill_frac=0.3,
                        initial_gauge_pressure_pa=350000, nozzle_diameter_m=0.009,
                        dry_mass_kg=0.15, has_parachute=True, parachute_diameter_m=0.6)


def test_measured_dimensions_drive_physics_mesh_and_print_parameters():
    geometry = PrintGeometry(body_diameter_mm=110, body_height_mm=315, nose_length_mm=95,
                             fin_root_mm=100, fin_tip_mm=36, fin_span_mm=50,
                             fin_sweep_mm=14, fin_count=3, fin_tail_inset_mm=100,
                             dimensions_measured=True)
    design = bottle().model_copy(update={"geometry": geometry})
    frame = airframe(design)
    config = parameters(PrintRequest(design=design))
    assert frame.params["fin_count"] == config["fin"]["count"] == 3
    assert frame.params["body_diameter_m"] == pytest.approx(0.110)
    assert frame.params["fin_root_chord_m"] == pytest.approx(0.100)
    assert frame.params["fin_sweep_m"] == pytest.approx(0.014)
    assert frame.params["length_m"] == pytest.approx(geometry.overall_mm / 1000)
    assert _Dynamics(design, Env()).area_m2 == pytest.approx(math.pi * 0.055**2)
    assert config["fin"]["mount_tail_z"] == 100
    assert config["fin"]["thickness"] == 2.4


def test_printing_cannot_override_analysed_dimensions():
    original = PrintGeometry.from_design(bottle())
    changed = original.model_copy(update={"body_diameter_mm": 100})
    with pytest.raises(ValueError, match="differ"):
        parameters(PrintRequest(design=bottle().model_copy(update={"geometry": original}),
                                geometry=changed))


def test_default_remains_unmeasured_and_no_fin_design_has_no_fin_mesh():
    original = bottle()
    geometry = PrintGeometry.from_design(original)
    assert not geometry.dimensions_measured
    assert airframe(original).params["fin_count"] == 4
    design = original.model_copy(update={"geometry": geometry, "has_fins": False})
    assert airframe(design).shells == 1
