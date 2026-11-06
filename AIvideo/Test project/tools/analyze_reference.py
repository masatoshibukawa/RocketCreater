"""Extract timed, unmodified reference frames for shot analysis."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "python"))

import imageio_ffmpeg
from PIL import Image, ImageDraw


def main():
    source = ROOT / "reference" / "source.mp4"
    reader = imageio_ffmpeg.read_frames(str(source), pix_fmt="rgb24")
    metadata = next(reader)
    width, height = metadata["size"]
    fps = metadata["fps"]
    duration = metadata["duration"]
    targets = {round((duration - 0.08) * i / 15 * fps): i for i in range(16)}
    sheet = Image.new("RGB", (4 * 480, 4 * 294), "#15191f")
    draw = ImageDraw.Draw(sheet)
    frames = 0
    for index, frame in enumerate(reader):
        frames += 1
        if index not in targets:
            continue
        number = targets[index]
        image = Image.frombytes("RGB", (width, height), frame)
        image.save(ROOT / "reference" / f"frame_{number:02d}.png")
        image.thumbnail((480, 270))
        x = (number % 4) * 480
        y = (number // 4) * 294
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + 273), f"{index / fps:.2f} s", fill="white")
    sheet.save(ROOT / "reference" / "contact_sheet.jpg", quality=94)
    result = {"metadata": metadata, "decoded_frames": frames}
    (ROOT / "reference" / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    probe = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(source)], capture_output=True, text=True)
    print(json.dumps(result))
    print(probe.stderr)


if __name__ == "__main__":
    main()
