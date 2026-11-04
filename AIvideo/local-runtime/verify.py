"""Remux and fully decode the generated clip; create a timed contact sheet."""

import hashlib
import json
from pathlib import Path
import subprocess

import av
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from bootstrap import ROOT


def main():
    request = json.loads((ROOT / "generation-result.json").read_text())
    if request["status"]["status_str"] != "success":
        raise RuntimeError("Generation has not succeeded")
    output = ROOT / "outputs"
    saved = request["outputs"]["12"]["images"][0]
    source = (output / saved["subfolder"] / saved["filename"]).resolve()
    if saved["type"] != "output" or not source.is_relative_to(output.resolve()):
        raise ValueError("Unexpected output path in generation result")
    final = output / "rocketwright_wan22_test.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-map", "0:v:0", "-c", "copy", "-map_metadata", "-1", "-metadata", "title=RocketWright Fairing AI Video Test", "-metadata", "comment=AI-generated with Wan2.2 TI2V-5B from an original Blender concept render; no engineering validation", "-movflags", "+faststart", str(final)], check=True)
    selected = sorted({0, request["frames"] // 5, request["frames"] * 2 // 5, request["frames"] * 3 // 5, request["frames"] * 4 // 5, request["frames"] - 1})
    sheet = Image.new("RGB", (3 * 416, 2 * 266), "#101820")
    draw = ImageDraw.Draw(sheet)
    count = 0
    previous = None
    motion = []
    first = last = None
    with av.open(str(final)) as container:
        stream = container.streams.video[0]
        dimensions = (stream.width, stream.height)
        fps = float(stream.average_rate)
        codec = stream.codec_context.name
        metadata = dict(container.metadata)
        audio_streams = len(container.streams.audio)
        for index, frame in enumerate(container.decode(stream)):
            count += 1
            image = frame.to_image().convert("RGB")
            small = np.asarray(image.resize((208, 120)), dtype=np.float32)
            if previous is not None:
                motion.append(float(np.abs(small - previous).mean()))
            previous = small
            if index == 0:
                first = small
                image.save(output / "first_frame.png")
            last = small
            if index in selected:
                position = selected.index(index)
                x, y = position % 3 * 416, position // 3 * 266
                thumb = image.copy()
                thumb.thumbnail((416, 240))
                sheet.paste(thumb, (x + (416 - thumb.width) // 2, y))
                draw.text((x + 8, y + 245), f"{index / fps:.2f}s / frame {index + 1}", fill="white")
        image.save(output / "last_frame.png")
    assert dimensions == (request["width"], request["height"])
    assert count == request["frames"] and fps == request["fps"]
    assert np.std(first) > 5 and np.std(last) > 5
    assert motion and max(motion) > 0.1, "No measurable frame change"
    metadata_hits = [term for term in ["c:\\users\\", "chatgpt", "codex", "utm_"] if term in json.dumps(metadata).lower()]
    assert not metadata_hits
    sheet.save(output / "contact_sheet.jpg", quality=94)
    report = {
        "file": "outputs/" + final.name,
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "bytes": final.stat().st_size,
        "video": {"width": dimensions[0], "height": dimensions[1], "fps": fps, "decoded_frames": count, "duration_seconds": count / fps, "codec": codec, "audio_streams": audio_streams},
        "generation_seconds": request["elapsed_seconds"],
        "frame_change_mean_absolute_pixel_difference": {"consecutive_mean": round(float(np.mean(motion)), 3), "first_to_last": round(float(np.abs(last - first).mean()), 3)},
        "metadata": metadata,
        "checks": {"full_decode": "passed", "dimensions_fps_and_frames": "passed", "nonblank_and_changing_frames": "passed", "metadata_paths_and_working_labels": "passed"},
        "visual_review": "Contact sheet created; review separately. No exact geometry preservation claim.",
        "watermark": "No service watermark or logo compositing step is used. Inspect the generated image for unwanted text separately.",
        "audio": "Silent model output; no generated audio added.",
    }
    (ROOT / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
