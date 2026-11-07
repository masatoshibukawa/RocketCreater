import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.report_refined_rl import audit_incumbents, local_file


def test_audit_rejects_lost_incumbent():
    rows = [
        dict(
            episode=episode,
            step=step,
            status="completed",
            loss=10 + step,
            incumbent_loss=10,
            incumbent_improved=step == 0,
        )
        for episode in range(32)
        for step in range(11)
    ]
    audit_incumbents(rows)
    rows[4]["incumbent_loss"] = 14
    with pytest.raises(ValueError, match="Incumbent"):
        audit_incumbents(rows)


def test_audit_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="out-of-directory"):
        local_file(tmp_path, "../other.json", "ignored")


def test_actual_feedback_preserves_best_and_charges_rejections(monkeypatch, tmp_path):
    sb3 = pytest.importorskip("stable_baselines3")
    from scripts import benchmark_refined_rl as benchmark
    from tests.test_analysis_record import spec

    monkeypatch.setattr(
        sb3.PPO,
        "load",
        lambda *a, **k: SimpleNamespace(predict=lambda *a, **k: (np.ones(11), None)),
    )
    monkeypatch.setattr(benchmark, "samples", lambda n, seed: np.full((n, 12), 0.5))
    monkeypatch.setattr(benchmark, "code_hash", lambda: "same")
    calls = []

    def measured(unit, *args):
        calls.append(unit.copy())
        step = (len(calls) - 1) % 11
        if step == 2:
            return dict(unit=unit.tolist(), status="failed"), 1e12
        # Only step 1 improves over the initial design; subsequent moves must start from it.
        value = -20 if step == 1 else -10
        return dict(
            unit=unit.tolist(),
            status="completed",
            spec_hash=str(len(calls)),
            metrics=dict(scenario_height_m=[-value], static_margin_cal=1.2),
        ), value

    monkeypatch.setattr(benchmark, "proposal", measured)
    policy = tmp_path / "policy.zip"
    policy.write_bytes(b"mock")
    model = dict(anchor=spec().model_dump(mode="json"), categories={11: 3}, cad={})
    result = benchmark.evaluate_refined(
        (model, "ppo-v2", 14291, 0, policy, tmp_path / "search.jsonl", "same")
    )
    rows = [json.loads(s) for s in (tmp_path / "search.jsonl").read_text().splitlines()]
    audit_incumbents(rows)
    assert result["evaluations"] == 352 and result["rejected"] == 32
    assert result["best_loss"] == -20
    np.testing.assert_allclose(calls[1][:11], 0.75)
    np.testing.assert_allclose(calls[2][:11], 0.978)
    # Invalid step 2 must not become the next starting point.
    np.testing.assert_allclose(calls[3][:11], 0.956)
