"""Recalculate the study's opaque sRGB contrast pairs using only the standard library.

Reference: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
This checks color pairs; it does not audit a complete page.
"""

import csv
import math
import re
from pathlib import Path


def luminance(hex_color: str) -> float:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color):
        raise ValueError(f"Expected opaque six-digit sRGB color: {hex_color!r}")
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))


def contrast(foreground: str, background: str) -> float:
    first, second = sorted((luminance(foreground), luminance(background)))
    return (second + 0.05) / (first + 0.05)


def main() -> None:
    if not math.isclose(contrast("#000000", "#FFFFFF"), 21.0):
        raise RuntimeError("Black/white reference pair failed.")
    if not math.isclose(contrast("#121D27", "#121D27"), 1.0):
        raise RuntimeError("Identical-color reference pair failed.")

    source = Path(__file__).resolve().parent.parent / "palette-contrast.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 24:
        raise ValueError("Expected 24 published color pairs.")
    for row in rows:
        ratio = contrast(row["foreground"], row["background"])
        if not math.isclose(ratio, float(row["ratio"]), rel_tol=0, abs_tol=5.01e-9):
            raise ValueError(f"Published ratio differs: {row['palette']} / {row['role']}")
        passes = ratio >= float(row["reference_threshold"])
        if str(passes).lower() != row["passes_pair_check"].lower():
            raise ValueError(f"Published classification differs: {row['palette']} / {row['role']}")
        if not passes:
            raise ValueError(f"Pair below its reference threshold: {row['palette']} / {row['role']}")
        print(f"{row['palette']} / {row['role']}: {ratio:.8f}:1")
    print(f"Verified {len(rows)} pairs and two reference cases.")


if __name__ == "__main__":
    main()
