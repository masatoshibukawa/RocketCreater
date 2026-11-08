import numpy as np
import pytest

from rocketwright.analysis.predictor_selection import HEIGHT_MODELS, select


def test_training_only_selection_beats_fixed_shrinkage_on_unseen_smooth_residual():
    x = np.linspace(0, 1, 8)[:, None]
    y = 0.1 + 0.2 * x[:, 0]
    q = np.array([0.55])
    r = select(x, y, np.ones(8), q, [str(i) for i in range(8)], models=HEIGHT_MODELS, bound=0.75)
    assert abs(r["prediction"] - 0.21) < 0.01
    assert r["selected_validation_mae"] < r["validation_mae"]["legacy_ridge"]
    assert r["selected"] != "raw"


def test_same_initial_state_stays_in_one_fold_and_no_gain_can_select_raw():
    x = np.repeat(np.linspace(0, 1, 4), 2)[:, None]
    groups = np.repeat(np.arange(4), 2)
    r = select(x, np.zeros(8), np.ones(8), [0.5], groups, models=HEIGHT_MODELS, bound=0.1)
    assert r["selected"] == "raw"
    assert r["prediction"] == 0
    with pytest.raises(ValueError, match="four"):
        select(x, np.zeros(8), np.ones(8), [0.5], [0] * 8, models=HEIGHT_MODELS)


def test_fit_honors_correction_bound_and_rejects_invalid_weights():
    x = np.arange(8)[:, None]
    r = select(x, np.ones(8) * 10, np.ones(8), [4], list(range(8)), models=HEIGHT_MODELS, bound=0.1)
    assert abs(r["prediction"]) <= 0.1
    with pytest.raises(ValueError):
        select(x, np.ones(8), np.zeros(8), [4], list(range(8)), models=HEIGHT_MODELS)
