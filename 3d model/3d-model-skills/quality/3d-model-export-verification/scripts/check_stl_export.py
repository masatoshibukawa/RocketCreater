"""Measure an exported STL's bounds without editing it. Python standard library only.

Units are explicit: STL has no reliable unit metadata. This tool does not assess
topology, wall thickness, placement, supports, fit or physical print readiness.
Exit 0: measurements completed and requested comparisons pass; 2: a comparison
fails; 1: unreadable/unsupported data; argparse uses 2 for invalid arguments.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4}


def finite_values(tokens, count):
    if len(tokens) != count:
        raise ValueError("Unexpected number of STL coordinates")
    values = [float(v) for v in tokens]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("STL contains non-finite coordinates or normals")
    return values


def ascii_triangles(blob):
    """Read one standard ASCII STL container; reject incomplete facets."""
    lines = [line.strip() for line in blob.decode("utf-8-sig").splitlines() if line.strip()]
    if not lines or lines[0].split()[0].lower() != "solid":
        raise ValueError("Not a complete ASCII or binary STL")
    i, count = 1, 0
    while i < len(lines) and lines[i].split()[0].lower() != "endsolid":
        if i + 6 >= len(lines):
            raise ValueError("Incomplete ASCII STL facet")
        facet = lines[i].lower().split()
        if facet[:2] != ["facet", "normal"]:
            raise ValueError("Expected ASCII STL facet normal")
        finite_values(facet[2:], 3)
        if lines[i + 1].lower().split() != ["outer", "loop"]:
            raise ValueError("Expected ASCII STL outer loop")
        vertices = []
        for line in lines[i + 2:i + 5]:
            words = line.split()
            if not words or words[0].lower() != "vertex":
                raise ValueError("Expected three ASCII STL vertices")
            vertices.append(finite_values(words[1:], 3))
        if lines[i + 5].lower() != "endloop" or lines[i + 6].lower() != "endfacet":
            raise ValueError("Incomplete ASCII STL facet")
        yield vertices
        i += 7
        count += 1
    if count == 0 or i != len(lines) - 1 or lines[i].split()[0].lower() != "endsolid":
        raise ValueError("Empty, incomplete or multiple-container ASCII STL")


def triangles(blob):
    # A binary header may begin with 'solid'; exact record length takes precedence.
    if len(blob) >= 84:
        count = struct.unpack_from("<I", blob, 80)[0]
        if len(blob) == 84 + 50 * count:
            if count == 0:
                raise ValueError("STL contains no facets")
            for offset in range(84, len(blob), 50):
                values = struct.unpack_from("<12f", blob, offset)
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("STL contains non-finite coordinates or normals")
                yield [values[3:6], values[6:9], values[9:12]]
            return
    yield from ascii_triangles(blob)


def inspect_stl(path, unit, expected=None, tolerance=None, build_volume=None,
                xy_margin=0.0, z_clearance=0.0):
    blob = Path(path).read_bytes()
    factor = UNIT_TO_MM[unit]
    low, high = [math.inf] * 3, [-math.inf] * 3
    count = 0
    for tri in triangles(blob):
        count += 1
        for vertex in tri:
            for axis, coordinate in enumerate(vertex):
                value = coordinate * factor
                if not math.isfinite(value):
                    raise ValueError("Unit conversion overflow")
                low[axis] = min(low[axis], value)
                high[axis] = max(high[axis], value)
    dimensions = [b - a for a, b in zip(low, high)]
    if not all(math.isfinite(v) for v in dimensions):
        raise ValueError("Invalid STL bounds")
    checks = {
        "expected_dimensions": {"status": "not_run"},
        "current_orientation_build_size": {"status": "not_run"},
    }
    if expected is not None:
        differences = [actual - target for actual, target in zip(dimensions, expected)]
        checks["expected_dimensions"] = {
            "status": "pass" if all(abs(d) <= tolerance for d in differences) else "fail",
            "expected_xyz_mm": list(expected), "tolerance_mm": tolerance,
            "difference_xyz_mm": differences,
        }
    if build_volume is not None:
        usable = [build_volume[0] - 2 * xy_margin,
                  build_volume[1] - 2 * xy_margin, build_volume[2] - z_clearance]
        checks["current_orientation_build_size"] = {
            "status": "pass" if all(d <= u for d, u in zip(dimensions, usable)) else "fail",
            "build_volume_xyz_mm": list(build_volume), "usable_size_xyz_mm": usable,
            "xy_margin_mm": xy_margin, "z_clearance_mm": z_clearance,
            "placement_and_toolpaths_checked": False,
        }
    return {
        "input_file": Path(path).name, "sha256": hashlib.sha256(blob).hexdigest(),
        "declared_input_unit": unit, "unit_source": "caller declaration; not inferred",
        "triangle_count": count, "bounds_min_max_xyz_mm": [low, high],
        "dimensions_xyz_mm": dimensions, "checks": checks,
        "overall_print_readiness": "not_assessed",
        "unmeasured": ["topology_and_solids", "wall_thickness", "hole_and_joint_dimensions",
                       "placement_and_exclusion_zones", "brim_and_support_toolpaths",
                       "physical_stability", "strength_and_fit"],
    }


def positive_vector(parser, values, name):
    if values is not None and not all(math.isfinite(v) and v > 0 for v in values):
        parser.error(name + " must contain three finite positive values")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path)
    parser.add_argument("--input-unit", choices=UNIT_TO_MM, required=True)
    parser.add_argument("--expected-mm", type=float, nargs=3, metavar=("X", "Y", "Z"))
    parser.add_argument("--tolerance-mm", type=float)
    parser.add_argument("--build-volume-mm", type=float, nargs=3, metavar=("X", "Y", "Z"))
    parser.add_argument("--xy-margin-mm", type=float, default=0.0)
    parser.add_argument("--z-clearance-mm", type=float, default=0.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    positive_vector(parser, args.expected_mm, "--expected-mm")
    positive_vector(parser, args.build_volume_mm, "--build-volume-mm")
    if (args.expected_mm is None) != (args.tolerance_mm is None):
        parser.error("--expected-mm and --tolerance-mm must be supplied together")
    for name, value in [("--tolerance-mm", args.tolerance_mm),
                        ("--xy-margin-mm", args.xy_margin_mm),
                        ("--z-clearance-mm", args.z_clearance_mm)]:
        if value is not None and (not math.isfinite(value) or value < 0):
            parser.error(name + " must be finite and non-negative")
    if args.xy_margin_mm or args.z_clearance_mm:
        if args.build_volume_mm is None:
            parser.error("Margins require --build-volume-mm")
    if args.build_volume_mm and (2 * args.xy_margin_mm >= min(args.build_volume_mm[:2])
                                or args.z_clearance_mm >= args.build_volume_mm[2]):
        parser.error("Margins leave no usable build size")
    if args.out is not None:
        same = args.out.resolve() == args.stl.resolve()
        if args.out.exists() and args.stl.exists():
            same = same or os.path.samefile(args.out, args.stl)
        if same:
            parser.error("Output must not replace the input STL")
    try:
        result = inspect_stl(args.stl, args.input_unit, args.expected_mm,
                             args.tolerance_mm, args.build_volume_mm,
                             args.xy_margin_mm, args.z_clearance_mm)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        print(json.dumps({"error": str(exc), "overall_print_readiness": "not_assessed"}))
        return 1
    output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 2 if any(check["status"] == "fail" for check in result["checks"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
