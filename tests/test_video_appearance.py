"""Photographic production reuses hash-bound local assets without network access."""

import hashlib
import json

import pytest
from pydantic import ValidationError

import rocketwright.agent.video_appearance as appearance
from api.workbench import PlanRequest, RenderRequest
from rocketwright.agent.local_runtime import LocalRuntimeError


def test_styles_are_bounded_before_starting_a_render():
    assert appearance.recipe("engineering")["frames_per_clip"] == 96
    with pytest.raises(ValueError):
        appearance.recipe("arbitrary-command")
    with pytest.raises(ValidationError):
        PlanRequest(revision=0, style="arbitrary-command")
    with pytest.raises(ValidationError):
        RenderRequest(revision=0, style="arbitrary-command")


def test_photographic_assets_missing_changed_and_escaping_cache_are_rejected(tmp_path, monkeypatch):
    media = tmp_path / "media"
    base = media / "pet-rocket/realism/cache"
    base.mkdir(parents=True)
    image = base / "workshop.exr"
    content = b"licensed-local-asset-fixture"
    row = {
        "file": "cache/workshop.exr",
        "sha256": hashlib.sha256(content).hexdigest(),
        "license": "CC0-1.0",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": [row]}), encoding="utf-8")
    monkeypatch.setenv("ROCKETWRIGHT_MEDIA_ROOT", str(media))
    monkeypatch.setattr(appearance, "MANIFEST", manifest)
    assert not appearance.appearance_runtime()["available"]
    image.write_bytes(content)
    out = tmp_path / "render"
    out.mkdir()
    appearance.freeze_assets(out)
    assert (out / "appearance/workshop.exr").read_bytes() == content
    image.write_bytes(b"changed")
    with pytest.raises(LocalRuntimeError, match="changed"):
        appearance.freeze_assets(out)
    manifest.write_text(json.dumps({"files": [row | {"file": "../outside.exr"}]}), encoding="utf-8")
    with pytest.raises(LocalRuntimeError, match="outside"):
        appearance.asset_files()
