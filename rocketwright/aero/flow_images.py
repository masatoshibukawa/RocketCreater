"""Flow pictures a CFD run leaves in `<artifacts_dir>/flow/`, shared by the two loop routes."""

from __future__ import annotations

import re
from pathlib import Path

from rocketwright.aero.flow_frames import FRAME_FOLDER, FRAME_NAME, frame_path, list_frames

__all__ = ["flow_frames_of", "flow_image_path", "flow_images"]

FLOW_IMAGE_NAME = re.compile(r"[A-Za-z0-9+_.-]+\.png")
# rocketcfd names a flow picture after its case: V015p00_A+04p00.png is 15 m/s at +4 degrees.
FLOW_IMAGE_CASE = re.compile(r"V(\d+)p(\d+)_A([+-]?\d+)p(\d+)\.png")


def _flow_directory(artifacts_dir: str | None) -> Path | None:
    return Path(artifacts_dir).resolve() / "flow" if artifacts_dir else None


def flow_images(artifacts_dir: str | None) -> list[dict]:
    """Name, speed and angle of each picture; the analytic backends leave none."""
    flow = _flow_directory(artifacts_dir)
    if flow is None or not flow.is_dir():
        return []
    images = []
    for path in sorted(flow.glob("*.png")):
        if not FLOW_IMAGE_NAME.fullmatch(path.name):
            continue
        case = FLOW_IMAGE_CASE.fullmatch(path.name)
        images.append(
            {
                "name": path.name,
                "speed_mps": float(f"{case[1]}.{case[2]}") if case else None,
                "alpha_deg": float(f"{case[3]}.{case[4]}") if case else None,
            }
        )
    return images


def flow_frames_of(artifacts_dir: str | None) -> list[dict]:
    """The frames taken while the run was solving, in order; only an OpenFOAM run has any."""
    return list_frames(Path(artifacts_dir) / FRAME_FOLDER) if artifacts_dir else []


def flow_image_path(artifacts_dir: str | None, name: str) -> Path:
    """One `flow/*.png` or frame of a run, and nothing else there. KeyError otherwise."""
    if artifacts_dir and FRAME_NAME.fullmatch(name):
        return frame_path(Path(artifacts_dir) / FRAME_FOLDER, name)
    if ".." in name or not FLOW_IMAGE_NAME.fullmatch(name):
        raise KeyError("Unknown image")
    flow = _flow_directory(artifacts_dir)
    if flow is None:
        raise KeyError("Unknown image")
    path = (flow / name).resolve()
    if path.parent != flow or not path.is_file():
        raise KeyError("Unknown image")
    return path
