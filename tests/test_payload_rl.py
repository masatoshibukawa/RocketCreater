import numpy as np
import pytest

pytest.importorskip("stable_baselines3")
from scripts.payload_rl import PayloadEnvironment
from tests.test_payload_search import anchor


class FakePredictor:
    anchors = [anchor()] * 3

    def predict(self, points, ids):
        return np.tile([40.0, 2.0, 0.01], (len(points), 1))


def test_vector_policy_terminal_state_and_rejected_moves_preserve_incumbent():
    env = PayloadEnvironment([], count=4, horizon=2, seed=2, predictor=FakePredictor())
    env.seed(821)
    initial = env.reset()
    env.units[:, 12] = 0.2
    env.values[:] = FakePredictor().predict(env.units, env.ids)
    from scripts.payload_search import loss, payload

    env.utilities = -np.arcsinh(loss(env.values, payload(env.units)))
    action = np.zeros((4, 12), dtype=np.float32)
    action[:, -1] = 0.1
    env.step_async(action)
    first, reward, done, info = env.step_wait()
    assert not done.any() and np.all(reward > 0)
    assert all(i["incumbent_improved"] for i in info)
    retained = env.units.copy()
    env.step_async(-action)
    final, reward, done, info = env.step_wait()
    assert done.all() and np.all(reward <= 0)
    assert all(not i["incumbent_improved"] for i in info)
    np.testing.assert_allclose(env.transitions[-1][3][:, :12], first[:, :12])
    assert env.transitions[-1][3][0, -1] == 0 and final[0, -1] == 1
    assert all(i["terminal_observation"][-1] == 0 and not i["TimeLimit.truncated"] for i in info)
    assert not np.array_equal(env.units, retained)
    env.seed(821)
    np.testing.assert_array_equal(env.reset(), initial)
