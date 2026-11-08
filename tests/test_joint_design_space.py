import numpy as np
import pytest

from rocketwright.analysis.design_space import AXES, assert_contract, decode, samples
from rocketwright.analysis.tradeoff import reconcile_payload
from tests.test_analysis_record import spec


def test_joint_space_preserves_mission_and_changes_coupled_variables():
    base, _ = reconcile_payload(spec())
    before = base.model_dump()
    for u in np.vstack([np.zeros(len(AXES)), np.ones(len(AXES)), samples(64, 17)]):
        candidate = decode(base, u)
        assert candidate.requirement == base.requirement
        assert candidate.design.payload_mass_kg == 0.06
        assert (
            candidate.geometry.fin_tip_mm + candidate.geometry.fin_sweep_mm
            <= candidate.geometry.fin_root_mm + 1e-9
        )
        assert candidate.measured_printed_mass_g is None
        assert candidate.design.geometry.model_dump() == candidate.geometry.model_dump()
    assert base.model_dump() == before
    candidate.design = candidate.design.model_copy(update={"payload_mass_kg": 0.03})
    with pytest.raises(ValueError, match="mission"):
        assert_contract(candidate, base)


def test_local_refinement_stays_in_fixed_bounds_and_is_repeatable():
    center = np.linspace(0, 1, len(AXES))
    points = samples(32, 42, center=center, radius=0.1)
    np.testing.assert_array_equal(points, samples(32, 42, center=center, radius=0.1))
    assert np.all((points >= 0) & (points <= 1))
    assert np.max(abs(points - center)) <= 0.1
