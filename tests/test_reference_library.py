import json
import shutil

import pytest
from fastapi.testclient import TestClient

import api.workbench as routes
from api.main import app
from rocketwright.agent.library import CAD, FILM, PARTS, ROOT, ReferenceLibrary
from rocketwright.agent.workbench import Conflict


@pytest.fixture
def library(tmp_path):
    for path in (CAD, FILM):
        shutil.copytree(
            ROOT / path, tmp_path / path, ignore=shutil.ignore_patterns("renders", "cache")
        )
    return ReferenceLibrary(tmp_path)


def test_real_catalog_and_verified_cad_have_separate_case_identity():
    library = ReferenceLibrary()
    view = library.view()
    assert view["geometry"]["measured"] is False
    assert view["geometry"]["fin_count"] == 3
    assert view["references"]["water"] >= 98
    assert view["references"]["model"] >= 50
    assert all(library.file(key).suffix == ".stl" for key in PARTS)
    result = library.references("ＮＡＳＡ", "water")
    assert result["total"] > 0
    assert all(row["group"] == "water" and "local" not in row for row in result["records"])
    assert not library.references("rocket", "invalid")["records"]


def test_missing_modified_and_mismatched_assets_are_not_downloadable(library):
    with pytest.raises(KeyError):
        library.file("launch-film")
    with pytest.raises(KeyError):
        library.file("../parameters.json")
    library.file("fin").write_text("changed geometry")
    with pytest.raises(Conflict, match="verified snapshot"):
        library.file("fin")
    path = library.root / CAD / "parameters.json"
    params = json.loads(path.read_text())
    params["bottle"]["body_diameter"] = 130
    path.write_text(json.dumps(params))
    with pytest.raises(Conflict, match="snapshots differ"):
        library.file("nose")


def test_library_api_is_read_only_and_range_downloads_work(monkeypatch):
    monkeypatch.setattr(routes, "DEFAULT_LIBRARY", ReferenceLibrary())
    with TestClient(app) as client:
        view = client.get("/workbench/library")
        assert view.status_code == 200
        response = client.get("/workbench/library/assets/fin", headers={"Range": "bytes=0-83"})
        assert response.status_code == 206
        assert len(response.content) == 84
        assert client.get("/workbench/library/assets/unknown").status_code == 404
        assert client.get("/workbench/references?category=bad").status_code == 422
        assert client.get("/workbench/references?q=D02&category=water").json()["total"] == 1
