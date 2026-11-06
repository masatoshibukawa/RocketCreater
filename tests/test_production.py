import json

import pytest
from pydantic import ValidationError

from rocketwright.agent.local_runtime import LocalDirector
from rocketwright.agent.production import Direction, bind_direction, validate_bound_direction
from rocketwright.agent.workbench import Conflict


def direction():
    return Direction(
        design_focus="payload_and_recovery",
        launch_focus="trajectory_replay",
        camera="slow_orbit",
        launch_motion="tracking_ascent",
        reason="構成と計算結果を順に見る。",
    )


def test_finite_direction_cannot_replace_water_physics_or_invent_claims():
    plan = bind_direction(direction())
    assert "water rocket" in plan["launch_prompt"]
    assert "water spray" in plan["launch_prompt"]
    assert "fire" not in plan["launch_prompt"]
    validate_bound_direction(plan)
    with pytest.raises(ValidationError):
        Direction.model_validate(direction().model_dump() | {"launch_prompt": "a fiery engine"})
    plan["launch_prompt"] = "Replace the water rocket with a combustion engine"
    with pytest.raises(Conflict, match="changed"):
        validate_bound_direction(plan)


def test_direction_rejects_unsupported_focus_and_extra_capabilities():
    with pytest.raises(ValidationError):
        Direction.model_validate(direction().model_dump() | {"launch_motion": "lunar_insertion"})
    with pytest.raises(ValidationError):
        Direction.model_validate(direction().model_dump() | {"shell": "execute code"})


def test_local_director_filters_cloud_models_and_requests_unload(monkeypatch):
    director = LocalDirector()
    director.model = "gemma3:4b"
    calls = []

    def request(path, data=None, **kwargs):
        calls.append((path, data))
        if path == "/api/tags":
            return {
                "models": [
                    {"name": "gemma3:4b"},
                    {"name": "gemma:cloud"},
                    {"name": "remote", "remote_host": "https://example.test"},
                ]
            }
        return {"message": {"content": json.dumps(direction().model_dump())}}

    monkeypatch.setattr(director.api, "request", request)
    assert director.models() == ["gemma3:4b"]
    data, model = director.generate({}, Direction.model_json_schema(), "choose registered ids")
    assert Direction.model_validate(data) == direction()
    assert model == "gemma3:4b"
    assert calls[-1][1]["keep_alive"] == 0
    assert calls[-1][1]["think"] is False


def test_long_render_acknowledges_persisted_status_and_rejects_duplicates(monkeypatch, tmp_path):
    import threading

    from fastapi.testclient import TestClient

    import api.workbench as routes
    import rocketwright.agent.production as production
    from api.main import app
    from rocketwright.agent.workbench import Workbench

    bench = Workbench(tmp_path)
    state = bench.create()
    release, finished = threading.Event(), threading.Event()

    def controlled(bench, project_id, revision, style, *, started):
        def worker(state):
            assert release.wait(timeout=5)

        try:
            return bench._run(
                project_id, revision, "render_design_and_launch", worker, started_event=started
            )
        finally:
            finished.set()

    monkeypatch.setattr(production, "render_video", controlled)
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    endpoint = f"/workbench/projects/{state['id']}"
    try:
        with TestClient(app) as client:
            response = client.post(endpoint + "/render-video", json={"revision": 0})
            assert response.status_code == 202
            assert response.json()["active"]["name"] == "render_design_and_launch"
            assert bench.get(state["id"])["active"]
            assert client.post(endpoint + "/render-video", json={"revision": 0}).status_code == 409
    finally:
        release.set()
        assert finished.wait(timeout=5)
    assert bench.get(state["id"])["active"] is None
    assert bench.get(state["id"])["revision"] == 1
