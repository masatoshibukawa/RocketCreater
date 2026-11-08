"""A cached picture must belong to the same visual inputs, independently of project bookkeeping."""

from copy import deepcopy

import pytest

from rocketwright.agent.video_appearance import recipe
from rocketwright.agent.video_cache import (
    MediaCache,
    composition_key,
    digest,
    pixel_key,
    template_for,
)
from scripts.render_checkpoint import Checkpoint


@pytest.fixture
def job(tmp_path):
    mesh = tmp_path / "nose.stl"
    mesh.write_bytes(b"verified-cad")
    return dict(
        dimensions_mm=dict(overall=600, body_diameter=100, fin_span=50),
        design=dict(
            has_fins=True,
            bottle_volume_m3=0.0015,
            water_fill_frac=0.3,
            dry_mass_kg=0.1,
            payload_mass_kg=0.06,
        ),
        trace=[dict(t_s=0, altitude_m=0), dict(t_s=1, altitude_m=15)],
        cad_files={"nose": str(mesh)},
        appearance_sha256="assets",
        source_id="project-a:v4",
        evidence=["adopted"],
        plan=recipe("photographic")
        | dict(camera="slow_orbit", design_caption="設計", launch_caption="飛行", status="planned"),
    )


def keys(job):
    return {
        mode: pixel_key(job, mode, {"renderer": "code-1"}, "Blender-fixture")
        for mode in ("design", "launch")
    }


def test_project_history_and_cad_path_do_not_invalidate_identical_pixels(job, tmp_path):
    before = keys(job)
    other = tmp_path / "other.stl"
    other.write_bytes(b"verified-cad")
    job.update(source_id="project-b:v8", evidence=["edited"], cad_files={"nose": str(other)})
    job["plan"].update(status="rendered", output_directory="new-path", pending_directory="retry")
    assert keys(job) == before


def test_captions_recompose_without_rerendering_and_trace_only_invalidates_flight(job, tmp_path):
    before = keys(job)
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    old_composition = composition_key(job, "design", before["design"], "compose-1", font)
    job["plan"]["design_caption"] = "寸法の確認"
    assert keys(job) == before
    assert composition_key(job, "design", before["design"], "compose-1", font) != old_composition
    job["trace"][-1]["altitude_m"] = 16
    assert keys(job)["design"] == before["design"]
    assert keys(job)["launch"] != before["launch"]


@pytest.mark.parametrize(
    "change", ["cad", "dimensions", "assets", "airframe", "quality", "runtime"]
)
def test_visual_changes_invalidate_both_clips(job, change):
    before = keys(job)
    if change == "cad":
        from pathlib import Path

        Path(job["cad_files"]["nose"]).write_bytes(b"new-verified-cad")
    elif change == "dimensions":
        job["dimensions_mm"]["overall"] += 10
    elif change == "assets":
        job["appearance_sha256"] = "new-assets"
    elif change == "airframe":
        job["airframe"] = {"id": "pet-15l", "asset_sha256": {"bottle": "changed"}}
    elif change == "quality":
        job["plan"].update(recipe("photographic", "preview"))
    after = (
        {m: pixel_key(job, m, {"renderer": "code-1"}, "new-Blender") for m in before}
        if change == "runtime"
        else keys(job)
    )
    assert all(after[m] != before[m] for m in before)


def test_cache_checks_content_and_rejects_paths(tmp_path):
    cache = MediaCache(tmp_path / "cache")
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"completed-media")
    identity = digest("inputs")
    cache.store("frames", identity, "0000.png", source)
    assert cache.restore("frames", identity, "0000.png", target)
    assert target.read_bytes() == source.read_bytes()
    (cache.directory("frames", identity) / "0000.png").write_bytes(b"damaged")
    assert not cache.restore("frames", identity, "0000.png", target)
    with pytest.raises(ValueError):
        cache.restore("frames", identity, "../outside", target)


def test_resume_invalidates_only_changed_clip_and_still_checks_frame_bytes(tmp_path):
    job = dict(plan={"frames_per_clip": 1}, clip_identities=dict(design="a", launch="b"))
    checkpoint = Checkpoint(tmp_path, job)
    for mode in ("design", "launch"):
        path = tmp_path / f"{mode}-frames/0000.png"
        path.parent.mkdir()
        path.write_bytes(mode.encode())
        checkpoint.finished(path, 1)
    changed = deepcopy(job)
    changed["clip_identities"]["launch"] = "c"
    resumed = Checkpoint(tmp_path, changed)
    assert resumed.valid(tmp_path / "design-frames/0000.png")
    assert not resumed.valid(tmp_path / "launch-frames/0000.png")
    (tmp_path / "design-frames/0000.png").write_bytes(b"tampered")
    assert not resumed.valid(tmp_path / "design-frames/0000.png")


def test_representative_templates_keep_wide_fins_in_frame_without_scaling_geometry():
    compact = dict(overall=400, body_diameter=90, fin_span=40)
    assert template_for(compact)["id"] == "compact"
    assert template_for(compact | {"overall": 600})["id"] == "standard"
    assert template_for(compact | {"overall": 1000})["id"] == "large"
    assert template_for(compact | {"fin_span": 500})["camera_distance_m"] >= 5.45
