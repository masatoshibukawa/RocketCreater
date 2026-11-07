"""Incumbent-preserving RL search with coarse-to-fine moves and training-only curriculum."""

import numpy as np

from scripts.design_rl import (
    CATEGORIES,
    CATEGORY_AXIS,
    CONTINUOUS,
    DesignEnvironment,
    loss,
    move,
    observation,
)
from scripts.mixed_genetic import canonical


def step_size(remaining):
    return 0.03 + 0.22 * float(np.clip(remaining, 0, 1))


class RefinedDesignEnvironment(DesignEnvironment):
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed, options=options)
        pool = self.models[self.anchor_id].get("curriculum_units", [])
        if pool and self.np_random.random() < 0.5:
            original = self.unit.copy()
            for _ in range(20):
                unit = np.array(pool[self.np_random.integers(len(pool))], float)
                unit[CONTINUOUS] = np.clip(
                    unit[CONTINUOUS] + self.np_random.normal(0, 0.04, len(CONTINUOUS)), 0, 1
                )
                self.unit = canonical(unit, {CATEGORY_AXIS: CATEGORIES})
                try:
                    self.metrics()
                    break
                except ValueError:
                    self.unit = original
        self.current = self.metrics()
        self.utility = -float(np.arcsinh(loss(self.current) / 30))
        self.obs = observation(self.unit, self.anchor_id, self.current, 1.0)
        return self.obs.copy(), dict(fidelity="surrogate", acceptance=False)

    def step(self, action):
        if self.done:
            raise RuntimeError("Reset after the finite episode ends")
        before, previous = self.obs.copy(), self.unit.copy()
        self.unit = move(self.unit, action, step_size((self.horizon - self.steps) / self.horizon))
        self.steps += 1
        invalid, accepted, reward = False, False, -0.001
        try:
            candidate = self.metrics()
            value = -float(np.arcsinh(loss(candidate) / 30))
            if value > self.utility:
                reward += 5 * (value - self.utility)
                self.utility, self.current, accepted = value, candidate, True
            else:
                reward += 0.1 * max(-1, value - self.utility)
        except ValueError:
            invalid, reward = True, -1.0
        if not accepted:
            self.unit = previous
        self.obs = observation(
            self.unit, self.anchor_id, self.current, (self.horizon - self.steps) / self.horizon
        )
        self.done = self.steps >= self.horizon
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
                incumbent_improved=accepted,
            ),
        )
