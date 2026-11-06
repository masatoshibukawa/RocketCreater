"""Flight -> CFD -> Cd -> flight -> design loop, the assembled airframe it solves and its
workbench route. No Docker or GPU: CFD is replaced by fakes behind the real registry."""

from __future__ import annotations

import importlib.util
import json
import math
import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.workbench as routes
from api.main import app
from rocketwright import aero
from rocketwright.aero import registry
from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult
from rocketwright.aero.lbm_gpu import LbmGpuBackend, assembly_for
from rocketwright.aero.openfoam_pipeline import write_case
from rocketwright.agent.workbench import Conflict, StepChoice, Workbench
from rocketwright.bottle_assembly import Workshop
from rocketwright.bottle_candidates import ENV, PRESSURE_KPA
from rocketwright.bottle_search import Action, Search
from rocketwright.geometry import AssembledShape, airframe, assembled_shape, edge_use_counts
from rocketwright.physics import water
from rocketwright.schema import BottleDesign, DesignAdapter

ROOT = Path(__file__).resolve().parents[1]
TARGET_M = 20.0
ADOPTED = "D02/9/325/25/carton_wide"
CONFIRMED_PATH = [
    "component/D02/9/300/25/carton_plain",
    "component/D02/9/300/25/carton_damped",
    "component/D02/9/300/25/carton_wide",
    "flight/D02/9/300/25/carton_wide",
    f"component/{ADOPTED}",
    f"flight/{ADOPTED}",
    f"screen/{ADOPTED}",
    f"confirm/{ADOPTED}",
]


def _workshop() -> Workshop:
    return Workshop.model_validate_json((ROOT / "scenarios/bottle_empty_workshop.json").read_text())


def _adopted() -> tuple[BottleDesign, dict]:
    search = Search("references", _workshop())
    action = Action("confirm", "D02", 9, 325, 25, "carton_wide")
    design = search.design(action)
    return design, search.plan(action, design)


