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
    learned = experience.estimate(found, 30)
    assert learned["mean_delta_height_m"] < 0
    assert learned["score_adjustment"] == 0  # No bound prediction error in legacy evidence.
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


def test_published_comparison_reports_disagreements_without_fitting():
    from rocketwright.analysis.benchmarks import run

    report = run()
    assert all(report["verification_checks"].values())
    assert len(report["reference_flights"]) == 5
    assert not all(row["within_measurement"] for row in report["reference_flights"])
    assert not report["fit_performed"] and not report["aircraft_validation"]
    assert {row["split"] for row in report["reference_flights"]} == {
        "legacy calibration overlap",
        "additional fixed audit",
        "off-nominal launch stress case",
    }


def test_multi_start_inputs_preserve_mission_and_have_independent_geometry():
    from rocketwright.analysis.portfolio import starts

    template = spec()
    options = starts(template)
    assert len(options) == 11
    assert len({digest(s.geometry.model_dump()) for s in options.values()}) == 8
    assert all(s.requirement == template.requirement for s in options.values())
    assert all(
        s.design.payload_mass_kg == template.design.payload_mass_kg for s in options.values()
    )


def test_default_precision_fingerprint_survives_saved_roundtrip():
    # Native iterations used to be discarded as stale after defaults 1/15 became 1.0/15.0.
    initial = Precision(require_cfd=False, require_fem=False)
    restored = Precision.model_validate_json(initial.model_dump_json())
    assert digest(initial.model_dump()) == digest(restored.model_dump())


def test_native_style_feedback_survives_default_precision_reload(tmp_path):
    from rocketwright.agent.design_projects import sha, write_json
    from rocketwright.analysis.service import code_hash

    _, h, state = started(tmp_path, max_versions=3, budget_s=5000)
    c, s, precision, limits = h._campaign(state)
    artifact = tmp_path / "data.json"
    write_json(artifact, {"apogee_m": 12})
    write_json(tmp_path / "manifest.json", {"data.json": sha(artifact)})
    c.results["screen"] = dict(
        value=dict(
            artifact=str(artifact),
            sha256=sha(artifact),
            manifest_sha256=sha(tmp_path / "manifest.json"),
        )
    )
    before = dict(apogee_m=10, incidence_deg=2, dry_mass_g=200, static_margin_cal=1.2)
    after = dict(before, apogee_m=12)
    h._snapshot = lambda _: after
    state["adaptive"]["outcome_pending"] = dict(
        before=before,
        features=experience.features(s),
        signature="geometry.fin_span_mm:-1",
        to_spec_hash=policy.identity(s),
        code=code_hash(),
        precision_hash=digest(state["adaptive"]["precision"]),
        remaining_s=5000,
        history_index=0,
        decision_index=-1,
    )
    h._feedback(c, s, precision)
    row = state["adaptive"]["observations"][-1]
    assert row["status"] == "measured" and row["delta"]["apogee_m"] == 2
    assert experience.verified(row)


def test_decision_view_bounds_history_and_keeps_variable_diversity():
    import json

    from rocketwright.analysis.planner import prompt_view

    offered = {
        f"change-{i}": dict(
            method="redesign",
            layer="high",
            score=100 - i,
            cost_s=1,
            target=dict(section="geometry", field=f"field-{i % 5}", value=i),
            retrieved_outcomes=[{"private_path": "x" * 20000}],
            prediction=dict(delta_height_m=1, delta_mass_g=-3),
            experience=dict(samples=2, mean_delta_height_m=0.8),
        )
        for i in range(50)
    }
    view, omitted = prompt_view(offered, {}, max_chars=4000)
    assert len(json.dumps(view, separators=(",", ":"))) <= 4000
    assert "change-0" in view["choices"] and omitted
    assert {r["target"]["field"] for r in view["choices"].values()} == {
        f"field-{i}" for i in range(5)
    }
    assert "private_path" not in json.dumps(view)
    assert offered["change-0"]["retrieved_outcomes"]


def test_single_eligible_dependency_avoids_a_model_call():
    from rocketwright.analysis.planner import choose

    class Unused:
        def generate(self, *args):
            raise AssertionError("No LLM choice exists here")

    decision = choose({"offered": {"thermal": {}}}, {}, SearchLimits(), director=Unused())
    assert decision["action"] == "thermal" and decision["planner"] == "forced_dependency"


def test_screening_surfaces_static_and_attitude_violations_before_confirmation(tmp_path):
    _, h, state = started(tmp_path)
    c, s, precision, limits = h._campaign(state)
    h._snapshot = lambda _: dict(apogee_m=10, static_margin_cal=-0.1, incidence_deg=30)
    h._feedback = lambda *args: None
    original = h.data
    h.data = lambda campaign, key: dict(apogee_m=10) if key == "screen" else original(campaign, key)
    choices, _, _ = h._choices(c, s, precision, limits)
    assert {"altitude", "static_margin", "attitude"} <= set(choices["unmet"])
