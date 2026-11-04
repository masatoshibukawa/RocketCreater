"""Package original project deliverables and verify the extracted archive."""

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / name for name in ["README.md", "LICENSE", "requirements.txt", "reference_spec.json", "verification.json", "reconstruction_review.md"]]
    files += sorted((ROOT / "tools").glob("*.py"))
    files += [ROOT / "renders" / name for name in ["rocketwright_fairing.mp4", "rocketwright_fairing_poster.png", "rocketwright_fairing.blend", "render_settings.json", "original_sound.wav", "verification_contact_sheet.jpg"]]
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path.name)
    archive = ROOT / "renders/rocketwright_fairing_project.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in files:
            output.write(path, path.relative_to(ROOT).as_posix())
    with tempfile.TemporaryDirectory(prefix="package-check-", dir=ROOT / "renders") as temporary:
        assert Path(temporary).resolve().parent == (ROOT / "renders").resolve()
        with zipfile.ZipFile(archive) as source:
            assert source.testzip() is None
            assert all(not name.startswith(("reference/", "tools/python/")) and ".." not in Path(name).parts for name in source.namelist())
            source.extractall(temporary)
        for original in files:
            extracted = Path(temporary) / original.relative_to(ROOT)
            assert hashlib.sha256(original.read_bytes()).digest() == hashlib.sha256(extracted.read_bytes()).digest()
    report = {
        "archive": "renders/" + archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": [path.relative_to(ROOT).as_posix() for path in files],
        "bytes": archive.stat().st_size,
        "extraction_and_hash_check": "passed",
        "excluded": ["reference footage", "raw page metadata", "dependency binaries", "render frame cache"],
    }
    (ROOT / "delivery_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
