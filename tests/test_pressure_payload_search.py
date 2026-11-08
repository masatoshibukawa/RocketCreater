import numpy as np
import pytest

from scripts import payload_search as base
from scripts import pressure_payload_search as pressure
from tests.test_payload_search import anchor


def test_pressure_changes_only_pressure_and_retains_projected_control_starts():
    a = anchor()
    points = pressure.initial(16, 41821, a)
    np.testing.assert_array_equal(points[:, :13], base.initial(16, 41821, a))
    assert np.all(points[:8, 13] == 1)
    u = points[0].copy()
    u[13] = 0
    low = pressure.candidate(a, u)
    u[13] = 1
    high = pressure.candidate(a, u)
    assert low.design.initial_gauge_pressure_pa == 50000
    assert high.design.initial_gauge_pressure_pa == 400000
    assert low.design.payload_mass_kg == high.design.payload_mass_kg
    assert low.geometry == high.geometry and low.env == high.env
    assert low.requirement == high.requirement
    with pytest.raises(ValueError):
        pressure.candidate(a, np.r_[u[:13], 1.01])


def test_policy_pressure_and_payload_controls_are_independent_and_bounded():
    u = np.full((4, 14), 0.5)
    action = np.zeros((4, 13))
    action[:, -1] = 1
    moved = pressure.move(u, action, np.ones(4))
    np.testing.assert_allclose(moved[:, :13], u[:, :13])
    assert np.all(moved[:, 13] > 0.5)
    obs = pressure.observation(
        moved, np.arange(4) % 3, np.tile([30, 1.2, 0.04], (4, 1)), np.ones(4)
    )
    assert obs.shape == (4, 23) and np.all(obs[:, -2] == moved[:, 13]) and np.all(obs[:, -1] == 1)


def test_pressure_vector_environment_actions_and_terminal_observation():
    pytest.importorskip("stable_baselines3")
    from scripts.pressure_payload_rl import PayloadEnvironment

    class Fake:
        anchors = [anchor()] * 3

        def predict(self, points, ids):
            # More pressure improves an otherwise infeasible predicted height.
            return np.column_stack(
                (10 + 10 * points[:, 13], np.full(len(points), 2), np.full(len(points), 0.01))
            )

    env = PayloadEnvironment([], count=4, horizon=1, seed=819, predictor=Fake())
    env.reset()
    env.units[:, 13] = 0.5
    env.values = Fake().predict(env.units, env.ids)
    env.utilities = -np.arcsinh(pressure.loss(env.values, pressure.payload(env.units)))
    actions = np.zeros((4, 13), np.float32)
    actions[:, -1] = 0.1
    env.step_async(actions)
    obs, rewards, done, infos = env.step_wait()
    assert obs.shape == (4, 23) and done.all() and np.all(rewards > 0)
    assert all(
        i["terminal_observation"].shape == (23,) and i["terminal_observation"][-1] == 0
        for i in infos
    )
