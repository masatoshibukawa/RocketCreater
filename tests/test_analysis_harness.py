import copy
from types import SimpleNamespace

import pytest

from rocketwright.agent.design_projects import DesignProjects, sha, write_json
from rocketwright.agent.workbench import Conflict
from rocketwright.analysis import planner, policy
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness
from tests.test_analysis_record import VOLUMES, spec


class FakeDirector:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.api = SimpleNamespace(timeout=None)

    def generate(self, context, schema, instructions):
        output = next(self.outputs)
        if callable(output):
            output = output(context)
        return output, "test-only-local-model"


def test_planner_rejects_unoffered_ids_extra_fields_and_labels_fallback():
    choices = {"offered": {"screen": {"score": 1}}}
    invalid = [
        {"action": "shell", "reason": "no"},
        {"action": "screen", "reason": "yes", "passed": True},
    ]
    outcome = planner.choose(choices, {}, SearchLimits(), director=FakeDirector(invalid))
    assert outcome["action"] is None and len(outcome["errors"]) == 2
    outcome = planner.choose(
        choices, {}, SearchLimits(fallback="baseline"), director=FakeDirector(invalid)
    )
    assert outcome["planner"] == "fallback_baseline"
    assert outcome["action"] == "screen"


def test_policy_moves_from_operating_variables_to_shape_and_invalidates_measured_mass():
    s = spec()
    s.measured_printed_mass_g = 30
    limits = SearchLimits(pressure_kpa=(300, 350), fills=(), nozzle_mm=())
    initial = policy.proposals(s, limits, ["altitude"], [policy.identity(s)])
    assert list(initial) == ["redesign/pressure-350"]
    s.design = s.design.model_copy(update={"initial_gauge_pressure_pa": 350000})
    later = policy.proposals(s, limits, ["altitude"], [policy.identity(s)])
    assert later["redesign/thinner-fin"]["spec"]["measured_printed_mass_g"] is None
    assert any(k.startswith("redesign/material") for k in later)
    strength = policy.proposals(s, limits, ["fin_deformation"], [])
    assert "redesign/reinforced-mount" in strength


class FixtureHarness(Harness):
    """Synthetic evidence exercises orchestration only; real physics has separate tests."""

    fail = None
    confirmation = False

    def _runner(self, kind):
        def execute(params, folder, campaign):
            if kind == self.fail:
                raise RuntimeError("injected solver failure")
            value = {"metrics": {}}
            if kind == "geometry":
                value["cad_metrics"] = VOLUMES
            if kind == "screen":
                value.update(apogee_m=10, metrics={"apogee_m": 10})
            if kind == "confirm":
                value.update(
                    unmet=[] if self.confirmation else ["altitude"],
                    metrics={"criteria_met": self.confirmation},
                )
            path = folder / "data.json"
            write_json(path, value)
            write_json(folder / "manifest.json", {"data.json": sha(path)})
            return dict(
                artifact=str(path.resolve()),
                sha256=sha(path),
                manifest_sha256=sha(folder / "manifest.json"),
                metrics=value["metrics"],
            )

        return execute


def started(tmp_path, **limits):
    store = DesignProjects(tmp_path / "projects")
    state = store.create(spec())
    h = FixtureHarness(store, runtime=Runtime())
    state = h.start(
        state["id"],
        state["revision"],
        Precision(require_cfd=False, require_fem=False),
        SearchLimits(planner="baseline", **limits),
    )
    return store, h, state


def test_redesign_creates_versions_reuses_only_current_geometry_and_stops_at_budget(tmp_path):
    store, h, s = started(tmp_path, max_versions=2)
    s = h.run(s["id"], s["revision"])
    a = s["adaptive"]
    assert s["version"] == 2 and len(a["revisions"]) == 1
    assert a["status"] == "unresolved" and not a["physical_qualification"]
    assert len([x for x in a["history"] if x["action"] == "geometry"]) == 1
    assert len([x for x in a["history"] if x["action"] == "screen"]) == 2
    assert a["remaining_s"] < a["limits"]["budget_s"]
    assert store.load(s["id"])["version"] == 2
    with pytest.raises(Conflict):
        store.adopt(s["id"], s["revision"])


def test_failed_solver_is_bounded_and_never_counts_as_confirmation(tmp_path):
    _, h, s = started(tmp_path)
    h.fail = "geometry"
    s = h.run(s["id"], s["revision"])
    assert s["adaptive"]["status"] == "unresolved"
    assert len(s["adaptive"]["history"]) == 2
    assert all(r["execution_status"] == "failed" for r in s["adaptive"]["history"])


def test_restart_edit_and_tampered_artifact_cannot_reuse_success(tmp_path):
    store, h, s = started(tmp_path, max_versions=1)
    h.confirmation = True
    s = h.run(s["id"], s["revision"])
    assert s["adaptive"]["status"] == "screening_criteria_met"
    old = s["adaptive"]["results"]["geometry"]["value"]["artifact"]
    from pathlib import Path

    Path(old).write_text("{}")
    restarted = FixtureHarness(DesignProjects(store.root))
    options = restarted.options(s["id"])
    assert "geometry" in options["offered"]
    assert "confirm" not in options["offered"]
    edited = copy.deepcopy(spec())
    edited.geometry = edited.geometry.model_copy(update={"fin_span_mm": 110})
    s = store.edit(s["id"], s["revision"], edited)
    assert s["adaptive"]["accepted_spec_hash"] is None
    assert s["adaptive"]["status"] == "running"


def test_capability_and_fin_count_gate_cfd_without_claiming_pass(tmp_path):
    store = DesignProjects(tmp_path / "projects")
    s = spec()
    s.geometry = s.geometry.model_copy(update={"fin_count": 3})
    state = store.create(s)
    h = FixtureHarness(store)
    state = h.start(state["id"], 0, Precision(), SearchLimits(planner="baseline", max_versions=1))
    state = h.run(state["id"], state["revision"])
    rejected = state["adaptive"]["last_choices"]["rejected"]["cfd_coarse"]
    assert "missing_capability" in rejected and "outside_domain:fin_count" in rejected
    assert state["adaptive"]["status"] == "unresolved"
