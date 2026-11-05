"""Watertight outer-surface STL of a bottle or amateur airframe (input for the CFD backends).

Pure numpy, deterministic (the same design always gives byte-identical STL).

Frame and units (shared with rocketwright/aero): **metres**, nose tip at the origin, the rocket
axis along +x towards the tail (the nose points in -x), fins at roll angles 0, 360/N, ... from
+y, so four fins form a "+" with two fins in the x-y pitch plane.

The surface is a set of closed shells: one body of revolution (nose + body, tail closed) and
one thin slab per fin whose root is sunk into the body. The shells overlap; CFD meshers that
need a single solid (e.g. the OpenFOAM pipeline, which unions overlapping closed bodies) merge
them. Every shell is closed (each edge belongs to exactly two triangles) and outward-oriented.

Shape rules (each one a `# SIMPLIFICATION:` shared with drawing.py / stability.py):

* amateur: `nose_length_m` nose (conical / tangent ogive / elliptical) followed by a
  `body_length_m` cylinder with a flat base; fins flush with the aft end (stability.py).
* bottle: drawing.py's PET rule. Diameter d = (4 V / (pi * 3.5))^(1/3), half-ellipse nose
  0.8 d, body 3.5 d with a rounded aft shoulder (0.35 r), neck 0.3 d long closed at the nozzle
  end; four fins (root 1.0 d, tip 0.35 root, span 0.8 d, trailing edge at the shoulder).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rocketwright.schema import AmateurDesign, BottleDesign, Design

__all__ = [
    "BOTTLE_FIN_COUNT",
    "BOTTLE_FIN_THICKNESS_M",
    "Airframe",
    "airframe",
    "bottle_dimensions",
    "edge_use_counts",
    "write_stl",
]

# Same constants as drawing.py (kept in sync by tests/test_geometry.py).
BOTTLE_ASPECT_RATIO = 3.5
BOTTLE_NOSE_DIAMETERS = 0.8
BOTTLE_NECK_DIAMETERS = 0.3
BOTTLE_SHOULDER_RADII = 0.35  # drawing.py rounds the body rectangle with rx = 0.35 r
BOTTLE_NECK_RADII = 0.45  # drawing.py: neck radius = min(0.45 r, 2 x nozzle radius)
# SIMPLIFICATION: BottleDesign only says has_fins; the fin set is drawing.py's representative
# planform with four fins of 2 mm sheet (provisional, not a measured kit).
BOTTLE_FIN_COUNT = 4
BOTTLE_FIN_ROOT_DIAMETERS = 1.0
BOTTLE_FIN_SPAN_DIAMETERS = 0.8
BOTTLE_FIN_TIP_ROOT_FRAC = 0.35
BOTTLE_FIN_THICKNESS_M = 0.002
# Smallest tip chord used for a slab (a pointed fin would give a degenerate face).
MIN_TIP_CHORD_M = 1e-3
DEFAULT_SEGMENTS = 48  # around the circumference
NOSE_STATIONS = 24


@dataclass(frozen=True)
class Airframe:
    """Closed shells of the outer surface. `vertices` (n, 3) in metres, `faces` (m, 3) indices
    into `vertices`, outward (counter-clockwise seen from outside)."""

    vertices: NDArray[np.float64]
    faces: NDArray[np.int64]
    shells: int
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def triangles(self) -> NDArray[np.float64]:
        return self.vertices[self.faces]

    def stl_bytes(self) -> bytes:
        """Binary STL in metres (80-byte header says so)."""
        tri = self.triangles.astype(np.float32)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        norm = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, norm, out=np.zeros_like(normals), where=norm > 0)
        rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        rec["n"] = normals
        rec["v"] = tri
        header = b"RocketWright airframe | units: metres | nose at origin, +x aft"
        return struct.pack("<80sI", header, len(tri)) + rec.tobytes()


def write_stl(path: Any, frame: Airframe) -> None:
    with open(path, "wb") as fh:
        fh.write(frame.stl_bytes())


def edge_use_counts(faces: NDArray[np.int64]) -> dict[tuple[int, int], int]:
    """Undirected edge -> number of triangles using it (2 everywhere for a closed surface)."""
    counts: dict[tuple[int, int], int] = {}
    for a, b, c in faces.tolist():
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------- shells


def _revolve(profile: list[tuple[float, float]], segments: int) -> tuple[NDArray, NDArray]:
    """Body of revolution about the x axis from a profile (x, r) that starts and ends on the
    axis (r = 0). Interior points must have r > 0."""
    if profile[0][1] != 0.0 or profile[-1][1] != 0.0:
        raise ValueError("profile must start and end on the axis")
    rings = profile[1:-1]
    theta = 2.0 * math.pi * np.arange(segments) / segments
    cos, sin = np.cos(theta), np.sin(theta)
    verts = [np.array([[profile[0][0], 0.0, 0.0]])]
    for x, r in rings:
        verts.append(np.column_stack([np.full(segments, x), r * cos, r * sin]))
    verts.append(np.array([[profile[-1][0], 0.0, 0.0]]))
    v = np.vstack(verts)
    tail = len(v) - 1
    faces: list[tuple[int, int, int]] = []

    def ring(i: int, j: int) -> int:
        return 1 + i * segments + (j % segments)

    for j in range(segments):  # nose fan
        faces.append((0, ring(0, j + 1), ring(0, j)))
    for i in range(len(rings) - 1):
        for j in range(segments):
            a, b = ring(i, j), ring(i, j + 1)
            c, d = ring(i + 1, j + 1), ring(i + 1, j)
            faces.append((a, b, c))
            faces.append((a, c, d))
    last = len(rings) - 1
    for j in range(segments):  # tail fan
        faces.append((tail, ring(last, j), ring(last, j + 1)))
    return v, np.array(faces, dtype=np.int64)


def _fin_slab(
    *,
    roll_rad: float,
    x_le: float,
    root: float,
    tip: float,
    span: float,
    sweep: float,
    r_surface: float,
    embed: float,
    thickness: float,
) -> tuple[NDArray, NDArray]:
    """Closed trapezoidal slab. Span coordinate s runs from the body surface (s = 0) to the
    tip (s = span); the slab continues to s = -embed so its root is buried in the body."""
    tip = max(tip, MIN_TIP_CHORD_M)

    def le(s: float) -> float:
        return x_le + sweep * s / span

    def te(s: float) -> float:
        return x_le + root + (sweep + tip - root) * s / span

    s_in = -embed
    corners = [  # (x, radial) in the fin plane, counter-clockwise seen from +tangent side
        (le(s_in), r_surface + s_in),
        (te(s_in), r_surface + s_in),
        (te(span), r_surface + span),
        (le(span), r_surface + span),
    ]
    radial = np.array([0.0, math.cos(roll_rad), math.sin(roll_rad)])
    tangent = np.array([0.0, -math.sin(roll_rad), math.cos(roll_rad)])
    verts = []
    for side in (-0.5, 0.5):
        for x, r in corners:
            verts.append(np.array([x, 0.0, 0.0]) + r * radial + side * thickness * tangent)
    v = np.array(verts)
    q = [
        (0, 3, 2, 1),  # -tangent face
        (4, 5, 6, 7),  # +tangent face
        (0, 1, 5, 4),  # root
        (1, 2, 6, 5),  # trailing edge
        (2, 3, 7, 6),  # tip
        (3, 0, 4, 7),  # leading edge
    ]
    faces = []
    for a, b, c, d in q:
        faces += [(a, b, c), (a, c, d)]
    return v, np.array(faces, dtype=np.int64)


def _signed_volume(v: NDArray, f: NDArray) -> float:
    t = v[f]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def _outward(v: NDArray, f: NDArray) -> NDArray:
    return f if _signed_volume(v, f) > 0 else f[:, ::-1].copy()


def _nose_radius(shape: str, s: float, length: float, radius: float) -> float:
    """Radius at distance s from the tip (same formulas as drawing._nose_points)."""
    if shape == "conical":
        return radius * s / length
    if shape == "elliptical":
        u = (length - s) / length
        return radius * math.sqrt(max(0.0, 1.0 - u * u))
    rho = (radius**2 + length**2) / (2.0 * radius)  # tangent ogive
    return math.sqrt(max(0.0, rho**2 - (length - s) ** 2)) + radius - rho


def _nose_profile(shape: str, length: float, radius: float) -> list[tuple[float, float]]:
    pts = [(0.0, 0.0)]
    for i in range(1, NOSE_STATIONS + 1):
        # cluster stations near the tip, where the radius changes fastest
        s = (
            length * (i / NOSE_STATIONS) ** 1.5
            if shape != "conical"
            else length * i / NOSE_STATIONS
        )
        pts.append((s, max(_nose_radius(shape, s, length, radius), 1e-6)))
    return pts


# --------------------------------------------------------------------------- designs


def bottle_dimensions(design: BottleDesign) -> dict[str, float]:
    """drawing.py's PET-bottle rule in metres."""
    d = (4.0 * design.bottle_volume_m3 / (math.pi * BOTTLE_ASPECT_RATIO)) ** (1.0 / 3.0)
    r = d / 2.0
    return {
        "body_diameter_m": d,
        "nose_length_m": BOTTLE_NOSE_DIAMETERS * d,
        "body_length_m": BOTTLE_ASPECT_RATIO * d,
        "neck_length_m": BOTTLE_NECK_DIAMETERS * d,
        "neck_radius_m": min(BOTTLE_NECK_RADII * r, max(design.nozzle_diameter_m, 0.15 * r)),
        "shoulder_m": BOTTLE_SHOULDER_RADII * r,
    }


