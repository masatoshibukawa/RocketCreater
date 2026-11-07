import numpy as np
import pytest

from scripts.expanded_design_data import from_original
from scripts.expanded_surrogate import advisor, contract, inverse, predict, transform
from tests.test_expanded_design_data import anchor


def test_wide_target_transform_preserves_zeros_and_signed_margin():
    y = np.array([[0, -5, 0], [20, 1.2, 0.02], [150, 8, 5]])
    np.testing.assert_allclose(inverse(transform(y)), y, atol=1e-12)
    with pytest.raises(ValueError):
        transform(np.array([[-1, 2, 0]]))


def test_nominal_expert_routes_only_its_exact_context(monkeypatch):
    from scripts import expanded_surrogate as module

    def fake(model, x):
        values = [20, 1.5, 0.02] if model["kind"] == "expert" else transform([[12, 1.2, 0.03]])[0]
        return np.tile(values, (len(x), 1))

    monkeypatch.setattr(module, "dense_predict", fake)
    base = anchor()
    bundle = dict(
        source_hash="same",
        input_contract=contract("same"),
        anchor=base.model_dump(mode="json"),
        cad={},
        members=[dict(kind="broad")],
        nominal_expert=dict(kind="expert"),
        validation_enabled=True,
    )
    x = from_original(np.full((3, 12), 0.5), base)
    x[1, 12] = 0.5  # Different pressure must not use the specialized expert.
    x[2, 0] = 1  # Wider water fraction must not use the specialized expert.
    np.testing.assert_allclose(
        predict(bundle, x), [[20, 1.5, 0.02], [12, 1.2, 0.03], [12, 1.2, 0.03]]
    )
    rank = advisor(bundle, base, {}, "same")
    assert np.isfinite(rank(x)).all()
    impossible = x[:1].copy()
    impossible[0, 2:4] = 0  # 35 mm root and 10% tip would violate the 10 mm tip minimum.
    assert np.isinf(rank(impossible)[0])
    with pytest.raises(ValueError, match="incompatible"):
        advisor(bundle, base, {}, "changed")
    x[0, 0] = 1.01
    with pytest.raises(ValueError, match="outside"):
        predict(bundle, x)
