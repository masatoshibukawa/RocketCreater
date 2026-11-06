import copy

import pytest

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis import experience
from rocketwright.analysis.schema import Precision
from tests.test_analysis_record import spec


def artifact(root, name, data):
    path = root / name / "data.json"
    write_json(path, data)
    manifest = path.parent / "manifest.json"
    write_json(manifest, {"data.json": sha(path)})
    return dict(artifact=str(path), sha256=sha(path), manifest_sha256=sha(manifest))


def measured(root, *, forecast=3, actual=2):
    s = spec()
    change = dict(section="geometry", field="fin_thickness_mm", value=3.6)
    prediction = dict(delta_height_m=forecast)
    before = dict(apogee_m=10, dry_mass_g=200)
    after = dict(apogee_m=10 + actual, dry_mass_g=190)
    evidence = artifact(root, "after", after)
    return dict(
        status="measured",
        code="solver",
        precision_hash=digest(Precision().model_dump()),
        features=experience.features(s),
        signature=experience.signature(change, s),
        transition_id=experience.transition_id(s, change, before),
        evidence_id=evidence["sha256"],
        evidence=evidence,
        before_evidence=artifact(root, "before", before),
        prediction_evidence=artifact(root, "survey", dict(candidates=dict(thinner=prediction))),
        prediction=prediction,
        prediction_action="thinner",
        before=before,
        after=after,
        delta=dict(apogee_m=actual),
        prediction_residual_m=actual - forecast,
        cost_s=20,
    )


def retrieve(rows):
    return experience.retrieve(
        rows,
        spec(),
        dict(section="geometry", field="fin_thickness_mm", value=3.6),
        code="solver",
        precision=Precision().model_dump(),
    )


def test_residual_corrects_an_overoptimistic_forecast_despite_positive_gain(tmp_path):
    row = measured(tmp_path)
    found = retrieve([row])
    result = experience.estimate(found, 30)
    assert result["mean_delta_height_m"] == 2
    assert result["residual_samples"] == 1
    assert result["height_correction_m"] == pytest.approx(-0.25)
    assert result["score_adjustment"] < 0
    assert row["delta"]["apogee_m"] == 2


def test_simulation_copy_is_not_an_independent_training_sample(tmp_path):
    a = measured(tmp_path / "a")
    b = measured(tmp_path / "b")
    b["evidence_id"] = "another-file-path-and-source-label"
    assert len(retrieve([a, b])) == 1
    s = spec()
    s.assumptions.evidence["source"] = "another source label"
    s.design = s.design.model_copy(update={"parachute_diameter_m": 0.4, "dry_mass_kg": 0.1})
    assert (
        experience.transition_id(
            s, dict(section="geometry", field="fin_thickness_mm", value=3.6), a["before"]
        )
        == a["transition_id"]
    )


def test_derived_delta_and_prediction_must_match_both_raw_artifacts(tmp_path):
    row = measured(tmp_path)
    for field in ("prediction_residual_m", "delta", "prediction", "before"):
        bad = copy.deepcopy(row)
        if field == "prediction_residual_m":
            bad[field] += 1
        elif field == "prediction":
            bad[field]["delta_height_m"] += 1
        else:
            bad[field]["apogee_m"] += 1
        assert not retrieve([bad])
    from pathlib import Path

    Path(row["before_evidence"]["artifact"]).write_text("{}")
    assert not retrieve([row])


def test_sparse_feedback_is_bounded_and_legacy_gains_do_not_replace_physics(tmp_path):
    row = measured(tmp_path, forecast=50)
    result = experience.estimate(retrieve([row]), 30, correction_limit_m=0.1)
    assert result["height_correction_m"] == -0.1 and result["correction_clipped"]
    del row["prediction_residual_m"]
    legacy = experience.estimate(retrieve([row]), 30)
    assert legacy["samples"] == 1 and legacy["residual_samples"] == 0
    assert legacy["height_correction_m"] == 0


def test_numerical_step_and_distinct_geometry_limit_retrieval(tmp_path):
    row = measured(tmp_path)
    row["screen_step_s"] = 0.01
    assert not retrieve([row])
    row["screen_step_s"] = 0.02
    row["features"]["root_mm"] += 200
    assert not retrieve([row])


def test_prompt_shows_followup_cost_instead_of_revision_write_cost():
    from rocketwright.analysis.planner import prompt_view

    offered = {
        "change": dict(
            method="new_design_revision",
            cost_s=1,
            estimated_followup_cost_s=500,
            experience=dict(mean_cost_s=80),
        ),
        "refine": dict(method="increase_grid", cost_s=200),
    }
    view, _ = prompt_view(offered, {})
    assert view["choices"]["change"]["cost_s"] == 80
    assert view["choices"]["refine"]["cost_s"] == 200