def _bottle(design: BottleDesign, segments: int) -> tuple[list, dict[str, Any]]:
    dim = bottle_dimensions(design)
    d = dim["body_diameter_m"]
    r = d / 2.0
    x_body0 = dim["nose_length_m"]
    x_body1 = x_body0 + dim["body_length_m"]
    x_tail = x_body1 + dim["neck_length_m"]
    c = dim["shoulder_m"]
    profile = _nose_profile("elliptical", x_body0, r)
    for i in range(1, 9):  # quarter-ellipse shoulder from (x_body1 - c, r) to (x_body1, r - c)
        a = 0.5 * math.pi * i / 8
        profile.append((x_body1 - c + c * math.sin(a), r - c + c * math.cos(a)))
    profile += [(x_body1, dim["neck_radius_m"]), (x_tail, dim["neck_radius_m"]), (x_tail, 0.0)]
    shells = [_revolve(profile, segments)]
    params: dict[str, Any] = {
        "length_m": x_tail,
        "body_diameter_m": d,
        "nose_shape": "elliptical",
        "nose_length_m": x_body0,
        "body_length_m": dim["body_length_m"],
        "neck_length_m": dim["neck_length_m"],
        "neck_diameter_m": 2.0 * dim["neck_radius_m"],
        "fin_count": 0,
    }
    if design.has_fins:
        root = BOTTLE_FIN_ROOT_DIAMETERS * d
        tip = BOTTLE_FIN_TIP_ROOT_FRAC * root
        span = BOTTLE_FIN_SPAN_DIAMETERS * d
        x_le = x_body1 - root
        for k in range(BOTTLE_FIN_COUNT):
            shells.append(
                _fin_slab(
                    roll_rad=2.0 * math.pi * k / BOTTLE_FIN_COUNT,
                    x_le=x_le,
                    root=root,
                    tip=tip,
                    span=span,
                    sweep=root - tip,
                    r_surface=r,
                    # buried below the shoulder (radius r - c) so the root never floats
                    embed=c + 0.05 * r,
                    thickness=BOTTLE_FIN_THICKNESS_M,
                )
            )
        params.update(
            fin_count=BOTTLE_FIN_COUNT,
            fin_root_chord_m=root,
            fin_tip_chord_m=tip,
            fin_span_m=span,
            fin_sweep_m=root - tip,
            fin_thickness_m=BOTTLE_FIN_THICKNESS_M,
            fin_root_le_from_nose_m=x_le,
            fin_tail_inset_m=x_tail - x_body1,
        )
    params.update(_bottle_cg(design, params))
    return shells, params


