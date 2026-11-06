import copy

import pytest

from rocketwright.analysis import predictor
from tests.test_residual_feedback import artifact, measured


def rows(root):
    result = []
    for i in range(6):
        row = measured(root / str(i), forecast=3, actual=2.8 + i * 0.01)
        row.update(transition_id=f"distinct-{i}", change_from=2.4, change_to=3.6, cost_s=20 + i)
        row["features"]["fill"] = 0.2 + i * 0.02
        row["learning_evidence"] = artifact(root / str(i), "learning", row)
        result.append(dict(row, similarity=1.0))
    return result


def query(row):
    return dict(features=row["features"], before=row["before"], step=0.5, raw_delta=3)


def test_fit_learns_residual_and_cost_without_acceptance_labels(tmp_path):
    data = rows(tmp_path)
    fitted = predictor.estimate(data[:5], query(data[5]), correction_limit_m=0.1)
    assert fitted["status"] == "fitted" and fitted["samples"] == 5
    assert -0.1 <= fitted["height_correction_m"] < 0
    assert 20 <= fitted["predicted_cost_s"] <= 25
    assert "distinct-5" not in fitted["model"]["training_ids"]
    actual = data[5]["prediction_residual_m"]
    assert abs(actual - fitted["height_correction_m"]) < abs(actual)
    assert not {"criteria_met", "passed"} & fitted.keys()


def test_sparse_or_duplicate_data_does_not_fit(tmp_path):
    data = rows(tmp_path)
    fitted = predictor.estimate([data[0]] * 8, query(data[0]), correction_limit_m=1)
    assert fitted["status"] == "insufficient_samples" and fitted["samples"] == 1


@pytest.mark.parametrize("field", ["cost_s", "features", "prediction_residual_m"])
def test_training_metadata_tampering_is_rejected(tmp_path, field):
    data = rows(tmp_path)
    bad = copy.deepcopy(data[0])
    if field == "features":
        bad[field]["fill"] = 0.99
    else:
        bad[field] += 100
    assert not predictor.sealed(bad)
    fitted = predictor.estimate([bad] + data[1:4], query(data[-1]), correction_limit_m=1)
    assert fitted["status"] == "insufficient_samples"


def test_planner_receives_cited_examples_and_fitted_estimates(tmp_path):
    from rocketwright.analysis.planner import prompt_view

    data = rows(tmp_path)
    fitted = predictor.estimate(data, query(data[0]), correction_limit_m=1)
    view, _ = prompt_view(
        {
            "change": dict(
                learned_prediction=fitted,
                retrieved_cases=predictor.snippets(data),
                estimated_followup_cost_s=500,
            )
        },
        {},
    )
    shown = view["choices"]["change"]
    assert shown["predictor"]["model_hash"] == fitted["model_hash"]
    assert len(shown["retrieved_cases"]) == 2
    assert shown["cost_s"] == round(fitted["predicted_cost_s"], 2)
    assert str(tmp_path) not in str(view)


def test_rich_prediction_pool_preserves_families_within_context_budget(tmp_path):
    import json

    from rocketwright.analysis.planner import prompt_view

    data = rows(tmp_path)
    fitted = predictor.estimate(data, query(data[0]), correction_limit_m=1)
    offered = {}
    for i in range(32):
        offered[f"redesign/{i}"] = dict(
            target=dict(section="geometry", field=f"variable-{i % 16}", value=1.234567891),
            method="new_design_revision",
            layer="high",
            score=50 - i,
            estimated_followup_cost_s=500,
            retrieved_cases=predictor.snippets(data) if i == 0 else [],
            learned_prediction=fitted if i == 0 else dict(status="insufficient_samples", samples=0),
            experience=dict(samples=0, residual_samples=0, height_correction_m=0, mean_cost_s=None),
            prediction=dict(
                delta_height_m=0.123456789123,
                raw_delta_height_m=0.123456789123,
                delta_static_margin_cal=0.123456789123,
                violation_reduction=0.123456789123,
            ),
        )
    view, omitted = prompt_view(offered, dict(precision={"altitude_error_m": 1.5}))
    assert len(json.dumps(view, ensure_ascii=False, separators=(",", ":"))) <= 9000
    assert {r["target"]["field"] for r in view["choices"].values()} == {
        f"variable-{i}" for i in range(16)
    }
    assert view["choices"]["redesign/0"]["retrieved_cases"]
    assert not (set(omitted) & set(view["choices"]))
