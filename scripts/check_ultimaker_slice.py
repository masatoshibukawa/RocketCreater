"""Inspect a locally sliced S5 UFP without changing it or contacting a printer."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

MODEL_TYPES = {"WALL-OUTER", "WALL-INNER", "SKIN", "FILL", "GAP-FILL"}


def inspect(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("UFP archive CRC failed")
        text = archive.read("/3D/model.gcode").decode("utf-8")
        metadata = json.loads(archive.read("/Cura/slicemetadata.json"))
        material = ET.fromstring(
            archive.read("/Materials/ultimaker_tough_pla_black.xml.fdm_material")
        )
    properties = {n.tag.rsplit("}", 1)[-1]: n.text for n in material.iter()}
    header = dict(re.findall(r"^;([A-Z0-9._]+):([^\n\r]+)", text, re.MULTILINE))
    if header.get("FLAVOR") != "Griffin" or header.get("TARGET_MACHINE.NAME") != "Ultimaker S5":
        raise ValueError("This review requires a Griffin S5 slice")
    diameter, density = float(properties["diameter"]), float(properties["density"])
    if (
        properties.get("brand") != "Ultimaker"
        or properties.get("material") != "Tough PLA"
        or properties.get("color") != "Black"
        or diameter != 2.85
        or density <= 0
        or properties.get("GUID") != header.get("EXTRUDER_TRAIN.0.MATERIAL.GUID")
        or header.get("EXTRUDER_TRAIN.0.NOZZLE.NAME") != "AA 0.4"
        or float(header.get("EXTRUDER_TRAIN.0.NOZZLE.DIAMETER", "0")) != 0.4
    ):
        raise ValueError("Expected matching Black Tough PLA 2.85 mm and AA 0.4 profiles")
    count = int(re.search(r"^;LAYER_COUNT:(\d+)", text, re.MULTILINE)[1])
    position = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
    layer, kind, tool, absolute_e = -1, "", 0, True
    layers, tools, types = Counter(), Counter(), Counter()
    low, high = [math.inf] * 3, [-math.inf] * 3
    for line in text.splitlines():
        if line.startswith(";LAYER:"):
            layer = int(line.split(":")[1])
        elif line.startswith(";TYPE:"):
            kind = line.split(":")[1]
        elif re.fullmatch(r"T\d+", line):
            tool = int(line[1:])
        elif line == "M82":
            absolute_e = True
        elif line == "M83":
            absolute_e = False
        elif line == "G91":
            raise ValueError("Relative XYZ motion is not handled by this review")
        elif line.startswith(("G0 ", "G1 ", "G92 ")):
            values = {k: float(v) for k, v in re.findall(r"([XYZE])(-?[0-9.]+)", line)}
            if line.startswith("G92 "):
                position.update(values)
                continue
            next_position = position | values
            delta_e = values.get("E", position["E"]) - position["E"]
            if not absolute_e:
                delta_e = values.get("E", 0)
                next_position["E"] = position["E"] + delta_e
            distance = math.hypot(
                next_position["X"] - position["X"], next_position["Y"] - position["Y"]
            )
            if layer >= 0 and line.startswith("G1 ") and delta_e > 0 and distance > 0.0001:
                types[kind] += 1
                tools[tool] += 1
                if kind in MODEL_TYPES:
                    layers[layer] += 1
                    for point in (position, next_position):
                        for index, axis in enumerate("XYZ"):
                            low[index] = min(low[index], point[axis])
                            high[index] = max(high[index], point[axis])
            position = next_position
    if not layers:
        raise ValueError("No model extrusion paths found")
    missing = sorted(set(range(max(layers) + 1)) - layers.keys())
    trailing = list(range(max(layers) + 1, count))
    support = sum(n for name, n in types.items() if name.startswith("SUPPORT"))
    bounds_ok = all(
        0 <= low[i] <= high[i] <= limit + 0.001 for i, limit in enumerate((330, 240, 300))
    )
    if (
        missing
        or len(trailing) > 1
        or max(layers) >= count
        or support
        or set(tools) != {0}
        or not bounds_ok
    ):
        raise ValueError(
            f"Unexpected slice: missing={missing}, support={support}, "
            f"tools={list(tools)}, bounds_ok={bounds_ok}"
        )
    settings = metadata["extruder_0"]["all_settings"]
    volume = float(header["EXTRUDER_TRAIN.0.MATERIAL.VOLUME_USED"])
    seconds = int(header["PRINT.TIME"])
    if volume <= 0 or seconds <= 0:
        raise ValueError("Material and time estimates must be positive")
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "target_machine": header["TARGET_MACHINE.NAME"],
        "generator_version": header["GENERATOR.VERSION"],
        "material_profile": "UltiMaker Black Tough PLA",
        "material_diameter_mm": diameter,
        "material_guid": header["EXTRUDER_TRAIN.0.MATERIAL.GUID"],
        "nozzle_initial_temperature_c": float(header["EXTRUDER_TRAIN.0.INITIAL_TEMPERATURE"]),
        "bed_initial_temperature_c": float(header["BUILD_PLATE.INITIAL_TEMPERATURE"]),
        "estimated_time_seconds": seconds,
        "estimated_filament_m": round(volume / (math.pi * (diameter / 2) ** 2) / 1000, 3),
        "estimated_mass_g": round(volume * density / 1000, 2),
        "layer_count": count,
        "model_layers": len(layers),
        "missing_model_layers": missing,
        "empty_trailing_layers": trailing,
        "support_segments": support,
        "used_tools": sorted(tools),
        "model_path_bounds_mm": [low, high],
        "model_paths_inside_s5": bounds_ok,
        "wall_line_count": settings["wall_line_count"],
        "infill_pct": settings["infill_sparse_density"],
        "layer_height_mm": settings["layer_height"],
        "adhesion_type": settings["adhesion_type"],
        "brim_width_mm": settings["brim_width"],
        "brim_location": settings["brim_location"],
        "physical_configuration_verified": False,
        "print_started": False,
        "limitations": [
            "Path and metadata review only; not physical fit, strength or flight qualification",
            "Bounds exclude machine-specific priming and non-extruding travel",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ufp", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.ufp)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
