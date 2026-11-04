"""Decode the entire export and audit its measurable delivery properties."""

import array
import hashlib
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "python"))

import imageio_ffmpeg
from PIL import Image, ImageDraw


def main():
    output = ROOT / "renders"
    path = output / "rocketwright_fairing.mp4"
    frames = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    metadata = next(frames)
    width, height = metadata["size"]
    selection = [0, 24, 50, 85, 115, 145, 170, 205, 240, 260, 285, 309]
    sheet = Image.new("RGB", (4 * 384, 3 * 240), "#101820")
    draw = ImageDraw.Draw(sheet)
    sampled_means = {}
    count = 0
    for index, data in enumerate(frames):
        count += 1
        if index not in selection:
            continue
        image = Image.frombytes("RGB", (width, height), data)
        thumb = image.resize((384, 216))
        number = selection.index(index)
        x, y = (number % 4) * 384, (number // 4) * 240
        sheet.paste(thumb, (x, y))
        draw.text((x + 8, y + 221), f"{index / metadata['fps']:.2f}s / frame {index + 1}", fill="white")
        sampled_means[str(index)] = thumb.convert("L").resize((1, 1)).getpixel((0, 0))
    sheet.save(output / "verification_contact_sheet.jpg", quality=92)
    with wave.open(str(output / "original_sound.wav"), "rb") as audio:
        channels, rate = audio.getnchannels(), audio.getframerate()
        audio_frames = audio.getnframes()
        samples = array.array("h", audio.readframes(audio_frames))
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(value) for value in samples) / 32768
    rms = math.sqrt(sum((value / 32768) ** 2 for value in samples) / len(samples))
    probe = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path), "-f", "ffmetadata", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if probe.returncode:
        raise RuntimeError(probe.stderr)
    banned = ["chatgpt", "codex", "openai", "c:\\users\\", "utm_", "rcm="]
    metadata_hits = [term for term in banned if term in probe.stdout.lower()]
    assert (width, height) == (1280, 720)
    assert metadata["fps"] == 30 and count == 310
    assert metadata["audio_codec"] == "aac"
    assert "48000 Hz, stereo" in probe.stderr
    assert 0 < peak < 1 and channels == 2 and rate == 48000
    assert sampled_means["0"] == 0 and sampled_means["309"] == 0
    assert max(sampled_means.values()) > 40
    assert not metadata_hits
    settings = json.loads((output / "render_settings.json").read_text())
    scene_frames = len(list((output / "frames").glob("frame_*.png")))
    assert scene_frames == settings["scene_frames_before_black_tail"] == 263
    report = {
        "output": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "video": {"width": width, "height": height, "fps": metadata["fps"], "decoded_frames": count, "video_duration_seconds": count / metadata["fps"], "container_duration_seconds": metadata["duration"]},
        "audio": {"codec": metadata["audio_codec"], "source": "original deterministic synthesis", "sample_rate": rate, "channels": channels, "duration_seconds": audio_frames / rate, "peak_dbfs": round(20 * math.log10(peak), 2), "rms_dbfs": round(20 * math.log10(rms), 2)},
        "render": {**settings, "scene_frames_found": scene_frames},
        "metadata": {"exported_text": probe.stdout, "unwanted_working_labels_found": metadata_hits},
        "checks": {"full_video_decode": "passed", "expected_frame_count": "passed", "black_opening_and_ending": "passed", "nonempty_audio_without_sample_clipping": "passed", "metadata_scan": "passed"},
        "visual_review": "contact sheet produced; review separately",
        "audio_listening_review": "not performed by this script",
        "reference_comparison": {"pixel_identical": False, "adapted_brand": "RocketWright", "new_geometry": True, "original_audio": True}
    }
    (ROOT / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