def _bottle_cg(design: BottleDesign, p: dict[str, Any]) -> dict[str, Any]:
    """SIMPLIFICATION: liftoff CG (least stable, water at the tail): dry mass spread evenly
    over the overall length, payload at the nose base, water a cylinder of the bottle diameter
    against the aft end of the body."""
    water_kg = design.bottle_volume_m3 * design.water_fill_frac * 1000.0
    x_body1 = p["nose_length_m"] + p["body_length_m"]
    water_len = min(p["body_length_m"], design.water_fill_frac * p["body_length_m"])
    moment = (
        design.dry_mass_kg * p["length_m"] / 2.0
        + design.payload_mass_kg * p["nose_length_m"]
        + water_kg * (x_body1 - water_len / 2.0)
    )
    mass = design.dry_mass_kg + design.payload_mass_kg + water_kg
    return {"cg_from_nose_m": moment / mass, "cg_basis": "liftoff, water loaded (estimate)"}


def _amateur(design: AmateurDesign, segments: int) -> tuple[list, dict[str, Any]]:
    d = design.body_diameter_m
    r = d / 2.0
    length = design.nose_length_m + design.body_length_m
    profile = _nose_profile(design.nose_shape, design.nose_length_m, r)
    profile += [(length, r), (length, 0.0)]
    shells = [_revolve(profile, segments)]
    f = design.fins
    x_le = length - f.root_chord_m
    for k in range(f.count):
        shells.append(
            _fin_slab(
                roll_rad=2.0 * math.pi * k / f.count,
                x_le=x_le,
                root=f.root_chord_m,
                tip=f.tip_chord_m,
                span=f.span_m,
                sweep=f.sweep_m,
                r_surface=r,
                embed=0.25 * r,
                thickness=f.thickness_m,
            )
        )
    params: dict[str, Any] = {
        "length_m": length,
        "body_diameter_m": d,
        "nose_shape": design.nose_shape,
        "nose_length_m": design.nose_length_m,
        "body_length_m": design.body_length_m,
        "fin_count": f.count,
        "fin_root_chord_m": f.root_chord_m,
        "fin_tip_chord_m": f.tip_chord_m,
        "fin_span_m": f.span_m,
        "fin_sweep_m": f.sweep_m,
        "fin_thickness_m": f.thickness_m,
        "fin_root_le_from_nose_m": x_le,
        "fin_tail_inset_m": 0.0,
    }
    try:  # loaded-motor CG, the same point stability.static_margin_cal uses
        from rocketwright.physics import solid, stability

        motor = solid.load_motor(design.motor_id)
        cg = stability.center_of_gravity_m(
            design, motor.total_mass_kg, motor_length_m=motor.length_m
        )
        params.update(cg_from_nose_m=cg, cg_basis="liftoff, motor loaded (stability.py)")
    except (KeyError, FileNotFoundError, ValueError):
        params.update(cg_from_nose_m=None, cg_basis="unknown motor")
    return shells, params


def airframe(design: Design, *, segments: int = DEFAULT_SEGMENTS) -> Airframe:
    """Outer surface of a bottle or amateur design plus its geometry parameters (metres)."""
    if isinstance(design, BottleDesign):
        shells, params = _bottle(design, segments)
    elif isinstance(design, AmateurDesign):
        shells, params = _amateur(design, segments)
    else:
        raise ValueError(
            f"airframe geometry covers the bottle and amateur tiers, not {design.tier!r}"
        )
    verts, faces, offset = [], [], 0
    for v, f in shells:
        verts.append(v)
        faces.append(_outward(v, f) + offset)
        offset += len(v)
    d = params["body_diameter_m"]
    params.update(
        units="m",
        frame="nose tip at origin, +x aft, fins at 0/90/... deg roll from +y",
        ref_diameter_m=d,
        ref_area_m2=math.pi * d * d / 4.0,
    )
    return Airframe(
        vertices=np.vstack(verts),
        faces=np.vstack(faces),
        shells=len(shells),
        params=params,
    )
