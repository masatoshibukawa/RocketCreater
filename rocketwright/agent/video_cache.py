"""Content-addressed local media cache. No project IDs, captions or absolute CAD paths in pixels."""

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def template_for(dimensions):
    height = dimensions["overall"] / 1000
    width = (dimensions["body_diameter"] + 2 * dimensions["fin_span"]) / 1000
    name = "compact" if height <= 0.45 else "standard" if height <= 0.8 else "large"
    # Both height and fin span must fit. Geometry is never scaled to fit a template.
    return dict(id=name, camera_distance_m=max(height * 4.5, width * 5), fstop=11)


def pixel_key(job, mode, code, runtime):
    plan = job["plan"]
    dimensions = job["dimensions_mm"]
    value = dict(
        schema=1,
        code=code,
        runtime=runtime,
        mode=mode,
        quality={k: plan.get(k) for k in ("style", "width", "height", "fps", "samples")},
        frames=plan.get(mode + "_frames", plan["frames_per_clip"]),
        dimensions=dimensions,
        template=template_for(dimensions),
        cad={k: file_sha(p) for k, p in job.get("cad_files", {}).items()},
        assets=job.get("appearance_sha256"),
        design={k: job["design"][k] for k in ("has_fins", "bottle_volume_m3", "water_fill_frac")},
    )
    if mode == "design":
        value["camera"] = plan["camera"]
    else:
        value.update(
            trace=job["trace"],
            dry_mass=job["design"]["dry_mass_kg"],
            payload_mass=job["design"]["payload_mass_kg"],
        )
    return digest(value)


def composition_key(job, mode, pixel_identity, code, font):
    return digest(
        dict(
            pixels=pixel_identity,
            code=code,
            font=file_sha(font) if Path(font).is_file() else "fallback",
            caption=job["plan"][mode + "_caption"],
            dimensions=job["dimensions_mm"] if mode == "design" else None,
            dry_mass=job["design"]["dry_mass_kg"] if mode == "design" else None,
        )
    )


def atomic_copy(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        shutil.copyfile(source, temp)
        replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def replace(source, target):
    for attempt in range(10):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


class MediaCache:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.manifests = {}

    def directory(self, category, identity):
        if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid media cache identity")
        return self.root / category / identity

    def manifest(self, category, identity):
        key = (category, identity)
        if key not in self.manifests:
            try:
                data = json.loads((self.directory(*key) / "manifest.json").read_text())
                if data.get("identity") != identity:
                    data = {}
            except (OSError, ValueError):
                data = {}
            self.manifests[key] = data.get("files", {})
        return self.manifests[key]

    def restore(self, category, identity, name, target):
        if Path(name).name != name:
            raise ValueError("Cache entries must be filenames")
        entry = self.manifest(category, identity).get(name)
        path = self.directory(category, identity) / name
        try:
            if entry and not path.is_symlink() and file_sha(path) == entry["sha256"]:
                atomic_copy(path, target)
                return True
        except (OSError, KeyError):
            pass
        return False

    def store(self, category, identity, name, source):
        if Path(name).name != name:
            raise ValueError("Cache entries must be filenames")
        directory = self.directory(category, identity)
        atomic_copy(source, directory / name)
        files = self.manifest(category, identity)
        files[name] = {"sha256": file_sha(directory / name)}
        atomic_json(directory / "manifest.json", dict(identity=identity, files=files))
