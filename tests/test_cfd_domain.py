import math
import time
from types import SimpleNamespace

import numpy as np
import pytest

from rocketwright.agent.design_projects import write_json
from rocketwright.analysis import refinement
from rocketwright.analysis.runtime import MAX_CFD_DURATION, Runtime
from rocketwright.analysis.worker import Worker
from scenarios.cfd.domain_geometry import bounds, clearance, upstream_for


def geometry():
    return dict(
        body_diameter=90,
        overall=618.696,
        nose_length=276.696,
        fin_root=38.863,
        fin_tip=22.82,
        fin_span=144.739,
        fin_sweep=13.923,
        fin_tail_inset=0,
        fin_count=4,
    )


def test_reverse_flow_preserves_three_diameters_of_actual_inlet_clearance():
    dims, cg = geometry(), 185.08985792889186
    old = clearance(dims, cg, 180, upstream=3, width=12.5, thickness_mm=1.246)
    assert old["inlet_D"] == pytest.approx(0.23870795397537448)
    upstream = upstream_for(dims, cg, 180, 1.246)
    assert upstream == 6
    for angle in np.linspace(0, 180, 37):
        upstream = upstream_for(dims, cg, angle, 1.246)
        actual = clearance(dims, cg, angle, upstream=upstream, width=14, thickness_mm=1.246)
        assert actual["inlet_D"] >= 3 - 1e-12
    assert upstream_for(dims, cg, 0, 1.246) == 3


def test_bounds_contain_independently_sampled_rotated_body():
    dims, cg, angle = geometry(), 185.1, 63
    lo, hi = bounds(dims, cg, angle, 1.2)
    azimuth = np.linspace(0, 2 * math.pi, 501)
    stations = np.linspace(0, dims["overall"], 201)
    radii = np.minimum(stations / dims["nose_length"], 1) * dims["body_diameter"] / 2
    x = np.broadcast_to(stations[:, None], (len(stations), len(azimuth)))
    y, z = radii[:, None] * np.cos(azimuth), radii[:, None] * np.sin(azimuth)
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    points = np.stack([c * (x - cg) + s * y + cg, -s * (x - cg) + c * y, z], -1) / 90
    assert np.all(points >= lo - 1e-12)
    assert np.all(points <= hi + 1e-12)


def test_finite_plate_shoe_cant_and_nonfinite_rejection():
    dims = dict(geometry(), fin_root_offset=12, fin_shoe_width=30)
    lo, hi = bounds(dims, 185.1, 0, 2.4, 3)
    assert hi[1] == pytest.approx((45 + 12 + dims["fin_span"]) / 90)
    assert lo[2] == pytest.approx(-hi[1])
    with pytest.raises(ValueError):
        bounds(dims, 185.1, np.nan)
    with pytest.raises(ValueError):
        bounds(dict(dims, fin_count=3), 185.1, 0)


def test_worker_passes_geometry_derived_inlet_setting(tmp_path, monkeypatch):
    assembly, output = tmp_path / "assembly.json", tmp_path / "case"
    write_json(assembly, dict(dimensions_mm=geometry(), loaded_cg_mm=185.08985792889186))
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        output.mkdir()
        write_json(output / "case.json", {"completed_fixture": True})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("rocketwright.analysis.worker.subprocess.run", run)
    worker = SimpleNamespace(
        ctx={"runtime": Runtime().model_dump()},
        spec=SimpleNamespace(geometry=SimpleNamespace(fin_thickness_mm=1.246)),
        deadline=time.monotonic() + 60,
    )
    Worker.run_case(worker, assembly, output, 35, 180, 20)
    assert float(commands[0][commands[0].index("--upstream") + 1]) == 6


def test_longer_averaging_remains_bounded_and_charged():
    from rocketwright.analysis.catalog import pool
    from rocketwright.analysis.schema import Precision

    before = Precision().model_dump()
    assert refinement.updated(Runtime(cfd_times=100), "refine/averaging").cfd_times == 150
    assert (
        refinement.updated(Runtime(cfd_times=600), "refine/averaging").cfd_times == MAX_CFD_DURATION
    )
    with pytest.raises(ValueError):
        Runtime(cfd_times=MAX_CFD_DURATION + 1)
    short = refinement.followup(pool(Precision()), Runtime(cfd_times=80), "refine/averaging")
    long = refinement.followup(pool(Precision()), Runtime(cfd_times=160), "refine/averaging")
    assert long["estimated_followup_cost_s"] > short["estimated_followup_cost_s"]
    assert set(long["affected_actions"]) == set(short["affected_actions"])
    assert "confirm" in long["affected_actions"]
    assert Precision().model_dump() == before
