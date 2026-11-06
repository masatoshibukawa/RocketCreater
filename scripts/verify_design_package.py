"""Read-only integrity verification. This does not certify printing or flight."""

import hashlib
import json
import sys
from pathlib import Path


def verify(root):
    root = root.resolve()
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    seen = set()
    for row in data["files"]:
        key = row["key"]
        path = root / key
        if key in seen or not path.resolve().is_relative_to(root):
            raise ValueError("Repeated or escaping path")
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError("Symbolic links are not accepted")
        if row["version"] != data["version"]:
            raise ValueError("Mixed design versions")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Changed file: {key}")
        seen.add(key)
    print(f"Verified {len(seen)} files for v{data['version']}. Physical checks remain pending.")
    return len(seen)


if __name__ == "__main__":
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
