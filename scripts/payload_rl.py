"""Batched CUDA surrogate environments for finite-horizon payload design policies."""

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from scripts.gpu_payload_surrogate import Predictor
from scripts.mixed_genetic import canonical
from scripts.payload_search import CATEGORIES, candidate, loss, move, observation, payload


class PayloadEnvironment(VecEnv):
    def __init__(self, bundles, *, count=64, horizon=15, seed=91731, record=True, predictor=None):
        self.predictor = predictor or Predictor(bundles)
        self.anchors = self.predictor.anchors
        self.horizon, self.rng, self.record = horizon, np.random.default_rng(seed), record
        self.units = np.zeros((count, 13))
        self.ids = np.zeros(count, int)
        self.steps = np.zeros(count, int)
        self.values = np.zeros((count, 3))
        self.utilities = np.zeros(count)
        self.transitions = []
        self.actions = None
        self.render_mode = None
        super().__init__(
            count,
            gym.spaces.Box(-np.inf, np.inf, (22,), dtype=np.float32),
            gym.spaces.Box(-1, 1, (12,), dtype=np.float32),
        )

    def _reset(self, indices):
        for i in indices:
            self.ids[i] = self.rng.integers(3)
            for _ in range(100):
                u = canonical(self.rng.random(13), CATEGORIES)
                try:
                    candidate(self.anchors[self.ids[i]], u)
                except ValueError:
                    continue
                self.units[i] = u
                break
            else:
                raise ValueError("No valid random reset")
        self.steps[indices] = 0
        self.values[indices] = self.predictor.predict(self.units[indices], self.ids[indices])
        self.utilities[indices] = -np.arcsinh(
            loss(self.values[indices], payload(self.units[indices]))
        )

    def _observe(self):
        return observation(self.units, self.ids, self.values, 1 - self.steps / self.horizon)

    def reset(self):
        if self._seeds[0] is not None:
            self.rng = np.random.default_rng(self._seeds[0])
            self._reset_seeds()
        self._reset(np.arange(self.num_envs))
        return self._observe()

    def step_async(self, actions):
        self.actions = np.asarray(actions).copy()

    def step_wait(self):
        if self.actions is None:
            raise RuntimeError("step_async must precede step_wait")
        before = self._observe()
        proposed = move(self.units, self.actions, 1 - self.steps / self.horizon)
        valid = np.ones(self.num_envs, bool)
        for i in range(self.num_envs):
            try:
                candidate(self.anchors[self.ids[i]], proposed[i])
            except ValueError:
                valid[i] = False
        predicted = self.predictor.predict(proposed, self.ids)
        utility = -np.arcsinh(loss(predicted, payload(proposed)))
        accepted = valid & (utility > self.utilities)
        reward = np.where(valid, -0.001 + 0.1 * np.clip(utility - self.utilities, -1, 0), -1.0)
        reward[accepted] = -0.001 + 5 * (utility[accepted] - self.utilities[accepted])
        self.units[accepted], self.values[accepted] = proposed[accepted], predicted[accepted]
        self.utilities[accepted] = utility[accepted]
        self.steps += 1
        obs = self._observe()
        done = self.steps >= self.horizon
        infos = [
            dict(
                fidelity="surrogate",
                acceptance=False,
                invalid_design=not valid[i],
                incumbent_improved=bool(accepted[i]),
                **{"TimeLimit.truncated": False},
            )
            for i in range(self.num_envs)
        ]
        if self.record:
            self.transitions.append(
                (
                    before.copy(),
                    self.actions.copy(),
                    reward.copy(),
                    obs.copy(),
                    done.copy(),
                    ~valid,
                    accepted.copy(),
                )
            )
        for i in np.flatnonzero(done):
            infos[i]["terminal_observation"] = obs[i].copy()
        if done.any():
            self._reset(np.flatnonzero(done))
            obs = self._observe()
        self.actions = None
        return obs, reward.astype(np.float32), done, infos

    def save(self, path):
        names = (
            "observations",
            "actions",
            "rewards",
            "next_observations",
            "terminated",
            "invalid",
            "accepted",
        )
        np.savez_compressed(
            path,
            **{
                name: np.concatenate([r[i] for r in self.transitions])
                for i, name in enumerate(names)
            },
        )

    def close(self):
        pass

    def get_attr(self, attr_name, indices=None):
        return [getattr(self, attr_name) for _ in self._get_indices(indices)]

    def set_attr(self, attr_name, value, indices=None):
        setattr(self, attr_name, value)

    def env_method(self, method_name, *args, indices=None, **kwargs):
        return [getattr(self, method_name)(*args, **kwargs) for _ in self._get_indices(indices)]

    def env_is_wrapped(self, wrapper_class, indices=None):
        return [False for _ in self._get_indices(indices)]
