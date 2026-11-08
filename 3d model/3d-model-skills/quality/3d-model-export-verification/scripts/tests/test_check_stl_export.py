"""Regression cases for exported units, orientation, malformed data and input retention."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "check_stl_export.py"
SPEC = importlib.util.spec_from_file_location("check_stl_export", MODULE)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def binary_stl(points, header=b"test"):
    return header.ljust(80, b" ")[:80] + struct.pack("<I", 1) + struct.pack(
        "<12fH", 0, 0, 1, *points[0], *points[1], *points[2], 0)


def ascii_stl(points):
    vertices = "\n".join("vertex " + " ".join(map(str, p)) for p in points)
    return ("solid part\nfacet normal 0 0 1\nouter loop\n" + vertices +
            "\nendloop\nendfacet\nendsolid part\n").encode()


class ExportCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sample.stl"

    def write(self, blob):
        self.path.write_bytes(blob)
        return self.path

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = CHECK.main([str(self.path), *args])
        return status, json.loads(output.getvalue())

    def test_ascii_units_are_explicit_and_bounds_keep_translation(self):
        self.write(ascii_stl([(1, 2, 3), (2, 2, 3), (1, 4, 6)]))
        r = CHECK.inspect_stl(self.path, "inch")
        for got, expected in zip(r["dimensions_xyz_mm"], [25.4, 50.8, 76.2]):
            self.assertAlmostEqual(got, expected)
        for got, expected in zip(r["bounds_min_max_xyz_mm"][0], [25.4, 50.8, 76.2]):
            self.assertAlmostEqual(got, expected)
        self.assertEqual(r["overall_print_readiness"], "not_assessed")

    def test_binary_header_may_begin_with_solid(self):
        self.write(binary_stl([(0, 0, 0), (10, 0, 0), (0, 20, 30)], b"solid not ASCII"))
        self.assertEqual(CHECK.inspect_stl(self.path, "mm")["dimensions_xyz_mm"], [10, 20, 30])

    def test_xyz_must_not_be_sorted_to_claim_current_orientation_fits(self):
        self.write(binary_stl([(0, 0, 0), (300, 0, 0), (0, 100, 100)]))
        r = CHECK.inspect_stl(self.path, "mm", build_volume=[256, 256, 300])
        self.assertEqual(r["checks"]["current_orientation_build_size"]["status"], "fail")

    def test_xy_margin_reduces_actual_usable_size(self):
        self.write(binary_stl([(0, 0, 0), (218, 0, 0), (0, 100, 100)]))
        r = CHECK.inspect_stl(self.path, "mm", build_volume=[220, 220, 250], xy_margin=2)
        self.assertEqual(r["checks"]["current_orientation_build_size"]["status"], "fail")

    def test_mismatch_fails_without_rescaling_or_editing_input(self):
        blob = binary_stl([(0, 0, 0), (80, 0, 0), (0, 30, 100)])
        self.write(blob)
        status, r = self.invoke("--input-unit", "mm", "--expected-mm", "40", "15", "50",
                                "--tolerance-mm", "0.01")
        self.assertEqual(status, 2)
        self.assertEqual(r["dimensions_xyz_mm"], [80, 30, 100])
        self.assertEqual(self.path.read_bytes(), blob)
        self.assertEqual(r["sha256"], hashlib.sha256(blob).hexdigest())

    def test_passing_dimensions_do_not_claim_printability(self):
        self.write(binary_stl([(0, 0, 0), (80, 0, 0), (0, 30, 100)]))
        status, r = self.invoke("--input-unit", "mm", "--expected-mm", "80", "30", "100",
                                "--tolerance-mm", "0", "--build-volume-mm", "220", "220", "250")
        self.assertEqual(status, 0)
        self.assertEqual(r["checks"]["expected_dimensions"]["status"], "pass")
        self.assertEqual(r["overall_print_readiness"], "not_assessed")
        self.assertIn("wall_thickness", r["unmeasured"])

    def test_truncated_binary_is_not_a_valid_measurement(self):
        self.write(binary_stl([(0, 0, 0), (1, 0, 0), (0, 1, 1)])[:-1])
        self.assertEqual(self.invoke("--input-unit", "mm")[0], 1)

    def test_nonfinite_coordinates_are_rejected(self):
        for data in [ascii_stl([(0, 0, 0), (float("nan"), 0, 0), (0, 1, 1)]),
                     binary_stl([(0, 0, 0), (float("inf"), 0, 0), (0, 1, 1)])]:
            self.write(data)
            self.assertEqual(self.invoke("--input-unit", "mm")[0], 1)

    def test_empty_and_incomplete_ascii_are_rejected(self):
        for data in [b"solid part\nendsolid part", b"solid part\nfacet normal 0 0 1"]:
            self.write(data)
            self.assertEqual(self.invoke("--input-unit", "mm")[0], 1)

    def test_missing_unit_is_not_guessed(self):
        self.write(ascii_stl([(0, 0, 0), (1, 0, 0), (0, 1, 1)]))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            CHECK.main([str(self.path)])

    def test_output_cannot_replace_input(self):
        blob = binary_stl([(0, 0, 0), (1, 0, 0), (0, 1, 1)])
        self.write(blob)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            CHECK.main([str(self.path), "--input-unit", "mm", "--out", str(self.path)])
        self.assertEqual(self.path.read_bytes(), blob)

    def test_tolerance_and_expectation_must_be_paired(self):
        self.write(ascii_stl([(0, 0, 0), (1, 0, 0), (0, 1, 1)]))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            CHECK.main([str(self.path), "--input-unit", "mm", "--expected-mm", "1", "1", "1"])

    def test_output_file_contains_same_report(self):
        self.write(binary_stl([(0, 0, 0), (1, 0, 0), (0, 1, 1)]))
        out = Path(self.tmp.name) / "reports" / "export.json"
        status, r = self.invoke("--input-unit", "cm", "--out", str(out))
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), r)


if __name__ == "__main__":
    unittest.main()
