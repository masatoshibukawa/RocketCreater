import copy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.search_drag_reserve import drag_spec
from scripts.search_fixed_mission import candidate, encode


def test_drag_probe_keeps_mission_and_does_not_modify_parent():
    original = json.loads(
        Path("scenarios/adaptive_design/expanded-confirmation-wide-new.json").read_text(
            encoding="utf-8"
        )
    )["spec"]
    before = copy.deepcopy(original)
    anchor = drag_spec(original, 1.4)
    proposal = candidate(anchor, encode(anchor))
    assert proposal.design.axial_drag_coefficient == 1.4
    assert proposal.design.initial_gauge_pressure_pa == 400000
    assert proposal.design.payload_mass_kg == proposal.requirement.payload_mass_kg == 0.04
    assert proposal.requirement.target_altitude_m == 20
    assert proposal.env == anchor.env
    assert proposal.assumptions == anchor.assumptions
    assert proposal.other_dry_mass_g == anchor.other_dry_mass_g
    assert original == before
    for cd in (np.nan, np.inf, -1, 0, 6):
        with pytest.raises(ValueError):
            drag_spec(original, cd)
