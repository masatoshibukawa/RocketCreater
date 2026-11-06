"""POST /artifacts/package: production files of one design, without a workbench project."""

from __future__ import annotations

import csv
import io
import json
import re

import pytest
from fastapi.testclient import TestClient

import api.manufacturing as routes
from api.main import app
from rocketwright import manufacturing
from rocketwright.agent.design_sheet import safety_notes, sheet_sections
from rocketwright.agent.fake_client import DEMO_PASSING_INDEX, DEMO_REQUIREMENTS, demo_designs
from rocketwright.agent.store import DEFAULT_STORE
from rocketwright.agent.tools import execute_tool
from rocketwright.manufacturing import PrintRequest, parameters
from rocketwright.schema import BottleDesign, SimResult
from rocketwright.summary import design_summary

client = TestClient(app)


def _design(tier: str) -> dict:
    return demo_designs(tier)[DEMO_PASSING_INDEX[tier]]


def _requirement(tier: str) -> dict:
    return {**DEMO_REQUIREMENTS[tier], "text": "x"}


def _auto(tier: str = "bottle") -> dict:
    return execute_tool(
        "auto_design", {"tier": tier, "requirement": _requirement(tier), "env": {}}, "auto"
    )


def _package(**body) -> dict:
    r = client.post("/artifacts/package", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _file(package: dict, kind: str) -> str:
    return next(row["url"] for row in package["files"] if row["kind"] == kind)


def test_passing_bottle_gets_every_file_the_design_can_support():
    body = _package(design=_design("bottle"), requirement=_requirement("bottle"))
    assert [row["kind"] for row in body["files"]] == ["sheet", "report", "json", "bom", "drawing"]
    pdf = client.get(_file(body, "sheet"))
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF-")
    assert client.get(_file(body, "drawing")).text.lstrip().startswith("<svg")
    assert client.get(_file(body, "report")).status_code == 200


def test_package_reports_what_a_free_design_cannot_give():
    body = _package(design=_design("bottle"))
    assert {row["item"] for row in body["unavailable"]} >= {
        "組立手順の文章",
        "原寸フィン型紙",
        "購入計画",
        "搭載部カラーと位置決め治具の STL",
    }
    assert all(row["reason"] for row in body["unavailable"])


def test_report_carries_the_dispersion_of_the_given_seed_and_n():
    design = _design("bottle")
    body = _package(design=design, requirement=_requirement("bottle"), seed=7, n=30)
    report = client.get(_file(body, "json")).json()
    expected = execute_tool(
        "run_dispersion",
        {"design": design, "requirement": _requirement("bottle"), "seed": 7, "n": 30},
        "x",
    )
    assert report["dispersion"]["n"] == 30
    assert report["dispersion"]["success_rate"] == pytest.approx(expected["success_rate"])


def test_a_failing_design_gets_no_files():
    design = _design("bottle") | {"initial_gauge_pressure_pa": 150000.0}
    before = len(DEFAULT_STORE)
    r = client.post(
        "/artifacts/package", json={"design": design, "requirement": _requirement("bottle")}
    )
    assert r.status_code == 409
    assert "合格しませんでした" in r.json()["detail"]
    assert len(DEFAULT_STORE) == before


def test_a_design_is_judged_in_the_env_it_is_sent_with():
    """The same design passes or fails with its launch conditions, so the screen sends them."""
    design = _design("bottle")
    body = {"design": design, "requirement": _requirement("bottle")}
    assert client.post("/artifacts/package", json=body).status_code == 200
    hot = {"temperature_offset_k": 0.0, "launch_altitude_m": 8000.0}
    assert client.post("/artifacts/package", json=body | {"env": hot}).status_code == 409


def test_parts_build_keeps_its_bill_and_stability():
    auto = _auto()
    assert auto["sim"]["success"] is True
    body = _package(
        design=auto["design"], build=auto["build"], requirement=_requirement("bottle"), env={}
    )
    bill = {row["part_id"] for row in auto["bill"]["parts"]}
    rows = list(csv.DictReader(io.StringIO(client.get(_file(body, "bom")).text)))
    assert {row["item_id"] for row in rows} == bill
    report = client.get(_file(body, "json")).json()
    keys = {row["key"] for row in report["metrics"]}
    assert {"stability_margin_cal", "dry_stability_margin_cal"} <= keys


def test_amateur_gets_the_report_files_but_no_bottle_sheet():
    body = _package(design=_design("amateur"), requirement=_requirement("amateur"))
    assert [row["kind"] for row in body["files"]] == ["report", "json", "bom", "drawing"]
    assert any("製作票" in row["item"] for row in body["unavailable"])


@pytest.mark.parametrize("tier", ["commercial", "heavy"])
def test_multistage_designs_get_no_production_files(tier):
    r = client.post("/artifacts/package", json={"design": _design(tier)})
    assert r.status_code == 422
    assert "ボトルとアマチュア" in r.json()["detail"]


def test_a_build_with_errors_is_refused():
    auto = _auto()
    build = auto["build"] | {"bottle_id": "no_such_bottle"}
    r = client.post("/artifacts/package", json={"design": auto["design"], "build": build})
    assert r.status_code == 400


def test_dispersion_size_is_bounded():
    r = client.post("/artifacts/package", json={"design": _design("bottle"), "n": 501})
    assert r.status_code == 422


@pytest.mark.parametrize("volume_m3", [0.0005, 0.001, 0.0015, 0.002])
def test_print_data_starts_from_a_free_bottle_design(monkeypatch, tmp_path, volume_m3):
    """Blender and CuraEngine are local tools; up to them the request is the design's own."""
    design = _design("bottle") | {"bottle_volume_m3": volume_m3}
    request = PrintRequest(design=BottleDesign.model_validate(design))
    assert parameters(request)["bottle"]["body_diameter"] > 0

    def prepare(received, directory):
        assert received.design == request.design and received.geometry is None
        directory.mkdir(parents=True)
        (directory / "fin-mm.stl").write_bytes(b"solid")
        return {"status": "fake", "parts": []}

    monkeypatch.setattr(manufacturing, "prepare", prepare)
    monkeypatch.setattr(
        manufacturing, "DEFAULT_PRINT_STORE", manufacturing.PrintStore(tmp_path / "print")
    )
    monkeypatch.setattr(routes, "DEFAULT_PRINT_STORE", manufacturing.DEFAULT_PRINT_STORE)
    r = client.post("/manufacturing/packages", json={"design": design})
    assert r.status_code == 200, r.text
    assert client.get(r.json()["files"][0]["url"]).content == b"solid"


def _sections(design_json: dict, requirement: dict | None = None) -> dict[str, dict[str, str]]:
    design = BottleDesign.model_validate(design_json)
    sim = SimResult.model_validate(
        execute_tool("simulate_design", {"design": design_json, "requirement": requirement}, "s")
    )
    return sheet_sections(design, sim, design_summary(design), None)


def test_sheet_values_are_the_designs_and_the_simulations():
    design = _design("bottle")
    sections = _sections(design, _requirement("bottle"))
    launch = sections["打ち上げの条件"]
    water_ml = design["bottle_volume_m3"] * design["water_fill_frac"] * 1e6
    assert launch["注水量"] == f"{water_ml:.0f} mL"
    assert launch["初期圧力差"] == f"{design['initial_gauge_pressure_pa'] / 1000:.0f} kPa"
    assert launch["噴射口の径"] == f"{design['nozzle_diameter_m'] * 1000:.1f} mm"
    assert launch["パラシュートの直径"] == f"{design['parachute_diameter_m'] * 1000:.0f} mm"
    assert sections["シミュレーションの結果"]["判定"] == "合格"


def test_sheet_states_no_body_dimensions_a_design_does_not_fix():
    """summary.py and the side view reach different representative sizes; a design fixes neither."""
    text = json.dumps(_sections(_design("bottle")), ensure_ascii=False)
    assert "全長" not in text and "胴体径" not in text


def test_sheet_says_a_margin_was_not_computed_rather_than_inventing_one():
    results = _sections(_design("bottle"))["シミュレーションの結果"]
    assert results["静安定余裕（注水時）"] == "未算出（部品のフィン未選択）"
    assert results["静安定余裕（空のとき）"] == "未算出（部品のフィン未選択）"


def test_sheet_never_quotes_the_recipe_dimensions():
    """The 1.5 L recipe's numbers belong to its own vehicle, not to a free design."""
    text = json.dumps(_sections(_design("bottle")), ensure_ascii=False)
    assert not re.search(r"搭載室|傘室|スカート|型紙", text)


def test_the_sheet_carries_launch_safety_notes_with_the_designs_pressure():
    design = BottleDesign.model_validate(_design("bottle"))
    notes = safety_notes(design)
    assert notes[0].startswith(f"圧力は {design.initial_gauge_pressure_pa / 1000:.0f} kPa まで")
    assert any("保護めがね" in note for note in notes)
    assert any("離れて" in note for note in notes)
