"""Adaptive mixed GA/DE proposal generators. Only measured losses select survivors."""

from types import SimpleNamespace

import numpy as np

from scripts.mixed_genetic import canonical


def reflect(points):
    """Reflect overshoots instead of accumulating clipped coordinates on a boundary."""
    return 1 - np.abs(np.mod(points, 2) - 1)


def diversity(population, categories):
    continuous = [i for i in range(population.shape[1]) if i not in categories]
    return float(np.std(population[:, continuous], axis=0).mean()) if continuous else 0.0


def minimize(objective, initial, *, generations, seed, method, categories=None, advisor=None):
    """Same n*(generations+1) measured calls with or without an advisory surrogate.

    GA uses adaptive mutation, mixed crossover and elitist survival. DE uses a
    current-to-pbest/rand mixture, an archive and successful-parameter adaptation.
    This small implementation is not a reference implementation of JADE or NSGA-II.
    An advisor may rank extra *unevaluated* proposals, never population survivors.
    """
    categories = categories or {}
    population = canonical(initial, categories)
    if (
        population.ndim != 2
        or len(population) < 8
        or population.shape[1] < 1
        or not isinstance(generations, int)
        or generations < 0
        or method not in {"ga", "de"}
    ):
        raise ValueError("Use ga/de, at least eight individuals and integer generations >= 0")
    n, dimensions = population.shape
    rng = np.random.default_rng(seed)
    calls, predicted, stale, restarts = 0, 0, 0, 0
    sigma, mean_f, mean_cr = 0.12, 0.5, 0.7
    archive = np.empty((0, dimensions))

    def evaluate(points):
        nonlocal calls
        losses = np.array([objective(x.copy()) for x in points], dtype=float)
        calls += len(points)
        if losses.shape != (len(points),) or not np.isfinite(losses).all():
            raise ValueError("Objective must return finite scalar losses")
        return losses

    values = evaluate(population)
    history = []

    def snapshot(generation):
        history.append(
            dict(
                generation=generation,
                best=float(values.min()),
                evaluations=calls,
                diversity=diversity(population, categories),
                mutation_sigma=sigma,
                mean_f=mean_f,
                mean_cr=mean_cr,
                restarts=restarts,
                predicted_candidates=predicted,
            )
        )

    snapshot(0)
    for generation in range(1, generations + 1):
        best_before = float(values.min())
        restart = stale >= 5 or diversity(population, categories) < 0.035
        restarts += int(restart)
        factor = 3 if advisor is not None else 1
        count = n * factor
        owners = np.tile(np.arange(n), factor)
        order = np.argsort(values, kind="stable")
        if method == "ga":
            contestants = rng.integers(n, size=(count, 2, 2))
            winners = np.take_along_axis(
                contestants, values[contestants].argmin(axis=2)[..., None], axis=2
            )[..., 0]
            a, b = population[winners[:, 0]], population[winners[:, 1]]
            # Simulated binary crossover; reflection handles extrapolated coordinates.
            u = rng.random((count, dimensions))
            beta = np.where(u <= 0.5, (2 * u) ** (1 / 11), (2 * (1 - u)) ** (-1 / 11))
            children = 0.5 * ((1 + beta) * a + (1 - beta) * b)
            mutation = rng.random(children.shape) < (2 if restart else 1) / dimensions
            children += mutation * rng.normal(0, sigma, children.shape)
            for axis, choices in categories.items():
                inherited = np.where(rng.random(count) < 0.5, a[:, axis], b[:, axis])
                children[:, axis] = np.where(
                    mutation[:, axis],
                    (rng.integers(choices, size=count) + 0.5) / choices,
                    inherited,
                )
            fs = crs = None
        else:
            fs = np.clip(rng.normal(mean_f, 0.1, count), 0.1, 1.0)
            crs = np.clip(rng.normal(mean_cr, 0.1, count), 0.05, 0.95)
            children = np.empty((count, dimensions))
            combined = np.vstack([population, archive])
            for j, owner in enumerate(owners):
                choices = np.delete(np.arange(n), owner)
                r1, r2, r3 = rng.choice(choices, 3, replace=False)
                pbest = rng.choice(order[: max(2, n // 5)])
                # Exclude target and r1 from the second difference endpoint.
                pool = np.setdiff1d(np.arange(len(combined)), [owner, r1])
                other = combined[rng.choice(pool)]
                donor = population[owner] + fs[j] * (
                    population[pbest] - population[owner] + population[r1] - other
                )
                if rng.random() < 0.2:
                    donor = population[r1] + fs[j] * (population[r2] - population[r3])
                crossover = rng.random(dimensions) < crs[j]
                crossover[rng.integers(dimensions)] = True
                children[j] = np.where(crossover, donor, population[owner])
                for axis, choices in categories.items():
                    children[j, axis] = population[r1 if crossover[axis] else owner, axis]
                    if rng.random() < 1 / dimensions:
                        children[j, axis] = (rng.integers(choices) + 0.5) / choices
        immigrants = max(1, count // (4 if restart else 20))
        children[rng.choice(count, immigrants, replace=False)] = rng.random(
            (immigrants, dimensions)
        )
        children = canonical(reflect(children), categories)
        # Avoid exact genotype repeats before spending simulator calls.
        seen = {tuple(x) for x in population}
        for i in range(count):
            for _ in range(8):
                key = tuple(children[i])
                if key not in seen:
                    break
                children[i] = canonical(rng.random(dimensions), categories)
            seen.add(tuple(children[i]))
        if advisor is not None:
            estimates = np.asarray(advisor(children), float)
            if estimates.shape != (count,):
                raise ValueError("Advisor must return one score per candidate")
            predicted += count
            if method == "ga":
                # At least 30% bypass prediction ranking; nonfinite advice gets no priority.
                explore = rng.choice(count, max(1, int(np.ceil(0.3 * n))), replace=False)
                remaining = np.setdiff1d(np.arange(count), explore)
                rank = np.argsort(np.where(np.isfinite(estimates), estimates, np.inf))
                exploit = [i for i in rank if i in remaining][: n - len(explore)]
                selected = np.r_[explore, exploit].astype(int)
            else:
                selected = []
                for owner in range(n):
                    options = np.flatnonzero(owners == owner)
                    finite = options[np.isfinite(estimates[options])]
                    chosen = (
                        rng.choice(options)
                        if rng.random() < 0.3 or not len(finite)
                        else finite[np.argmin(estimates[finite])]
                    )
                    selected.append(chosen)
                selected = np.array(selected)
            children, owners = children[selected], owners[selected]
            if fs is not None:
                fs, crs = fs[selected], crs[selected]
        child_values = evaluate(children)
        if method == "ga":
            success = float(np.mean(child_values < np.median(values)))
            sigma = float(np.clip(sigma * np.exp(0.3 * (success - 0.2)), 0.02, 0.25))
            merged = np.vstack([population, children])
            losses = np.r_[values, child_values]
            survivors = np.argsort(losses, kind="stable")[:n]
            population, values = merged[survivors], losses[survivors]
        else:
            improved = child_values < values[owners]
            if improved.any():
                archive = np.vstack([archive, population[owners[improved]]])
                if len(archive) > n:
                    archive = archive[rng.choice(len(archive), n, replace=False)]
                successful_f, successful_cr = fs[improved], crs[improved]
                mean_f = float(0.9 * mean_f + 0.1 * np.sum(successful_f**2) / np.sum(successful_f))
                mean_cr = float(0.9 * mean_cr + 0.1 * successful_cr.mean())
                population[owners[improved]] = children[improved]
                values[owners[improved]] = child_values[improved]
        stale = stale + 1 if values.min() >= best_before - 1e-10 else 0
        if restart:
            stale = 0
        snapshot(generation)
    best = int(values.argmin())
    return SimpleNamespace(
        x=population[best].copy(),
        fun=float(values[best]),
        nfev=calls,
        history=history,
        predicted_candidates=predicted,
    )
