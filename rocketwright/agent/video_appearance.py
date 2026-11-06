"""Pinned local photographic assets and render recipes, never model-provided paths."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Literal

from rocketwright.agent.local_runtime import LocalRuntimeError

ROOT = Path(__file__).resolve().parents[2]
RenderStyle = Literal["engineering", "photographic"]
MANIFEST = ROOT / "AIvideo/pet-rocket/realism/asset-manifest.json"


def recipe(style: str, quality="final") -> dict:
    if quality not in {"preview", "final"}:
        raise ValueError("Unknown video quality")
    if quality == "preview" and style != "photographic":
        raise ValueError("Lightweight previews require photographic style")
    if style == "engineering":
        return dict(style=style, width=960, height=540, fps=24, frames_per_clip=96)
    if style == "photographic":
        if quality == "preview":
            return dict(
                style=style,
                width=960,
                height=540,
                fps=12,
                frames_per_clip=144,
                design_frames=192,
                launch_frames=144,
                samples=8,
            )
        return dict(
            style=style,
            width=1920,
            height=1080,
            fps=24,
            frames_per_clip=288,
            design_frames=384,
            launch_frames=288,
            samples=32,
        )
    raise ValueError("Unknown video render style")


def plan_key(style: str) -> str:
    recipe(style)
    return "photographic_video_plan" if style == "photographic" else "video_plan"


def asset_files() -> tuple[dict, list[tuple[dict, Path]]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = Path(os.getenv("ROCKETWRIGHT_MEDIA_ROOT", ROOT / "AIvideo")) / "pet-rocket/realism"
    pairs = []
    for row in manifest["files"]:
        path = (base / row["file"]).resolve()
        if not path.is_relative_to((base / "cache").resolve()):
            raise LocalRuntimeError("Photographic asset is outside the fixed cache")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise LocalRuntimeError(
                "Photographic assets are missing or changed; restore the saved cache"
            )
        pairs.append((row, path))
    return manifest, pairs


def appearance_runtime() -> dict:
    try:
        asset_files()
        return {"available": True, "source": "AIvideo/pet-rocket/realism", "license": "CC0-1.0"}
    except (OSError, ValueError, LocalRuntimeError):
        return {"available": False, "source": "AIvideo/pet-rocket/realism", "license": "CC0-1.0"}


def freeze_assets(directory: Path) -> dict:
    manifest, pairs = asset_files()
    cache = directory / "appearance"
    cache.mkdir(exist_ok=True)
    for row, source in pairs:
        target = cache / source.name
        shutil.copyfile(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
            raise LocalRuntimeError("Photographic asset changed while copying")
    (directory / "appearance-sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
