"""Record one already-running printer job; never send printer control commands."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def write_state(directory: Path, state: dict) -> None:
    temporary = directory / "capture-state.tmp"
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / "capture-state.json")


def encode(directory: Path, ffmpeg: Path, fps: int) -> None:
    temporary = directory / "printer-timelapse-building.mp4"
    with (directory / "timelapse-encoding.log").open("a", encoding="utf-8") as log:
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(directory / "frames/printer-%05d.jpg"),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                str(temporary),
            ],
            stdout=log,
            stderr=log,
            check=True,
            timeout=60,
        )
    temporary.replace(directory / "printer-timelapse.mp4")


def capture(args) -> dict:
    directory = args.out.resolve()
    frames = directory / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    if list(frames.glob("printer-*.jpg")) or (directory / "capture-state.json").exists():
        raise ValueError("Use a new capture directory; existing recordings are preserved")
    if not args.ffmpeg.is_file() or args.interval <= 0 or args.max_seconds <= 0:
        raise ValueError("A local ffmpeg and positive recording intervals are required")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def read(url: str, limit: int = 1_000_000) -> bytes:
        with opener.open(url, timeout=8) as response:
            return response.read(limit)

    state = {
        "status": "recording",
        "source": "Built-in camera of the laboratory S5; actual photographs",
        "capture_started_utc": dt.datetime.now(dt.UTC).isoformat(),
        "interval_seconds": args.interval,
        "playback_fps": args.fps,
        "nominal_speed_multiplier": args.interval * args.fps,
        "frame_count": 0,
        "audio": "none",
        "printer_control_commands_sent": 0,
        "first_layer_adhesion": "awaiting_physical_observation",
    }
    write_state(directory, state)
    started = time.monotonic()
    failures = 0
    last_encoded = 0
    try:
        while time.monotonic() - started < args.max_seconds:
            tick = time.monotonic()
            if (directory / "STOP").exists():
                state["status"] = "stopped_by_local_request"
                break
            try:
                job = json.loads(read(args.printer.rstrip("/") + "/api/v1/print_job"))
                if job.get("uuid") != args.job_uuid:
                    state["status"] = "target_job_no_longer_active"
                    break
                stamp = dt.datetime.now(dt.UTC).isoformat()
                data = read(args.camera, 3_000_000)
                if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                    raise ValueError("Camera did not return a complete JPEG")
                filename = f"printer-{state['frame_count']:05d}.jpg"
                (frames / filename).write_bytes(data)
                row = {
                    "file": "frames/" + filename,
                    "captured_at_utc": stamp,
                    "job_state": job.get("state"),
                    "progress": job.get("progress"),
                    "print_time_elapsed_seconds": job.get("time_elapsed"),
                }
                with (directory / "frame-times.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps(row) + "\n")
                state["frame_count"] += 1
                state["last_frame"] = row
                failures = 0
                if job.get("state") not in {"pre_print", "printing", "paused"}:
                    state["status"] = "target_job_ended"
                    break
            except (OSError, ValueError, urllib.error.URLError) as exc:
                failures += 1
                state["last_error_type"] = type(exc).__name__
                state["consecutive_read_failures"] = failures
                if failures >= 5:
                    state["status"] = "stopped_after_read_failures"
                    break
            if state["frame_count"] - last_encoded >= 15:
                try:
                    encode(directory, args.ffmpeg, args.fps)
                    last_encoded = state["frame_count"]
                    state["encoded_frames"] = last_encoded
                except (OSError, subprocess.SubprocessError) as exc:
                    state["encoding_error_type"] = type(exc).__name__
            write_state(directory, state)
            time.sleep(max(0, args.interval - (time.monotonic() - tick)))
        else:
            state["status"] = "recording_time_limit_reached"
    finally:
        if state["frame_count"]:
            try:
                encode(directory, args.ffmpeg, args.fps)
                state["encoded_frames"] = state["frame_count"]
            except (OSError, subprocess.SubprocessError) as exc:
                state["encoding_error_type"] = type(exc).__name__
        state["capture_stopped_utc"] = dt.datetime.now(dt.UTC).isoformat()
        write_state(directory, state)
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--printer", required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--job-uuid", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--interval", default=20, type=float)
    parser.add_argument("--fps", default=10, type=int)
    parser.add_argument("--max-seconds", default=5400, type=float)
    print(json.dumps(capture(parser.parse_args())))
