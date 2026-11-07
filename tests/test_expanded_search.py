import json

import numpy as np
import pytest

from scripts import benchmark_expanded_search as study
from scripts.report_expanded_search import audit_rows, local_file


@pytest.fixture
def anchor():
    # Same registered baseline used by the existing joint-space tests, without model weights.
    from rocketwright.analysis.tradeoff import reconcile_payload
    from tests.test_analysis_record import spec

    return reconcile_payload(spec())[0]


def test_fixed_context_and_pairing(anchor):
    for domain in ("core", "wide"):
        a = study.initial_population(16, 137, anchor, domain)
        b = study.initial_population(16, 137, anchor, domain)
        np.testing.assert_array_equal(a, b)
        x = study.expanded_points(a, anchor, domain)
        for unit in x:
            try:
                spec = study.decode(anchor, unit)
            except ValueError:
                continue
            study.fixed_mission(spec, anchor)
            changed = spec.model_copy(deep=True)
            changed.design = changed.design.model_copy(update={"payload_mass_kg": 0.03})
            with pytest.raises(ValueError, match="fixed mission"):
                study.fixed_mission(changed, anchor)


def test_old_advisor_never_extrapolates(anchor, monkeypatch):
    seen = []

    def predict(model, points):
        seen.extend(points.tolist())
        assert np.all((points >= 0) & (points <= 1))
        return np.tile([20.0, 1.2, 0.01], (len(points), 1))

    monkeypatch.setattr(study, "expert_predict", predict)
    counts = dict(proposed=0, old_supported=0, finite_advice=0)
    rank = study.make_advisor({"nominal_expert": {}}, anchor, "wide-old", counts)
    core = study.from_original(np.full((1, 12), 0.5), anchor)[0, :12]
    wide = core.copy()
    wide[0] = 1  # 75% fill, outside the old 8–35% input contract.
    values = rank(np.array([core, wide]))
    assert values[0] == -20 and np.isnan(values[1])
    assert len(seen) == 1 and counts["old_supported"] == 1


def test_failures_consume_budget_without_fabricated_height(tmp_path, anchor, monkeypatch):
    bundle = dict(anchor=anchor.model_dump(mode="json"), cad={})
    path = tmp_path / "model.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    monkeypatch.setattr(study, "code_hash", lambda: "source")
    monkeypatch.setattr(study, "make_advisor", lambda *args: lambda x: np.zeros(len(x)))

    def failed(*args):
        raise RuntimeError("deliberate simulator failure")

    monkeypatch.setattr(study, "measure", failed)
    output = tmp_path / "rows.jsonl"
    result = study.experiment((path, "core-old", 137, 0, 8, 1, output, "source"))
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert result["evaluations"] == 16 == len(rows)
    assert result["completed"] == 0 and result["best"] is None
    assert all("metrics" not in row and row["loss"] == 1e12 for row in rows)
    audit_rows(rows, result, anchor, 8, 1)
    rows[0]["metrics"] = {"apogee_m": 0}
    with pytest.raises(ValueError, match="fabricated"):
        audit_rows(rows, result, anchor, 8, 1)


def test_audit_rejects_changed_loss_and_population(tmp_path, anchor, monkeypatch):
    path = tmp_path / "model.json"
    path.write_text(
        json.dumps(dict(anchor=anchor.model_dump(mode="json"), cad={})), encoding="utf-8"
    )
    monkeypatch.setattr(study, "code_hash", lambda: "source")
    monkeypatch.setattr(study, "make_advisor", lambda *args: lambda x: np.zeros(len(x)))
    monkeypatch.setattr(
        study,
        "measure",
        lambda *args: dict(
            static_margin_cal=1.2, scenario_height_m=[20.0, 25.0], conservative_beam_ratio=0.01
        ),
    )
    output = tmp_path / "rows.jsonl"
    result = study.experiment((path, "core-old", 137, 0, 8, 1, output, "source"))
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(audit_rows(rows, result, anchor, 8, 1)) == 16
    rows[0]["loss"] = -40
    with pytest.raises(ValueError, match="loss"):
        audit_rows(rows, result, anchor, 8, 1)
    rows[0]["loss"] = -20
    rows[0]["unit"][0] = 1
    with pytest.raises(ValueError, match="Initial population"):
        audit_rows(rows, result, anchor, 8, 1)
    with pytest.raises(ValueError, match="escapes"):
        local_file(tmp_path, "../foreign.json")
