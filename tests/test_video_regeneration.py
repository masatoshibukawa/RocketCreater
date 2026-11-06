"""A failed replacement must leave the previous registered movie usable."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rocketwright.agent import production
from rocketwright.agent.local_runtime import LocalRuntimeError
from rocketwright.agent.project_jobs import progress
from rocketwright.agent.workbench import Conflict
from tests.test_design_projects import adopted
from tests.test_design_projects import store as store


@pytest.mark.parametrize("style", ["engineering", "photographic"])
def test_regeneration_failure_preserves_old_movie_and_retry_uses_pending_directory(
    store, monkeypatch, style
):
    state = adopted(store)
    state = production.plan_video(store, state["id"], state["revision"], local=False, style=style)
    monkeypatch.setattr(
        production,
        "media_settings",
        lambda: dict(blender=Path(sys.executable), python=Path(sys.executable), libs=store.root),
    )
    monkeypatch.setattr(production, "freeze_assets", lambda directory: {})
    fail = False
    rendered = []

    def native_fixture(command, **kwargs):
        nonlocal fail
        if "--background" in command:
            path = Path(command[-1])
            rendered.append(path.parent.name)
            job = json.loads(path.read_text(encoding="utf-8"))
            (path.parent / "progress.json").write_text(
                json.dumps(dict(job_id=job["job_id"], completed=1, total=2))
            )
            running = store.load(state["id"])["active"]
            assert progress(store, state["id"], running)["completed"] == 1
        else:
            path = Path(command[2])
            (path.parent / "launch-cg.mp4").write_bytes(str(len(rendered)).encode())
            if fail:
                raise subprocess.CalledProcessError(1, command)
            (path.parent / "verification.json").write_text('{"passed":true}')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(production.subprocess, "run", native_fixture)
    state = production.render_video(store, state["id"], state["revision"], style)
    kind = "photographic_video" if style == "photographic" else "video"
    old = next(f.copy() for f in state["files"] if f["kind"] == kind and f["name"].endswith("mp4"))
    original = store.file(state["id"], old["key"]).read_bytes()
    source = store.file(state["id"], "production/report.json").read_bytes()
    with pytest.raises(Conflict):
        production.render_video(store, state["id"], state["revision"], style)
    state = store.get(state["id"])
    fail = True
    with pytest.raises(LocalRuntimeError):
        production.render_video(store, state["id"], state["revision"], style, regenerate=True)
    state = store.get(state["id"])
    assert next(f for f in state["files"] if f["key"] == old["key"])["kind"] == kind
    assert store.file(state["id"], old["key"]).read_bytes() == original
    pending = rendered[-1]
    fail = False
    state = production.render_video(store, state["id"], state["revision"], style, regenerate=True)
    assert rendered[-1] == pending != rendered[0]
    current = next(f for f in state["files"] if f["kind"] == kind and f["name"].endswith("mp4"))
    assert current["key"] != old["key"]
    assert next(f for f in state["files"] if f["key"] == old["key"])["kind"] == kind + "_history"
    assert store.file(state["id"], old["key"]).read_bytes() == original
    assert store.file(state["id"], "production/report.json").read_bytes() == source
    assert state["version"] == 1


def test_current_project_api_dispatches_explicit_regeneration(store, monkeypatch):
    from fastapi.testclient import TestClient

    import api.design_projects as routes
    from api.main import app

    state = adopted(store)
    calls = []

    def queue(bench, project_id, revision, operation, style, *, regenerate):
        calls.append((project_id, revision, operation, style, regenerate))
        return bench.get(project_id)

    monkeypatch.setattr(routes, "DEFAULT_PROJECTS", store)
    monkeypatch.setattr(routes, "queue", queue)
    with TestClient(app) as client:
        response = client.post(
            f"/design-projects/{state['id']}/render-video",
            json={"revision": state["revision"], "style": "photographic", "regenerate": True},
        )
    assert response.status_code == 202
    assert calls == [(state["id"], state["revision"], "render_video", "photographic", True)]
