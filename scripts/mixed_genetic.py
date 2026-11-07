"""Small bounded mixed-variable GA for candidate generation, never acceptance."""

from types import SimpleNamespace

import numpy as np


def canonical(points, categories):
    """Represent each unordered category by its bin center, not an interpolated material."""
    result = np.asarray(points, float).copy()
    if result.ndim not in (1, 2) or not np.isfinite(result).all():
        raise ValueError("Finite unit-cube points required")
    if np.any((result < 0) | (result > 1)):
        raise ValueError("Points must lie within the unit cube")
    for axis, count in categories.items():
        if not isinstance(count, int) or count < 2 or not 0 <= axis < result.shape[-1]:
            raise ValueError("Categorical axes require at least two choices")
        result[..., axis] = (
            np.minimum((result[..., axis] * count).astype(int), count - 1) + 0.5
        ) / count
    return result


def minimize(objective, initial, *, generations, seed, categories=None):
    """Tournament selection, blend crossover, typed mutation and two retained elites.

    Each generation evaluates a full population, matching a DE generation's maximum
    objective-call budget. Random immigrants retain global coverage. No uncertainty
    estimates, Pareto optimality or global optimum are claimed.
    """
    categories = categories or {}
    population = canonical(initial, categories)
    if population.ndim != 2 or len(population) < 8 or population.shape[1] < 1 or generations < 0:
        raise ValueError("Use at least eight individuals and nonnegative generations")
    n, dimensions = population.shape
    rng = np.random.default_rng(seed)
    calls = 0

    def evaluate(points):
        nonlocal calls
        values = np.array([objective(x.copy()) for x in points], float)
        calls += len(points)
        if values.shape != (len(points),) or not np.isfinite(values).all():
            raise ValueError("Objective must return finite scalar losses")
        return values

    values = evaluate(population)
    history = [dict(generation=0, best=float(values.min()), evaluations=calls)]
    for generation in range(1, generations + 1):
        parents = rng.integers(n, size=(n, 2, 2))
        winners = np.take_along_axis(parents, values[parents].argmin(axis=2)[..., None], axis=2)[
            ..., 0
        ]
        a, b = population[winners[:, 0]], population[winners[:, 1]]
        blend = rng.uniform(-0.25, 1.25, size=(n, dimensions))
        children = a + blend * (b - a)
        mutate = rng.random((n, dimensions)) < 1 / dimensions
        children += mutate * rng.normal(0, 0.12, size=children.shape)
        for axis, count in categories.items():
            inherited = np.where(rng.random(n) < 0.5, a[:, axis], b[:, axis])
            replacement = (rng.integers(count, size=n) + 0.5) / count
            children[:, axis] = np.where(mutate[:, axis], replacement, inherited)
        immigrants = max(1, n // 10)
        children[-immigrants:] = rng.random((immigrants, dimensions))
        children = canonical(np.clip(children, 0, 1), categories)
        child_values = evaluate(children)
        elites = np.argsort(values, kind="stable")[:2]
        survivors = np.argsort(child_values, kind="stable")[: n - 2]
        population = np.vstack([population[elites], children[survivors]])
        values = np.r_[values[elites], child_values[survivors]]
        history.append(dict(generation=generation, best=float(values.min()), evaluations=calls))
    best = int(values.argmin())
    return SimpleNamespace(x=population[best], fun=float(values[best]), nfev=calls, history=history)
