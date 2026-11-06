"""Small, Blender-independent render checkpoint with content-verified frame reuse."""

import hashlib
import json
import time
from pathlib import Path


def write(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            temp.replace(path)
            return
        except PermissionError:
            # Windows readers can briefly deny replacement. Keep the last complete
            # checkpoint; never delete it or discard rendered frames to retry.
            if attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


class Checkpoint:
    def __init__(self, directory, job):
        self.directory, self.job = Path(directory), job
        self.path = self.directory / "frame-checkpoint.json"
        self.started = time.time()
        self.samples, self.reused = [], 0
        try:
            old = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            old = {}
        self.frames = (
            old.get("frames", {}) if old.get("identity") == job.get("render_identity") else {}
        )
        self.total = sum(
            job["plan"].get(m + "_frames", job["plan"]["frames_per_clip"])
            for m in ("design", "launch")
        )

    def check_cancel(self):
        path = self.job.get("cancel_file")
        if path and Path(path).exists():
            raise RuntimeError("Render cancelled; verified frames retained")

    def valid(self, path):
        self.check_cancel()
        key = Path(path).relative_to(self.directory).as_posix()
        row = self.frames.get(key)
        if (
            row
            and Path(path).is_file()
            and hashlib.sha256(Path(path).read_bytes()).hexdigest() == row["sha256"]
        ):
            self.reused += 1
            self.update()
            return True
        return False

    def finished(self, path, seconds):
        self.check_cancel()
        key = Path(path).relative_to(self.directory).as_posix()
        self.frames[key] = dict(
            sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), seconds=seconds
        )
        self.samples.append(seconds)
        write(self.path, dict(identity=self.job.get("render_identity"), frames=self.frames))
        self.update()

    def update(self):
        valid = sum((self.directory / key).is_file() for key in self.frames)
        remaining = max(0, self.total - valid)
        timings = self.samples[-10:]
        mean = sum(timings) / len(timings) if timings else None
        write(
            self.directory / "progress.json",
            dict(
                job_id=self.job.get("job_id"),
                phase="rendering",
                completed=valid,
                total=self.total,
                reused=self.reused,
                elapsed_s=time.time() - self.started,
                eta_s=[remaining * mean * 0.8, remaining * mean * 1.5] if mean else None,
                eta_basis="measured last frames; render only" if mean else "not measured",
            ),
        )
