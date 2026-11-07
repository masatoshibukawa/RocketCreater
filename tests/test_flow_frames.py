"""Tests for the pictures of the flow taken while the solver runs (no solver here)."""

from pathlib import Path

import pytest
from PIL import Image

from rocketwright.aero import flow_frames
from rocketwright.aero.flow_frames import (
    FRAME_EVERY,
    frame_path,
    list_frames,
    read_slice,
    render_new_frames,
    sample_during_the_run,
)

CASE = "V021p00_A+04p00"
CONTROL_DICT = """\
application     simpleFoam;
writeControl    timeStep;
writeInterval   800;
runTimeModifiable true;
functions
{
    slices
    {
        type            surfaces;
        libs            (sampling);
        writeControl    writeTime;
        surfaceFormat   vtk;
    }
    residuals
    {
        type            solverInfo;
        writeControl    timeStep;
    }
}
"""


def _vtk(points: list[tuple], polygons: list[tuple], speed: float = 21.0) -> str:
    coords = "\n".join(f"{x} {y} {z}" for x, y, z in points)
    faces = "\n".join(f"{len(p)} " + " ".join(map(str, p)) for p in polygons)
    total = sum(len(p) + 1 for p in polygons)
    n = len(points)
    pressure = " ".join("0" for _ in points)
    velocity = "\n".join(f"{speed} 0 0" for _ in points)
    return (
        "# vtk DataFile Version 2.0\ntime='1'\nASCII\nDATASET POLYDATA\n"
        "FIELD FieldData 1\nTimeValue 1 1 float\n1\n"
        f"POINTS {n} float\n{coords}\nPOLYGONS {len(polygons)} {total}\n{faces}\n"
        f"POINT_DATA {n}\nFIELD FieldData 2\np 1 {n} float\n{pressure}\n"
        f"U 3 {n} float\n{velocity}\n"
    )


PLANE = _vtk(
    [(-1.0, -1.0, 0), (2.0, -1.0, 0), (2.0, 1.0, 0), (-1.0, 1.0, 0)],
    [(0, 1, 2), (0, 2, 3)],
)
SURFACE = _vtk([(0.0, -0.1, 0), (1.0, -0.1, 0), (1.0, 0.1, 0), (0.0, 0.1, 0)], [(0, 1, 2, 3)])


def _sample(case: Path, iteration: int) -> Path:
    folder = case / "postProcessing" / "slices" / str(iteration)
    folder.mkdir(parents=True)
    (folder / "pitchPlane.vtk").write_text(PLANE)
    (folder / "rocketSurface.vtk").write_text(SURFACE)
    return folder


def test_the_slices_function_alone_is_set_to_sample_during_the_run(tmp_path):
    path = tmp_path / "controlDict"
    path.write_text(CONTROL_DICT)

    assert sample_during_the_run(path) is True

    text = path.read_text()
    assert f"writeInterval   {FRAME_EVERY};" in text
    assert "writeInterval   800;" in text
    assert text.count("writeTime") == 0
    assert "type            solverInfo;\n        writeControl    timeStep;" in text


def test_a_control_dict_is_set_once_and_a_missing_one_is_left_alone(tmp_path):
    path = tmp_path / "controlDict"
    path.write_text(CONTROL_DICT)
    sample_during_the_run(path)

    assert sample_during_the_run(path) is False
    assert sample_during_the_run(tmp_path / "missing") is False


def test_read_slice_gives_points_polygons_and_velocity(tmp_path):
    path = tmp_path / "pitchPlane.vtk"
    path.write_text(PLANE)

    points, polygons, velocity = read_slice(path)

    assert points.shape == (4, 3)
    assert [list(p) for p in polygons] == [[0, 1, 2], [0, 2, 3]]
    assert velocity.shape == (4, 3)
    assert velocity[0, 0] == 21.0


@pytest.mark.parametrize("cut", [40, len(PLANE) // 2, len(PLANE) - 8])
def test_a_slice_still_being_written_reads_as_not_ready(tmp_path, cut):
    path = tmp_path / "pitchPlane.vtk"
    path.write_text(PLANE[:cut])

    assert read_slice(path) is None


def test_each_sample_becomes_one_frame_and_old_samples_are_cleared(tmp_path):
    case = tmp_path / CASE
    older = _sample(case, 10)
    newest = _sample(case, 20)
    frames = tmp_path / "frames"

    render_new_frames(case, frames)
    render_new_frames(case, frames)

    assert sorted(p.name for p in frames.iterdir()) == [f"{CASE}_00010.jpg", f"{CASE}_00020.jpg"]
    assert not older.exists()
    assert newest.exists()  # rocketcfd draws its final picture from the newest sample
    with Image.open(frames / f"{CASE}_00020.jpg") as image:
        assert image.format == "JPEG"
        assert image.width > image.height


def test_a_sample_being_written_waits_for_the_next_look(tmp_path):
    case = tmp_path / CASE
    folder = _sample(case, 10)
    (folder / "pitchPlane.vtk").write_text(PLANE[:60])
    frames = tmp_path / "frames"

    render_new_frames(case, frames)
    assert list(frames.glob("*.jpg")) == []

    (folder / "pitchPlane.vtk").write_text(PLANE)
    render_new_frames(case, frames)
    assert len(list(frames.glob("*.jpg"))) == 1


def test_frames_are_listed_in_the_order_they_were_taken(tmp_path):
    case = tmp_path / CASE
    _sample(case, 20)
    frames = tmp_path / "frames"
    render_new_frames(case, frames)
    other = tmp_path / "V021p00_A+00p00"
    _sample(other, 10)
    render_new_frames(other, frames)

    listed = list_frames(frames)

    assert [row["iteration"] for row in listed] == [20, 10]
    assert listed[0] == {
        "name": f"{CASE}_00020.jpg",
        "speed_mps": 21.0,
        "alpha_deg": 4.0,
        "iteration": 20,
    }


def test_frame_path_serves_a_frame_and_nothing_else(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / f"{CASE}_00010.jpg").write_bytes(b"x")
    (frames / "secret.txt").write_text("x")

    assert frame_path(frames, f"{CASE}_00010.jpg").name == f"{CASE}_00010.jpg"
    for name in ("secret.txt", f"../{CASE}_00010.jpg", f"{CASE}_00011.jpg"):
        with pytest.raises(KeyError):
            frame_path(frames, name)


def test_missing_folders_list_nothing(tmp_path):
    assert list_frames(tmp_path / "none") == []
    render_new_frames(tmp_path / CASE, tmp_path / "frames")
    assert flow_frames.FRAME_FOLDER == "frames"
