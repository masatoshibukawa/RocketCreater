#!/usr/bin/env python3
"""Read-only checks of an exported package; no engineering approval is performed."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

MAX_JSON_BYTES = 16 * 1024 * 1024
STATES = {"planned", "queued", "generating", "ready", "failed", "cancelled", "stale"}
DATA_FILES = (
    "design/requirements.json", "design/equipment.json", "design/design.json",
    "assembly/steps.json", "analysis/results.json", "provenance/sources.json",
    "verification/technical-status.json",
)


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Invalid relative path")
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("Empty, absolute or parent path component")
    target = root.joinpath(*relative.split("/"))
    target.resolve(strict=True).relative_to(root)
    for item in (target, *target.parents):
        if item == root:
            break
        if item.is_symlink():
            raise ValueError("Symbolic links are not package artifacts")
    if not target.is_file():
        raise ValueError("Artifact is not a file")
    return target


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("JSON file exceeds the supported size")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def listed_files(root: Path) -> set[str]:
    pending, found = [root], set()
    while pending:
        directory = pending.pop()
        for item in directory.iterdir():
            item.resolve(strict=True).relative_to(root)
            if item.is_symlink():
                raise ValueError("Symbolic links are not supported")
            if item.is_dir():
                pending.append(item)
            elif item.is_file():
                found.add(item.relative_to(root).as_posix())
            if len(found) + len(pending) > 5000:
                raise ValueError("Package exceeds the supported file count")
    return found


def check_references(root: Path, manifest: dict, errors: list[str]) -> None:
    data = {name: read_json(safe_path(root, name)) for name in DATA_FILES}
    for name, record in data.items():
        for key in ("schema_version", "package_id", "design_revision"):
            if record.get(key) != manifest.get(key):
                errors.append(f"version_or_identity:{name}:{key}")
    source_rows = data["provenance/sources.json"]["sources"]
    source_ids = [row["source_id"] for row in source_rows]
    if len(source_ids) != len(set(source_ids)):
        errors.append("duplicate_source_id")
    known_sources = set(source_ids)
    for name, record in data.items():
        if not set(record.get("source_ids", [])).issubset(known_sources):
            errors.append(f"unknown_source:{name}")
    design = data["design/design.json"]
    part_rows = design["parts"]
    part_ids = [part["part_id"] for part in part_rows]
    if len(part_ids) != len(set(part_ids)):
        errors.append("duplicate_part_id")
    parts = {row["part_id"]: row for row in part_rows}
    bom_text = safe_path(root, "parts/bom.csv").read_text(encoding="utf-8")
    bom = list(csv.DictReader(io.StringIO(bom_text)))
    bom_ids = [row["part_id"] for row in bom]
    if len(bom_ids) != len(set(bom_ids)) or set(bom_ids) != set(parts):
        errors.append("bom_part_set")
    for row in bom:
        part = parts.get(row["part_id"])
        if part is None:
            continue
        if row["revision"] != part["revision"] or row["source_id"] not in known_sources:
            errors.append(f"bom_reference:{row['part_id']}")
        expected_quantity = part.get("quantity")
        if expected_quantity is None:
            if row["quantity"] != "" or row["quantity_status"] != "needs_input":
                errors.append(f"unknown_quantity:{row['part_id']}")
        elif row["quantity"] != str(expected_quantity):
            errors.append(f"bom_quantity:{row['part_id']}")
    procedure = data["assembly/steps.json"]
    steps = procedure["steps"]
    step_ids = [step["step_id"] for step in steps]
    if len(step_ids) != len(set(step_ids)):
        errors.append("duplicate_step_id")
    dependencies = {step["step_id"]: set(step["depends_on"]) for step in steps}
    for step in steps:
        sid = step["step_id"]
        if not set(step["part_ids"]).issubset(parts):
            errors.append(f"unknown_step_part:{sid}")
        if not dependencies[sid].issubset(dependencies):
            errors.append(f"unknown_predecessor:{sid}")
        for parameter in step.get("process_parameters", []):
            source_id = parameter.get("source_id")
            if source_id is not None and source_id not in known_sources:
                errors.append(f"unknown_parameter_source:{sid}")
            if parameter.get("status") == "confirmed" and (
                parameter.get("value") is None or source_id is None
            ):
                errors.append(f"unsubstantiated_parameter:{sid}")
    remaining = {sid: set(deps) for sid, deps in dependencies.items()}
    while remaining:
        ready = {sid for sid, deps in remaining.items() if not deps}
        if not ready:
            errors.append("step_dependency_cycle_or_missing_reference")
            break
        remaining = {
            sid: deps - ready for sid, deps in remaining.items() if sid not in ready
        }
    operator_ids = {
        item["id"] for item in data["design/equipment.json"]["operator_profiles"]
    }
    if not set(procedure["operator_profile_ids"]).issubset(operator_ids):
        errors.append("unknown_operator_profile")


def verify(root: Path) -> dict:
    root = root.resolve(strict=True)
    errors: list[str] = []
    ready_count = 0
    manifest: dict = {}
    try:
        manifest = read_json(safe_path(root, "manifest.json"))
        if manifest.get("schema_version") != "1.0-draft":
            errors.append("unsupported_schema_version")
        artifacts = manifest["artifacts"]
        identifiers = [item["artifact_id"] for item in artifacts]
        if len(identifiers) != len(set(identifiers)):
            errors.append("duplicate_artifact_id")
        artifact_ids = set(identifiers)
        expected, portable_paths = {"manifest.json"}, set()
        for item in artifacts:
            aid = item["artifact_id"]
            if item["state"] not in STATES:
                errors.append(f"unsupported_state:{aid}")
            if item["design_revision"] != manifest["design_revision"]:
                errors.append(f"artifact_revision:{aid}")
            if not set(item.get("depends_on", [])).issubset(artifact_ids):
                errors.append(f"artifact_dependency:{aid}")
            if item["state"] != "ready":
                if item.get("path") is not None or item.get("sha256") is not None:
                    errors.append(f"non_ready_artifact_has_file:{aid}")
                continue
            relative = item["path"]
            if relative.casefold() in portable_paths or relative == "manifest.json":
                errors.append(f"duplicate_artifact_path:{aid}")
            portable_paths.add(relative.casefold())
            expected.add(relative)
            try:
                path = safe_path(root, relative)
                if path.stat().st_size != item["size_bytes"]:
                    errors.append(f"file_size:{aid}")
                if digest(path) != item["sha256"]:
                    errors.append(f"file_hash:{aid}")
                if path.suffix != ".pdf":
                    content = path.read_bytes()
                    content.decode("utf-8")
                    if b"\r" in content or content.startswith(b"\xef\xbb\xbf"):
                        errors.append(f"text_encoding_or_newline:{aid}")
                ready_count += 1
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"artifact_path_or_content:{aid}:{type(exc).__name__}")
        actual = listed_files(root)
        for path in sorted(actual - expected):
            errors.append(f"unlisted_file:{path}")
        for path in sorted(expected - actual):
            errors.append(f"missing_file:{path}")
        check_references(root, manifest, errors)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f"package_format:{type(exc).__name__}")
    return {
        "package_id": manifest.get("package_id"),
        "design_revision": manifest.get("design_revision"),
        "package_integrity": "passed" if not errors else "failed",
        "files_checked": ready_count,
        "errors": errors,
        "engineering_check": "not_performed",
        "ready_for_manufacturing": False,
        "note": "File integrity and selected references only; no CAD, strength, assembly or flight approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Write a JSON report to stdout")
    args = parser.parse_args()
    try:
        report = verify(args.root)
    except OSError as exc:
        report = {
            "package_integrity": "failed", "errors": [f"package_root:{type(exc).__name__}"],
            "engineering_check": "not_performed", "ready_for_manufacturing": False,
        }
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"ファイル整合: {report['package_integrity']}")
        print("技術評価: 未実施 / 製作承認を行うスクリプトではありません。")
        for error in report["errors"]:
            print(f"- {error}")
    return 0 if report["package_integrity"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
