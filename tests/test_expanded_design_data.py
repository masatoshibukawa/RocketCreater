import numpy as np
import pytest

from scripts.expanded_design_data import (
    CATEGORIES,
    decode,
    from_original,
    parent_split,
    sample_rows,
)


def anchor():
    from rocketwright.analysis.tradeoff import case_spec
    from tests.test_analysis_record import spec

    original = spec()
    original = case_spec(original, 20, 60, 400)
    return original.model_copy(update={"other_dry_mass_g": 150})


def test_expanded_context_is_consistent_and_does_not_mutate_original():
    base = anchor()
    before = base.model_dump(mode="json")
    unit = np.full(20, 0.5)
    candidate = decode(base, unit)
    assert candidate.design.payload_mass_kg == candidate.requirement.payload_mass_kg == 0.105
    assert candidate.design.initial_gauge_pressure_pa == 225000
    assert candidate.geometry.fin_count == 5
    assert candidate.other_dry_mass_g == 190
    assert base.model_dump(mode="json") == before
    unit[12] = 1.01
    with pytest.raises(ValueError):
        decode(base, unit)


def test_nominal_mapping_preserves_context_and_pressure_cap():
    from rocketwright.analysis.design_space import decode as original_decode

    base = anchor()
    original = np.full((1, 12), 0.5)
    mapped = from_original(original, base)[0]
    assert decode(base, mapped).model_dump() == original_decode(base, original[0]).model_dump()
    mapped[12] = 1
    assert decode(base, mapped).design.initial_gauge_pressure_pa == 400000


def test_mixture_has_fixed_counts_disjoint_parents_and_categories():
    base = anchor()
    parents = [dict(spec_hash=f"{i:064x}", unit=np.full(12, 0.5).tolist()) for i in range(1, 300)]
    # Vary leading digits because parent grouping hashes the first eight hex characters.
    for i, row in enumerate(parents):
        row["spec_hash"] = f"{i:08x}" + "0" * 56
    for split in ("train", "validation", "test"):
        rows = sample_rows(64, base, parents, seed=42, split=split)
        assert len(rows) == 64
        assert {
            f: sum(r["distribution"] == f for r in rows)
            for f in ("core", "context", "wide", "boundary", "residual")
        } == {"core": 24, "context": 8, "wide": 16, "boundary": 8, "residual": 8}
        assert all(parent_split(r["parent"]) == split for r in rows if r["parent"])
        assert rows == sample_rows(64, base, parents, seed=42, split=split)
        x = np.array([r["unit"] for r in rows])
        assert np.all((x >= 0) & (x <= 1))
        for axis, count in CATEGORIES.items():
            assert np.allclose(x[:, axis] * count - 0.5, np.round(x[:, axis] * count - 0.5))
