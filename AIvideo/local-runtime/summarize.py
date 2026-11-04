"""Build a concise campaign record and before/after visual from completed takes."""

import json
from PIL import Image, ImageDraw

from bootstrap import ROOT
from iterate import RECORDS, OUTPUTS, digest, gallery, write_json


def main():
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(RECORDS.glob("*/record.json"))]
    complete = [record for record in records if record["status"] == "completed"]
    selected = []
    for record in complete:
        review_path = RECORDS / record["id"] / "review.json"
        if review_path.exists() and json.loads(review_path.read_text(encoding="utf-8"))["decision"] == "selected":
            selected.append(record)
    if len(selected) != 1:
        raise ValueError("Select exactly one take before making the campaign summary")
    winner = selected[0]
    assert digest(ROOT / winner["output"]) == winner["output_sha256"]
    baseline = OUTPUTS / "baseline-5b/poster.jpg"
    after = OUTPUTS / winner["id"] / "poster.jpg"
    canvas = Image.new("RGB", (1280, 420), "#10151c")
    draw = ImageDraw.Draw(canvas)
    for x, path, label in [(0, baseline, "Before: CG source / Wan2.2 5B"), (640, after, "After: photographic concept / Wan2.2 14B")]:
        with Image.open(path) as image:
            image.thumbnail((640, 360))
            canvas.paste(image, (x + (640-image.width)//2, 28))
        draw.text((x + 12, 8), label, fill="white")
    draw.text((12, 397), "Local AI concept comparison. Geometry differs; this is not engineering validation.", fill="#b5c4d0")
    canvas.save(OUTPUTS / "before_after.jpg", quality=95)
    summary = {
        "selected_take": winner["id"],
        "selected_video": winner["output"],
        "sha256": winner["output_sha256"],
        "video": winner["metrics"],
        "server_seconds": winner["server_seconds"],
        "completed_takes": len(complete),
        "generated_images": sum(record["config"]["backend"] == "photo" for record in complete),
        "generated_videos": sum(record["config"]["backend"] in {"wan5b", "wan14b"} for record in complete),
        "imported_baselines": sum(record["config"]["backend"] == "import" for record in complete),
        "gallery": "outputs/experiments/index.html",
        "comparison_image": "outputs/experiments/before_after.jpg",
        "findings": [
            "In reviewed frames, photographic source preparation improved material and workshop appearance more clearly than prompt changes on the original CG.",
            "The 14B candidates preserve the photographic source appearance, but this small trial does not establish a general quality advantage over 5B.",
            "The 720p candidate succeeds at higher resolution with substantially higher generation time; softened thin details remain.",
            "Source concepts change mechanical geometry. Nozzle orientation remains incorrect relative to the intended upright rocket arrangement.",
        ],
        "review_scope": "Source images, timed contact sheets and selected full-resolution frames. Full real-time playback was not reviewed.",
        "audio": "Silent outputs",
    }
    write_json(ROOT / "experiment-summary.json", summary)
    gallery()
    print(json.dumps({key:summary[key] for key in ("selected_take", "completed_takes", "generated_images", "generated_videos", "server_seconds")}, indent=2))


if __name__ == "__main__":
    main()
