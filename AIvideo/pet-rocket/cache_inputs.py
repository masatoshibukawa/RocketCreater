"""Fingerprint the design and scenario inputs used by the PET rendering pipeline."""

import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def signature():
    files=[ROOT/name for name in ("scenario.json","simulation.json","render-settings.json","render_scene.py","timeline.py")]
    files+=sorted((ROOT/"source-data").glob("*.json"))+sorted((ROOT/"assets").glob("*.stl"))
    digest=hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
