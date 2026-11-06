import copy
from pathlib import Path
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


def test_policy_offers_shape_alongside_operations_and_invalidates_measured_mass():
    s = spec()
    s.measured_printed_mass_g = 30
    limits = SearchLimits(pressure_kpa=(300, 350), fills=(), nozzle_mm=())
    initial = policy.proposals(s, limits, ["altitude"], [policy.identity(s)])
    assert "redesign/pressure-350" in initial
    assert "redesign/thinner-fin" in initial
    assert "redesign/nose_wall_mm-0.75" in initial
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
            if kind == "benchmarks":
                value["metrics"] = {"exact_benchmarks_pass": True}
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
    geometry = [r for r in s["adaptive"]["history"] if r["action"] == "geometry"]
    assert len(geometry) == 2
    assert all(r["execution_status"] == "failed" for r in geometry)


def test_restart_edit_and_tampered_artifact_cannot_reuse_success(tmp_path):
    store, h, s = started(tmp_path, max_versions=1)
    h.confirmation = True
    s = h.run(s["id"], s["revision"])
    assert s["adaptive"]["status"] == "screening_criteria_met"
    old = s["adaptive"]["results"]["geometry"]["value"]["artifact"]
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


def test_numerical_failure_offers_refinement_before_redesign(tmp_path):
    _, h, s = started(tmp_path, exploratory_redesign=False)
    c, specification, precision, limits = h._campaign(s)
    original = h.data
    h.data = lambda campaign, key: (
        {"unmet": ["altitude", "aero_grid", "temporal"], "metrics": {"criteria_met": False}}
        if key == "confirm"
        else original(campaign, key)
    )
    choices, proposals, _ = h._choices(c, specification, precision, limits)
    assert "refine/cfd" in choices["offered"]
    assert "refine/time" in choices["offered"]
    assert not proposals


def test_interrupted_attempt_keeps_time_and_retry_accounting(tmp_path):
    store, h, s = started(tmp_path)
    c, _, _, _ = h._campaign(s)
    import time

    s["adaptive"]["pending"] = dict(
        action="geometry",
        fingerprint=c.fingerprint("geometry"),
        at=time.time() - 10,
        timeout_s=30,
        reserved_s=20,
    )
    s["adaptive"]["remaining_s"] -= 20
    store._write(s)
    s = h.step(s["id"], s["revision"])
    history = s["adaptive"]["history"]
    assert [r["execution_status"] for r in history] == ["interrupted", "completed"]
    executed_cost = c.pool.actions[history[-1]["action"]].cost_s
    assert s["adaptive"]["remaining_s"] <= s["adaptive"]["limits"]["budget_s"] - 20 - executed_cost


def test_api_rejects_runtime_paths_and_stale_revision(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api import design_projects as routes
    from api.main import app

    store = DesignProjects(tmp_path / "projects")
    monkeypatch.setattr(routes, "DEFAULT_PROJECTS", store)
    s = store.create(spec())
    client = TestClient(app)
    url = f"/design-projects/{s['id']}/adaptive"
    response = client.post(
        url + "/start",
        json={
            "revision": 0,
            "precision": {"require_cfd": False, "require_fem": False},
            "limits": {"planner": "baseline"},
        },
    )
    assert response.status_code == 200
    assert set(client.get(url + "/options").json()["offered"]) == {"geometry", "benchmarks"}
    assert client.post(url + "/step", json={"revision": 0}).status_code == 409
    assert (
        client.post(
            url + "/start", json={"revision": 1, "runtime": {"calculix": "model-selected.exe"}}
        ).status_code
        == 422
    )


def test_fem_refinement_preserves_thermal_and_flight_fingerprints(tmp_path):
    _, h, state = started(tmp_path)
    initial, _, _, _ = h._campaign(state)
    state["adaptive"]["runtime"]["fem_level"] = 3
    refined, _, _, _ = h._campaign(state)
    assert initial.fingerprint("thermal") == refined.fingerprint("thermal")
    assert initial.fingerprint("screen") == refined.fingerprint("screen")


def test_existing_search_starts_import_without_old_mass_or_pass_claims():
    from rocketwright.analysis import seeds

    s = spec()
    s.measured_printed_mass_g = 20
    choices = seeds.options()
    assert {v["label"] for v in choices.values()}
    assert len(choices) == 3
    for key in choices:
        imported = seeds.import_seed(key, s)
        assert imported.geometry == s.geometry
        assert imported.other_dry_mass_g == s.other_dry_mass_g
        assert imported.requirement == s.requirement
        assert imported.measured_printed_mass_g is None
        assert imported.assumptions.evidence["initial_search_id"] == key
    with pytest.raises(ValueError):
        seeds.import_seed("unregistered", s)


def test_pending_accuracy_blocks_redesign_until_reconfirmation(tmp_path):
    _, h, state = started(tmp_path, max_versions=3, exploratory_redesign=False)
    for _ in range(5):
        state = h.step(state["id"], state["revision"])
    assert state["adaptive"]["results"]["screen"]["execution_status"] == "completed"
    state["adaptive"]["quality_pending"] = ["fem_mesh"]
    c, specification, precision, limits = h._campaign(state)
    choices, proposals, _ = h._choices(c, specification, precision, limits)
    assert not proposals  # altitude shortfall cannot bypass unfinished precision work
    assert not any(k.startswith("refine/") for k in choices["offered"])
    assert not any(k.startswith("redesign/") for k in choices["offered"])


def test_independent_aero_failures_offer_numerical_work_and_block_redesign(tmp_path):
    _, h, s = started(tmp_path, exploratory_redesign=False)
    c, specification, precision, limits = h._campaign(s)
    original = h.data
    h.data = lambda campaign, key: (
        {
            "unmet": ["altitude", "aero_interpolation", "aero_domain_size", "aero_lattice"],
            "metrics": {},
        }
        if key == "confirm"
        else original(campaign, key)
    )
    choices, proposals, _ = h._choices(c, specification, precision, limits)
    assert {"refine/table", "refine/domain", "refine/lattice"} <= choices["offered"].keys()
    assert not proposals
