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


# --------------------------------------------------------------------------- artifacts

AMATEUR_DESIGN = {
    "tier": "amateur",
    "body_diameter_m": 0.054,
    "body_length_m": 0.9,
    "nose_shape": "ogive",
    "nose_length_m": 0.15,
    "fins": {"count": 4, "root_chord_m": 0.1, "tip_chord_m": 0.05, "span_m": 0.06},
    "motor_id": "dummy-F32",
    "dry_mass_kg": 0.5,
    "payload_mass_kg": 1.0,
    "parachute_diameter_m": 0.6,
    "deploy_delay_s": 4.0,
}


def test_render_artifact_then_get_svg():
    r = client.post("/artifacts/render", json={"design": AMATEUR_DESIGN})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "amateur"
    assert body["svg_chars"] > 0
    path = body["download"]["svg"]
    assert path == f"/artifacts/{body['id']}.svg"

    g = client.get(path)
    assert g.status_code == 200
    assert g.headers["content-type"].startswith("image/svg+xml")
    assert g.text.startswith("<svg")
    assert len(g.text) == body["svg_chars"]


def test_render_artifact_rejects_bad_design():
    r = client.post("/artifacts/render", json={"design": {"tier": "amateur"}})
    assert r.status_code == 422


def test_get_artifact_404_for_unknown_or_bad_ext():
    assert client.get("/artifacts/svg_999999.svg").status_code == 404
    assert client.get("/artifacts/svg_1.exe").status_code == 404


def test_report_artifacts_served_with_media_types():
    from rocketwright.agent.tools import execute_tool

    sim = {
        "tier": "amateur",
        "success": False,
        "failure_reasons": ["apogee 812.0 m outside +-10% of target 1500.0 m"],
        "metrics": {"apogee_m": 812.0, "descent_speed_mps": 5.1},
        "cost_jpy": 40_000.0,
        "source_id": "toolu_api_sim",
    }
    out = execute_tool(
        "export_report",
        {
            "design": AMATEUR_DESIGN,
            "result_json": json.dumps(sim),
            "requirement": None,
            "dispersion_json": None,
        },
        "toolu_api_rep",
    )
    assert "error" not in out, out
    md = client.get(out["download"]["report"])
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"]
    assert "toolu_api_sim" in md.text
    bom = client.get(out["download"]["bom"])
    assert bom.status_code == 200
    assert bom.headers["content-type"].startswith("text/csv")
    assert bom.text.splitlines()[0] == "item_id,name,qty,mass_kg,price_jpy,source_or_provisional"
    js = client.get(out["download"]["json"])
    assert js.status_code == 200
    assert js.json()["tier"] == "amateur"
