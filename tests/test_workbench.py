import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.workbench as routes
from api.main import app
from rocketwright.agent.local_runtime import LocalJSON
from rocketwright.agent.workbench import Conflict, StepChoice, Workbench
from rocketwright.bottle_assembly import Workshop

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


def test_workshop_replay_exports_same_design_and_integrity_checked_downloads(bench, monkeypatch):
    # Numerical search fixture, not an equipment pressure rating. The default
    # 400 kPa ceiling must remain unchanged even if a new model cannot reach target.
    workshop = Workshop.model_validate_json(
        (ROOT / "scenarios/bottle_empty_workshop.json").read_text()
    ).model_copy(update={"pressure_ceiling_kpa": 500})
    state = bench.create(workshop)
    choices = json.loads((ROOT / "scenarios/bottle_prototype_choices.json").read_text())
    for choice in choices[:4]:
        state = bench.step(state["id"], state["revision"], StepChoice(**choice))
    # Follow only eligible IDs, rather than replaying an obsolete pressure result.
    for _ in range(20):
        if state["confirmed"]:
            break
        eligible = [
            o
            for o in state["options"]
            if o["architecture"] == "D02" and o["variant"] == "carton_wide"
        ]
        priority = {"confirm": 0, "screen": 1, "flight": 2, "component": 3}
        chosen = min(eligible, key=lambda o: (priority[o["method"]], -o["pressure_kpa"]))
        state = bench.step(
            state["id"],
            state["revision"],
            StepChoice(id=chosen["id"], reason="Recalculate an eligible candidate"),
        )
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
    # Real Blender/Cura builds are covered separately; here test the frozen-source
    # boundary, revision gate and download registry through the workbench API.
    import rocketwright.manufacturing as manufacturing

    captured = []

    def inspected_fixture(request, directory):
        captured.append(request)
        directory.mkdir()
        (directory / "fin-S5.ufp").write_bytes(b"inspected-fixture")
        return {"status": "slice_checked_physical_trial_pending"}

    monkeypatch.setattr(manufacturing, "prepare", inspected_fixture)
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    frozen_report = path.read_bytes()
    assembly = json.loads(
        bench.file(state["id"], "production/assembly.json").read_text(encoding="utf-8")
    )
    endpoint = f"/workbench/projects/{state['id']}/print-package"
    with TestClient(app) as client:
        assert client.post(endpoint, json={"revision": 0}).status_code == 409
        assert not captured
        path.write_bytes(b"changed after export")
        response = client.post(endpoint, json={"revision": state["revision"]})
        assert response.status_code == 409 and "changed" in response.text
        assert not captured
        path.write_bytes(frozen_report)
        state = bench.get(state["id"])
        response = client.post(endpoint, json={"revision": state["revision"]})
        assert response.status_code == 200, response.text
        state = response.json()
        assert len(captured) == 1
        assert captured[0].design.model_dump(mode="json") == state["design"]
        assert captured[0].geometry == manufacturing.PrintGeometry.from_plan(
            assembly["dimensions_mm"]
        )
        assert state["history"] == history
        printed = next(f for f in state["files"] if f["kind"] == "manufacturing")
        assert client.get(printed["url"]).content == b"inspected-fixture"
        bench.file(state["id"], printed["key"]).write_bytes(b"tampered")
        assert client.get(printed["url"]).status_code == 409
        assert client.post(endpoint, json={"revision": state["revision"]}).status_code == 409
        assert len(captured) == 1
    # A photographic production must coexist with the shorter engineering clips.
    from rocketwright.agent.production import plan_video

    state = bench.get(state["id"])
    state = plan_video(bench, state["id"], state["revision"], local=False)
    engineering = state["video_plan"]
    state = plan_video(bench, state["id"], state["revision"], local=False, style="photographic")
    photo = state["photographic_video_plan"]
    assert state["video_plan"] == engineering
    assert photo["design_source"] == json.loads(frozen_report)["sim_source_id"]
    assert (
        photo["width"] == 1920 and photo["design_frames"] == 384 and photo["launch_frames"] == 288
    )
    import sys

    import rocketwright.agent.production as production
    from rocketwright.agent.production import render_video

    monkeypatch.setattr(production, "media_settings", lambda: {
        "blender": Path(sys.executable), "python": Path(sys.executable)
    })

    modified = bench.load(state["id"])
    modified["photographic_video_plan"]["width"] = 2000
    bench._write(modified)
    with pytest.raises(Conflict, match="settings changed"):
        render_video(bench, state["id"], state["revision"], style="photographic")
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
                endpoint + "/print-package", json={"revision": state["revision"]}
            ).status_code
            == 409
        )
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
