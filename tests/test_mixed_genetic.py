import numpy as np
import pytest

from scripts.mixed_genetic import canonical, minimize


def test_mixed_ga_is_reproducible_bounded_and_improves_known_problem():
    points = np.random.default_rng(21).random((48, 3))
    checked = []

    def objective(x):
        assert np.all((x >= 0) & (x <= 1))
        assert x[2] in {1 / 6, 0.5, 5 / 6}
        checked.append(x.copy())
        category = int(x[2] * 3)
        return float((x[0] - 0.15) ** 2 + (x[1] - 0.8) ** 2 + 0.2 * (category != 2))

    result = minimize(objective, points, generations=20, seed=14, categories={2: 3})
    assert result.nfev == len(checked) == 48 * 21
    assert result.fun < 0.0005
    assert all(
        b["best"] <= a["best"] for a, b in zip(result.history[:-1], result.history[1:], strict=True)
    )
    repeated = minimize(objective, points, generations=20, seed=14, categories={2: 3})
    np.testing.assert_array_equal(result.x, repeated.x)
    assert result.fun == repeated.fun


def test_category_endpoints_do_not_create_nonexistent_or_fractional_options():
    values = canonical([[0, 0], [0.5, 0.9999], [1, 1]], {1: 3})
    np.testing.assert_array_equal(values[:, 1], [1 / 6, 5 / 6, 5 / 6])
    with pytest.raises(ValueError):
        canonical([[0, 1.1]], {1: 3})
    with pytest.raises(ValueError):
        canonical([[0, 1]], {1: 1})


def test_budget_abort_and_invalid_losses_are_not_hidden():
    points = np.zeros((8, 2))

    def abort(x):
        raise TimeoutError("reserved for native confirmation")

    with pytest.raises(TimeoutError):
        minimize(abort, points, generations=1, seed=1)
    with pytest.raises(ValueError, match="finite scalar"):
        minimize(lambda x: float("nan"), points, generations=1, seed=1)


def test_invalid_decoded_geometry_is_rejected_without_aborting_search(monkeypatch):
    from scripts import search_joint_designs as search

    def invalid(*args):
        raise ValueError("Fin tip and sweep must fit inside the root chord")

    monkeypatch.setattr(search, "decode", invalid)
    row, loss = search.proposal(np.ones(12), None, None, "initial")
    assert row["status"] == "failed" and "root chord" in row["error"]
    assert "metrics" not in row and "spec" not in row
    assert loss == 1e12
