"""Read-only, case-bound access to committed reference designs and local media."""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from rocketwright.agent.workbench import ROOT, Conflict

CAD = Path("3d model/prototypes/pet-rocket-coke-2l")
FILM = Path("AIvideo/pet-rocket")
# IDs are public handles; neither request paths nor catalog paths select files.
PARTS = {
    "fin": ("fin.stl", "フィン / 45°印刷姿勢"),
    "nose": ("nose_cone.stl", "ノーズ / 軟質キャップは別途必要"),
    "fit-ring": ("fit_ring.stl", "ボトル径の試着リング"),
    "mount-gauge": ("mount_gauge.stl", "取付部の試着ゲージ"),
}
MEDIA = {
    "design-film": ("pet_rocket_design_cinematic.mp4", "設計説明 / 16秒"),
    "launch-film": ("pet_rocket_launch_cinematic.mp4", "上昇予測 / 12秒"),
    "design-poster": ("design-cinematic-poster.png", "設計説明の表紙"),
    "launch-poster": ("launch-cinematic-poster.png", "上昇予測の表紙"),
}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username:
        return value
    return None


class ReferenceLibrary:
    def __init__(self, root: Path = ROOT, media_root: Path | None = None):
        self.root = root
        # Existing local renders may live outside the isolated integration checkout.
        self.media_root = media_root or Path(os.getenv("ROCKETWRIGHT_MEDIA_ROOT", root / "AIvideo"))

    def _bound(self) -> bool:
        """Do not present a changed CAD design under a frozen film's case label."""
        try:
            return read(self.root / CAD / "parameters.json") == read(
                self.root / FILM / "source-data/parameters.json"
            ) and read(self.root / CAD / "improved/assembly.json") == read(
                self.root / FILM / "source-data/assembly.json"
            )
        except (OSError, ValueError):
            return False

    def _record(self, asset_id: str) -> tuple[Path, Path, str, str]:
        if asset_id in PARTS:
            name, label = PARTS[asset_id]
            report = read(self.root / CAD / "reports/geometry-verification.json")
            row = next(r for r in report["files"] if r["file"] == name)
            if not report["valid"] or not row["valid"]:
                raise Conflict("The geometry verification did not pass")
            base = self.root / CAD / "improved"
            return base, base / name, row["sha256"], label
        if asset_id in MEDIA:
            name, label = MEDIA[asset_id]
            manifest = read(self.root / FILM / "realism/delivery-manifest.json")
            row = next(r for r in manifest["files"] if r["path"] == f"realism/renders/{name}")
            base = self.media_root / "pet-rocket"
            return base, base / row["path"], row["sha256"], label
        raise KeyError("Unknown reference asset")

    def file(self, asset_id: str) -> Path:
        if asset_id not in PARTS and asset_id not in MEDIA:
            raise KeyError("Unknown reference asset")
        if not self._bound():
            raise Conflict("Reference CAD and film snapshots differ")
        try:
            base, path, expected, _ = self._record(asset_id)
            path = path.resolve()
            if not path.is_relative_to(base.resolve()) or not path.is_file():
                raise KeyError("Reference asset is not installed")
            if digest(path) != expected:
                raise Conflict("Reference asset differs from its verified snapshot")
            # A film must also reference the same STL geometry as this case.
            if asset_id in MEDIA:
                report = read(self.root / CAD / "reports/geometry-verification.json")
                hashes = {r["file"]: r["sha256"] for r in report["files"] if r["valid"]}
                for name in ("fin_assembly.stl", "nose_cone.stl"):
                    if digest(self.root / FILM / "assets" / name) != hashes.get(name):
                        raise Conflict("Film geometry differs from the reference CAD")
            return path
        except (FileNotFoundError, StopIteration) as exc:
            raise KeyError("Reference asset is not installed") from exc

    def view(self) -> dict:
        assets = []
        for asset_id, (_, label) in (PARTS | MEDIA).items():
            status, url = "available", None
            try:
                self.file(asset_id)
                url = f"/workbench/library/assets/{asset_id}"
            except KeyError:
                status = "missing"
            except Conflict:
                status = "changed"
            assets.append({"id": asset_id, "label": label, "status": status, "url": url})
        params = read(self.root / CAD / "parameters.json")
        return {
            "case_id": "pet-coke-2l-v2",
            "title": "2 L PET / 試作 v2",
            "description": "既存CADを使った製作・映像の参照例。1.5 Lの卵回収設計とは別の機体です。",
            "geometry": {
                "revision": params["revision"],
                "diameter_mm": params["bottle"]["body_diameter"],
                "bottle_height_mm": params["bottle"]["height"],
                "fin_count": params["fin"]["count"],
                "measured": params["bottle"]["fit_measured"],
            },
            "limitations": [
                "ボトルの外径110 mm・高さ315 mmは未実測の仮定です。",
                "STLの形状検査と汎用FDMスライス確認済み。実機への適合・取付保持・強度・飛行安定性は未確認です。",
                "映像は1920 × 1080 / 24 fps。仮定した条件での上昇のみを示し、回収系は未設計です。",
            ],
            "assets": assets,
            "references": self.references(limit=0)["counts"],
        }

    def references(self, query: str = "", category: str = "all", limit: int = 200) -> dict:
        def normalize(value):
            return unicodedata.normalize("NFKC", value).casefold()

        needle = normalize(query.strip())
        records = []
        catalogs = (("water", "文献/目録.json"), ("model", "文献/モデルロケット/目録.json"))
        for group, path in catalogs:
            catalog = read(self.root / path)
            for row in catalog["records"]:
                fields = ("id", "title", "author", "year", "kind", "note", "category")
                record = {k: row.get(k) for k in fields}
                lang = row.get("lang", [])
                record.update(
                    group=group,
                    languages=[lang] if isinstance(lang, str) else lang,
                    source=public_url(row.get("source")),
                    checked_on=catalog.get("checked_on"),
                )
                records.append(record)
        counts = {group: sum(r["group"] == group for r in records) for group in ("water", "model")}
        matches = [
            r
            for r in records
            if (category == "all" or r["group"] == category)
            and (not needle or needle in normalize(json.dumps(r, ensure_ascii=False)))
        ]
        return {"counts": counts, "total": len(matches), "records": matches[:limit]}


DEFAULT_LIBRARY = ReferenceLibrary()
