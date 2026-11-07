"""The live view of a CFD job reads what the solver leaves in its case directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from rocketwright.aero import live

LOG = """2026-11-06 14:51:57,345 INFO rocketcfd.pipeline: Meshing (surface cells 4.22 mm) ...
2026-11-06 14:52:33,704 INFO rocketcfd.pipeline: Mesh: 151,837 cells, checkMesh OK
2026-11-06 14:52:33,706 INFO rocketcfd.pipeline: [1/2] V021p00_A+00p00 (V = 21 m/s, AoA = 0 deg): solving ...
2026-11-06 14:53:50,830 INFO rocketcfd.pipeline: [1/2] V021p00_A+00p00 (V = 21 m/s, AoA = 0 deg): solved in 77 s
2026-11-06 14:53:50,838 INFO rocketcfd.pipeline: [1/2] V021p00_A+00p00 (V = 21 m/s, AoA = 0 deg): CD = 0.5967, CN = 0.0692, Xcp = 1
2026-11-06 14:53:51,774 INFO rocketcfd.pipeline: [2/2] V021p00_A+04p00 (V = 21 m/s, AoA = 4 deg): solving ...
"""  # noqa: E501
SOLVER_INFO = """# Solver information
# Time\tU_solver\tUx_initial\tUx_final\tUx_iters\tp_solver\tp_initial\tp_final
1\tsmooth\t5.0e-01\t4.0e-02\t2\tGAMG\t9.0e-01\t1.0e-02
2\tsmooth\t2.0e-01\t1.0e-02\t4\tGAMG\t4.0e-01\t1.0e-02
"""
FORCE = """# Force
# CofR : (0 0 0)
#
# Time total_x total_y total_z
1 0.5 0.1 0.0
2 0.9 0.1 0.0
3 0.9
"""


@pytest.fixture
def run(tmp_path):
    out = tmp_path / "out" / "rw"
    (out / "flow").mkdir(parents=True)
    (out / "pipeline.log").write_text(LOG)
    (out / "flow" / "V021p00_A+00p00.png").write_bytes(b"png")
    case = tmp_path / "foam" / "rw" / "cases" / "V021p00_A+04p00"
    (case / "postProcessing" / "residuals" / "0").mkdir(parents=True)
    (case / "postProcessing" / "forces" / "0").mkdir(parents=True)
    (case / "system").mkdir()
    (case / "postProcessing" / "residuals" / "0" / "solverInfo.dat").write_text(SOLVER_INFO)
    (case / "postProcessing" / "forces" / "0" / "force.dat").write_text(FORCE)
    (case / "system" / "controlDict").write_text("stopAt endTime;\nendTime         800;\n")
    return tmp_path


def test_a_run_reports_its_case_iteration_and_series(run):
    state = live.read_run(run)
    assert state["stage"] == "solve"
    assert (state["case_index"], state["case_total"]) == (2, 2)
    assert (state["speed_mps"], state["alpha_deg"]) == (21.0, 4.0)
    assert state["cells"] == 151837
    assert state["iteration"] == 2 and state["iterations_total"] == 800
    assert state["residuals"]["Ux"] == [[1.0, 0.5], [2.0, 0.2]]
    assert state["residuals"]["p"] == [[1.0, 0.9], [2.0, 0.4]]
    # The last, half-written line of the force file is left out.
    assert state["axial_force_n"] == [[1.0, 0.5], [2.0, 0.9]]
    assert state["finished"] == [{"alpha_deg": 0.0, "cd": 0.5967}]
    assert state["images"] == ["V021p00_A+00p00.png"]


def test_a_run_that_has_just_started_is_only_preparing(tmp_path):
    state = live.read_run(tmp_path)
    assert state["stage"] == "prepare"
    assert state["residuals"] == {} and state["iteration"] is None


def test_series_stay_small_and_keep_the_latest_point():
    rows = [[float(i), 1.0] for i in range(1, 1001)]
    thin = live._thin(rows)
    assert len(thin) <= live.MAX_SERIES_POINTS + 1
    assert thin[-1] == rows[-1]


def test_snapshot_follows_the_running_job_only(run):
    assert live.snapshot() is None
    live.begin(run)
    try:
        assert live.snapshot()["case_index"] == 2
        assert live.image_path("V021p00_A+00p00.png").is_file()
        with pytest.raises(KeyError):
            live.image_path("../../secret.png")
    finally:
        live.end(run)
    assert live.snapshot() is None
    with pytest.raises(KeyError):
        live.image_path("V021p00_A+00p00.png")


def _writing_case(tmp_path: Path) -> Path:
    from tests.test_flow_frames import CONTROL_DICT, PLANE, SURFACE

    case = tmp_path / "foam" / "rw" / "cases" / "V021p00_A+04p00"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text(CONTROL_DICT)
    sample = case / "postProcessing" / "slices" / "10"
    sample.mkdir(parents=True)
    (sample / "pitchPlane.vtk").write_text(PLANE)
    (sample / "rocketSurface.vtk").write_text(SURFACE)
    return case


def test_scan_starts_sampling_and_makes_frames(tmp_path):
    case = _writing_case(tmp_path)

    live.scan(tmp_path)

    assert "writeTime" not in (case / "system" / "controlDict").read_text()
    frames = live.read_run(tmp_path)["frames"]
    assert [frame["iteration"] for frame in frames] == [10]


def test_the_watcher_leaves_the_last_frames_behind_when_the_run_ends(tmp_path):
    _writing_case(tmp_path)

    live.begin(tmp_path)
    live.end(tmp_path)

    assert (tmp_path / "frames" / "V021p00_A+04p00_00010.jpg").is_file()


def test_a_frame_of_the_running_job_is_served(tmp_path):
    _writing_case(tmp_path)
    live.begin(tmp_path)
    try:
        live.scan(tmp_path)
        name = "V021p00_A+04p00_00010.jpg"
        assert live.image_path(name) == tmp_path / "frames" / name
        with pytest.raises(KeyError):
            live.image_path("V021p00_A+04p00_00011.jpg")
    finally:
        live.end(tmp_path)
