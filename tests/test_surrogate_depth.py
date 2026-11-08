import copy

import pytest

from scripts.benchmark_surrogate_depth import ARCHITECTURES, SEEDS, select_architecture


def test_depth_selection_uses_all_validation_pairs_not_test_or_lucky_seed():
    rows = [
        dict(
            architecture=list(architecture),
            anchor=i,
            seed=seed,
            validation_mae=[1.0, 1.0, 1.0],
            validation_enabled=True,
            elapsed_s=1,
        )
        for architecture in ARCHITECTURES
        for i in range(3)
        for seed in SEEDS
    ]
    for row in rows:
        if row["architecture"] == list(ARCHITECTURES[2]):
            row["validation_mae"] = [0.5, 0.7, 1.0]
        # These deliberately conflicting values must have no effect on validation selection.
        row["test_mae"] = 0 if row["architecture"] == list(ARCHITECTURES[3]) else 100
    assert select_architecture(rows)["selected"] == list(ARCHITECTURES[2])
    invalid = copy.deepcopy(rows)
    invalid[18]["validation_enabled"] = False
    assert select_architecture(invalid)["selected"] == list(ARCHITECTURES[0])
    with pytest.raises(ValueError, match="Three anchors"):
        select_architecture(rows[:-1])
