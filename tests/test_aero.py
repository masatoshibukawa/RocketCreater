"""rocketwright.aero: registry/cache, L0 values, OpenFOAM/LBM I/O and the opt-in tool wiring.
No Docker or GPU is used: CFD backends are replaced by fakes or fed recorded output files."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from rocketwright import aero
from rocketwright.aero import registry
from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult
from rocketwright.aero.lbm_gpu import LbmGpuBackend, assembly_for, parse_cases
from rocketwright.aero.openfoam_pipeline import (
    OpenFoamPipelineBackend,
    docker_command,
    parse_results,
    write_case,
)
from rocketwright.agent.tools import execute_tool, get_tool_definitions
from rocketwright.geometry import airframe
from rocketwright.physics import solid, stability, water
from rocketwright.schema import DesignAdapter

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "examples" / "designs"
OPENFOAM_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "aero_openfoam"


def _design(name: str):
    return DesignAdapter.validate_python(json.loads((DESIGNS / f"{name}.json").read_text()))


class FakeCFD:
    """Counts evaluations; returns a fixed Cd on the geometry's reference diameter."""

    fidelity = "L2"
    cacheable = True

    def __init__(self, name: str = "fake_cfd", cd: float = 0.5, ok: bool = True, fail=False):
        self.name, self.cd, self.ok, self.fail, self.calls = name, cd, ok, fail, 0

    def available(self):
        return self.ok, "fake" if self.ok else "fake is off"

    def supports(self, design):
        return True, ""

    def evaluate(self, query: AeroQuery) -> AeroResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("solver blew up")
        p = airframe(query.design).params
        x_cp = 0.2
        cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else p["cg_from_nose_m"]
        return AeroResult(
            cd=self.cd,
            cn_alpha_per_rad=8.0,
            x_cp_from_nose_m=x_cp,
            static_margin_cal=(x_cp - cg) / p["ref_diameter_m"],
            cg_from_nose_m=cg,
            ref_diameter_m=p["ref_diameter_m"],
            per_case=[
                AeroCase(speed_mps=query.speed_mps, alpha_deg=a, cd=self.cd, cn=0.0, cm=0.0)
                for a in query.alphas_deg
            ],
            backend=self.name,
            fidelity="L2",
            source="fake",
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


# --------------------------------------------------------------------------- L0


def test_barrowman_amateur_equals_todays_constants(isolated):
    a = _design("amateur")
    r = aero.evaluate(AeroQuery(design=a), backend="barrowman")
    assert r.fidelity == "L0" and r.backend == "barrowman"
    assert r.cd == solid.DEFAULT_CD
    assert r.x_cp_from_nose_m == pytest.approx(stability.center_of_pressure_m(a))
    cn_f, _ = stability.fin_normal_force(a)
    assert r.cn_alpha_per_rad == pytest.approx(stability.NOSE_CN + cn_f)
    assert r.static_margin_cal == pytest.approx(stability.static_margin_cal(a))
    assert aero.cd_for_physics(r, a) == pytest.approx(solid.DEFAULT_CD)


def test_barrowman_bottle_equals_water_constant(isolated):
    b = _design("bottle")
    r = aero.evaluate(AeroQuery(design=b), backend="barrowman")
    assert r.cd == water.DEFAULT_CD
    assert r.ref_diameter_m == pytest.approx(water.bottle_diameter_m(b.bottle_volume_m3))
    assert aero.cd_for_physics(r, b) == pytest.approx(water.DEFAULT_CD)
    assert r.cn_alpha_per_rad > 2.0 and 0 < r.x_cp_from_nose_m < airframe(b).params["length_m"]
    own = b.model_copy(update={"axial_drag_coefficient": 0.42})
    assert aero.evaluate(AeroQuery(design=own), backend="barrowman").cd == 0.42


def test_barrowman_rejects_multistage(isolated):
    with pytest.raises(ValueError):
        aero.evaluate(AeroQuery(design=_design("commercial")), backend="barrowman")


# --------------------------------------------------------------------------- registry/cache


def test_cache_solves_each_shape_once(isolated):
    fake = FakeCFD()
    registry.register(fake)
    b = _design("bottle")
    first = aero.evaluate(AeroQuery(design=b, speed_mps=15), backend="fake_cfd")
    again = aero.evaluate(AeroQuery(design=b, speed_mps=15), backend="fake_cfd")
    assert fake.calls == 1 and not first.cached and again.cached
    assert again.cd == first.cd
    files = list((isolated / "cache").glob("*.json"))
    assert len(files) == 1 and files[0].stem == registry.cache_key("fake_cfd", AeroQuery(b, 15))
    # mass changes move the CG, not the shape: no new solve, margin recomputed
    moved = aero.evaluate(AeroQuery(design=b, cg_from_nose_m=0.1), backend="fake_cfd")
    assert fake.calls == 1 and moved.static_margin_cal == pytest.approx(
        (0.2 - 0.1) / moved.ref_diameter_m
    )
    # another speed or another shape is a new solve
    aero.evaluate(AeroQuery(design=b, speed_mps=20), backend="fake_cfd")
    aero.evaluate(AeroQuery(design=b.model_copy(update={"has_fins": False})), backend="fake_cfd")
    assert fake.calls == 3


def test_cache_key_ignores_cg_but_not_angles():
    b = _design("bottle")
    k = registry.cache_key("x", AeroQuery(b, 15, (0, 4)))
    assert k == registry.cache_key("x", AeroQuery(b, 15, (0.0, 4.0), cg_from_nose_m=0.2))
    assert k != registry.cache_key("x", AeroQuery(b, 15, (0, 2)))
    assert k != registry.cache_key("y", AeroQuery(b, 15, (0, 4)))


def test_auto_prefers_cfd_then_falls_back_to_l0(isolated):
    b = _design("bottle")
    off = FakeCFD(name="off", ok=False)
    registry.register(off)
    r = aero.evaluate(AeroQuery(design=b))
    assert r.backend == "barrowman" and any("off: fake is off" in n for n in r.notes)
    broken = FakeCFD(name="broken", fail=True)
    registry.register(broken)
    r = aero.evaluate(AeroQuery(design=b))
    assert r.backend == "barrowman" and any("broken failed" in n for n in r.notes)
    good = FakeCFD(name="good", cd=0.33)
    registry.register(good)
    r = aero.evaluate(AeroQuery(design=b))
    assert r.backend == "good" and r.cd == 0.33


def test_named_backend_errors(isolated):
    registry.register(FakeCFD(name="off", ok=False))
    with pytest.raises(RuntimeError, match="unavailable"):
        aero.evaluate(AeroQuery(design=_design("bottle")), backend="off")
    with pytest.raises(ValueError, match="unknown aero backend"):
        aero.evaluate(AeroQuery(design=_design("bottle")), backend="nope")


def test_default_registry_order():
    assert list(aero.backends()) == ["openfoam_pipeline", "lbm_gpu", "barrowman"]


# --------------------------------------------------------------------------- OpenFOAM pipeline


def test_openfoam_case_files(tmp_path):
    b = _design("bottle")
    p = airframe(b).params
    cfg = write_case(tmp_path, AeroQuery(design=b, speed_mps=15, alphas_deg=(0, 4)), nprocs=8)
    on_disk = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert on_disk == cfg
    assert (tmp_path / "airframe.stl").read_bytes() == airframe(b).stl_bytes()
    g = cfg["geometry"]
    assert g["units"] == "m" and g["nose_direction"] == "-x"
    assert g["ref_diameter"] == pytest.approx(p["ref_diameter_m"], abs=1e-6)
    assert g["cg_from_nose"] == pytest.approx(p["cg_from_nose_m"], abs=1e-6)
    assert cfg["mesh"]["preset"] == "coarse" and cfg["render_3d"] is False
    assert cfg["regime"] == "incompressible" and cfg["sweeps"]["speed"] is None
    assert cfg["sweeps"]["aoa"] == {"speed": 15.0, "angles": [0.0, 4.0]}
    assert cfg["solver"]["nprocs"] == 8 and cfg["openfoam"]["runner"] == "native"
    fast = write_case(tmp_path / "f", AeroQuery(design=b, speed_mps=150))
    assert fast["regime"] == "compressible"


def test_openfoam_results_parsing_from_recorded_run():
    """Fixture = results.csv / centre_of_pressure.json of the real coarse bottle run."""
    b = _design("bottle")
    q = AeroQuery(design=b, speed_mps=15, alphas_deg=(0, 4))
    r = parse_results(OPENFOAM_FIXTURE, q, ref_diameter_m=0.0817, cg_from_nose_m=0.262)
    assert r.backend == "openfoam_pipeline" and r.fidelity == "L2" and r.provisional
    assert [c.alpha_deg for c in r.per_case] == [0.0, 4.0]
    assert r.cd == pytest.approx(0.377779)
    cn0, cn4 = (c.cn for c in r.per_case)
    assert r.cn_alpha_per_rad == pytest.approx((cn4 - cn0) / math.radians(4))
    cp = json.loads((OPENFOAM_FIXTURE / "centre_of_pressure.json").read_text())
    assert r.x_cp_from_nose_m == pytest.approx(cp["xcp_m"])
    assert r.static_margin_cal == pytest.approx((cp["xcp_m"] - 0.262) / 0.0817)
    assert any("not converged" in n for n in r.notes)
    assert any("coarse" in n for n in r.notes)


def test_openfoam_docker_command_is_limited_and_offline(tmp_path):
    cmd = docker_command("img:1", tmp_path, "rw-x", 8)
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--cpus=8" in cmd and "--network=none" in cmd
    assert f"{tmp_path}:/case" in cmd
    assert cmd[-3:] == ["rocketcfd", "run", "/case/config.yaml"]


def test_openfoam_unavailable_without_docker(monkeypatch):
    import rocketwright.aero.openfoam_pipeline as of

    monkeypatch.setattr(of.shutil, "which", lambda _name: None)
    ok, reason = OpenFoamPipelineBackend().available()
    assert not ok and "docker" in reason


# --------------------------------------------------------------------------- LBM


def test_lbm_assembly_has_run_flow_inputs():
    ref = json.loads((ROOT / "scenarios" / "cfd" / "r03_reference.json").read_text())
    asm = assembly_for(_design("bottle"))
    assert set(ref["dimensions_mm"]) <= set(asm["dimensions_mm"])
    assert {"key", "loaded_cg_mm", "axial_cd"} <= set(asm)
    assert asm["rocketwright_shape"] == "rounded_flat"
    assert asm["dimensions_mm"]["overall"] == pytest.approx(
        airframe(_design("bottle")).params["length_m"] * 1000
    )


def test_lbm_supports_only_four_fins():
    assert not LbmGpuBackend().supports(_design("amateur"))[0]  # 3 fins, 11 D long
    assert LbmGpuBackend().supports(_design("bottle"))[0]


def test_lbm_case_parsing(tmp_path):
    files = []
    for a, cy, cm in ((0.0, 0.0, 0.0), (4.0, 0.6, 0.3)):
        f = tmp_path / f"{a}.json"
        f.write_text(json.dumps({"angle_deg": a, "speed_mps": 15, "mean": {
            "Cd": 1.0 + a / 100, "Cl": 0, "Cx": 1.0, "Cy": cy, "Cz": 0,
            "Croll": 0, "Cpitch_y": 0, "Cm_z": cm}}))  # fmt: skip
        files.append(f)
    q = AeroQuery(design=_design("bottle"))
    r = parse_cases(files, q, ref_diameter_m=0.08, cg_from_nose_m=0.25)
    assert r.cd == 1.0 and r.cn_alpha_per_rad == pytest.approx(0.6 / math.radians(4))
    assert r.static_margin_cal == pytest.approx(0.5)
    assert r.x_cp_from_nose_m == pytest.approx(0.25 + 0.5 * 0.08)
    assert all(c.cm_ref_from_nose_m == 0.25 for c in r.per_case)


# --------------------------------------------------------------------------- tool wiring


def _sim_input(**extra):
    return {
        "design": json.loads((DESIGNS / "bottle.json").read_text()),
        "env": {},
        "seed": None,
        "requirement": None,
        "tune_pitch": False,
        **extra,
    }


def test_tool_schema_has_nullable_aero_backend():
    defs = {d["name"]: d for d in get_tool_definitions()}
    for name in ("simulate_design", "design_from_parts"):
        schema = defs[name]["input_schema"]
        assert "aero_backend" in schema["required"]
        assert {"type": "null"} in schema["properties"]["aero_backend"]["anyOf"]


def test_simulate_design_default_unchanged_and_l0_identical(isolated):
    base = execute_tool("simulate_design", _sim_input(), "t0")
    none = execute_tool("simulate_design", _sim_input(aero_backend="none"), "t1")
    l0 = execute_tool("simulate_design", _sim_input(aero_backend="barrowman"), "t2")
    assert "aero" not in base and "aero" not in none
    assert none["metrics"] == base["metrics"]
    assert l0["metrics"]["apogee_m"] == pytest.approx(base["metrics"]["apogee_m"])
    assert l0["metrics"]["aero_cd_ratio"] == pytest.approx(water.DEFAULT_CD)
    assert "aero_static_margin_cal" in l0["metrics"]
    assert any(w.startswith("aero: Cd 0.800 from barrowman (L0") for w in l0["warnings"])
    assert l0["aero"]["backend"] == "barrowman"


def test_simulate_design_uses_cfd_cd(isolated):
    fake = FakeCFD(name="openfoam_pipeline", cd=0.4)
    registry.register(fake, replace=True)
    out = execute_tool("simulate_design", _sim_input(aero_backend="openfoam_pipeline"), "t3")
    assert "error" not in out, out
    b = _design("bottle")
    d_geo = airframe(b).params["ref_diameter_m"]
    expected = 0.4 * (d_geo / water.bottle_diameter_m(b.bottle_volume_m3)) ** 2
    assert out["metrics"]["aero_cd_ratio"] == pytest.approx(expected)
    base = execute_tool("simulate_design", _sim_input(), "t4")
    assert out["metrics"]["apogee_m"] > base["metrics"]["apogee_m"]  # less drag than 0.8
    assert out["aero"]["fidelity"] == "L2" and out["source_id"] == "t3"
    execute_tool("simulate_design", _sim_input(aero_backend="openfoam_pipeline"), "t5")
    assert fake.calls == 1  # cached per shape


def test_simulate_design_rejects_bad_aero_backend(isolated):
    out = execute_tool("simulate_design", _sim_input(aero_backend="xfoil"), "t6")
    assert "error" in out and "aero_backend" in out["error"]


BOTTLE_BUILD = {
    "tier": "bottle",
    "bottle_id": "pet_bottle_1p5l",
    "water_fill_frac": 0.4,
    "initial_gauge_pressure_pa": 400000,
    "nozzle_id": "nozzle_21p7mm",
    "fin_set_id": "bottle_fins_cardboard",
    "parachute_id": "chute_0p5m_plastic",
    "launcher_id": "launcher_bike_pump",
    "payload_mass_kg": 0.06,
}


def test_design_from_parts_aero_wiring(isolated, monkeypatch):
    from rocketwright import parts

    monkeypatch.setattr(
        parts, "DEFAULT_PARTS_PATH", Path(__file__).parent / "fixtures" / "parts_v2.yaml"
    )
    registry.register(FakeCFD(name="lbm_gpu", cd=0.6), replace=True)
    inp = {"build": BOTTLE_BUILD, "env": None, "requirement": None, "seed": None}
    plain = execute_tool("design_from_parts", inp, "p0")
    out = execute_tool("design_from_parts", {**inp, "aero_backend": "lbm_gpu"}, "p1")
    assert "error" not in out, out
    assert out["sim"] is not None and "aero_cd_ratio" in out["sim"]["metrics"]
    assert out["aero"]["backend"] == "lbm_gpu"
    assert "aero" not in plain and "aero_cd_ratio" not in plain["sim"]["metrics"]
