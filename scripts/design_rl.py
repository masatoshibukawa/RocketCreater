"""Sequential continuous design changes for PPO/SAC; never an acceptance controller."""

import gymnasium as gym
import numpy as np

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.analysis.design_space import AXES, decode
from scripts.mixed_genetic import canonical
from scripts.search_surrogate import predict

CATEGORY_AXIS = list(AXES).index("material_index")
CONTINUOUS = [i for i in range(len(AXES)) if i != CATEGORY_AXIS]
CATEGORIES = int(AXES["material_index"][1])


def loss(metrics):
    return 2000 * max(0, 1.12 - metrics["static_margin_cal"]) - metrics["scenario_height_m"][0]


def observation(unit, anchor_id, metrics, remaining):
    """No undocumented history: geometry, categories, measured/predicted state and horizon."""
    return np.r_[
        np.asarray(unit)[CONTINUOUS],
        np.eye(CATEGORIES)[min(int(unit[CATEGORY_AXIS] * CATEGORIES), CATEGORIES - 1)],
        np.eye(3)[anchor_id],
        metrics["scenario_height_m"][0] / 30,
        metrics["static_margin_cal"] / 3,
        remaining,
    ].astype(np.float32)


def move(unit, action, step_scale=0.15):
    action = np.asarray(action, float)
    if action.shape != (len(CONTINUOUS),) or not np.isfinite(action).all():
        raise ValueError("Eleven finite continuous actions are required")
    result = np.asarray(unit, float).copy()
    result[CONTINUOUS] = np.clip(result[CONTINUOUS] + step_scale * np.clip(action, -1, 1), 0, 1)
    return canonical(result, {CATEGORY_AXIS: CATEGORIES})


class DesignEnvironment(gym.Env):
    """Frozen-surrogate training only. Real simulation evaluation is separate.

    The material is sampled by the host at reset and fixed for the episode.
    Reward is the increment in -asinh(search_loss/30), minus a small step cost.
    With gamma=1 this telescopes to final improvement; revisiting a design cannot
    manufacture positive reward. The finite horizon is part of the observation.
    """

    metadata = {"render_modes": []}

    def __init__(self, models, *, horizon=10, record=False):
        super().__init__()
        if len(models) != 3 or not isinstance(horizon, int) or horizon < 1:
            raise ValueError("Three compatible surrogate anchors and positive horizon required")
        self.models = models
        self.anchors = [DesignSpec.model_validate(m["anchor"]) for m in models]
        self.horizon, self.record = horizon, record
        self.action_space = gym.spaces.Box(-1, 1, (len(CONTINUOUS),), dtype=np.float32)
        size = len(CONTINUOUS) + CATEGORIES + 3 + 3
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (size,), dtype=np.float32)
        self.transitions = []
        self.done = True

    def metrics(self):
        decode(self.anchors[self.anchor_id], self.unit)
        y = predict(self.models[self.anchor_id], self.unit[None])[0]
        if not np.isfinite(y).all():
            raise ValueError("Nonfinite surrogate prediction")
        return dict(scenario_height_m=[float(y[0])], static_margin_cal=float(y[1]))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.anchor_id = int(self.np_random.integers(3))
        for _ in range(100):
            self.unit = canonical(self.np_random.random(len(AXES)), {CATEGORY_AXIS: CATEGORIES})
            try:
                metrics = self.metrics()
                break
            except ValueError:
                continue
        else:
            raise ValueError("No valid reset design")
        self.steps, self.done = 0, False
        self.utility = -float(np.arcsinh(loss(metrics) / 30))
        self.obs = observation(self.unit, self.anchor_id, metrics, 1.0)
        return self.obs.copy(), {"fidelity": "surrogate", "acceptance": False}

    def step(self, action):
        if self.done:
            raise RuntimeError("Reset after the finite episode ends")
        before = self.obs.copy()
        self.unit = move(self.unit, action)
        self.steps += 1
        invalid = False
        try:
            metrics = self.metrics()
            utility = -float(np.arcsinh(loss(metrics) / 30))
            reward = utility - self.utility - 0.001
            self.utility = utility
            self.obs = observation(
                self.unit, self.anchor_id, metrics, (self.horizon - self.steps) / self.horizon
            )
        except ValueError:
            invalid, reward = True, -10.0
        # The horizon is the end of this design task, not an unobserved time-limit truncation.
        self.done = invalid or self.steps >= self.horizon
        if self.record:
            self.transitions.append(
                (
                    before,
                    np.asarray(action, np.float32).copy(),
                    float(reward),
                    self.obs.copy(),
                    self.done,
                    invalid,
                )
            )
        return (
            self.obs.copy(),
            float(reward),
            self.done,
            False,
            dict(
                fidelity="surrogate",
                acceptance=False,
                invalid_design=invalid,
            ),
        )

    def save_transitions(self, path):
        rows = self.transitions
        np.savez_compressed(
            path,
            observations=np.array([r[0] for r in rows]),
            actions=np.array([r[1] for r in rows]),
            rewards=np.array([r[2] for r in rows]),
            next_observations=np.array([r[3] for r in rows]),
            terminated=np.array([r[4] for r in rows]),
            invalid=np.array([r[5] for r in rows]),
        )
