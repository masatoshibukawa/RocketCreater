"""Template choices stay editable and unanalysed; CAD reuse cannot carry old flight results."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rocketwright.agent.airframe_parts import context, publish_parts
from rocketwright.agent.airframe_templates import (
    TemplateRequest,
    create,
    make_spec,
    recommend,
)
from rocketwright.agent.video_cache import file_sha
from tests.test_design_projects import store as store


@pytest.mark.parametrize("template_id,litres", [("pet-1l", 1), ("pet-15l", 1.5), ("pet-2l", 2)])
def test_registered_templates_are_valid_unmeasured_editable_designs(template_id, litres):
    request = TemplateRequest(template_id=template_id)
    spec = make_spec(request)
    assert spec.design.bottle_volume_m3 * 1000 == litres
    assert not spec.geometry.dimensions_measured
    assert spec.geometry.fin_count == 4 and spec.measured_printed_mass_g is None
    assert spec.geometry.fin_root_mm + spec.geometry.fin_tail_inset_mm <= spec.geometry.nose_base_mm
    tuned = spec.geometry.model_dump() | {"fin_span_mm": spec.geometry.fin_span_mm + 5}
    edited = make_spec(TemplateRequest(template_id=template_id, geometry=tuned, payload_g=80))
    assert edited.geometry.fin_span_mm == tuned["fin_span_mm"]
    assert edited.design.payload_mass_kg == 0.08


def test_choice_cannot_inject_geometry_or_select_an_unregistered_model():
    class Director:
        def generate(self, context, schema, instruction):
            assert len(context["registered_templates"]) == 3
            return {"template_id": "pet-15l", "reason": "1.5 Lの依頼に対応"}, "local-fixture"

    assert recommend("1.5 Lで回収付き", Director())["template_id"] == "pet-15l"
    with pytest.raises(ValidationError):
        TemplateRequest(template_id="external-path")
    with pytest.raises(ValidationError):
        TemplateRequest(template_id="pet-1l", source_path="arbitrary.stl")


def test_verified_part_cache_reuses_only_geometry_and_recomputes_mass_and_flight(
    store, monkeypatch
):
    monkeypatch.setenv("ROCKETWRIGHT_AIRFRAME_CACHE", str(store.root / "shared-parts"))
    request = TemplateRequest(template_id="pet-15l")
    first = create(store, request)
    first = store.analyse(first["id"], first["revision"])
    path = store.directory(first["id"]) / "cad/parameters.json"
    path.write_text("{}")  # Test CAD builder omits this generated file.
    first["analysis"]["cad_sha256"][path.name] = file_sha(path)
    store._write(first)
    publish_parts(store, first)
    second = create(store, request.model_copy(update={"payload_g": 80}))
    assert second["cad_reuse"]["from_template"] == "pet-15l"
    assert second["analysis"] is None and not second["adopted"]

    import rocketwright.agent.design_projects as projects

    def forbidden(*args):
        raise AssertionError("Identical verified CAD should be reused")

    monkeypatch.setattr(projects, "prepare_geometry", forbidden)
    second = store.analyse(second["id"], second["revision"])
    assert second["analysis"]["design"]["payload_mass_kg"] == 0.08
    assert (
        second["analysis"]["result"]["metrics"]["apogee_m"]
        != first["analysis"]["result"]["metrics"]["apogee_m"]
    )
    # A corrupted cached file and a changed geometry must both miss.
    _, key, cache, _ = context(first)
    (cache.directory("parts", key) / "nose-mm.stl").write_bytes(b"damaged")
    assert not create(store, request).get("cad_reuse")
    changed = request.model_copy(
        update={"geometry": make_spec(request).geometry.model_copy(update={"fin_span_mm": 70})}
    )
    assert not create(store, changed).get("cad_reuse")


def test_api_lists_templates_and_creates_an_unadopted_project(store, monkeypatch):
    import api.design_projects as routes
    from api.main import app

    monkeypatch.setattr(routes, "DEFAULT_PROJECTS", store)
    monkeypatch.setenv("ROCKETWRIGHT_AIRFRAME_CACHE", str(store.root / "shared-parts"))
    with TestClient(app) as client:
        response = client.get("/design-projects/airframe-templates")
        assert response.status_code == 200 and len(response.json()["templates"]) == 3
        response = client.post(
            "/design-projects/from-airframe-template", json={"template_id": "pet-2l"}
        )
        assert response.status_code == 200
        state = response.json()
        assert not state["adopted"] and state["analysis"] is None
        assert state["airframe_template"]["id"] == "pet-2l"
        assert (
            client.post(
                "/design-projects/from-airframe-template", json={"template_id": "other"}
            ).status_code
            == 422
        )
