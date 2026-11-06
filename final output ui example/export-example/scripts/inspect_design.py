#!/usr/bin/env python3
"""Print selected design inputs and missing information without changing files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def load(root: Path, relative: str) -> dict:
    path = root / relative
    path.resolve(strict=True).relative_to(root)
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Unsupported input file")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        root = args.root.resolve(strict=True)
        manifest = load(root, "manifest.json")
        requirements = load(root, "design/requirements.json")
        equipment = load(root, "design/equipment.json")
        technical = load(root, "verification/technical-status.json")
        for record in (requirements, equipment, technical):
            if (record["package_id"], record["design_revision"]) != (
                manifest["package_id"], manifest["design_revision"]
            ):
                raise ValueError("Design versions differ")
        altitude = requirements["mission"]["target_altitude"]
        altitude_text = (
            "未入力" if altitude["value"] is None
            else f"{altitude['value']} {altitude['unit']}"
        )
        print(f"設計版: {manifest['design_revision']}")
        print(f"内容の状態: {manifest['content_status']}")
        print(f"目標高度: {altitude_text}")
        print(f"プリンター: {equipment['printer']['selection_status']}")
        print(f"製作版: {technical['manufacturing_release']}")
        print("次に確認すること:")
        for blocker in technical["blockers"]:
            print(f"- {blocker}")
        print("この要約はファイルの完全性や技術的な合格を確認しません。")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"要約できません: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
