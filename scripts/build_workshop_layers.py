"""Cut the workshop drafts into a base picture and moving parts for web/public/workshop/.

Each part is a feathered polygon of the draft; the base has the hole filled by diffusion, so
that a head or arm can move without leaving a double image. Writes the pictures and the layer
table web/app/lib/workshopLayers.ts. Run: uv run python scripts/build_workshop_layers.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "final output ui example" / "drafts"
OUT = ROOT / "web" / "public" / "workshop"
TABLE = ROOT / "web" / "app" / "lib" / "workshopLayers.ts"

SUPERSAMPLE = 4
FEATHER_PX = 1.2
HOLE_MARGIN_PX = 3
FILL_ITERATIONS = 400

# Polygons and pivots are in the cropped picture's pixels. Moves are named in workshop.css.
SCENES = {
    "diorama": {
        "draft": "02-analysis.png",
        "box": (372, 92, 1262, 792),
        "cover": ((480, 108, 572, 160), (380, 108, 490, 160)),  # the drafted 解析中 badge
        "parts": {
            "top-head": ("nod", (530, 196), [(497, 146), (505, 133), (520, 126), (541, 126),
                                             (558, 137), (567, 158), (566, 176), (561, 188),
                                             (548, 191), (540, 195), (525, 195), (510, 191),
                                             (502, 180), (499, 160)]),
            "top-board": ("write", (528, 214), [(461, 182), (478, 177), (482, 168), (490, 176),
                                                (504, 183), (507, 192), (518, 198), (523, 214),
                                                (516, 226), (500, 226), (472, 234), (461, 226)]),
            "left-head": ("nod", (186, 498), [(151, 470), (155, 445), (170, 428), (195, 423),
                                              (215, 430), (228, 448), (234, 456), (224, 462),
                                              (222, 480), (210, 493), (190, 498), (172, 491),
                                              (164, 479)]),
            "left-tool": ("measure", (214, 526), [(217, 518), (236, 510), (247, 496), (239, 482),
                                                  (250, 473), (277, 480), (279, 489), (270, 493),
                                                  (273, 532), (262, 532), (258, 503), (247, 530),
                                                  (232, 541), (216, 538)]),
            "right-head": ("nod", (694, 501), [(655, 468), (661, 441), (680, 425), (705, 422),
                                               (725, 434), (733, 456), (729, 471), (721, 473),
                                               (716, 478), (710, 489), (690, 498), (672, 491),
                                               (664, 479)]),
            "right-hand-a": ("fold", (662, 520), [(645, 527), (660, 519), (675, 525), (675, 541),
                                                  (664, 547), (650, 546), (644, 536)]),
            "right-hand-b": ("fold-late", (722, 524), [(703, 536), (720, 524), (733, 524),
                                                       (736, 540), (722, 553), (706, 551)]),
        },
    },
    "crew": {
        "draft": "06-analysis-backscreen.png",
        "box": (306, 552, 1352, 772),
        "parts": {
            "left-head": ("nod", (176, 95), [(147, 82), (150, 60), (165, 44), (185, 41),
                                             (200, 49), (209, 62), (204, 67), (201, 78),
                                             (193, 89), (178, 93), (166, 89), (160, 85)]),
            "left-tool": ("measure", (196, 112), [(201, 110), (212, 104), (221, 92), (214, 86),
                                                  (225, 81), (242, 87), (243, 95), (237, 97),
                                                  (236, 123), (229, 123), (227, 103), (218, 113),
                                                  (206, 126), (199, 121)]),
            "middle-head": ("nod", (731, 100), [(705, 62), (712, 54), (725, 46), (745, 46),
                                                (759, 60), (761, 80), (756, 93), (741, 93),
                                                (736, 99), (720, 99), (708, 88)]),
            "right-head": ("nod", (846, 58), [(827, 30), (830, 14), (845, 4), (865, 7), (879, 22),
                                              (879, 45), (866, 53), (851, 51), (846, 56),
                                              (832, 51)]),
            "right-arm": ("point", (838, 60), [(796, 22), (805, 19), (816, 37), (836, 47),
                                               (840, 63), (822, 66), (805, 51), (796, 40)]),
        },
    },
}


def polygon_mask(size: tuple[int, int], points: list[tuple[int, int]]) -> Image.Image:
    big = Image.new("L", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), 0)
    ImageDraw.Draw(big).polygon([(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points], fill=255)
    return big.resize(size, Image.LANCZOS)


def fill_holes(picture: Image.Image, holes: np.ndarray) -> Image.Image:
    """Diffuse the surrounding colours into the holes."""
    pixels = np.asarray(picture, dtype=np.float32).copy()
    known = pixels.copy()
    pixels[holes] = pixels[~holes].mean(axis=0)
    for _ in range(FILL_ITERATIONS):
        blurred = ndimage.uniform_filter(pixels, size=(3, 3, 1))
        pixels[holes] = blurred[holes]
    pixels[~holes] = known[~holes]
    return Image.fromarray(pixels.round().astype(np.uint8))


def build_scene(name: str, scene: dict) -> dict:
    draft = Image.open(DRAFTS / scene["draft"]).convert("RGB")
    if "cover" in scene:
        source, target = scene["cover"]
        draft.paste(draft.crop(source).resize((target[2] - target[0], target[3] - target[1])),
                    target[:2])
    picture = draft.crop(scene["box"])
    holes = np.zeros((picture.height, picture.width), dtype=bool)
    parts = []
    for part, (move, pivot, points) in scene["parts"].items():
        mask = polygon_mask(picture.size, points)
        holes |= ndimage.binary_dilation(np.asarray(mask) > 8, iterations=HOLE_MARGIN_PX)
        alpha = mask.filter(ImageFilter.GaussianBlur(FEATHER_PX))
        box = alpha.getbbox()
        layer = picture.convert("RGBA")
        layer.putalpha(alpha)
        file = f"{name}-{part}.webp"
        layer.crop(box).save(OUT / file, quality=90, method=6)
        width, height = box[2] - box[0], box[3] - box[1]
        parts.append({
            "src": f"/workshop/{file}", "move": move,
            "left": round(100 * box[0] / picture.width, 3),
            "top": round(100 * box[1] / picture.height, 3),
            "width": round(100 * width / picture.width, 3),
            "originX": round(100 * (pivot[0] - box[0]) / width, 1),
            "originY": round(100 * (pivot[1] - box[1]) / height, 1),
        })
    fill_holes(picture, holes).save(OUT / f"{name}-base.webp", quality=88, method=6)
    return {"base": f"/workshop/{name}-base.webp", "width": picture.width,
            "height": picture.height, "parts": parts}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenes = {name: build_scene(name, scene) for name, scene in SCENES.items()}
    TABLE.write_text(
        "/** Generated by scripts/build_workshop_layers.py. */\n\n"
        f"export const WORKSHOP_SCENES = {json.dumps(scenes, indent=2)} as const;\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