class ScriptedCFD:
    """Fake L2 backend: Cd (on the geometry's diameter) comes from `cds` in turn, the last
    value repeating. Records every query it actually solves."""

    fidelity = "L2"

    def __init__(self, cds=(0.3,), name="fake_cfd", cacheable=True, fail=False):
        self.name, self.cds, self.cacheable, self.fail = name, tuple(cds), cacheable, fail
        self.queries: list[AeroQuery] = []

    def available(self):
        return True, "fake"

    def supports(self, design):
        return True, ""

    def evaluate(self, query: AeroQuery) -> AeroResult:
        if self.fail:
            raise RuntimeError("solver blew up")
        cd = self.cds[min(len(self.queries), len(self.cds) - 1)]
        self.queries.append(query)
        p = airframe(query.design, shape=query.shape).params
        cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else p["cg_from_nose_m"]
        x_cp = 0.45
        return AeroResult(
            cd=cd,
            cn_alpha_per_rad=8.0,
            x_cp_from_nose_m=x_cp,
            static_margin_cal=(x_cp - cg) / p["ref_diameter_m"],
            cg_from_nose_m=cg,
            ref_diameter_m=p["ref_diameter_m"],
            per_case=[
                AeroCase(speed_mps=query.speed_mps, alpha_deg=a, cd=cd, cn=0.0, cm=0.0)
                for a in query.alphas_deg
            ],
            backend=self.name,
            fidelity="L2",
            source="fake",
            wall_time_s=1.0,
            artifacts_dir="/tmp/fake-artifacts",
        )


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Private cache dir and a registry with only the L0 backend (no docker/GPU probes)."""
    monkeypatch.setenv("ROCKETWRIGHT_AERO_CACHE", str(tmp_path / "cache"))
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    registry.register(aero.BarrowmanBackend())
    yield tmp_path
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


# --------------------------------------------------------------------------- assembled shape


def test_assembled_shape_is_the_plans_outer_surface():
    design, plan = _adopted()
    g = plan["dimensions_mm"]
    shape = assembled_shape(g)
    frame = airframe(design, shape=shape)
    p = frame.params
    assert p["length_m"] == pytest.approx(g["overall"] / 1000)
    assert p["body_diameter_m"] == pytest.approx(g["body_diameter"] / 1000)
    assert p["nose_shape"] == "conical" and p["nose_length_m"] == pytest.approx(0.1)
    assert p["fin_count"] == 4 and frame.shells == 5
    assert p["fin_root_chord_m"] == pytest.approx(g["fin_root"] / 1000)
    assert p["fin_tip_chord_m"] == pytest.approx(g["fin_tip"] / 1000)
    assert p["fin_span_m"] == pytest.approx(g["fin_span"] / 1000) == pytest.approx(0.14)
    assert p["fin_sweep_m"] == pytest.approx(g["fin_sweep"] / 1000)
    # same station as bottle_packet.side_view: end - tail inset - root
    assert p["fin_root_le_from_nose_m"] == pytest.approx(0.497)
    assert p["fin_tail_inset_m"] == pytest.approx(0.005)
    assert frame.vertices[:, 0].max() == pytest.approx(0.572)
    assert frame.vertices[:, 1].max() == pytest.approx(0.045 + 0.14)
    assert set(edge_use_counts(frame.faces).values()) == {2}


def test_design_without_shape_keeps_the_representative_airframe():
    design, plan = _adopted()
    assert airframe(design).stl_bytes() == airframe(design, shape=None).stl_bytes()
    assert (
        airframe(design).stl_bytes()
        != airframe(design, shape=assembled_shape(plan["dimensions_mm"])).stl_bytes()
    )


def test_assembled_shape_is_for_bottles_only():
    amateur = DesignAdapter.validate_python(
        json.loads((ROOT / "examples/designs/amateur.json").read_text())
    )
    _, plan = _adopted()
    with pytest.raises(ValueError, match="bottle"):
        airframe(amateur, shape=assembled_shape(plan["dimensions_mm"]))


def test_barrowman_reproduces_the_plans_centre_of_pressure(isolated):
    design, plan = _adopted()
    shape = assembled_shape(plan["dimensions_mm"])
    cg = plan["wet_cg_mm"] / 1000
    result = aero.evaluate(
        AeroQuery(design=design, shape=shape, cg_from_nose_m=cg), backend="barrowman"
    )
    assert result.x_cp_from_nose_m == pytest.approx(plan["cp_mm"] / 1000)
    assert result.static_margin_cal == pytest.approx((plan["cp_mm"] / 1000 - cg) / 0.09)
    standard = aero.evaluate(AeroQuery(design=design), backend="barrowman")
    assert standard.x_cp_from_nose_m != pytest.approx(result.x_cp_from_nose_m)


def test_fin_shape_is_part_of_the_cache_key(isolated):
    fake = ScriptedCFD()
    registry.register(fake)
    design, plan = _adopted()
    wide = assembled_shape(plan["dimensions_mm"])
    narrow = assembled_shape(plan["dimensions_mm"] | {"fin_span": 70})
    assert registry.cache_key("fake_cfd", AeroQuery(design)) != registry.cache_key(
        "fake_cfd", AeroQuery(design, shape=wide)
    )
    first = aero.evaluate(AeroQuery(design=design, shape=wide), backend="fake_cfd")
    second = aero.evaluate(AeroQuery(design=design, shape=narrow), backend="fake_cfd")
    again = aero.evaluate(AeroQuery(design=design, shape=wide), backend="fake_cfd")
    assert len(fake.queries) == 2
    assert not first.cached and not second.cached and again.cached
    # the same shape on another operating point is the same solve
    moved = design.model_copy(update={"initial_gauge_pressure_pa": 300e3})
    assert aero.evaluate(AeroQuery(design=moved, shape=wide), backend="fake_cfd").cached


def test_fin_thickness_alone_changes_the_cache_key():
    design, plan = _adopted()
    shape = assembled_shape(plan["dimensions_mm"])
    fins = shape.fins.model_copy(update={"thickness_m": 0.001})
    thin = AssembledShape(
        body_diameter_m=shape.body_diameter_m,
        nose_length_m=shape.nose_length_m,
        length_m=shape.length_m,
        fins=fins,
        fin_tail_inset_m=shape.fin_tail_inset_m,
    )
    assert registry.cache_key("x", AeroQuery(design, shape=shape)) != registry.cache_key(
        "x", AeroQuery(design, shape=thin)
    )


def test_openfoam_case_gets_the_assembled_stl_and_diameter(tmp_path):
    design, plan = _adopted()
    shape = assembled_shape(plan["dimensions_mm"])
    query = AeroQuery(
        design=design, speed_mps=25, shape=shape, cg_from_nose_m=plan["wet_cg_mm"] / 1000
    )
    config = write_case(tmp_path, query, nprocs=8)
    assert (tmp_path / "airframe.stl").read_bytes() == airframe(design, shape=shape).stl_bytes()
    assert config["geometry"]["ref_diameter"] == pytest.approx(0.09)
    assert config["geometry"]["cg_from_nose"] == pytest.approx(plan["wet_cg_mm"] / 1000, abs=1e-6)


def test_lbm_assembly_carries_the_plans_fins():
    design, plan = _adopted()
    asm = assembly_for(design, 0.43, assembled_shape(plan["dimensions_mm"]))
    g = plan["dimensions_mm"]
    for key in (
        "overall",
        "body_diameter",
        "nose_length",
        "fin_root",
        "fin_tip",
        "fin_span",
        "fin_sweep",
        "fin_tail_inset",
    ):
        assert asm["dimensions_mm"][key] == pytest.approx(g[key])
    assert asm["rocketwright_shape"] == "flat"  # conical nose


def test_lbm_refuses_a_fin_count_its_kernel_cannot_draw_and_auto_notes_why(isolated, monkeypatch):
    design, plan = _adopted()
    shape = assembled_shape(plan["dimensions_mm"])
    three = AssembledShape(
        body_diameter_m=shape.body_diameter_m,
        nose_length_m=shape.nose_length_m,
        length_m=shape.length_m,
        fins=shape.fins.model_copy(update={"count": 3}),
        fin_tail_inset_m=shape.fin_tail_inset_m,
    )
    query = AeroQuery(design=design, shape=three, cg_from_nose_m=0.43)
    backend = LbmGpuBackend()
    with pytest.raises(ValueError, match="four fins"):
        backend.evaluate(query)
    monkeypatch.setattr(LbmGpuBackend, "available", lambda self: (True, "fake"))
    registry.register(backend)
    result = aero.evaluate(query, backend="auto")
    assert result.backend == "barrowman"
    assert any("lbm_gpu failed" in n and "four fins" in n for n in result.notes)


# --------------------------------------------------------------------------- loop


def _bottle(pressure_kpa=325.0, cd=0.8277) -> BottleDesign:
    design, _ = _adopted()
    return design.model_copy(
        update={"initial_gauge_pressure_pa": pressure_kpa * 1000, "axial_drag_coefficient": cd}
    )


def _loop(design: BottleDesign, **kwargs):
    """The loop on the plan's shape, whose reference diameter is the flight model's."""
    _, plan = _adopted()
    defaults = {
        "target_apogee_m": TARGET_M,
        "backend": "fake_cfd",
        "pressures_kpa": PRESSURE_KPA,
        "shape": assembled_shape(plan["dimensions_mm"]),
    }
    return aero.run_aero_loop(design, ENV, **(defaults | kwargs))


def _nearest(design: BottleDesign, cd: float, pressures) -> float:
    def miss(p):
        trial = design.model_copy(update={"initial_gauge_pressure_pa": p * 1000.0})
        return abs(water.simulate(trial, ENV, 0, cd=cd).metrics["apogee_m"] - TARGET_M)

    return float(min(pressures, key=miss))


def test_loop_converges_and_updates_the_design(isolated):
    fake = ScriptedCFD(cds=(0.32,))
    registry.register(fake)
    design = _bottle()
    result = _loop(design)
    assert result.converged and len(result.rounds) == 2
    first, last = result.rounds
    assert first.cd == pytest.approx(0.32) and not first.cached
    assert first.flight_cd == pytest.approx(0.8277) and first.flight_pressure_kpa == 325
    assert first.cd_change_frac == pytest.approx(abs(0.32 - 0.8277) / 0.8277)
    assert first.pressure_kpa == _nearest(design, 0.32, PRESSURE_KPA)
    assert last.cd_change_frac == pytest.approx(0.0)
    assert last.pressure_kpa == first.pressure_kpa
    assert last.flight_pressure_kpa == first.pressure_kpa
    assert last.flight_apogee_m == pytest.approx(first.apogee_m)
    assert last.cfd_speed_mps == round(last.max_speed_mps) != first.cfd_speed_mps
    final = result.final_design
    assert final.axial_drag_coefficient == pytest.approx(0.32)
    assert final.initial_gauge_pressure_pa == pytest.approx(last.pressure_kpa * 1000)
    assert water.simulate(final, ENV, 0).metrics["apogee_m"] == pytest.approx(last.apogee_m)
    assert result.artifacts_dir == "/tmp/fake-artifacts"
    assert design.axial_drag_coefficient == pytest.approx(0.8277)  # the input stays frozen


def test_repeating_the_loop_reuses_the_cached_solves(isolated):
    fake = ScriptedCFD(cds=(0.32,))
    registry.register(fake)
    first = _loop(_bottle())
    again = _loop(_bottle())
    assert len(fake.queries) == len(first.rounds) == 2
    assert all(r.cached for r in again.rounds) and again.final_design == first.final_design


def test_loop_solves_at_the_flown_speed_rounded_to_one_mps(isolated):
    fake = ScriptedCFD(cds=(0.8277,))
    registry.register(fake)
    design = _bottle()
    result = _loop(design, pressures_kpa=[325])
    flown = water.simulate(design, ENV, 0).metrics["max_speed_mps"]
    assert fake.queries[0].speed_mps == round(flown)
    assert result.rounds[0].max_speed_mps == pytest.approx(flown)
    assert result.rounds[0].cfd_speed_mps == round(flown)


def test_loop_passes_the_shape_and_cg_to_the_backend(isolated):
    fake = ScriptedCFD(cds=(0.8277,))
    registry.register(fake)
    design, plan = _adopted()
    shape = assembled_shape(plan["dimensions_mm"])
    cg = plan["wet_cg_mm"] / 1000
    result = _loop(design, pressures_kpa=[325], shape=shape, cg_from_nose_m=cg)
    assert fake.queries[0].shape == shape and fake.queries[0].cg_from_nose_m == cg
    assert result.rounds[0].x_cp_from_nose_m == pytest.approx(0.45)
    assert result.rounds[0].static_margin_cal == pytest.approx((0.45 - cg) / 0.09)


def test_loop_stops_at_the_round_limit_without_claiming_convergence(isolated):
    fake = ScriptedCFD(cds=(0.3, 0.5, 0.3, 0.5), cacheable=False)
    registry.register(fake)
    result = _loop(_bottle(), max_rounds=3)
    assert not result.converged and len(result.rounds) == 3 and len(fake.queries) == 3
    assert result.final_design.axial_drag_coefficient == pytest.approx(0.3)
    assert any("3 rounds" in n for n in result.notes)


def test_small_cd_change_with_a_moved_pressure_is_not_convergence(isolated):
    # Round 1 keeps the Cd but moves the pressure: only the next round can confirm it.
    fake = ScriptedCFD(cds=(0.8277,))
    registry.register(fake)
    result = _loop(_bottle(pressure_kpa=200))
    assert result.rounds[0].cd_change_frac == pytest.approx(0.0)
    assert result.rounds[0].pressure_kpa != 200
    assert result.converged and len(result.rounds) == 2


def test_loop_says_the_cfd_cd_is_outside_the_calibration(isolated):
    registry.register(ScriptedCFD())
    assert any("calibrat" in n for n in _loop(_bottle()).notes)
    closed_form = _loop(_bottle(), backend="barrowman", pressures_kpa=[325])
    assert closed_form.converged and closed_form.rounds[0].fidelity == "L0"
    assert not any("calibrat" in n for n in closed_form.notes)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"pressures_kpa": []}, "pressure"),
        ({"pressures_kpa": [0]}, "pressure"),
        ({"pressures_kpa": [325], "max_rounds": 0}, "max_rounds"),
        ({"pressures_kpa": [325], "target_apogee_m": 0}, "target"),
    ],
)
def test_loop_rejects_bad_inputs(isolated, kwargs, message):
    with pytest.raises(ValueError, match=message):
        aero.run_aero_loop(_bottle(), ENV, **({"target_apogee_m": TARGET_M} | kwargs))


def test_loop_is_for_bottles(isolated):
    amateur = DesignAdapter.validate_python(
        json.loads((ROOT / "examples/designs/amateur.json").read_text())
    )
    with pytest.raises(ValueError, match="bottle"):
        aero.run_aero_loop(amateur, ENV, target_apogee_m=TARGET_M, pressures_kpa=[325])


def test_loop_rejects_a_vehicle_that_does_not_fly(isolated):
    grounded = _bottle().model_copy(update={"initial_gauge_pressure_pa": 1.0})
    with pytest.raises(ValueError, match="did not fly"):
        aero.run_aero_loop(grounded, ENV, target_apogee_m=TARGET_M, pressures_kpa=[325])


def test_cli_runs_a_workbench_candidate(isolated, capsys):
    path = isolated / "loop.json"
    spec = importlib.util.spec_from_file_location("aero_loop_cli", ROOT / "scripts/aero_loop.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    code = cli.main(["--action", ADOPTED, "--backend", "barrowman", "--json", str(path)])
    saved = json.loads(path.read_text())
    assert code == 0 and "converged" in capsys.readouterr().out
    assert saved["rounds"][0]["x_cp_from_nose_m"] == pytest.approx(_adopted()[1]["cp_mm"] / 1000)


# --------------------------------------------------------------------------- workbench


@pytest.fixture(scope="module")
def confirmed_root(tmp_path_factory):
    """One confirmed project on disk; each test works on its own copy."""
    root = tmp_path_factory.mktemp("confirmed")
    bench = Workbench(root)
    state = bench.create()
    for step in CONFIRMED_PATH:
        state = bench.step(state["id"], state["revision"], StepChoice(id=step, reason="fixture"))
    assert state["confirmed"]
    return root, state["id"]


@pytest.fixture
def confirmed(confirmed_root, tmp_path, isolated, monkeypatch):
    root, project_id = confirmed_root
    shutil.copytree(root / project_id, tmp_path / "bench" / project_id)
    fake = ScriptedCFD(cds=(0.40,))
    registry.register(fake)
    monkeypatch.setenv("ROCKETWRIGHT_AERO_BACKEND", "fake_cfd")
    monkeypatch.setattr(aero, "BACKEND_NAMES", (*aero.BACKEND_NAMES, "fake_cfd"))
    return Workbench(tmp_path / "bench"), project_id, fake


def test_workbench_loop_stores_a_parallel_result_and_touches_nothing_else(confirmed):
    bench, project_id, fake = confirmed
    before = bench.get(project_id)
    after = bench.aero_loop(project_id, before["revision"])
    for key in ("history", "files", "design", "plan", "workshop", "confirmed"):
        assert after[key] == before[key]
    assert after["revision"] == before["revision"] + 1 and after["active"] is None
    loop = after["aero_loop"]
    assert bench.load(project_id)["aero_loop"] == loop
    assert loop["converged"] and loop["source_action"] == f"confirm/{ADOPTED}"
    assert loop["target_apogee_m"] == TARGET_M and loop["backend_requested"] == "fake_cfd"
    final = BottleDesign.model_validate(loop["final_design"])
    p = airframe(final, shape=fake.queries[0].shape).params
    assert final.axial_drag_coefficient == pytest.approx(0.40 * (p["ref_diameter_m"] / 0.09) ** 2)
    assert p["fin_span_m"] == pytest.approx(0.14)
    assert fake.queries[0].cg_from_nose_m == pytest.approx(before["plan"]["wet_cg_mm"] / 1000)
    assert loop["baseline"]["pressure_kpa"] == 325
    assert loop["baseline"]["cd"] == pytest.approx(before["design"]["axial_drag_coefficient"])
    assert loop["baseline"]["success_rate"] == before["history"][-1]["result"]["success_rate"]
    assert all(r["pressure_kpa"] <= 400 for r in loop["rounds"])  # workshop ceiling


def test_workbench_dispersion_repeats_the_confirmation_conditions_on_the_final_design(confirmed):
    bench, project_id, _ = confirmed
    state = bench.get(project_id)
    confirmation = state["history"][-1]["result"]
    spread = bench.aero_loop(project_id, state["revision"])["aero_loop"]["dispersion"]
    assert (spread["n"], spread["seed"]) == (confirmation["n"], confirmation["seed"])
    assert math.isclose(spread["passes"], spread["n"] * spread["success_rate"], abs_tol=0.5)
    assert spread["apogee_m"]["p05"] <= spread["apogee_m"]["p50"] <= spread["apogee_m"]["p95"]
    assert spread["apogee_m"] != confirmation["apogee_m"]  # the new Cd reached the samples


def test_workbench_loop_requires_a_confirmed_project(tmp_path, isolated):
    bench = Workbench(tmp_path / "bench")
    state = bench.create()
    with pytest.raises(Conflict, match="Confirm"):
        bench.aero_loop(state["id"], 0)
    assert bench.get(state["id"])["aero_loop"] is None


def test_workbench_view_of_an_older_project_has_no_loop(confirmed):
    bench, project_id, _ = confirmed
    state = bench.load(project_id)
    state.pop("aero_loop", None)
    bench._write(state)
    assert bench.get(project_id)["aero_loop"] is None


def test_workbench_rejects_an_unknown_backend(confirmed, monkeypatch):
    bench, project_id, _ = confirmed
    monkeypatch.setenv("ROCKETWRIGHT_AERO_BACKEND", "nonsense")
    state = bench.get(project_id)
    with pytest.raises(ValueError, match="ROCKETWRIGHT_AERO_BACKEND"):
        bench.aero_loop(project_id, state["revision"])
    assert bench.get(project_id)["active"] is None


def test_api_runs_the_loop_and_returns_it(confirmed, monkeypatch):
    bench, project_id, _ = confirmed
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    with TestClient(app) as client:
        endpoint = f"/workbench/projects/{project_id}"
        revision = client.get(endpoint).json()["revision"]
        response = client.post(endpoint + "/aero-loop", json={"revision": revision})
        assert response.status_code == 200
        assert response.json()["aero_loop"]["converged"]
        assert client.get(endpoint).json()["aero_loop"] == response.json()["aero_loop"]


def test_api_conflicts_and_missing_projects(confirmed, monkeypatch, tmp_path):
    bench, project_id, _ = confirmed
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    with TestClient(app) as client:
        endpoint = f"/workbench/projects/{project_id}"
        revision = client.get(endpoint).json()["revision"]
        stale = client.post(endpoint + "/aero-loop", json={"revision": revision + 1})
        assert stale.status_code == 409 and "revision" in stale.json()["detail"]
        unconfirmed = client.post("/workbench/projects", json={}).json()
        response = client.post(
            f"/workbench/projects/{unconfirmed['id']}/aero-loop", json={"revision": 0}
        )
        assert response.status_code == 409 and "Confirm" in response.json()["detail"]
        missing = client.post(f"/workbench/projects/{'0' * 32}/aero-loop", json={"revision": 0})
        assert missing.status_code == 404
        assert client.post(endpoint + "/aero-loop", json={}).status_code == 422


def test_api_conflicts_while_another_operation_runs(confirmed, monkeypatch):
    bench, project_id, _ = confirmed
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    state = bench.get(project_id)
    bench._locks[project_id] = lock = threading.Lock()
    lock.acquire()
    with TestClient(app) as client:
        response = client.post(
            f"/workbench/projects/{project_id}/aero-loop", json={"revision": state["revision"]}
        )
    assert response.status_code == 409 and "Another operation" in response.json()["detail"]


def test_api_reports_a_solver_failure_and_keeps_the_previous_result(confirmed, monkeypatch):
    bench, project_id, fake = confirmed
    monkeypatch.setattr(routes, "DEFAULT_WORKBENCH", bench)
    state = bench.get(project_id)
    state = bench.aero_loop(project_id, state["revision"])
    kept = state["aero_loop"]
    shutil.rmtree(Path(registry.cache_dir()))
    fake.fail = True
    with TestClient(app) as client:
        endpoint = f"/workbench/projects/{project_id}"
        response = client.post(endpoint + "/aero-loop", json={"revision": state["revision"]})
        assert response.status_code == 503 and "solver blew up" in response.json()["detail"]
        after = client.get(endpoint).json()
    assert after["aero_loop"] == kept and "solver blew up" in after["error"]
    assert after["active"] is None
