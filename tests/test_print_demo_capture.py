"""Replay a pause transition without recording another person's printer job."""

import io
import json
import urllib.error
from types import SimpleNamespace

from scripts import capture_print_demo as recorder


def test_pause_and_resume_then_missing_job_preserves_all_frames(tmp_path, monkeypatch):
    states = iter(["printing", "pausing", "paused", "resuming", "printing", None])
    requests = []

    class ReadOnlyPrinter:
        def open(self, url, timeout):
            requests.append(url)
            if url.endswith("/print_job"):
                state = next(states)
                if state is None:
                    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
                return io.BytesIO(json.dumps({"uuid": "trial", "state": state}).encode())
            return io.BytesIO(b"\xff\xd8test-frame\xff\xd9")

    monkeypatch.setattr(recorder.urllib.request, "build_opener", lambda *_: ReadOnlyPrinter())
    encoded_counts = []
    monkeypatch.setattr(
        recorder,
        "encode",
        lambda directory, *_: encoded_counts.append(
            len(list((directory / "frames").glob("*.jpg")))
        ),
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.touch()
    args = SimpleNamespace(
        out=tmp_path / "capture",
        ffmpeg=ffmpeg,
        interval=0.001,
        max_seconds=5,
        fps=10,
        printer="http://printer.invalid",
        camera="http://printer.invalid/camera",
        job_uuid="trial",
    )

    result = recorder.capture(args)

    assert result["status"] == "target_job_no_longer_available"
    assert result["frame_count"] == result["encoded_frames"] == 5
    assert encoded_counts == [5]
    assert result["last_frame"]["job_state"] == "printing"
    assert requests.count(args.camera) == 5
    assert len(requests) == 11


def test_changed_job_is_not_photographed(tmp_path, monkeypatch):
    class OtherJob:
        def open(self, url, timeout):
            assert url.endswith("/print_job")
            return io.BytesIO(b'{"uuid": "someone-else", "state": "printing"}')

    monkeypatch.setattr(recorder.urllib.request, "build_opener", lambda *_: OtherJob())
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.touch()
    args = SimpleNamespace(
        out=tmp_path / "capture",
        ffmpeg=ffmpeg,
        interval=0.001,
        max_seconds=5,
        fps=10,
        printer="http://printer.invalid",
        camera="http://printer.invalid/camera",
        job_uuid="trial",
    )
    result = recorder.capture(args)
    assert result["status"] == "target_job_no_longer_active"
    assert result["frame_count"] == 0
