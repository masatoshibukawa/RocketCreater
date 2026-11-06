"""FastAPI tests: /health and the SSE stream of POST /design (loop monkeypatched, no network)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as main
from rocketwright.agent.events import AgentEvent

client = TestClient(main.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_points_to_ui_and_docs():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "localhost:3000" in body["ui"]
    assert body["docs"] == "/docs"


def test_design_streams_events(monkeypatch):
    monkeypatch.setenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN", "1")
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
        assert "no-transform" in r.headers["cache-control"]
        assert r.headers["x-accel-buffering"] == "no"
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


def test_paid_design_is_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN", raising=False)

    async def must_not_call(*args, **kwargs):
        raise AssertionError("Paid design loop must not be reached")
        yield

    monkeypatch.setattr(main, "run_design_loop", must_not_call)
    assert client.post("/design", json={"text": "design a rocket"}).status_code == 423


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


def test_summary_artifact_for_amateur_demo_design():
    from rocketwright.agent.fake_client import DEMO_REQUIREMENTS, demo_designs
    from rocketwright.cost import estimate_cost_jpy
    from rocketwright.schema import DesignAdapter

    design = demo_designs("amateur")[0]
    r = client.post(
        "/artifacts/summary",
        json={"design": design, "requirement": DEMO_REQUIREMENTS["amateur"], "width_px": 600},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "tier",
        "cost_jpy",
        "cost_breakdown",
        "bom",
        "drawing",
        "mass",
        "dimensions",
    }
    assert body["tier"] == "amateur"
    assert body["cost_jpy"] == pytest.approx(
        estimate_cost_jpy(DesignAdapter.validate_python(design))
    )
    assert sum(i["jpy"] for i in body["cost_breakdown"]) == pytest.approx(body["cost_jpy"])
    assert all(set(i) == {"label", "jpy", "note", "provisional"} for i in body["cost_breakdown"])
    assert len(body["bom"]) >= 3
    assert set(body["bom"][0]) == {
        "item_id",
        "name",
        "qty",
        "mass_kg",
        "price_jpy",
        "source_or_provisional",
    }
    assert body["mass"]["liftoff_mass_kg"] > body["mass"]["payload_mass_kg"] == 1.0
    assert body["mass"]["propellant_mass_kg"] > 0  # dummy_J420 is a catalog motor
    assert body["dimensions"]["length_m"] == pytest.approx(
        design["nose_length_m"] + design["body_length_m"]
    )
    drawing = body["drawing"]
    assert drawing["url"] == f"/artifacts/{drawing['id']}.svg"
    g = client.get(drawing["url"])
    assert g.status_code == 200
    assert g.text.startswith("<svg") and 'width="600"' in g.text

    # requirement is optional; a tier override that disagrees with the design is a 400
    assert client.post("/artifacts/summary", json={"design": design}).status_code == 200
    bad = client.post(
        "/artifacts/summary",
        json={
            "design": design,
            "requirement": {**DEMO_REQUIREMENTS["amateur"], "tier_override": "bottle"},
        },
    )
    assert bad.status_code == 400
    assert "tier" in bad.json()["detail"]
    assert (
        client.post("/artifacts/summary", json={"design": {"tier": "amateur"}}).status_code == 422
    )


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


# --------------------------------------------------------------------------- SSE framing

_FRAME_RE = re.compile(r"\Aevent: ([a-z_]+)\ndata: ([^\n]+)\n\n\Z")


def _ts_event_types() -> list[str]:
    src = (Path(__file__).resolve().parent.parent / "web/app/lib/types.ts").read_text("utf-8")
    m = re.search(r"export const EVENT_TYPES\b[^=]*=\s*\[(.*?)\];", src, re.S)
    assert m
    return re.findall(r'"([^"]+)"', m.group(1))


def test_design_sse_framing_with_fake_client(monkeypatch):
    """The real loop (scripted fake Claude, real physics) streamed through the API: every frame
    is `event: <type>\\ndata: <one-line json>\\n\\n`, with types the web client knows."""
    monkeypatch.setenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN", "1")
    from rocketwright.agent.fake_client import FakeAnthropicClient, build_demo_script
    from rocketwright.agent.loop import run_design_loop

    text = "1.5 L ペットボトルで卵を割らずに 30 m まで上げて回収したい。予算 3,000 円。"
    env = {"launch_latitude_deg": 35.0, "launch_altitude_m": 20, "wind_speed_mps": 2.0}

    def loop_with_fake(request_text: str, **kwargs):
        client = FakeAnthropicClient(
            build_demo_script("bottle", request_text, env, 7, reviews=True)
        )
        return run_design_loop(request_text, client=client, **kwargs)

    monkeypatch.setattr(main, "run_design_loop", loop_with_fake)
    with client.stream("POST", "/design", json={"text": text, "seed": 7, "env": env}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())

    frames = [f + "\n\n" for f in body.split("\n\n") if f]
    assert len(frames) >= 10
    allowed = set(_ts_event_types())
    types: list[str] = []
    for frame in frames:
        m = _FRAME_RE.match(frame)
        assert m, f"bad SSE frame: {frame[:120]!r}"
        event_type, data = m.group(1), m.group(2)
        assert "\n" not in data and "\r" not in data
        parsed = json.loads(data)
        assert parsed["type"] == event_type
        assert event_type in allowed, f"web/app/lib/types.ts does not know {event_type!r}"
        AgentEvent.model_validate(parsed)
        types.append(event_type)
    assert types[-1] == "final"
    assert {"tool_call", "tool_result", "candidate", "review"} <= set(types)
    final = json.loads(_FRAME_RE.match(frames[-1]).group(2))
    assert final["payload"]["provenance_violations"] == []
    assert any(d["passed"] for d in final["payload"]["result"]["designs"])


def test_cors_preflight_exposes_methods_and_headers():
    r = client.options(
        "/design",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in r.headers["access-control-allow-methods"]
    assert "content-type" in r.headers["access-control-allow-headers"].lower()
    denied = client.options(
        "/design",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_summary_artifact_from_build(monkeypatch):
    """`build` on /artifacts/summary: cost and BOM come from the parts bill, the drawing from
    the resolved design."""
    from rocketwright import parts

    monkeypatch.setattr(
        parts, "DEFAULT_PARTS_PATH", Path(__file__).resolve().parent / "fixtures" / "parts_v2.yaml"
    )
    build = {
        "tier": "amateur",
        "body_tube_id": "estes_bt50",
        "body_length_m": 0.24,
        "nose_cone_id": "estes_pnc50",
        "motor_mount_id": "mount_18mm_bt50",
        "motor_id": "estes_C6",
        "fin_material_id": "balsa_3_32in",
        "fins": {"count": 3, "root_chord_m": 0.064, "tip_chord_m": 0.025, "span_m": 0.044},
        "parachute_id": "chute_12in",
    }
    # the design field is required by the request model but the build wins (a literal
    # placeholder: the demo designs are seeded from kit builds the fixture catalog lacks)
    placeholder = {
        "tier": "amateur",
        "body_diameter_m": 0.05,
        "body_length_m": 0.6,
        "nose_shape": "ogive",
        "nose_length_m": 0.15,
        "fins": {"count": 3, "root_chord_m": 0.1, "tip_chord_m": 0.05, "span_m": 0.06},
        "motor_id": "estes_C6",
        "dry_mass_kg": 0.3,
        "parachute_diameter_m": 0.6,
    }
    r = client.post("/artifacts/summary", json={"design": placeholder, "build": build})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cost_jpy"] == pytest.approx(body["bill"]["cost_jpy"])
    assert [row["item_id"] for row in body["bom"]] == [p["part_id"] for p in body["bill"]["parts"]]
    assert body["design"]["body_diameter_m"] == pytest.approx(0.0246)
    assert body["drawing"]["url"].endswith(".svg")
    assert body["issues"] == [] or all("severity" in i for i in body["issues"])
    bad = client.post(
        "/artifacts/summary", json={"design": placeholder, "build": dict(build, nose_cone_id="x")}
    )
    assert bad.status_code == 400 and "x" in bad.json()["detail"]
