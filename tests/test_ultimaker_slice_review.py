"""Reject machine/profile mismatches and missing deposition before lab handoff."""

import json
import zipfile

import pytest

from scripts.check_ultimaker_slice import inspect

GCODE = """;FLAVOR:Griffin
;TARGET_MACHINE.NAME:Ultimaker S5
;GENERATOR.VERSION:5.12.0
;EXTRUDER_TRAIN.0.NOZZLE.NAME:AA 0.4
;EXTRUDER_TRAIN.0.NOZZLE.DIAMETER:0.4
;EXTRUDER_TRAIN.0.MATERIAL.GUID:test-material
;EXTRUDER_TRAIN.0.MATERIAL.VOLUME_USED:1000
;PRINT.TIME:60
;LAYER_COUNT:3
M82
G92 E0
G0 X100 Y100 Z0.2
;LAYER:0
;TYPE:WALL-OUTER
G1 X110 E1
;LAYER:1
G0 Z0.4
G1 X100 E2
;LAYER:2
G0 Z0.6
G1 X110 E3
"""
MATERIAL = """<fdmmaterial><brand>Ultimaker</brand><material>Tough PLA</material>
<color>Black</color><GUID>test-material</GUID><diameter>2.85</diameter>
<density>1.24</density></fdmmaterial>"""
SETTINGS = {
    "wall_line_count": 3,
    "infill_sparse_density": 20,
    "layer_height": 0.2,
    "adhesion_type": "brim",
    "brim_width": 7,
    "brim_location": "outside",
}


def package(tmp_path, gcode=GCODE, material=MATERIAL):
    path = tmp_path / "trial.ufp"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("/3D/model.gcode", gcode)
        archive.writestr("/Materials/ultimaker_tough_pla_black.xml.fdm_material", material)
        archive.writestr(
            "/Cura/slicemetadata.json", json.dumps({"extruder_0": {"all_settings": SETTINGS}})
        )
    return path


def test_native_material_units_and_unstarted_state(tmp_path):
    report = inspect(package(tmp_path))
    assert report["estimated_mass_g"] == 1.24
    assert report["estimated_filament_m"] == 0.157
    assert report["model_layers"] == 3
    assert report["physical_configuration_verified"] is False
    assert report["print_started"] is False


def test_one_empty_top_layer_is_explicit_not_an_internal_gap(tmp_path):
    report = inspect(package(tmp_path, GCODE.replace("LAYER_COUNT:3", "LAYER_COUNT:4")))
    assert report["empty_trailing_layers"] == [3]
    assert report["missing_model_layers"] == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Ultimaker S5", "Ultimaker 3"),
        ("AA 0.4", "AA 0.8"),
        ("MATERIAL.GUID:test-material", "MATERIAL.GUID:other-material"),
        (";LAYER:1", ";LAYER:0"),
        ("LAYER_COUNT:3", "LAYER_COUNT:5"),
        ("LAYER_COUNT:3", "LAYER_COUNT:2"),
        (";LAYER:2", "T1\n;LAYER:2"),
        ("TYPE:WALL-OUTER", "TYPE:SUPPORT"),
        ("X110", "X340"),
        ("M82", "G91\nM82"),
    ],
)
def test_rejects_incompatible_or_incomplete_slice(tmp_path, old, new):
    with pytest.raises(ValueError):
        inspect(package(tmp_path, GCODE.replace(old, new)))


def test_rejects_material_content_despite_expected_filename(tmp_path):
    with pytest.raises(ValueError, match="matching Black Tough PLA"):
        inspect(package(tmp_path, material=MATERIAL.replace("2.85", "1.75")))
