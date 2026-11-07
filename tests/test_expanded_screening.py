import numpy as np
import pytest

from scripts.expanded_design_data import simulate
from scripts.expanded_screening import measure as extended
from scripts.search_joint_designs import measure as original
from tests.test_expanded_design_data import anchor


def test_longer_discharge_limit_preserves_fast_case_results():
    spec = anchor()
    cad = dict(fin=dict(volume_mm3=8000), nose=dict(volume_mm3=15000))
    standard, longer = original(spec, spec, cad), extended(spec, spec, cad)
    for key in ("scenario_height_m", "static_margin_cal", "conservative_beam_ratio", "max_q_pa"):
        assert longer[key] == pytest.approx(standard[key], rel=1e-9, abs=1e-10)


def test_incomplete_discharge_is_retried_and_not_zero_filled(monkeypatch):
    from scripts import expanded_design_data as module

    def incomplete(*args):
        raise RuntimeError("Screen discharge incomplete")

    monkeypatch.setattr(module, "measure", incomplete)
    monkeypatch.setattr(
        module,
        "extended_measure",
        lambda *args: dict(
            scenario_height_m=[4, 6], static_margin_cal=1.2, conservative_beam_ratio=0.01
        ),
    )
    model = dict(anchor=anchor().model_dump(mode="json"), cad={})
    sample = dict(unit=np.full(20, 0.5).tolist(), distribution="wide", split="train", parent=None)
    result = simulate((model, sample))
    assert result["status"] == "completed" and result["screening_attempts"] == 2
    assert result["metrics"]["scenario_height_m"] == [4, 6]
    monkeypatch.setattr(module, "extended_measure", incomplete)
    result = simulate((model, sample))
    assert result["status"] == "analysis_failed" and result["metrics"] is None
