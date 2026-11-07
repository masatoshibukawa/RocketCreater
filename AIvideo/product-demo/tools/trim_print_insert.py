"""Remove exactly the first second of the six-second printer master."""

import hashlib
import json
from pathlib import Path
import subprocess

import av
import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    master_report = json.loads((ROOT / "print-progress-verification.json").read_text(encoding="utf-8"))
    folder = REPO / "output/media/product-demo/generated/print-progress"
    source = folder / "printing-progress-6s.mp4"
    target = folder / "printing-progress-5s.mp4"
    before = sha(source)
    assert before == next(v["sha256"] for v in master_report["videos"] if v["file"] == source.name)
    with av.open(str(source)) as container:
        assert float(container.streams.video[0].average_rate) == 30
        original = [f.to_ndarray(format="rgb24") for f in container.decode(video=0)]
    assert len(original) == 180
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source), "-vf", "trim=start_frame=30:end_frame=180,setpts=PTS-STARTPTS",
        "-an", "-r", "30", "-frames:v", "150", "-c:v", "libx264", "-crf", "16",
        "-pix_fmt", "yuv420p", "-color_range", "pc", "-colorspace", "bt470bg",
        "-map_metadata", "-1", "-metadata", "title=Fin printing progress - five second insert",
        "-movflags", "+faststart", str(target),
    ], check=True)
    maximum_error = 0.0
    with av.open(str(target)) as container:
        stream = container.streams.video[0]
        assert float(stream.average_rate) == 30 and not container.streams.audio
        duration = float(stream.duration * stream.time_base)
        assert duration == 5.0
        for index, frame in enumerate(container.decode(video=0)):
            assert index < 150
            delta = frame.to_ndarray(format="rgb24").astype(np.float32) - original[index + 30].astype(np.float32)
            maximum_error = max(maximum_error, float(np.mean(np.abs(delta))))
        assert index + 1 == 150 and maximum_error < 4
        metadata = {"container": dict(container.metadata), "streams": [dict(s.metadata) for s in container.streams]}
    assert sha(source) == before
    result = {
        "checks": "passed", "source": source.relative_to(REPO).as_posix(), "source_sha256": before,
        "source_unchanged": True, "trim_interval_s": [1, 6], "source_frames_inclusive": [30, 179],
        "output": target.relative_to(REPO).as_posix(), "sha256": sha(target), "duration_s": duration,
        "fps": 30, "frames": 150, "audio": False, "all_frames_compared": True,
        "maximum_rgb_mean_absolute_error": maximum_error,
        "original_recording_frame_mapping": master_report["six_second_source_frame_mapping"][30:],
        "metadata": metadata, "scope": master_report["scope"], "full_real_time_playback": False,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "print-insert-5s-verification.json").write_text(text, encoding="utf-8")
    (folder / "verification-5s.json").write_text(text, encoding="utf-8")
    print(json.dumps({"checks": "passed", "duration_s": duration, "frames": 150, "source_unchanged": True}))


if __name__ == "__main__":
    main()
