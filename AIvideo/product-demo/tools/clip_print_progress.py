"""Create a six-second time-compressed real-printer clip, preserving its full cut range."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess

import av
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    recipe = json.loads((ROOT / "print-progress-cut.json").read_text(encoding="utf-8"))
    source = REPO / recipe["source"]
    assert sha(source) == recipe["source_sha256"]
    out = (REPO / recipe["output_directory"]).resolve()
    assert out.is_relative_to((REPO / "output/media/product-demo").resolve())
    out.mkdir(parents=True, exist_ok=True)
    start, end = recipe["start_frame_inclusive"], recipe["end_frame_exclusive"]
    assert 0 <= start < end <= recipe["first_toppling_frame_observed"]
    source_fps = recipe["source_fps"]
    frames = recipe["demo_duration_s"] * recipe["demo_fps"]
    mapping = [start + round(i * (end - start - 1) / (frames - 1)) for i in range(frames)]
    assert mapping[0] == start and mapping[-1] == end - 1
    assert len(set(mapping)) == frames
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cuts = [
        ("printing-progress-200x.mp4", list(range(start, end)), source_fps),
        ("printing-progress-6s.mp4", mapping, recipe["demo_fps"]),
    ]
    source_images = {}
    source_yuv = {}
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        assert float(stream.average_rate) == source_fps
        assert stream.codec_context.format.name == "yuvj420p" and stream.codec_context.color_range == 2
        width, height = stream.width, stream.height
        for index, frame in enumerate(container.decode(stream)):
            if start <= index < end:
                source_images[index] = frame.to_ndarray(format="rgb24")
                source_yuv[index] = frame.to_ndarray(format="yuvj420p").tobytes()
        assert index + 1 == recipe["source_frames"]
    for name, selected, fps in cuts:
        # Feed the chosen original frames at the output clock; no CFR resampling
        # can duplicate the first frames or drop the final upright frame.
        process = subprocess.Popen([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-color_range", "pc", "-colorspace", "bt470bg", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-frames:v", str(len(selected)), "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-color_range", "pc", "-colorspace", "bt470bg", "-map_metadata", "-1", "-metadata", "title=Fin printing trial progress", "-metadata", "comment=Actual printer recording excerpt; printing progress, not a finished-part demonstration", "-movflags", "+faststart", str(out / name)], stdin=subprocess.PIPE)
        for frame_number in selected:
            process.stdin.write(source_yuv[frame_number])
        process.stdin.close()
        if process.wait():
            raise RuntimeError("Clip encoding failed")
    reports = []
    sheet = Image.new("RGB", (1600, 644), "#101820")
    draw = ImageDraw.Draw(sheet)
    contact_positions = [0, 25, 50, 75, 100, 125, 150, 179]
    for name, selected, fps in cuts:
        max_error, minimum_psnr = 0., float("inf")
        with av.open(str(out / name)) as container:
            assert not container.streams.audio
            stream = container.streams.video[0]
            assert (stream.width, stream.height) == (width, height)
            assert Fraction(stream.average_rate) == Fraction(fps)
            for index, frame in enumerate(container.decode(stream)):
                assert index < len(selected)
                actual = frame.to_ndarray(format="rgb24")
                expected = source_images[selected[index]]
                delta = actual.astype(np.float32) - expected.astype(np.float32)
                mae = float(np.mean(np.abs(delta)))
                mse = float(np.mean(delta * delta))
                psnr = 99. if mse == 0 else 10 * math.log10(255 * 255 / mse)
                max_error = max(max_error, mae)
                minimum_psnr = min(minimum_psnr, psnr)
                if name.endswith("6s.mp4") and index in contact_positions:
                    slot = contact_positions.index(index)
                    x, y = slot % 4 * 400, slot // 4 * 322
                    sheet.paste(Image.fromarray(actual).resize((400, 300)), (x, y))
                    draw.text((x + 7, y + 304), f"{index/fps:.2f}s / source {selected[index]}", fill="white")
                    if index == contact_positions[-1]:
                        Image.fromarray(actual).save(out / "last-upright-frame.png")
            assert index + 1 == len(selected)
            metadata = {"container": dict(container.metadata), "streams": [dict(s.metadata) for s in container.streams]}
        assert max_error < 4 and minimum_psnr > 35, (name, max_error, minimum_psnr)
        assert not any(word in json.dumps(metadata).lower() for word in ("chatgpt", "codex", "c:\\users\\", "utm_"))
        reports.append({"file": name, "sha256": sha(out / name), "bytes": (out / name).stat().st_size, "width": width, "height": height, "fps": fps, "frames": len(selected), "duration_s": len(selected) / fps, "full_decode": "passed", "maximum_rgb_mean_absolute_error": max_error, "minimum_rgb_psnr_db": minimum_psnr, "first_source_frame": selected[0], "last_source_frame": selected[-1], "metadata": metadata})
    sheet.save(out / "contact.jpg", quality=95)
    assert sha(source) == recipe["source_sha256"]
    result = {"checks": "passed", "source": recipe["source"], "source_sha256": recipe["source_sha256"], "source_unchanged": True, "cut_source_interval_s": [start / source_fps, end / source_fps], "cut_duration_s": (end - start) / source_fps, "additional_speed_multiplier": ((end - start) / source_fps) / recipe["demo_duration_s"], "nominal_combined_speed_multiplier": recipe["source_nominal_speed_multiplier"] * ((end - start) / source_fps) / recipe["demo_duration_s"], "six_second_source_frame_mapping": mapping, "videos": reports, "scope": recipe["scope"], "source_gap_note": recipe["source_recording_gap"], "design_binding": recipe["design_binding"], "full_real_time_playback": False}
    (ROOT / "print-progress-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": "passed", "cut_seconds": result["cut_duration_s"], "demo_seconds": recipe["demo_duration_s"], "additional_speed_multiplier": result["additional_speed_multiplier"], "videos": [r["file"] for r in reports]}, indent=2))


if __name__ == "__main__":
    main()
