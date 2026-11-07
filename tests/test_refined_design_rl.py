import numpy as np
import pytest

pytest.importorskip("gymnasium")

from scripts.refined_design_rl import RefinedDesignEnvironment, step_size


def environment(monkeypatch, **kwargs):
    from tests.test_analysis_record import spec

    monkeypatch.setattr(
        RefinedDesignEnvironment,
        "metrics",
        lambda self: dict(scenario_height_m=[10 + self.unit[0]], static_margin_cal=1.2),
    )
    models = [{"anchor": spec().model_dump(mode="json")} for _ in range(3)]
    return RefinedDesignEnvironment(models, **kwargs)


def test_worse_moves_preserve_incumbent_and_cannot_farm_reward(monkeypatch):
    env = environment(monkeypatch, horizon=3)
    env.reset(seed=18)
    action = np.zeros(11)
    action[0] = 0.1
    _, reward, done, _, info = env.step(action)
    assert reward > 0 and not done and info["incumbent_improved"]
    incumbent, value = env.unit.copy(), env.utility
    for proposed in (-action, np.zeros(11)):
        obs, reward, done, _, info = env.step(proposed)
        assert reward < 0 and not info["incumbent_improved"]
        np.testing.assert_array_equal(env.unit, incumbent)
        assert env.utility == value
    assert done and obs[-1] == 0


def test_invalid_proposal_spends_step_without_losing_incumbent(monkeypatch):
    env = environment(monkeypatch, horizon=2, record=True)
    first, _ = env.reset(seed=18)
    incumbent = env.unit.copy()

    def invalid(self):
        raise ValueError("Invalid geometry")

    monkeypatch.setattr(RefinedDesignEnvironment, "metrics", invalid)
    obs, reward, done, truncated, info = env.step(np.ones(11))
    assert info["invalid_design"] and reward == -1 and not done and not truncated
    np.testing.assert_array_equal(env.unit, incumbent)
    np.testing.assert_array_equal(obs[:-1], first[:-1])
    assert obs[-1] == 0.5 and env.steps == 1 and len(env.transitions) == 1
    assert env.step(np.ones(11))[2]


def test_curriculum_reset_is_repeatable_and_material_stays_discrete(monkeypatch):
    env = environment(monkeypatch)
    for model in env.models:
        model["curriculum_units"] = [np.full(12, 0.5).tolist()]
    for seed in range(12):
        first, _ = env.reset(seed=seed)
        again, _ = env.reset(seed=seed)
        np.testing.assert_array_equal(first, again)
        assert np.all((env.unit >= 0) & (env.unit <= 1))
        assert env.unit[11] in (1 / 6, 0.5, 5 / 6)
    assert step_size(1) == 0.25
    assert step_size(0) == 0.03
    assert step_size(1) > step_size(0.5) > step_size(0)
