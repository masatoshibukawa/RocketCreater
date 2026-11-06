import copy

import pytest

from rocketwright.adaptive import digest
from rocketwright.analysis import experience, policy
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.screening import axial_flight, estimated_volumes
from tests.test_analysis_harness import started
from tests.test_analysis_record import VOLUMES, spec


def test_accuracy_failure_allows_provisional_search_but_preserves_acceptance(tmp_path):
    _, h, state = started(tmp_path, budget_s=15000)
    c, s, precision, limits = h._campaign(state)
    original = h.data
    h.data = lambda campaign, key: (
        {"unmet": ["altitude", "aero_grid"], "metrics": {"criteria_met": False}}
        if key == "confirm"
        else {"candidates": {}}
        if key == "survey"
        else original(campaign, key)
    )
    choices, proposals, confirm = h._choices(c, s, precision, limits)
    assert proposals and "refine/cfd" in choices["offered"]
    assert all(choices["offered"][k]["provisional"] for k in proposals)
    assert choices["precision_pending"] == ["aero_grid"]
    assert not confirm["metrics"]["criteria_met"]
    c.remaining_s = 1
    choices, proposals, _ = h._choices(c, s, precision, limits)
    assert not proposals
    assert "reserve_for_confirmation" in choices["rejected"]["redesign"]


def test_feedback_preserves_losses_and_rejects_other_code_or_precision(tmp_path):
    from rocketwright.agent.design_projects import sha, write_json

    evidence_path = tmp_path / "data.json"
    write_json(evidence_path, {"apogee_m": 10})
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, {"data.json": sha(evidence_path)})
    s = spec()
    change = {"section": "geometry", "field": "fin_thickness_mm", "value": 3.6}
    p = Precision().model_dump()
    row = dict(
        code="solver1",
        precision_hash=digest(p),
        signature=experience.signature(change, s),
        evidence_id="result1",
        status="measured",
        features=experience.features(s),
        delta={"apogee_m": -2},
        cost_s=90,
        evidence=dict(
            artifact=str(evidence_path),
            sha256=sha(evidence_path),
            manifest_sha256=sha(manifest_path),
        ),
    )
    found = experience.retrieve([row, row], s, change, code="solver1", precision=p)
    assert len(found) == 1
    assert experience.estimate(found, 30)["score_adjustment"] < 0
    assert not experience.retrieve([row], s, change, code="solver2", precision=p)
    assert not experience.retrieve(
        [row], s, change, code="solver1", precision={**p, "altitude_error_m": 2}
    )
    failed = dict(row, status="failed")
    assert not experience.retrieve([failed], s, change, code="solver1", precision=p)
    evidence_path.write_text("{}")
    assert not experience.retrieve([row], s, change, code="solver1", precision=p)


def test_counterfactual_geometry_does_not_inherit_weighed_mass_or_change_requirement():
    s = spec()
    s.measured_printed_mass_g = 35
    before = copy.deepcopy(s.model_dump())
    rows = policy.proposals(s, SearchLimits(), ["altitude", "static_margin"], [])
    assert any(r["change"]["field"] == "nose_wall_mm" for r in rows.values())
    assert any(r["spec"]["material"] == "Prusament ASA" for r in rows.values())
    for row in rows.values():
        assert row["spec"]["requirement"] == before["requirement"]
        if row["change"]["section"] == "geometry" or row["change"]["field"] == "material":
            assert row["spec"]["measured_printed_mass_g"] is None
    assert s.model_dump() == before
    assert estimated_volumes(s, s, VOLUMES) == VOLUMES


def test_axial_solver_matches_constant_thrust_vacuum_solution():
    # Independent piecewise analytic solution: acceleration 10-9.80665 for 1 s,
    # then ballistic coast. Zero drag is an exact verification case, not validation.
    p = {"trace": {"time_s": [0, 1], "mass_kg": [1, 1], "thrust_n": [10, 10]}}
    result = axial_flight(None, p, area=0, cd=0, max_step=0.001)
    a = 10 - 9.80665
    expected = a / 2 + a * a / (2 * 9.80665)
    assert result["apogee_m"] == pytest.approx(expected, rel=1e-4)
