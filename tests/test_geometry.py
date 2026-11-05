"""rocketwright.geometry: closed, outward, deterministic airframe surfaces (no CFD needed)."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np
import pytest

from rocketwright import drawing, geometry
from rocketwright.geometry import airframe, edge_use_counts
from rocketwright.physics import stability
from rocketwright.schema import DesignAdapter

DESIGNS = Path(__file__).resolve().parents[1] / "examples" / "designs"


def _design(name: str):
    return DesignAdapter.validate_python(json.loads((DESIGNS / f"{name}.json").read_text()))


@pytest.fixture(params=["bottle", "amateur"])
def design(request):
    return _design(request.param)


def _shells(frame):
    """Connected components of the face graph (vertex-sharing)."""
    parent = list(range(len(frame.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in frame.faces.tolist():
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    groups: dict[int, list[int]] = {}
    for k, f in enumerate(frame.faces.tolist()):
        groups.setdefault(find(f[0]), []).append(k)
    return [frame.faces[idx] for idx in groups.values()]


def test_every_edge_is_shared_by_exactly_two_triangles(design):
    frame = airframe(design)
    counts = edge_use_counts(frame.faces)
    assert counts and set(counts.values()) == {2}


def test_stl_bytes_are_watertight_by_position(design):
    """Same check on the written STL (merging identical float32 vertex positions)."""
    data = airframe(design).stl_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    assert len(data) == 84 + 50 * n
    rec = np.frombuffer(data[84:], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = rec["v"].reshape(-1, 3)
    _, idx = np.unique(tri, axis=0, return_inverse=True)
    faces = idx.reshape(-1, 3)
    assert set(edge_use_counts(faces).values()) == {2}
    assert b"metres" in data[:80]


def test_each_shell_is_closed_and_outward(design):
    frame = airframe(design)
    shells = _shells(frame)
    assert len(shells) == frame.shells
    for faces in shells:
        t = frame.vertices[faces]
        vol = np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0
        assert vol > 0


def test_bottle_bounding_box_matches_the_drawing_rule():
    d_design = _design("bottle")
    frame = airframe(d_design)
    p = frame.params
    d = (4 * d_design.bottle_volume_m3 / (math.pi * drawing.BOTTLE_ASPECT_RATIO)) ** (1 / 3)
    assert geometry.BOTTLE_ASPECT_RATIO == drawing.BOTTLE_ASPECT_RATIO
    assert p["body_diameter_m"] == pytest.approx(d)
    assert p["length_m"] == pytest.approx((0.8 + 3.5 + 0.3) * d)
    lo, hi = frame.vertices.min(axis=0), frame.vertices.max(axis=0)
    assert lo[0] == pytest.approx(0.0, abs=1e-12)
    assert hi[0] == pytest.approx(p["length_m"])
    assert hi[1] == pytest.approx(d / 2 + 0.8 * d)  # fin at roll 0 points along +y
    assert p["fin_count"] == 4 and frame.shells == 5
    assert 0 < p["cg_from_nose_m"] < p["length_m"]


def test_finless_bottle_is_one_shell():
    d = _design("bottle").model_copy(update={"has_fins": False})
    frame = airframe(d)
    assert frame.shells == 1 and frame.params["fin_count"] == 0
    assert frame.vertices[:, 1].max() == pytest.approx(frame.params["body_diameter_m"] / 2)


def test_amateur_bounding_box_and_cg():
    a = _design("amateur")
    frame = airframe(a)
    p = frame.params
    r, f = a.body_diameter_m / 2, a.fins
    lo, hi = frame.vertices.min(axis=0), frame.vertices.max(axis=0)
    assert hi[0] == pytest.approx(a.nose_length_m + a.body_length_m)
    assert lo[0] == pytest.approx(0.0, abs=1e-12)
    assert hi[1] == pytest.approx(r + f.span_m, rel=1e-9)
    assert p["fin_root_le_from_nose_m"] == pytest.approx(hi[0] - f.root_chord_m)
    assert frame.shells == 1 + f.count
    # same loaded-motor CG as stability.static_margin_cal
    margin = (stability.center_of_pressure_m(a) - p["cg_from_nose_m"]) / a.body_diameter_m
    assert margin == pytest.approx(stability.static_margin_cal(a))


def test_deterministic(design):
    assert airframe(design).stl_bytes() == airframe(design).stl_bytes()


def test_multistage_is_rejected():
    with pytest.raises(ValueError, match="bottle and amateur"):
        airframe(_design("commercial"))
