"""Reuse only verified non-pressure parts with identical generating inputs and implementation."""

import json
import os
import uuid
from pathlib import Path

from rocketwright.agent.design_projects import implementation_fingerprint
from rocketwright.agent.video_cache import MediaCache, atomic_json, digest, file_sha
from rocketwright.manufacturing import PrintRequest, parameters

ROOT = Path(__file__).resolve().parents[2]
FILES = ("parameters.json", "geometry-check.json", "fin-assembly-mm.stl") + tuple(
    f"{part}-{suffix}"
    for part in ("nose", "fin", "fit-ring")
    for suffix in ("mm.stl", "mm.3mf", "preview.png")
)


def context(state):
    from rocketwright.agent.design_projects import DesignSpec

    spec = DesignSpec.model_validate(state["spec"])
    design = spec.design.model_copy(update={"geometry": spec.geometry})
    implementation = implementation_fingerprint()
    key = digest(
        dict(parameters=parameters(PrintRequest(design=design)), implementation=implementation)
    )
    cache = MediaCache(os.getenv("ROCKETWRIGHT_AIRFRAME_CACHE", ROOT / "output/airframe-cache"))
    return spec, key, cache, implementation


def publish_parts(store, state):
    if not state.get("airframe_template") or not state.get("analysis"):
        return
    spec, key, cache, implementation = context(state)
    analysis = state["analysis"]
    if analysis["implementation_sha256"] != implementation:
        return
    source = store.base(state["id"]) / f"v{state['version']}" / "cad"
    files = {name: sha for name, sha in analysis["cad_sha256"].items() if name in FILES}
    if not {"parameters.json", "geometry-check.json", "nose-mm.stl"} <= files.keys():
        return
    if any(file_sha(source / name) != sha for name, sha in files.items()):
        raise ValueError("Inspected template CAD changed before caching")
    for name in files:
        cache.store("parts", key, name, source / name)
    atomic_json(
        cache.directory("parts", key) / "verified.json",
        dict(
            geometry_sha256=digest(spec.geometry.model_dump()),
            implementation=implementation,
            files=files,
            basis="existing native CAD checks; no physical qualification",
        ),
    )


def seed_parts(store, state):
    spec, key, cache, implementation = context(state)
    try:
        record = json.loads((cache.directory("parts", key) / "verified.json").read_text())
        if (
            record["implementation"] != implementation
            or record["geometry_sha256"] != digest(spec.geometry.model_dump())
            or not record["files"]
            or set(record["files"]) - set(FILES)
        ):
            return False
        if any(
            file_sha(cache.directory("parts", key) / name) != sha
            for name, sha in record["files"].items()
        ):
            return False
    except (OSError, ValueError, KeyError):
        return False
    target = store.directory(state["id"]) / "cad"
    temp = target.with_name("cad-template-" + uuid.uuid4().hex)
    temp.mkdir()
    for name in record["files"]:
        if not cache.restore("parts", key, name, temp / name):
            return False  # Keep an incomplete attempt for inspection; never mark it reusable.
    temp.rename(target)
    state["cad_reuse"] = dict(
        from_template=state["airframe_template"]["id"],
        geometry_sha256=record["geometry_sha256"],
        cad_sha256=record["files"],
    )
    return True
