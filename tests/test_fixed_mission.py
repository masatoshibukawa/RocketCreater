import copy
import json
from pathlib import Path

from scripts.reevaluate_fixed_mission import mission_spec, violation
from scripts.verify_payload_change import check_payload_only


def test_fixed_mission_preserves_shape_material_and_environment():
    data = json.loads(
        Path("scenarios/adaptive_design/expanded-confirmation-wide-new.json").read_text(
            encoding="utf-8"
        )
    )["spec"]
    saved = copy.deepcopy(data)
    updated = mission_spec(data).model_dump(mode="json")
    check_payload_only(data, updated)
    assert updated["design"]["initial_gauge_pressure_pa"] == 400000
    assert updated["design"]["payload_mass_kg"] == 0.04
    assert updated["requirement"]["payload_mass_kg"] == 0.04
    assert updated["requirement"]["target_altitude_m"] == 20
    assert data == saved
    data["design"]["initial_gauge_pressure_pa"] = 300000
    assert mission_spec(data).model_dump(mode="json") == updated


def test_height_target_does_not_relax_static_or_beam_constraints():
    metrics = dict(scenario_height_m=[20, 23], static_margin_cal=1.12, conservative_beam_ratio=0.05)
    assert violation(metrics) == 0
    assert violation(dict(metrics, scenario_height_m=[19, 23])) > 0
    assert violation(dict(metrics, static_margin_cal=1.0)) > 0
    assert violation(dict(metrics, conservative_beam_ratio=0.06)) > 0
