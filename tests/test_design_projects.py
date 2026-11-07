import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from api.main import app
from rocketwright.agent import design_projects as module
from rocketwright.agent.design_projects import DesignProjects, DesignSpec
from rocketwright.agent.production import plan_video
from rocketwright.agent.project_assembly import assembly_assessment
from rocketwright.agent.project_assembly_guide import assembly_procedures
from rocketwright.agent.project_detail_drawing import axial_section
from rocketwright.agent.workbench import Conflict
from rocketwright.manufacturing import PrintGeometry
from rocketwright.schema import BottleDesign
from scripts.verify_design_package import verify


def spec():
    design = BottleDesign(
        bottle_volume_m3=0.002,
        water_fill_frac=0.3,
        initial_gauge_pressure_pa=350000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.12,
        payload_mass_kg=0.06,
        has_parachute=True,
        parachute_diameter_m=0.7,
    )
    return DesignSpec(
        name="保存と出力の確認",
        design=design,
        geometry=PrintGeometry.from_design(design),
        other_dry_mass_g=100,
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    def cad(request, directory):
        directory.mkdir()
        data = {
            name: {"volume_mm3": volume, "solid_mass_g_at_assumed_density": volume * 0.00124}
            for name, volume in [("fin", 1000), ("nose", 3000), ("fit-ring", 1000)]
        }
        (directory / "geometry-check.json").write_text(json.dumps(data))
        (directory / "nose-mm.stl").write_bytes(b"unit fixture, not an actual CAD")
        (directory / "fin-assembly-mm.stl").write_bytes(b"fixture")
        return {}, data

    monkeypatch.setattr(module, "prepare_geometry", cad)
    return DesignProjects(tmp_path / "projects")


def adopted(store):
    s = store.create(spec())
    s = store.analyse(s["id"], s["revision"])
    assert s["analysis"]["result"]["success"], s["analysis"]["result"]["failure_reasons"]
    return store.adopt(s["id"], s["revision"])


def test_persistent_revision_invalidation_restore_and_old_file_access(store):
    s = adopted(store)
    old = store.file(s["id"], "production/report.json")
    old_bytes = old.read_bytes()
    assert s["analysis"]["design"]["dry_mass_kg"] == pytest.approx(0.10868)
    original_revision = s["revision"]
    new_spec = spec().model_copy(update={"other_dry_mass_g": 140})
    s = store.edit(s["id"], original_revision, new_spec)
    assert s["version"] == 2 and s["analysis"] is None and not s["adopted"]
    with pytest.raises(Conflict):
        store.adopt(s["id"], s["revision"])
    assert store.file(s["id"], "production/report.json", 1).read_bytes() == old_bytes
    with pytest.raises(Conflict):
        store.edit(s["id"], original_revision, new_spec)
    restarted = DesignProjects(store.root)
    s = restarted.get(s["id"])
    assert s["spec"]["other_dry_mass_g"] == 140
    s = restarted.restore(s["id"], s["revision"], 1)
    assert s["version"] == 3 and s["spec"]["other_dry_mass_g"] == 100
    assert s["analysis"] is None


def test_manual_archive_integrity_and_tampering(store, tmp_path):
    s = adopted(store)
    s = store.manual(s["id"], s["revision"])
    pdf = store.file(s["id"], "manual/assembly.pdf")
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert store.file(s["id"], "manual/design-drawing.pdf").read_bytes().startswith(b"%PDF-")
    provenance = json.loads(store.file(s["id"], "manual/provenance.json").read_text())
    assert provenance["drawing_page_count"] == 1 and provenance["drawing_cad_sources"] == []
    svg = store.file(s["id"], "manual/side-view.svg").read_text(encoding="utf-8")
    assert "ノズル端を 0 mm" in svg and "翼後端 100" in svg and "4 枚 / 90° 等配" in svg
    s = store.archive(s["id"], s["revision"])
    archive = store.file(s["id"], "package/design-package.zip")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert "source/rocketwright/agent/project_package.py" in z.namelist()
        assert "reproduction/requirements.txt" in z.namelist()
        assert "scripts/reproduce_package.py" in z.namelist()
        assert "source/rocketwright/agent/project_assembly_guide.py" in z.namelist()
        assert "manual/design-drawing.pdf" in z.namelist()
        assert "manual/side-view.svg" in z.namelist()
        assert not any("node_modules" in name or "/.env" in name for name in z.namelist())
        expected = json.loads(z.read("reproduction/input.json"))
        assert expected["source_version"] == s["version"] and not expected["adaptive_required"]
        assert json.loads(z.read("manifest.json"))["physical_print_verified"] is False
        z.extractall(tmp_path / "unpacked")
    assert verify(tmp_path / "unpacked") > 5
    (tmp_path / "unpacked/production/report.json").write_text("changed")
    with pytest.raises(ValueError, match="Changed"):
        verify(tmp_path / "unpacked")
    pdf.write_bytes(b"changed")
    with pytest.raises(Conflict):
        store.file(s["id"], "manual/assembly.pdf")
    with pytest.raises(KeyError):
        store.file(s["id"], "../state.json")


def test_axial_section_deduplicates_plane_edges_and_interpolates_crossings():
    seam = ((5, 0, 2), (3, 0, 1))
    faces = (
        (*seam, (5, 2, 0)),
        (*reversed(seam), (4, -2, 4)),
        ((2, -1, 0), (4, 1, 2), (1, 1, 3)),
        ((7, 0, 7), (7, 2, 8), (9, 2, 8)),
    )
    assert axial_section(faces) == [
        ((1.0, 3.0), (1.5, 1.5)),
        ((1, 3), (2, 5)),
    ]


def test_assembly_procedures_match_saved_component_options():
    s = spec()
    guide = assembly_procedures(s, assembly_assessment(s)["cad_parameters"])
    assert "90°" in guide["fin_mount"].actions[1][1]
    assert "S1・S2" in guide["finish"].actions[-1][1]
    s = s.model_copy(
        update={"design": s.design.model_copy(update={"has_fins": False, "has_parachute": False})}
    )
    guide = assembly_procedures(s, assembly_assessment(s)["cad_parameters"])
    assert len(guide["fin_mount"].actions) == 1
    assert "S1" not in str(guide["finish"].actions)
    assert "回収傘" not in str(guide["recovery"].actions)


def test_video_plan_and_geometry_bound_to_adopted_revision(store):
    s = adopted(store)
    s = plan_video(store, s["id"], s["revision"], local=False, style="photographic")
    assert s["photographic_video_plan"]["design_source"].endswith(":v1")
    assert s["photographic_video_plan"]["style"] == "photographic"
    assert s["photographic_video_plan"]["model"] == "deterministic_recipe"


def test_api_saved_projects_validation_and_paid_guard(store, monkeypatch):
    import api.design_projects as routes

    monkeypatch.setattr(routes, "DEFAULT_PROJECTS", store)
    monkeypatch.setenv("ROCKETWRIGHT_ENABLE_CLOUD_DESIGN", "0")
    client = TestClient(app)
    response = client.post("/design-projects", json={"spec": spec().model_dump(mode="json")})
    assert response.status_code == 200
    s = response.json()
    assert client.get(f"/design-projects/{s['id']}").json()["name"] == spec().name
    assert len(client.get("/design-projects").json()["projects"]) == 1
    assert client.post(f"/design-projects/{s['id']}/adopt", json={"revision": 0}).status_code == 409
    invalid = spec().model_dump(mode="json")
    invalid["geometry"]["fin_count"] = 100
    assert client.post("/design-projects", json={"spec": invalid}).status_code == 422
    assert client.post("/design", json={"text": "test"}).status_code == 423


def test_restart_recovers_interrupted_job_and_rejects_code_changes(store, monkeypatch):
    s = adopted(store)
    s["active"] = {"name": "test", "owner": "previous-process"}
    store._write(s)
    s = DesignProjects(store.root).get(s["id"])
    assert s["active"] is None and "中断" in s["error"]
    monkeypatch.setattr(module, "implementation_fingerprint", lambda: "changed-code")
    with pytest.raises(Conflict):
        store.require_adopted(s)


def test_failed_analysis_does_not_publish_manufacturing_meshes(store):
    from rocketwright.schema import Requirement

    draft = spec().model_copy(
        update={
            "requirement": Requirement(
                goal_kind="altitude", target_altitude_m=1000, payload_mass_kg=0.06
            )
        }
    )
    s = store.create(draft)
    s = store.analyse(s["id"], s["revision"])
    assert not s["analysis"]["result"]["success"]
    assert not any(f["name"] == "fin-assembly-mm.stl" for f in s["files"])
    with pytest.raises(KeyError):
        store.file(s["id"], "cad/fin-assembly-mm.stl")
    with pytest.raises(Conflict):
        store.adopt(s["id"], s["revision"])


def test_input_capacity_cannot_exceed_external_geometry():
    data = spec().model_dump(mode="json")
    data["geometry"]["body_diameter_mm"] = 30
    with pytest.raises(ValueError, match="最大体積"):
        DesignSpec.model_validate(data)


def test_requirement_payload_and_recovery_must_match_computed_inputs():
    data = spec().model_dump(mode="json")
    data["requirement"] = dict(goal_kind="altitude", target_altitude_m=24, payload_mass_kg=1)
    with pytest.raises(ValueError, match="搭載質量"):
        DesignSpec.model_validate(data)
    data["requirement"].update(payload_mass_kg=0.06, recovery_required=True)
    data["design"]["has_parachute"] = False
    with pytest.raises(ValueError, match="回収"):
        DesignSpec.model_validate(data)


def test_unpriced_budget_is_not_a_pass_even_after_prototype_adoption(store):
    from rocketwright.schema import Requirement

    baseline = store.create(spec())
    baseline = store.analyse(baseline["id"], baseline["revision"])
    value = spec().model_copy(
        update={
            "requirement": Requirement(
                goal_kind="altitude",
                target_altitude_m=baseline["analysis"]["result"]["metrics"]["apogee_m"],
                payload_mass_kg=0.06,
                budget_jpy=1,
            )
        }
    )
    s = store.create(value)
    s = store.analyse(s["id"], s["revision"])
    assert s["analysis"]["result"]["success"]
    checks = s["analysis"]["requirements"]
    assert not checks["all_requirements_passed"]
    assert next(r for r in checks["checks"] if r["id"] == "budget")["status"] == "not_evaluated"
    s = store.adopt(s["id"], s["revision"])
    assert s["adoption_scope"] == "prototype_screening"


def test_observations_keep_version_history_and_invalidate_documents(store):
    from rocketwright.agent.project_assembly import Observation

    s = adopted(store)
    s = store.manual(s["id"], s["revision"])
    s = store.observe(
        s["id"],
        s["revision"],
        Observation(
            step="nose_fit",
            status="observed",
            operator="test operator",
            observed_on="2026-11-06",
            note="fit trial only; no flight claim",
            measured_values={"clearance_mm": 0.4},
        ),
    )
    assert s["observations"][0]["version"] == 1
    assert not any(row["kind"] in {"manual", "package"} for row in s["files"])
    assert s["adopted"]
    s = store.edit(s["id"], s["revision"], spec())
    assert not s["observations"]
    import json

    old = json.loads((store.base(s["id"]) / "v1/observations/observations.json").read_text())
    assert old[0]["note"].startswith("fit trial")


def test_revision_comparison_reuses_cad_but_recalculates_changed_physics(store, monkeypatch):
    s = adopted(store)
    changed = spec()
    changed.design = changed.design.model_copy(update={"initial_gauge_pressure_pa": 300000})
    s = store.edit(s["id"], s["revision"], changed)
    assert s["cad_reuse"]["from_version"] == 1 and s["analysis"] is None
    diff = store.compare(s["id"], 1)
    assert "CAD" in diff["preserved"] and "flight" in diff["invalidated"]

    def forbidden(*args, **kwargs):
        raise AssertionError("unchanged CAD must not run Blender again")

    monkeypatch.setattr(module, "prepare_geometry", forbidden)
    s = store.analyse(s["id"], s["revision"])
    assert s["analysis"]["design"]["initial_gauge_pressure_pa"] == 300000
    renamed = changed.model_copy(update={"name": "renamed project"})
    s = store.edit(s["id"], s["revision"], renamed)
    assert s["analysis"]["reused_from_version"] == 2
    assert not s["adopted"]
    assert s["analysis"]["input_sha256"] == module.fingerprint(s["spec"])
