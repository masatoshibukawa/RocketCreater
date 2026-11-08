import numpy as np
import pytest

from scripts.adaptive_evolution import minimize, reflect


@pytest.mark.parametrize("method", ["ga", "de"])
@pytest.mark.parametrize("advised", [False, True])
def test_adaptive_search_uses_only_measured_bounded_losses(method, advised):
    initial = np.random.default_rng(12).random((32, 3))
    calls = []

    def objective(x):
        assert np.all((x >= 0) & (x <= 1))
        assert x[2] in {1 / 6, 0.5, 5 / 6}
        calls.append(tuple(x))
        return float((x[0] - 0.2) ** 2 + (x[1] - 0.8) ** 2 + (int(x[2] * 3) != 2))

    # Deliberately misleading predictions cannot become measured fitness or final acceptance.
    advisor = (lambda xs: -1000 * xs[:, 0]) if advised else None
    result = minimize(
        objective,
        initial,
        generations=16,
        seed=3,
        method=method,
        categories={2: 3},
        advisor=advisor,
    )
    assert result.nfev == len(calls) == 32 * 17
    assert tuple(result.x) in calls
    assert result.fun == objective(result.x)
    assert result.fun < 0.02
    assert all(
        b["best"] <= a["best"] for a, b in zip(result.history, result.history[1:], strict=False)
    )
    again = minimize(
        objective,
        initial,
        generations=16,
        seed=3,
        method=method,
        categories={2: 3},
        advisor=advisor,
    )
    np.testing.assert_array_equal(result.x, again.x)
    assert result.history == again.history


def test_reflection_and_failure_propagation():
    np.testing.assert_allclose(reflect([-0.2, 1.2, 2.2, -2.2]), [0.2, 0.8, 0.2, 0.2])
    initial = np.zeros((8, 2))
    with pytest.raises(ValueError, match="finite scalar"):
        minimize(lambda x: np.nan, initial, generations=1, seed=1, method="ga")

    def abort(x):
        raise TimeoutError("native reserve")

    with pytest.raises(TimeoutError):
        minimize(abort, initial, generations=1, seed=1, method="de")


@pytest.mark.parametrize("method", ["ga", "de"])
def test_plateau_triggers_restart_without_losing_incumbent(method):
    result = minimize(lambda x: 1.0, np.full((8, 2), 0.5), generations=7, seed=2, method=method)
    assert result.nfev == 64 and result.fun == 1
    assert result.history[-1]["restarts"] >= 1
