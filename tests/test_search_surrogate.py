import json

import numpy as np
import pytest

from scripts.search_surrogate import advisor, features, fit, predict


def test_materials_are_one_hot_and_out_of_bounds_rejected():
    x = features(np.array([[0.1, 0], [0.2, 1]]), {1: 3})
    np.testing.assert_array_equal(x[:, 1:], [[1, 0, 0], [0, 0, 1]])
    with pytest.raises(ValueError):
        features(np.array([[0.1, 1.1]]), {1: 3})


def test_frozen_json_predictions_and_validation_fallback():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(71)
    x = rng.random((800, 3))
    y = np.column_stack([20 * x[:, 0] ** 2, 2 * x[:, 1], 0.1 * x[:, 0] * x[:, 1]])
    model = fit(x[:600], y[:600], x[600:700], y[600:700], categories={2: 3})
    restored = json.loads(json.dumps(model))
    np.testing.assert_allclose(predict(model, x[700:]), predict(restored, x[700:]), atol=0)
    error = np.abs(predict(model, x[700:]) - y[700:]).mean(0)
    baseline = np.abs(y[:600].mean(0) - y[700:]).mean(0)
    assert np.all(error < baseline * 0.25)
    assert model["validation_enabled"]
    # Validation labels may enable ranking, but cannot change already fitted weights.
    altered = fit(x[:600], y[:600], x[600:700], -y[600:700], categories={2: 3})
    assert model["weights"] == altered["weights"]
    assert not model["predicted_acceptance"]
    assert advisor(dict(model, validation_enabled=False)) is None
