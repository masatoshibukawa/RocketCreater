"""Millimetre STL patterns for non-pressure rings on the bench prototype."""

import math
import struct

import numpy as np


def ring_stl(path, inner_mm, outer_mm, height_mm, marks=False):
    """Annulus with an optional V mark every quarter turn on the outer edge."""
    sides = 128
    surface = []
    for radius, height, marked in (
        (inner_mm / 2, 0, False),
        (outer_mm / 2, 0, marks),
        (inner_mm / 2, height_mm, False),
        (outer_mm / 2, height_mm, marks),
    ):
        ring = []
        for i in range(sides):
            angle = i * 2 * math.pi / sides
            r = radius - 2 if marked and i % (sides // 4) == 0 else radius
            ring.append(np.array([r * math.cos(angle), r * math.sin(angle), height]))
        surface.append(ring)
    low_in, low_out, top_in, top_out = surface
    tris = []
    for i in range(sides):
        j = (i + 1) % sides
        for a, b, c, d in (
            (low_in[i], low_in[j], low_out[j], low_out[i]),
            (top_out[i], top_out[j], top_in[j], top_in[i]),
            (low_out[i], low_out[j], top_out[j], top_out[i]),
            (low_in[j], low_in[i], top_in[i], top_in[j]),
        ):
            tris.extend([(a, b, c), (a, c, d)])
    with path.open("wb") as f:
        f.write(struct.pack("<80sI", b"RocketWright | millimetres", len(tris)))
        for a, b, c in tris:
            normal = np.cross(b - a, c - a)
            normal /= np.linalg.norm(normal)
            f.write(struct.pack("<12fH", *normal, *a, *b, *c, 0))


def print_parts(directory, g):
    inside = g["dummy_width"] + 2 * g["padding"] + g["fit_allowance"]
    outside = g["bay_clear_diameter"] - g["fit_allowance"]
    thick = 2.4
    ring_stl(directory / "payload-collar-mm.stl", inside, outside, thick)
    jig_id = g["body_diameter"] + 2
    ring_stl(directory / "fin-marking-jig-mm.stl", jig_id, jig_id + 10, 4, True)
    return {
        "collar_inner_mm": inside,
        "collar_outer_mm": outside,
        "thickness_mm": thick,
        "pair_solid_pla_g": 2 * math.pi * (outside**2 - inside**2) / 4 * thick / 1000 * 1.24,
        "jig_inner_mm": jig_id,
    }
