"""What a running CFD job is doing now, read from the files the solver writes.

The pipeline runs as an external process, so this only reads what it leaves in the case
directory: pipeline.log for the stage, and per-iteration residuals and forces.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

MAX_SERIES_POINTS = 200
RUN_FOLDER = "rw"
_IMAGE_NAME = re.compile(r"^[\w.+-]+\.png$")
_CASE_LINE = re.compile(
    r"\[(\d+)/(\d+)\] (\S+) \(V = ([\d.]+) m/s, AoA = ([-\d.]+) deg\): "
    r"(solving|solved|CD = ([\d.]+))"
)
_CELLS_LINE = re.compile(r"Mesh: ([\d,]+) cells")
_END_TIME = re.compile(r"^endTime\s+(\d+)", re.M)

_lock = threading.Lock()
_case_dir: Path | None = None


def begin(case_dir: Path) -> None:
    global _case_dir
    with _lock:
        _case_dir = case_dir


def end(case_dir: Path) -> None:
    global _case_dir
    with _lock:
        if _case_dir == case_dir:
            _case_dir = None


def _current() -> Path | None:
    with _lock:
        return _case_dir


def _thin(rows: list[list[float]]) -> list[list[float]]:
    step = max(1, -(-len(rows) // MAX_SERIES_POINTS))
    kept = rows[::step]
    return kept if not rows or kept[-1] == rows[-1] else [*kept, rows[-1]]


def _data_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """The last `#` header's column names and the data rows of an OpenFOAM .dat file."""
    header: list[str] = []
    rows: list[list[str]] = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return header, rows
    for line in lines:
        if line.startswith("#"):
            header = line.lstrip("# ").split()
        elif line.strip():
            rows.append(line.split())
    # A file being written can end in half a line.
    return header, [row for row in rows if len(row) == len(rows[0])]


def _latest(case: Path, pattern: str) -> Path | None:
    found = sorted(case.glob(pattern))
    return found[-1] if found else None


def _residuals(case: Path) -> dict[str, list[list[float]]]:
    path = _latest(case, "postProcessing/residuals/*/solverInfo.dat")
    if path is None:
        return {}
    header, rows = _data_rows(path)
    out: dict[str, list[list[float]]] = {}
    for index, name in enumerate(header):
        if not name.endswith("_initial"):
            continue
        series: list[list[float]] = []
        for row in rows:
            try:
                series.append([float(row[0]), float(row[index])])
            except (ValueError, IndexError):
                continue
        if series:
            out[name.removesuffix("_initial")] = _thin(series)
    return out


def _axial_force(case: Path) -> list[list[float]]:
    path = _latest(case, "postProcessing/forces/*/force.dat")
    if path is None:
        return []
    _, rows = _data_rows(path)
    series: list[list[float]] = []
    for row in rows:
        try:
            series.append([float(row[0]), float(row[1])])
        except (ValueError, IndexError):
            continue
    return _thin(series)


def _end_iteration(case: Path) -> int | None:
    try:
        match = _END_TIME.search((case / "system" / "controlDict").read_text(errors="replace"))
    except OSError:
        return None
    return int(match.group(1)) if match else None


def read_run(case_dir: Path) -> dict[str, Any]:
    """The state of one run directory. A file that is not there yet just leaves its part out."""
    out_dir = next(iter(sorted((case_dir / "out").glob("*"))), case_dir / "out" / "rw")
    try:
        log = (out_dir / "pipeline.log").read_text(errors="replace")
    except OSError:
        log = ""
    state: dict[str, Any] = {
        "stage": "prepare",
        "cells": None,
        "case_index": None,
        "case_total": None,
        "speed_mps": None,
        "alpha_deg": None,
        "iteration": None,
        "iterations_total": None,
        "residuals": {},
        "axial_force_n": [],
        "finished": [],
        "images": sorted(p.name for p in out_dir.glob("flow/*.png")),
    }
    if "Meshing" in log:
        state["stage"] = "mesh"
    cells = _CELLS_LINE.search(log)
    if cells:
        state["cells"] = int(cells.group(1).replace(",", ""))
    name = None
    for match in _CASE_LINE.finditer(log):
        index, total, case, speed, alpha, event, cd = match.groups()
        state.update(
            stage="solve",
            case_index=int(index),
            case_total=int(total),
            speed_mps=float(speed),
            alpha_deg=float(alpha),
        )
        name = case
        if cd is not None:
            state["finished"].append({"alpha_deg": float(alpha), "cd": float(cd)})
    if name is not None:
        case = case_dir / "foam" / RUN_FOLDER / "cases" / name
        state["residuals"] = _residuals(case)
        state["axial_force_n"] = _axial_force(case)
        state["iterations_total"] = _end_iteration(case)
        series = state["axial_force_n"] or next(iter(state["residuals"].values()), [])
        state["iteration"] = int(series[-1][0]) if series else None
    return state


def snapshot() -> dict[str, Any] | None:
    case_dir = _current()
    return None if case_dir is None else read_run(case_dir)


def image_path(name: str) -> Path:
    """A flow picture of the running job. KeyError for anything else."""
    case_dir = _current()
    if case_dir is None or not _IMAGE_NAME.fullmatch(name):
        raise KeyError(name)
    for path in (case_dir / "out").glob(f"*/flow/{name}"):
        return path
    raise KeyError(name)
