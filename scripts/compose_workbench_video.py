"""Composite trusted evidence labels and fully decode each resulting MP4."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("job", type=Path)
parser.add_argument("--libs", type=Path)
args = parser.parse_args()
if args.libs and args.libs.is_dir():
    sys.path.insert(0, str(args.libs))
import imageio_ffmpeg  # noqa: E402 -- Optional isolated media libraries above.
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

job = json.loads(args.job.read_text(encoding="utf-8"))
directory = args.job.parent
plan = job["plan"]
font_path = Path("C:/Windows/Fonts/YuGothM.ttc")
font = (
    ImageFont.truetype(str(font_path), 20)
    if font_path.is_file()
    else ImageFont.load_default(size=20)
)
small = ImageFont.truetype(str(font_path), 15) if font_path.is_file() else font
records = []
for mode, filename in (("design", "design-explanation.mp4"), ("launch", "launch-cg.mp4")):
    path = directory / filename
    writer = imageio_ffmpeg.write_frames(
        str(path),
        (plan["width"], plan["height"]),
        fps=plan["fps"],
        codec="libx264",
        pix_fmt_out="yuv420p",
        macro_block_size=2,
        output_params=["-movflags", "+faststart", "-map_metadata", "-1"],
    )
    writer.send(None)
    for i in range(plan["frames_per_clip"]):
        with Image.open(directory / f"{mode}-frames/{i:04d}.png") as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, image.width, 86), fill=(10, 13, 16))
        draw.text(
            (26, 15),
            "RocketWright  /  " + ("設計の構成" if mode == "design" else "飛行解析の再生"),
            font=font,
            fill=(225, 235, 237),
        )
        draw.text(
            (26, 49),
            plan["design_caption" if mode == "design" else "launch_caption"],
            font=small,
            fill=(162, 195, 199),
        )
        draw.rectangle((0, image.height - 62, image.width, image.height), fill=(10, 13, 16))
        if mode == "design":
            label = (
                f"全長 {job['dimensions_mm']['overall']:.0f} mm  /  "
                f"乾燥質量 {job['design']['dry_mass_kg'] * 1000:.1f} g"
            )
        else:
            label = "軌跡は計算結果・機体姿勢と地面は概形表示 / 飛行時間を短縮再生"
        draw.text((26, image.height - 51), label, font=small, fill=(205, 218, 220))
        draw.text(
            (26, image.height - 28),
            "数値解析の可視化 / 実機未検証 / 音声なし",
            font=small,
            fill=(150, 165, 168),
        )
        writer.send(image.tobytes())
    writer.close()
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    metadata = next(reader)
    hashes = set()
    decoded = 0
    for frame in reader:
        decoded += 1
        hashes.add(hashlib.sha256(frame).hexdigest())
    reader.close()
    # ffmpeg's successful complete decode is separate from visual/physical review.
    records.append(
        {
            "file": filename,
            "fps": metadata["fps"],
            "size": metadata["size"],
            "duration": metadata["duration"],
            "changing_frames": len(hashes) > 1,
            "full_decode": decoded == plan["frames_per_clip"],
            "decoded_frames": decoded,
            "audio": "none",
        }
    )
shutil.copyfile(directory / "design-frames/0000.png", directory / "design-reference.png")
shutil.copyfile(directory / "launch-frames/0000.png", directory / "launch-reference.png")
(directory / "verification.json").write_text(
    json.dumps(
        {
            "passed": all(
                r["changing_frames"]
                and r["full_decode"]
                and r["fps"] == plan["fps"]
                and r["size"] == (plan["width"], plan["height"])
                for r in records
            ),
            "files": records,
            "source_id": job["source_id"],
            "visual_review": "pending",
            "physical_validation": "not_performed",
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
