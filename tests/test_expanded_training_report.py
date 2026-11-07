import copy

import numpy as np
import pytest

from scripts.report_expanded_training import same_scores
from scripts.train_expanded_surrogate import scores


def test_boundary_false_positive_and_missed_feasible_are_kept_separate():
    truth = np.array([[0, 0.9, 0], [10, 1.3, 0.02], [3, 0, 0.01]])
    estimate = np.array([[1, 1.2, 0.01], [9, 1.1, 0.03], [4, 0.2, 0.02]])
    result = scores(truth, estimate)
    assert result["false_static_headroom"] == 1 and result["missed_static_headroom"] == 1
    assert result["true_static_headroom"] == result["predicted_static_headroom"] == 1
    assert result["boundary_count"] == 2
    assert result["boundary_mae"] == pytest.approx([1, 0.25, 0.01])
    same_scores(result, result)
    corrupt = copy.deepcopy(result)
    corrupt["missed_static_headroom"] = 0
    with pytest.raises(ValueError, match="counts"):
        same_scores(result, corrupt)
    no_boundary = scores(truth[2:], estimate[2:])
    assert no_boundary["boundary_count"] == 0 and no_boundary["boundary_mae"] is None
