"""FastAPI tests: /health and the SSE stream of POST /design (loop monkeypatched, no network)."""

import json

from fastapi.testclient import TestClient

import api.main as main
from rocketwright.agent.events import AgentEvent

client = TestClient(main.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_design_streams_events(monkeypatch):
    seen: dict = {}

    async def fake_loop(text: str, **kwargs):
        seen["text"] = text
        seen["kwargs"] = kwargs
        yield AgentEvent(type="text", attempt=0, payload={"text": "hello"}, t_s=0.0)
        yield AgentEvent(type="final", attempt=2, payload={"result": {"designs": []}}, t_s=1.5)

    monkeypatch.setattr(main, "run_design_loop", fake_loop)
    with client.stream("POST", "/design", json={"text": "go to 2 km", "seed": 5}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())

    frames = [f for f in body.split("\n\n") if f.strip()]
    assert len(frames) == 2
    assert frames[0].startswith("event: text\ndata: ")
    assert frames[1].startswith("event: final\ndata: ")
    data = json.loads(frames[1].split("data: ", 1)[1])
    assert data["attempt"] == 2
    assert data["payload"]["result"] == {"designs": []}
    assert seen["text"] == "go to 2 km"
    assert seen["kwargs"]["seed"] == 5


def test_design_rejects_empty_text():
    r = client.post("/design", json={"text": ""})
    assert r.status_code == 422


def test_cors_allows_localhost_3000():
    r = client.options(
        "/design",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
