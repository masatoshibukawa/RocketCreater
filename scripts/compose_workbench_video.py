"""Composite trusted evidence labels and fully decode each resulting MP4."""

import argparse
import csv
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import imageio_ffmpeg  # noqa: E402 -- Optional isolated media libraries above.
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from rocketwright.agent.video_cache import MediaCache, composition_key, file_sha  # noqa: E402

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
photographic = plan.get("style") == "photographic"
<<<<<<< HEAD


def encode(mode, path, frame_count):
=======
for mode, filename in (("design", "design-explanation.mp4"), ("launch", "launch-cg.mp4")):
    path = directory / filename
>>>>>>> origin/checkpoint/video-worktree-20261106
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
<<<<<<< HEAD
    for i in range(frame_count):
        if job.get("cancel_file") and Path(job["cancel_file"]).exists():
            writer.close()
            raise RuntimeError("Composition cancelled; source frames retained")
=======
    frame_count = plan.get(mode + "_frames", plan["frames_per_clip"])
    for i in range(frame_count):
>>>>>>> origin/checkpoint/video-worktree-20261106
        with Image.open(directory / f"{mode}-frames/{i:04d}.png") as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        if photographic:
            draw.rectangle(
                (18, image.height - 62, image.width - 18, image.height - 12), fill=(10, 13, 16)
            )
            draw.text(
                (30, image.height - 52),
                "RocketWright / CG・数値解析 / 未実測の形状表現・音声なし",
                font=font,
                fill=(225, 235, 237),
            )
        else:
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
        if not photographic:
            draw.text((26, image.height - 51), label, font=small, fill=(205, 218, 220))
            draw.text(
                (26, image.height - 28),
                "数値解析の可視化 / 実機未検証 / 音声なし",
                font=small,
                fill=(150, 165, 168),
            )
<<<<<<< HEAD
        if photographic:
            draw.rounded_rectangle(
                (18, 16, min(image.width - 18, 650), 55), radius=6, fill=(10, 13, 16)
            )
            draw.text((30, 23), plan[mode + "_caption"], font=font, fill=(225, 235, 237))
=======
>>>>>>> origin/checkpoint/video-worktree-20261106
        writer.send(image.tobytes())
    writer.close()


cache_report = json.loads((directory / "render-cache.json").read_text())
cache = MediaCache(job.get("cache_directory", directory / "local-cache"))
for mode, filename in (("design", "design-explanation.mp4"), ("launch", "launch-cg.mp4")):
    path = directory / filename
    frame_count = plan.get(mode + "_frames", plan["frames_per_clip"])
    identity = composition_key(
        job, mode, cache_report["clips"][mode]["identity"], file_sha(__file__), font_path
    )
    reused = cache.restore("movies", identity, filename, path)
    if not reused:
        encode(mode, path, frame_count)
    cache_report["clips"][mode]["composition_reused"] = reused
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
    metadata = next(reader)
    hashes = set()
    decoded = 0
    for frame in reader:
        decoded += 1
        hashes.add(hashlib.sha256(frame).hexdigest())
    reader.close()
    if decoded != frame_count or len(hashes) < 2:
        raise RuntimeError("Movie did not completely decode into changing frames")
    if not reused:
        cache.store("movies", identity, filename, path)
    # ffmpeg's successful complete decode is separate from visual/physical review.
    records.append(
        {
            "file": filename,
            "fps": metadata["fps"],
            "size": metadata["size"],
            "duration": metadata["duration"],
            "changing_frames": len(hashes) > 1,
            "full_decode": decoded == frame_count,
            "decoded_frames": decoded,
            "audio": "none",
        }
    )
(directory / "render-cache.json").write_text(json.dumps(cache_report, indent=2), encoding="utf-8")
shutil.copyfile(directory / "design-frames/0000.png", directory / "design-reference.png")
shutil.copyfile(directory / "launch-frames/0000.png", directory / "launch-reference.png")
trajectory_check = {"passed": False, "frames": 0, "max_position_error_m": None}
with (directory / "rendered-trajectory.csv").open(encoding="utf-8") as stream:
    states = list(csv.DictReader(stream))
errors = []
for row in states:
    t = float(row["simulation_time_s"])
    trace = job["trace"]
    right = next((i for i, p in enumerate(trace) if p["t_s"] >= t), len(trace) - 1)
    a, b = trace[max(0, right - 1)], trace[right]
    mix = (t - a["t_s"]) / max(1e-9, b["t_s"] - a["t_s"])
    for axis in ("east_m", "north_m", "altitude_m"):
        errors.append(abs(float(row[axis]) - (a[axis] + (b[axis] - a[axis]) * mix)))
expected_count = plan.get("launch_frames", plan["frames_per_clip"])
trajectory_check = {
<<<<<<< HEAD
    "passed": len(states) == expected_count and max(errors, default=1) < 1e-5,
    "frames": len(states),
    "max_position_error_m": max(errors, default=None),
    "attitude": "illustrative, not integrated attitude dynamics",
    "position_basis": states[0].get("position_basis", "solver_position_commands")
    if states
    else None,
    "scope": "Position records against solver interpolation; not independent image tracking",
=======
    "passed": len(states) == expected_count and max(errors, default=1) < 1e-8,
    "frames": len(states),
    "max_position_error_m": max(errors, default=None),
    "attitude": "illustrative, not integrated attitude dynamics",
>>>>>>> origin/checkpoint/video-worktree-20261106
}
(directory / "verification.json").write_text(
    json.dumps(
        {
            "passed": trajectory_check["passed"]
            and all(
                r["changing_frames"]
                and r["full_decode"]
                and r["fps"] == plan["fps"]
                and r["size"] == (plan["width"], plan["height"])
                for r in records
            ),
            "files": records,
            "source_id": job["source_id"],
            "style": plan.get("style", "engineering"),
            "rendered_trajectory": trajectory_check,
            "visual_review": "pending",
            "physical_validation": "not_performed",
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
