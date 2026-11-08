import json
from pathlib import Path

import numpy as np
import pytest

from rocketwright.agent.design_projects import DesignSpec
from scripts.search_fixed_mission import candidate, encode, expanded, loss


def test_fixed_mission_contract_and_design_roundtrip():
    data = json.loads(
        Path("scenarios/adaptive_design/expanded-confirmation-wide-new.json").read_text(
            encoding="utf-8"
        )
    )["spec"]
    anchor = DesignSpec.model_validate(data)
    unit = encode(anchor)
    changed = candidate(anchor, unit)
    assert changed.geometry == anchor.geometry
    assert changed.material == anchor.material
    assert changed.env == anchor.env
    assert changed.other_dry_mass_g == anchor.other_dry_mass_g
    assert changed.assumptions == anchor.assumptions
    assert changed.design.initial_gauge_pressure_pa == 400000
    assert changed.design.payload_mass_kg == changed.requirement.payload_mass_kg == 0.04
    assert changed.requirement.target_altitude_m == 20
    assert anchor.requirement.target_altitude_m == 30
    full = expanded(unit, anchor)[0]
    assert full[12] == 1
    assert full[13] == (40 - 10) / 190
    with pytest.raises(ValueError):
        expanded([np.nan] * 12, anchor)


def test_reserves_do_not_accept_low_height_static_or_stiffness():
    y = [[23, 1.2, 0.10], [21.9, 1.2, 0.10], [23, 1.0, 0.10], [23, 1.2, 0.21]]
    values = loss(y)
    assert values[0] < 0
    assert np.all(values[1:] > 1)
    assert loss([[24, 1.2, 0.10]])[0] < values[0]
    with pytest.raises(ValueError):
        loss([[np.nan, 1.2, 0.01]])
