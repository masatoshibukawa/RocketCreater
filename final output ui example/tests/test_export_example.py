"""Behavior checks for the read-only export example utilities."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
EXAMPLE = Path(__file__).resolve().parents[1] / "export-example"
SPEC = importlib.util.spec_from_file_location(
    "export_package_checker", EXAMPLE / "scripts/verify_package.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECKER)


class ExportExampleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rocketwright-export-")
        self.root = Path(self.temporary.name).resolve() / "出力 content"
        shutil.copytree(EXAMPLE, self.root)

    def tearDown(self):
        assert self.root.resolve().is_relative_to(Path(self.temporary.name).resolve())
        self.temporary.cleanup()

    def manifest(self):
        return json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, manifest):
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )

    def change_json(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        manifest = self.manifest()
        item = next(row for row in manifest["artifacts"] if row["path"] == relative)
        item["size_bytes"] = path.stat().st_size
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_manifest(manifest)

    def errors(self):
        return CHECKER.verify(self.root)["errors"]

    def test_normal_package_has_no_engineering_approval(self):
        result = CHECKER.verify(self.root)
        self.assertEqual(result["package_integrity"], "passed")
        self.assertEqual(result["engineering_check"], "not_performed")
        self.assertFalse(result["ready_for_manufacturing"])

    def test_utilities_do_not_write_and_accept_unicode_paths(self):
        def snapshot():
            return {p.relative_to(self.root).as_posix(): p.read_bytes()
                    for p in self.root.rglob("*") if p.is_file()}
        before = snapshot()
        for script, options in (("verify_package.py", ["--json"]),
                                ("inspect_design.py", [])):
            run = subprocess.run(
                [sys.executable, str(self.root / "scripts" / script),
                 "--root", str(self.root), *options],
                cwd=self.temporary.name, capture_output=True, encoding="utf-8",
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual(before, snapshot())

    def test_changed_file_is_detected(self):
        with (self.root / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("changed\n")
        self.assertIn("file_hash:readme", self.errors())

    def test_missing_file_is_detected(self):
        (self.root / "parts/bom.csv").unlink()
        self.assertIn("missing_file:parts/bom.csv", self.errors())

    def test_unlisted_file_is_detected(self):
        (self.root / "extra.txt").write_text("unlisted", encoding="utf-8")
        self.assertIn("unlisted_file:extra.txt", self.errors())

    def test_revision_mismatch_is_detected_after_hash_refresh(self):
        self.change_json("design/equipment.json",
                         lambda d: d.update(design_revision="r99"))
        self.assertIn("version_or_identity:design/equipment.json:design_revision",
                      self.errors())

    def test_unknown_part_reference_is_detected_after_hash_refresh(self):
        self.change_json("assembly/steps.json",
                         lambda d: d["steps"][1]["part_ids"].append("missing-part"))
        self.assertIn("unknown_step_part:A-020", self.errors())

    def test_dependency_cycle_is_detected_after_hash_refresh(self):
        self.change_json(
            "assembly/steps.json",
            lambda d: d["steps"][0].update(depends_on=["A-020"]),
        )
        self.assertIn("step_dependency_cycle_or_missing_reference", self.errors())

    def test_parent_path_is_rejected(self):
        manifest = self.manifest()
        item = next(row for row in manifest["artifacts"]
                    if row["artifact_id"] == "readme")
        item["path"] = "../outside.txt"
        self.write_manifest(manifest)
        self.assertTrue(any(x.startswith("artifact_path_or_content:readme:")
                            for x in self.errors()))

    def test_confirmed_process_value_requires_a_source(self):
        def change(data):
            data["steps"][1]["process_parameters"][0].update(
                status="confirmed", value=1, source_id=None,
            )
        self.change_json("assembly/steps.json", change)
        self.assertIn("unsubstantiated_parameter:A-020", self.errors())

    def test_planned_output_cannot_have_a_download_path(self):
        manifest = self.manifest()
        item = next(row for row in manifest["artifacts"]
                    if row["artifact_id"] == "assembly-pdf")
        item["path"] = "not-created.pdf"
        self.write_manifest(manifest)
        self.assertIn("non_ready_artifact_has_file:assembly-pdf", self.errors())


if __name__ == "__main__":
    unittest.main()
