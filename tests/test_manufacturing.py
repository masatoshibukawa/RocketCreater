"""Design-bound local CAD/slice exports, range gates and verified downloads."""

import math
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.manufacturing as routes
from api.main import app
from rocketwright.manufacturing import (
    ROOT,
    PrintGeometry,
    PrintRequest,
    PrintStore,
    centered_stl,
    parameters,
    runtime,
)
from rocketwright.schema import BottleDesign


def design(volume=0.0015):
    return BottleDesign(
        bottle_volume_m3=volume,
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=300000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.12,
    )


def test_geometry_follows_new_design_and_keeps_explicit_units():
    a, b = parameters(PrintRequest(design=design())), parameters(PrintRequest(design=design(0.002)))
    assert a["units"] == b["units"] == "mm"
    assert a["fin"]["root_chord"] != b["fin"]["root_chord"]
    assert a["bottle"]["body_diameter"] != b["bottle"]["body_diameter"]
    assert a["print_assumption"]["outer_brim_mm"] == 20
    assert a["bottle"]["fit_measured"] is False
    f = a["fin"]
    angle = math.radians(f["print_rotation_y_deg"])
    assert abs(f["span"] * math.sin(angle) - f["tip_trailing_offset"] * math.cos(angle)) < 1e-8


def test_zero_trailing_offset_is_a_valid_planform_but_outside_tip_is_rejected():
    g = PrintGeometry(
        body_diameter_mm=90,
        body_height_mm=305,
        nose_length_mm=100,
        fin_root_mm=70,
        fin_tip_mm=35,
        fin_span_mm=140,
        fin_sweep_mm=35,
    )
    assert parameters(PrintRequest(design=design(), geometry=g))["fin"]["tip_trailing_offset"] == 0
    with pytest.raises(ValidationError):
        PrintGeometry(**(g.model_dump() | {"fin_sweep_mm": 36}))


def test_oversized_mesh_does_not_get_silently_rescaled(tmp_path):
    source = ROOT / "3d model/prototypes/pet-rocket-coke-2l/improved/fin.stl"
    with pytest.raises(ValueError, match="does not fit"):
        centered_stl(source, tmp_path / "out.stl", [40, 40, 40])
    assert not (tmp_path / "out.stl").exists()


def test_unknown_printer_and_missing_download_reject_without_running_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "DEFAULT_PRINT_STORE", PrintStore(tmp_path))
    with TestClient(app) as client:
        assert (
            client.post(
                "/manufacturing/packages",
                json={"design": design().model_dump(), "printer": "another-printer"},
            ).status_code
            == 422
        )
        assert (
            client.get("/manufacturing/packages/" + "a" * 32 + "/files/fin.stl").status_code == 404
        )


@pytest.mark.skipif(
    not runtime()["available"], reason="Local Blender/CuraEngine/materials not installed"
)
@pytest.mark.parametrize("case", ["1.5L", "2L", "workbench"])
def test_actual_api_builds_closed_design_bound_parts_and_machine_slices(
    monkeypatch, tmp_path, case
):
    store = PrintStore(tmp_path)
    monkeypatch.setattr(routes, "DEFAULT_PRINT_STORE", store)
    request = {"design": design(0.002 if case == "2L" else 0.0015).model_dump()}
    if case == "workbench":
        request["geometry"] = dict(
            body_diameter_mm=90,
            body_height_mm=305,
            nose_length_mm=100,
            fin_root_mm=70,
            fin_tip_mm=35,
            fin_span_mm=140,
            fin_sweep_mm=35,
        )
    with TestClient(app) as client:
        response = client.post("/manufacturing/packages", json=request)
        assert response.status_code == 200, response.text
        result = response.json()
        manifest = result["manifest"]
        assert manifest["source_design"] == request["design"]
        assert manifest["physical_print_verified"] is False
        assert manifest["substitution_requires_mass_and_flight_reanalysis"] is True
        assert {p["part"] for p in manifest["parts"]} == {"fin", "nose", "fit-ring"}
        for p in manifest["parts"]:
            assert p["all_print_paths_inside_s5"] and not p["missing_model_layers"]
            assert p["brim_width_mm"] >= 20 and p["brim_gap_mm"] == 0
            assert p["solid_centroid_support_margin_mm"] >= 2
            assert max(p["extrusion_speed_max_mm_s_by_type"].values()) <= 35.01
        files = {f["name"]: f for f in result["files"]}
        geometry_report = client.get(files["geometry-check.json"]["url"]).json()
        assert all(len(part["preview_visible_meshes"]) == 1 for part in geometry_report.values())
        assert {"fin-mm.3mf", "fin-S5.ufp", "nose-S5.ufp", "print-package.zip"} <= files.keys()
        model = client.get(files["fin-mm.3mf"]["url"]).content
        import io

        with zipfile.ZipFile(io.BytesIO(model)) as archive:
            assert archive.testzip() is None
            root = ET.fromstring(archive.read("3D/3dmodel.model"))
            assert root.attrib["unit"] == "millimeter"
            edges = Counter()
            for t in root.findall(".//{*}triangle"):
                a, b, c = [int(t.attrib[k]) for k in ["v1", "v2", "v3"]]
                for u, v in [(a, b), (b, c), (c, a)]:
                    edges[tuple(sorted((u, v)))] += 1
            assert set(edges.values()) == {2}
        for name in ["fin-preview.png", "nose-preview.png"]:
            payload = client.get(files[name]["url"]).content
            assert payload.startswith(b"\x89PNG") and b"C:\\Users" not in payload
        nose = next(p for p in manifest["parts"] if p["part"] == "nose")
        expected = (
            request.get("geometry")
            or PrintGeometry.from_design(design(0.002 if case == "2L" else 0.0015)).model_dump()
        )["nose_length_mm"]
        assert abs(nose["dimensions_mm"][2] - expected) < 0.05
        bad = store.directory(result["id"]) / "fin-S5.ufp"
        bad.write_bytes(b"tampered")
        assert client.get(files["fin-S5.ufp"]["url"]).status_code == 422
