"""POST /aero/loop: the flight/CFD loop on a free-request design, run as a background job.
No Docker or GPU: CFD is replaced by fakes behind the real registry."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.aero as routes
from api.main import app
from rocketwright import aero
from rocketwright.aero import registry
from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult
from rocketwright.agent.design_aero import AeroJobs, JobQueueFull, bottle_pressures_kpa
from rocketwright.agent.fake_client import DEMO_PASSING_INDEX, demo_designs
from rocketwright.bottle_candidates import PRESSURE_KPA
from rocketwright.geometry import airframe
from rocketwright.physics import solid
from rocketwright.schema import AmateurDesign, BottleDesign, DesignAdapter

client = TestClient(app)
TARGET_M = 30.0
WAIT_S = 20.0


class FakeCFD:
    """Fake L2 backend. `gate`, when given, holds every solve until it is set."""

    name = "fake_cfd"
    fidelity = "L2"
    cacheable = False

    def __init__(self, cds=(0.3,), gate=None, fail=False, artifacts_dir=None):
        self.cds, self.gate, self.fail, self.artifacts_dir = tuple(cds), gate, fail, artifacts_dir
        self.queries: list[AeroQuery] = []

    def available(self):
        return True, "fake"

    def supports(self, design):
        return True, ""

    def evaluate(self, query: AeroQuery) -> AeroResult:
        if self.gate is not None:
            assert self.gate.wait(WAIT_S)
        if self.fail:
            raise RuntimeError("solver blew up")
        cd = self.cds[min(len(self.queries), len(self.cds) - 1)]
        self.queries.append(query)
        p = airframe(query.design, shape=query.shape).params
        return AeroResult(
            cd=cd,
            cn_alpha_per_rad=8.0,
            x_cp_from_nose_m=0.45,
            static_margin_cal=2.0,
            cg_from_nose_m=p["cg_from_nose_m"],
            ref_diameter_m=p["ref_diameter_m"],
            per_case=[AeroCase(speed_mps=query.speed_mps, alpha_deg=0, cd=cd, cn=0.0, cm=0.0)],
            backend=self.name,
            fidelity="L2",
            source="fake",
            wall_time_s=1.0,
            artifacts_dir=self.artifacts_dir,
        )


def _design(tier: str) -> dict:
    return demo_designs(tier)[DEMO_PASSING_INDEX[tier]]


def _body(tier: str = "bottle", **changes) -> dict:
    return {"design": _design(tier), "target_altitude_m": TARGET_M, **changes}


@pytest.fixture
def jobs(monkeypatch, tmp_path):
    """A private job store, cache and registry with only the L0 backend."""
    monkeypatch.setenv("ROCKETWRIGHT_AERO_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("ROCKETWRIGHT_AERO_BACKEND", raising=False)
    monkeypatch.setattr(routes, "DEFAULT_AERO_JOBS", store := AeroJobs())
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    registry.register(aero.BarrowmanBackend())
    yield store
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


@pytest.fixture
def fake_backend(monkeypatch, jobs):
    """Registers a FakeCFD and selects it through ROCKETWRIGHT_AERO_BACKEND."""

    def install(backend: FakeCFD) -> FakeCFD:
        registry.register(backend, replace=True)
        monkeypatch.setenv("ROCKETWRIGHT_AERO_BACKEND", backend.name)
        monkeypatch.setattr(aero, "BACKEND_NAMES", (*aero.BACKEND_NAMES, backend.name))
        return backend

    return install


def _finished(job_id: str) -> dict:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        view = client.get(f"/aero/loop/{job_id}").json()
        if view["status"] in ("done", "failed"):
            return view
        time.sleep(0.02)
    raise AssertionError("the aero job did not finish")


def test_start_returns_at_once_and_the_job_is_polled_to_its_end(fake_backend):
    gate = threading.Event()
    fake_backend(FakeCFD(gate=gate))
    started = client.post("/aero/loop", json=_body())
    assert started.status_code == 202, started.text
    job = started.json()
    assert job["status"] in ("queued", "running")
    assert job["result"] is None and job["error"] is None

    running = client.get(f"/aero/loop/{job['id']}").json()
    assert running["status"] in ("queued", "running")
    gate.set()
    done = _finished(job["id"])
    assert done["status"] == "done", done
    assert done["elapsed_s"] >= 0
    assert done["result"]["rounds"][0]["backend"] == "fake_cfd"


def test_bottle_result_matches_the_panel_and_keeps_paths_private(fake_backend):
    fake_backend(FakeCFD(cds=(0.3,), artifacts_dir="/srv/secret"))
    body = _body(n=20, seed=5)
    job = _finished(client.post("/aero/loop", json=body).json()["id"])
    result = job["result"]
    design = BottleDesign.model_validate(body["design"])
    assert result["tier"] == "bottle"
    assert result["target_altitude_m"] == TARGET_M
    assert result["backend_requested"] == "fake_cfd"
    assert result["baseline"] == {
        "pressure_kpa": design.initial_gauge_pressure_pa / 1000,
        "cd": None,
    }
    assert result["dispersion"]["n"] == 20 and result["dispersion"]["seed"] == 5
    assert 0 <= result["dispersion"]["passes"] <= 20
    assert result["final_design"]["axial_drag_coefficient"] == pytest.approx(
        result["rounds"][-1]["cd"]
    )
    assert "artifacts_dir" not in result and "/srv/secret" not in str(job)


def test_the_loop_never_raises_a_designs_pressure(fake_backend):
    backend = fake_backend(FakeCFD(cds=(9.0,)))  # huge drag: more pressure would fly nearer
    body = _body()
    own_kpa = body["design"]["initial_gauge_pressure_pa"] / 1000
    job = _finished(client.post("/aero/loop", json=body).json()["id"])
    assert backend.queries
    assert all(row["pressure_kpa"] <= own_kpa for row in job["result"]["rounds"])


@pytest.mark.parametrize("own_kpa", [150.0, 325.0, 333.0, 493.0, 700.0])
def test_listed_pressures_end_at_the_designs_own(own_kpa):
    design = BottleDesign.model_validate(
        _design("bottle") | {"initial_gauge_pressure_pa": own_kpa * 1000}
    )
    pressures = bottle_pressures_kpa(design)
    assert pressures[-1] == own_kpa
    assert max(pressures) == own_kpa
    assert set(pressures[:-1]) <= set(PRESSURE_KPA)
    assert len(pressures) == len(set(pressures))


def test_a_budget_cannot_decide_the_flow_loops_spread(fake_backend):
    fake_backend(FakeCFD())
    requirement = {
        "goal_kind": "altitude",
        "target_altitude_m": 1.0,  # the request's target wins
        "payload_mass_kg": 0.06,
        "budget_jpy": 1,
        "recovery_required": True,
    }
    started = client.post("/aero/loop", json=_body(requirement=requirement, n=5))
    job = _finished(started.json()["id"])
    assert not any("budget" in reason for reason in job["result"]["dispersion"]["failure_counts"])


def test_amateur_design_flies_with_the_cfd_cd_and_stays_as_given(fake_backend):
    backend = fake_backend(FakeCFD(cds=(0.5, 0.42, 0.42)))
    design = _design("amateur")
    job = _finished(
        client.post("/aero/loop", json={"design": design, "target_altitude_m": 2000}).json()["id"]
    )
    result = job["result"]
    assert result["tier"] == "amateur"
    assert result["converged"] is True
    assert result["final_design"] == AmateurDesign.model_validate(design).model_dump(mode="json")
    assert result["dispersion"] is None
    assert result["baseline"] == {"pressure_kpa": None, "cd": solid.DEFAULT_CD}
    first, *_, last = result["rounds"]
    assert first["flight_cd"] == solid.DEFAULT_CD and first["cd"] == pytest.approx(0.5, rel=1e-6)
    assert "pressure_kpa" not in first
    assert last["cd_change_frac"] < 0.02
    assert len(backend.queries) == len(result["rounds"])
    assert backend.queries[0].speed_mps == first["cfd_speed_mps"]


def test_amateur_on_l0_converges_on_the_module_cd(jobs):
    job = _finished(
        client.post(
            "/aero/loop", json={"design": _design("amateur"), "target_altitude_m": 2000}
        ).json()["id"]
    )
    assert job["status"] == "done"
    assert job["result"]["rounds"][0]["fidelity"] == "L0"
    assert job["result"]["rounds"][0]["cd"] == pytest.approx(solid.DEFAULT_CD)


@pytest.mark.parametrize("tier", ["commercial", "heavy"])
def test_multistage_designs_are_refused(jobs, tier):
    r = client.post("/aero/loop", json=_body(tier))
    assert r.status_code == 422
    assert "ボトルとアマチュア" in r.json()["detail"]


def test_an_unknown_backend_setting_is_refused(jobs, monkeypatch):
    monkeypatch.setenv("ROCKETWRIGHT_AERO_BACKEND", "nonsense")
    r = client.post("/aero/loop", json=_body())
    assert r.status_code == 422
    assert "ROCKETWRIGHT_AERO_BACKEND" in r.json()["detail"]


@pytest.mark.parametrize("target", [0, -1])
def test_a_bad_target_is_refused(jobs, target):
    assert client.post("/aero/loop", json=_body(target_altitude_m=target)).status_code == 422


def test_the_same_request_shares_one_job(jobs):
    first = client.post("/aero/loop", json=_body()).json()
    second = client.post("/aero/loop", json=_body()).json()
    other = client.post("/aero/loop", json=_body(target_altitude_m=31.0)).json()
    assert first["id"] == second["id"]
    assert other["id"] != first["id"]
    assert _finished(first["id"])["status"] == _finished(other["id"])["status"] == "done"


def test_a_failed_job_reports_its_reason_and_can_run_again(fake_backend):
    fake_backend(FakeCFD(fail=True))
    failed = _finished(client.post("/aero/loop", json=_body()).json()["id"])
    assert failed["status"] == "failed"
    assert "solver blew up" in failed["error"] and failed["result"] is None
    retry = client.post("/aero/loop", json=_body()).json()
    assert retry["id"] != failed["id"]
    _finished(retry["id"])


def test_a_full_queue_is_told_to_wait(fake_backend, monkeypatch):
    gate = threading.Event()
    fake_backend(FakeCFD(gate=gate))
    monkeypatch.setattr(routes, "DEFAULT_AERO_JOBS", AeroJobs(max_pending=1))
    first = client.post("/aero/loop", json=_body()).json()
    r = client.post("/aero/loop", json=_body(target_altitude_m=31.0))
    assert r.status_code == 429
    gate.set()
    _finished(first["id"])


def test_finished_jobs_are_forgotten_oldest_first():
    store = AeroJobs(max_kept=2)
    ids = []
    for i in range(3):
        view = store.submit(str(i), lambda: {"tier": "bottle"})
        deadline = time.monotonic() + WAIT_S
        while store.view(view["id"])["status"] != "done":
            assert time.monotonic() < deadline
            time.sleep(0.005)
        ids.append(view["id"])
    with pytest.raises(KeyError):
        store.view(ids[0])
    assert store.view(ids[2])["status"] == "done"


def test_queue_limit_counts_only_unfinished_jobs():
    store = AeroJobs(max_pending=1)
    gate = threading.Event()
    store.submit("a", lambda: gate.wait(WAIT_S) and {})
    with pytest.raises(JobQueueFull):
        store.submit("b", dict)
    gate.set()


@pytest.mark.parametrize("job_id", ["nope", "0" * 32, "g" * 32])
def test_unknown_jobs_are_not_found(jobs, job_id):
    assert client.get(f"/aero/loop/{job_id}").status_code == 404
    assert client.get(f"/aero/loop/{job_id}/images/a.png").status_code == 404


# --------------------------------------------------------------------------- flow pictures


def _flow_run(fake_backend, tmp_path: Path) -> dict:
    run = tmp_path / "run"
    (run / "flow").mkdir(parents=True)
    (run / "flow" / "V015p00_A+04p00.png").write_bytes(b"\x89PNG flow")
    (run / "flow" / "notes.txt").write_text("not a picture")
    (run / "secret.png").write_bytes(b"\x89PNG outside")
    (tmp_path / "outside.png").write_bytes(b"\x89PNG outside")
    os.symlink(tmp_path / "outside.png", run / "flow" / "link.png")
    fake_backend(FakeCFD(artifacts_dir=str(run)))
    return _finished(client.post("/aero/loop", json=_body()).json()["id"])


def test_flow_pictures_are_listed_and_served(fake_backend, tmp_path):
    job = _flow_run(fake_backend, tmp_path)
    image = next(row for row in job["images"] if row["name"].startswith("V015"))
    assert image["speed_mps"] == 15.0 and image["alpha_deg"] == 4.0
    assert image["url"] == f"/aero/loop/{job['id']}/images/V015p00_A+04p00.png"
    served = client.get(image["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == b"\x89PNG flow"


@pytest.mark.parametrize(
    "name",
    ["notes.txt", "secret.png", "..%2Fsecret.png", "%2E%2E%2Fsecret.png", "link.png", "gone.png"],
)
def test_only_flow_pictures_are_served(fake_backend, tmp_path, name):
    job = _flow_run(fake_backend, tmp_path)
    assert client.get(f"/aero/loop/{job['id']}/images/{name}").status_code == 404


def test_a_design_without_pictures_lists_none(jobs):
    job = _finished(client.post("/aero/loop", json=_body()).json()["id"])
    assert job["images"] == []


def test_result_design_is_a_valid_design(jobs):
    job = _finished(client.post("/aero/loop", json=_body()).json()["id"])
    assert DesignAdapter.validate_python(job["result"]["final_design"]).tier == "bottle"


def test_the_flow_sees_the_fins_the_parts_chose(fake_backend, monkeypatch):
    seen = []
    loop = aero.run_aero_loop
    monkeypatch.setattr(
        aero, "run_aero_loop", lambda *a, **k: seen.append(k["shape"]) or loop(*a, **k)
    )
    fake_backend(FakeCFD(cds=(0.3,)))
    build = {
        "tier": "bottle",
        "bottle_id": "pet_bottle_1p5l",
        "water_fill_frac": 0.4,
        "initial_gauge_pressure_pa": 300000,
        "nozzle_id": "bottle_nozzle_full_bore_22mm",
        "fin_set_id": "bottle_fin_set_pp_sheet_4_wide",
        "parachute_id": "bottle_parachute_30cm_plastic",
        "launcher_id": None,
        "payload_mass_kg": 0.06,
    }
    design = _design("bottle") | {"has_fins": True}
    job = _finished(client.post("/aero/loop", json=_body(design=design, build=build)).json()["id"])
    assert job["status"] == "done", job["error"]
    assert job["result"]["parts_fins"] is True
    assert seen[-1].fins.span_m == pytest.approx(0.12) and seen[-1].fins.count == 4
    without = _finished(client.post("/aero/loop", json=_body(design=design)).json()["id"])
    assert without["result"]["parts_fins"] is False and seen[-1] is None
