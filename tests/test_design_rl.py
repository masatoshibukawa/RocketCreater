import numpy as np
import pytest

pytest.importorskip("gymnasium")

from scripts.design_rl import CATEGORIES, CATEGORY_AXIS, DesignEnvironment, move, observation


def test_continuous_action_preserves_material_and_bounds():
    unit = np.full(12, 0.5)
    unit[CATEGORY_AXIS] = 0.5 / CATEGORIES
    changed = move(unit, np.full(11, 100.0))
    assert np.all((changed >= 0) & (changed <= 1))
    assert changed[CATEGORY_AXIS] == unit[CATEGORY_AXIS]
    np.testing.assert_allclose(changed[:11], 0.65)
    with pytest.raises(ValueError):
        move(unit, np.full(11, np.nan))


def test_observation_has_categories_and_remaining_horizon():
    unit = np.full(12, 0.5)
    metrics = dict(scenario_height_m=[15.0], static_margin_cal=1.2)
    full = observation(unit, 2, metrics, 1)
    end = observation(unit, 2, metrics, 0)
    assert full.shape == (20,) and full.dtype == np.float32
    assert np.array_equal(full[:-1], end[:-1])
    assert full[-1] == 1 and end[-1] == 0


def test_finite_horizon_and_round_trip_cannot_generate_reward(monkeypatch):
    from tests.test_analysis_record import spec

    monkeypatch.setattr(
        DesignEnvironment,
        "metrics",
        lambda self: dict(
            scenario_height_m=[10 + float(self.unit[0])],
            static_margin_cal=1.2,
        ),
    )
    models = [{"anchor": spec().model_dump(mode="json")} for _ in range(3)]
    env = DesignEnvironment(models, horizon=2, record=True)
    first, info = env.reset(seed=18)
    assert info["fidelity"] == "surrogate" and not info["acceptance"]
    action = np.zeros(11)
    action[0] = 0.01
    _, reward1, ended1, _, _ = env.step(action)
    last, reward2, ended2, truncated, _ = env.step(-action)
    assert not ended1 and ended2 and not truncated and last[-1] == 0
    assert np.isclose(reward1 + reward2, -0.002)
    assert len(env.transitions) == 2
    with pytest.raises(RuntimeError, match="Reset"):
        env.step(action)
    repeated, _ = env.reset(seed=18)
    np.testing.assert_array_equal(first, repeated)
