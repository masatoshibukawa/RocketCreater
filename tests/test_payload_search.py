import copy

import numpy as np
import pytest

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.worker import read
from scripts.payload_search import candidate, expanded, initial, loss, move, observation


def anchor():
    return DesignSpec.model_validate(read("scenarios/adaptive_design/payload50-spec.json"))


def test_payload_is_an_independent_axis_and_keeps_context_and_mission_consistent():
    base = anchor()
    u = initial(16, 821, base)[0]
    u[12] = 0
    light = candidate(base, u)
    u[12] = 1
    heavy = candidate(base, u)
    assert light.design.payload_mass_kg == light.requirement.payload_mass_kg == 0.01
    assert heavy.design.payload_mass_kg == heavy.requirement.payload_mass_kg == 0.2
    assert light.geometry == heavy.geometry
    assert light.env == heavy.env == base.env
    assert light.design.initial_gauge_pressure_pa == base.design.initial_gauge_pressure_pa
    assert heavy.requirement.target_altitude_m == 30


def test_payload_reduction_does_not_win_after_height_and_constraints_are_met():
    y = [[30, 1.12, 0.05], [50, 2, 0.01]]
    assert loss(y, [200, 10])[0] < loss(y, [200, 10])[1]
    assert loss([[29.99, 2, 0.01]], 200)[0] > loss([[30, 1.12, 0.05]], 10)[0]
    assert loss([[35, 1.1, 0.05]], 200)[0] > 0
    assert loss([[35, 1.2, 0.06]], 200)[0] > 0
    with pytest.raises(ValueError):
        loss(y, [0, 100])


def test_policy_action_can_move_payload_but_preserves_material_and_bounds():
    u = np.full((4, 13), 0.5)
    original = u.copy()
    a = np.zeros((4, 12))
    a[:, -1] = 1
    after = move(u, a, np.ones(4))
    assert np.array_equal(u, original)
    assert np.all(after[:, 12] > u[:, 12])
    np.testing.assert_allclose(after[:, :11], u[:, :11])
    np.testing.assert_allclose(after[:, 11], u[:, 11])
    obs = observation(after, np.array([0, 1, 2, 0]), np.tile([25, 1.2, 0.1], (4, 1)), np.ones(4))
    assert obs.shape == (4, 22) and obs.dtype == np.float32
    with pytest.raises(ValueError):
        move(u, np.full((4, 12), np.nan), np.ones(4))
    with pytest.raises(ValueError):
        expanded(np.full(13, 1.1), anchor())


def test_batched_torch_ensemble_agrees_with_portable_predictions():
    torch = pytest.importorskip("torch")
    from scripts.expanded_surrogate import inverse
    from scripts.gpu_payload_surrogate import network
    from scripts.search_surrogate import predict

    rng = np.random.default_rng(315)
    members = []
    for _ in range(3):
        members.append(
            dict(
                categories={},
                x_mean=[0.5] * 4,
                x_scale=[0.3] * 4,
                y_mean=[1.0, 0.5, 0.1],
                y_scale=[0.3] * 3,
                weights=[rng.normal(0, 0.1, (4, 8)).tolist(), rng.normal(0, 0.1, (8, 3)).tolist()],
                biases=[[0] * 8, [0] * 3],
            )
        )
    saved = copy.deepcopy(members)
    x = rng.random((16, 4))
    model = network({"members": members}, "cpu")
    with torch.no_grad():
        actual = model.physical(torch.tensor(x, dtype=torch.float32)).numpy()
    expected = np.mean([inverse(predict(m, x)) for m in members], axis=0)
    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-6)
    assert members == saved
