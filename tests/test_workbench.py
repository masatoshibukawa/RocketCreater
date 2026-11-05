import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.workbench as routes
from api.main import app
from rocketwright.agent.local_runtime import LocalJSON
from rocketwright.agent.workbench import Conflict, StepChoice, Workbench

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bench(tmp_path):
    return Workbench(tmp_path)


def test_step_checkpoints_persist_and_reject_skips_and_stale_revisions(bench):
    state = bench.create()
    project_id = state["id"]
    with pytest.raises(Conflict, match="Confirm"):
        bench.export(project_id, 0)
    state = bench.get(project_id)
    with pytest.raises(ValueError, match="listed ID"):
        bench.step(
            project_id,
            state["revision"],
            StepChoice(id="confirm/D02/9/400/25/carton_wide", reason="skip evidence"),
        )
    state = bench.get(project_id)
    original_revision = state["revision"]
    state = bench.step(
        project_id,
        original_revision,
        StepChoice(id="component/D02/9/300/25/carton_plain", reason="inspect reference fins"),
    )
    assert state["history"][-1]["result"]["eligible"] is False
    assert Workbench(bench.root).get(project_id)["history"] == state["history"]
    with pytest.raises(Conflict, match="revision"):
        bench.step(
            project_id,
            original_revision,
            StepChoice(id=state["recommendation"], reason="stale browser tab"),
        )


def test_model_proposal_is_validated_and_does_not_execute_analysis(bench):
    class Director:
        def generate(self, context, schema, instructions):
            return {"id": context["eligible"][0], "reason": "基準案から確認する"}, "local-test"

    state = bench.create()
    state = bench.propose(state["id"], 0, Director())
    assert not state["history"]
    assert state["proposal"]["id"] in {o["id"] for o in state["options"]}

    class InvalidDirector:
        def generate(self, *args):
            return {"id": "run arbitrary shell", "reason": "wrong output"}, "local-test"

    with pytest.raises(Conflict, match="ineligible"):
        bench.propose(state["id"], state["revision"], InvalidDirector())
    assert not bench.get(state["id"])["history"]


def test_workshop_replay_exports_same_design_and_integrity_checked_downloads(bench):
    state = bench.create()
    choices = json.loads((ROOT / "scenarios/bottle_prototype_choices.json").read_text())
    for choice in choices:
        state = bench.step(state["id"], state["revision"], StepChoice(**choice))
    assert state["confirmed"]
    state = bench.export(state["id"], state["revision"])
    history = state["history"]
    state = bench.manual(state["id"], state["revision"])
    pdf = next(f for f in state["files"] if f["kind"] == "manual")
    assert bench.file(state["id"], pdf["key"]).read_bytes().startswith(b"%PDF-")
    assert state["history"] == history  # Viewing/printing cannot complete a physical step.
    with pytest.raises(Conflict, match="already exists"):
        bench.manual(state["id"], state["revision"])
    names = {f["name"] for f in state["files"]}
    assert {"payload-collar-mm.stl", "fin-marking-jig-mm.stl", "report.json", "trace.json"} <= names
    report_file = next(f for f in state["files"] if f["name"] == "report.json")
    path = bench.file(state["id"], report_file["key"])
    assert json.loads(path.read_text(encoding="utf-8"))["design"] == state["design"]
    path.write_text("tampered")
    with pytest.raises(Conflict, match="changed"):
        bench.file(state["id"], report_file["key"])
    with pytest.raises(KeyError):
        bench.file(state["id"], "../../state.json")


def test_api_checkpoints_validation_and_resume(monkeypatch, bench):
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    with TestClient(app) as client:
        assert (
            client.post(
                "/workbench/projects", json={"workshop": {"unavailable": ["bad"]}}
            ).status_code
            == 422
        )
        state = client.post("/workbench/projects", json={}).json()
        endpoint = f"/workbench/projects/{state['id']}"
        assert client.get(endpoint).json()["revision"] == 0
        assert client.post(endpoint + "/exports", json={"revision": 0}).status_code == 409
        state = client.get(endpoint).json()
        assert (
            client.post(
                endpoint + "/assembly-pdf", json={"revision": state["revision"]}
            ).status_code
            == 409
        )
        assert client.get("/workbench/projects/not-an-id").status_code == 404
        assert client.get(endpoint + "/files/state.json").status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost@evil.test",
        "http://127.0.0.1:8188/path",
        "http://127.0.0.1:8188?redirect=1",
    ],
)
def test_local_inference_rejects_external_or_ambiguous_origins(url):
    with pytest.raises(ValueError, match="loopback"):
        LocalJSON(url)
