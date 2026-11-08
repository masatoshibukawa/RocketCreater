import copy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.verify_payload_change import check_payload_only, payload_spec, rebase_case


def example():
    return json.loads(
        Path("scenarios/adaptive_design/expanded-confirmation-wide-new.json").read_text(
            encoding="utf-8"
        )
    )["spec"]


def test_payload_and_requirement_change_together_without_mutating_parent():
    base = example()
    saved = copy.deepcopy(base)
    changed = payload_spec(base, 50, 30)
    check_payload_only(base, changed)
    assert changed["design"]["payload_mass_kg"] == changed["requirement"]["payload_mass_kg"] == 0.05
    assert changed["requirement"]["target_altitude_m"] == 30
    assert base == saved


@pytest.mark.parametrize("field,value", [("material", "Prusament PETG"), ("other_dry_mass_g", 100)])
def test_reuse_rejects_additional_design_changes(field, value):
    base = example()
    changed = payload_spec(base, 50, 30)
    changed[field] = value
    with pytest.raises(ValueError):
        check_payload_only(base, changed)


def test_reuse_rejects_geometry_pressure_and_mismatched_mission():
    base = example()
    for section, field, value in [
        ("geometry", "fin_span_mm", 100),
        ("design", "initial_gauge_pressure_pa", 300000),
        ("requirement", "payload_mass_kg", 0.06),
    ]:
        changed = payload_spec(base, 50, 30)
        changed[section][field] = value
        with pytest.raises(ValueError):
            check_payload_only(base, changed)


def test_moment_translation_matches_cross_product_and_preserves_raw_simulation():
    values = dict(Cx=1.2, Cy=0.7, Cz=-0.3, Croll=0.1, Cpitch_y=0.2, Cm_z=0.4)
    case = dict(
        cg_mm=180,
        dimensions_mm={"body_diameter": 90},
        mean=values,
        split_window_difference={k: v / 10 for k, v in values.items()},
    )
    saved = copy.deepcopy(case)
    rebased = rebase_case(case, 210)
    for key in ("mean", "split_window_difference"):
        row = case[key]
        expected = np.array([row[n] for n in ("Croll", "Cpitch_y", "Cm_z")]) + np.cross(
            [(180 - 210) / 90, 0, 0], [row[n] for n in ("Cx", "Cy", "Cz")]
        )
        np.testing.assert_allclose(
            [rebased[key][n] for n in ("Croll", "Cpitch_y", "Cm_z")], expected
        )
    assert case == saved and rebased["cg_mm"] == 180
    restored = rebase_case(rebased, 180)
    assert restored["mean"] == pytest.approx(values)
