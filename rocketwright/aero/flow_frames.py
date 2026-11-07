"""Pictures of the flow taken while the solver runs.

The pipeline samples the pitch plane once, at the end of a case. OpenFOAM re-reads
system/controlDict as it runs, so `sample_during_the_run` asks the `slices` function for a sample
every FRAME_EVERY iterations, and `render_new_frames` turns each sample into one picture. Played
in order, they are the flow settling around the airframe.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy.interpolate import LinearNDInterpolator

__all__ = [
    "FRAME_EVERY",
    "FRAME_FOLDER",
    "frame_path",
    "list_frames",
    "read_slice",
    "render_new_frames",
    "sample_during_the_run",
]

FRAME_EVERY = 10  # iterations; a case stops near 235 and takes about three per second
FRAME_FOLDER = "frames"
FRAME_NAME = re.compile(r"(V(\d+)p(\d+)_A([+-]?\d+)p(\d+))_(\d+)\.jpg")
_SLICES_FUNCTION = re.compile(r"(\bslices\s*\{[^{}]*?)writeControl\s+writeTime;")

FRAME_WIDTH_PX = 960
JPEG_QUALITY = 82
# The view around the body, in body lengths: room for the wake behind it.
VIEW_AHEAD = 0.15
VIEW_BEHIND = 0.5
VIEW_HALF_HEIGHT = 0.42
VIEW_FIN_MARGIN = 1.2  # fins wider than that still fit, with this much space around them
# |U| / V: the same scale on every frame, so a change of colour is a change of flow.
MAX_SPEED_RATIO = 1.3
SPEED_COLOURS = ((68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37))
BODY_COLOUR = (214, 218, 224)

Slice = tuple[np.ndarray, list[np.ndarray], np.ndarray]


def sample_during_the_run(control_dict: Path) -> bool:
    """Set a case's `slices` function to sample as it goes. True when the file was changed."""
    try:
        text = control_dict.read_text()
    except OSError:
        return False
    changed, count = _SLICES_FUNCTION.subn(
        rf"\1writeControl    timeStep;\n        writeInterval   {FRAME_EVERY};", text
    )
    if count == 0:
        return False
    # The solver may read the file at any moment, so it must never see half of it.
    part = control_dict.with_suffix(".part")
    part.write_text(changed)
    os.replace(part, control_dict)
    return True


def read_slice(path: Path) -> Slice | None:
    """Points, polygons and velocity of a legacy-VTK surface; None while it is being written."""
    try:
        words = path.read_text().split()
        at_points = words.index("POINTS")
        count = int(words[at_points + 1])
        start = at_points + 3
        points = np.array(words[start : start + 3 * count], dtype=float).reshape(count, 3)

        at_polygons = words.index("POLYGONS", start)
        size = int(words[at_polygons + 2])
        start = at_polygons + 3
        flat = np.array(words[start : start + size], dtype=int)
        polygons: list[np.ndarray] = []
        offset = 0
        while offset < size:
            polygons.append(flat[offset + 1 : offset + 1 + flat[offset]])
            offset += flat[offset] + 1

        start = words.index("U", start + size) + 4
        velocity = np.array(words[start : start + 3 * count], dtype=float).reshape(count, 3)
    except (OSError, ValueError, IndexError):
        return None
    return points, polygons, velocity


def _colour_table() -> np.ndarray:
    stops = np.linspace(0, 255, len(SPEED_COLOURS))
    channels = np.array(SPEED_COLOURS, dtype=float).T
    return np.stack([np.interp(np.arange(256), stops, c) for c in channels], axis=1).astype("uint8")


def _render(plane: Slice, body: np.ndarray, speed_mps: float) -> Image.Image:
    points, polygons, velocity = plane
    nose, tail = float(body[:, 0].min()), float(body[:, 0].max())
    length = tail - nose
    left, right = nose - VIEW_AHEAD * length, tail + VIEW_BEHIND * length
    half_height = max(VIEW_HALF_HEIGHT * length, VIEW_FIN_MARGIN * float(np.abs(body[:, 1]).max()))
    bottom, top = -half_height, half_height
    pixels_per_metre = FRAME_WIDTH_PX / (right - left)
    height_px = round((top - bottom) * pixels_per_metre)

    # Sampled on a grid, then cut to the polygons: the body is a hole in the slice.
    ratio = np.linalg.norm(velocity, axis=1) / speed_mps
    grid_x, grid_y = np.meshgrid(
        left + (np.arange(FRAME_WIDTH_PX) + 0.5) / pixels_per_metre,
        top - (np.arange(height_px) + 0.5) / pixels_per_metre,
    )
    field = LinearNDInterpolator(points[:, :2], ratio)(grid_x, grid_y)

    mask = Image.new("1", (FRAME_WIDTH_PX, height_px))
    draw = ImageDraw.Draw(mask)
    for polygon in polygons:
        corners = points[polygon, :2]
        px = (corners[:, 0] - left) * pixels_per_metre
        py = (top - corners[:, 1]) * pixels_per_metre
        draw.polygon(list(zip(px.tolist(), py.tolist(), strict=True)), fill=1)
    in_flow = np.asarray(mask, dtype=bool) & np.isfinite(field)

    scaled = np.nan_to_num(field) / MAX_SPEED_RATIO * 255
    rgb = _colour_table()[np.clip(scaled, 0, 255).astype("uint8")]
    rgb[~in_flow] = BODY_COLOUR
    return Image.fromarray(rgb, "RGB")


def _speed_of(case: str) -> float | None:
    match = FRAME_NAME.fullmatch(f"{case}_0.jpg")
    return float(f"{match[2]}.{match[3]}") if match else None


def _frame(sample: Path, out: Path, speed_mps: float) -> bool:
    plane = read_slice(sample / "pitchPlane.vtk")
    body = read_slice(sample / "rocketSurface.vtk")
    if plane is None or body is None:
        return False
    part = out.with_suffix(".part")
    _render(plane, body[0], speed_mps).save(part, format="JPEG", quality=JPEG_QUALITY)
    os.replace(part, out)
    return True


def render_new_frames(case: Path, frames: Path) -> None:
    """One frame for each sample of a case that has none yet. All samples but the newest are
    then cleared, since a run writes hundreds and the case directory holds them all."""
    speed = _speed_of(case.name)
    slices = case / "postProcessing" / "slices"
    if speed is None or not slices.is_dir():
        return
    samples = sorted(
        (p for p in slices.iterdir() if p.is_dir() and p.name.isdigit()),
        key=lambda p: int(p.name),
    )
    frames.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        out = frames / f"{case.name}_{int(sample.name):05d}.jpg"
        if not out.exists() and not _frame(sample, out, speed):
            continue
        if sample != samples[-1]:
            shutil.rmtree(sample, ignore_errors=True)


def list_frames(frames: Path) -> list[dict[str, Any]]:
    """Speed, angle and iteration of each frame, in the order they were taken."""
    if not frames.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(frames.glob("*.jpg"), key=lambda p: (p.stat().st_mtime_ns, p.name)):
        match = FRAME_NAME.fullmatch(path.name)
        if match:
            rows.append(
                {
                    "name": path.name,
                    "speed_mps": float(f"{match[2]}.{match[3]}"),
                    "alpha_deg": float(f"{match[4]}.{match[5]}"),
                    "iteration": int(match[6]),
                }
            )
    return rows


def frame_path(frames: Path, name: str) -> Path:
    """One frame of a folder, and nothing else in it. KeyError otherwise."""
    path = frames / name
    if not FRAME_NAME.fullmatch(name) or not path.is_file():
        raise KeyError(name)
    return path
