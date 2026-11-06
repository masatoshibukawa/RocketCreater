"""Deterministic design -> inspected non-pressure CAD -> local machine-specific slices.

This module never contacts a printer, an LLM, or a cloud service.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from rocketwright.agent.local_runtime import LocalRuntimeError
from rocketwright.schema import BottleDesign, BottleGeometry
from scripts.check_ultimaker_slice import inspect

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "s5-gray-aa04"
PROFILE_PATH = ROOT / "rocketwright/catalog/print_profiles/s5-gray-aa04.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class PrintGeometry(BottleGeometry):
    @classmethod
    def from_design(cls, design: BottleDesign):
        if design.geometry is not None:
            return cls.model_validate(design.geometry.model_dump())
        # Explicitly unmeasured defaults; editing saves these in the design.
        d = (4 * design.bottle_volume_m3 / (math.pi * 3.5)) ** (1 / 3) * 1000
        return cls(
            body_diameter_mm=d,
            body_height_mm=3.5 * d,
            nose_length_mm=0.8 * d,
            fin_root_mm=d,
            fin_tip_mm=0.35 * d,
            fin_span_mm=0.8 * d,
            fin_tail_inset_mm=0.25 * 3.5 * d,
            fin_sweep_mm=0.35 * d,
        )

    @classmethod
    def from_plan(cls, g: dict):
        return cls(
            body_diameter_mm=g["body_diameter"],
            body_height_mm=g.get("bottle_length", g["overall"] - g["nose_length"]),
            nose_length_mm=g["nose_length"],
            fin_root_mm=g["fin_root"],
            fin_tip_mm=g["fin_tip"],
            fin_span_mm=g["fin_span"],
            fin_sweep_mm=g["fin_sweep"],
        )


class PrintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: BottleDesign
    geometry: PrintGeometry | None = None
    printer: Literal["s5-gray-aa04"] = PROFILE_ID


def tools() -> dict[str, Path]:
    engine = Path(
        os.getenv(
            "ROCKETWRIGHT_CURA_ENGINE", "C:/Program Files/UltiMaker Cura 5.12.0/CuraEngine.exe"
        )
    )
    blender = Path(
        os.getenv(
            "ROCKETWRIGHT_BLENDER",
            shutil.which("blender")
            or "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
        )
    )
    resources = Path(
        os.getenv("ROCKETWRIGHT_CURA_RESOURCES", str(engine.parent / "share/cura/resources"))
    )
    material = resources / "materials/ultimaker_tough_pla_gray.xml.fdm_material"
    return {"engine": engine, "blender": blender, "material": material}


def runtime() -> dict:
    paths = tools()
    return {
        "printer": PROFILE_ID,
        "label": "UltiMaker S5 / Tough PLA Gray / AA 0.4",
        "available": all(p.is_file() for p in paths.values()),
        "dependencies": {k: p.is_file() for k, p in paths.items()},
        "brim_width_mm": 20,
        "brim_gap_mm": 0,
        "physical_validation": "pending",
    }


def parameters(request: PrintRequest) -> dict:
    g = request.geometry or PrintGeometry.from_design(request.design)
    if request.design.geometry and g.model_dump() != request.design.geometry.model_dump():
        raise ValueError("Print dimensions differ from the analysed design")
    c = json.loads((ROOT / "3d model/prototypes/pet-rocket-coke-2l/parameters.json").read_text())
    c["revision"] = "design-bound-print-v1"
    c["include_fins"] = request.design.has_fins
    c["bottle"]["description"] = "Design-derived envelope; dimensions are not physically measured"
    c["bottle"].update(
        body_diameter=g.body_diameter_mm,
        height=g.body_height_mm,
        cylinder_start_z=0.25 * g.body_height_mm,
        cylinder_end_z=0.9 * g.body_height_mm,
    )
    # Match the source nose length, rather than copying the frozen 2 L nose height.
    n = c["nose"]
    n["wall"] = g.nose_wall_mm
    n["skirt_height"] = min(28, g.nose_length_mm / 4)
    outer = g.body_diameter_mm / 2 + c["bottle"]["radial_clearance"] + n["wall"]
    cap = n["tip_radius"]
    cut = math.sqrt((cap - n["wall"]) ** 2 - (n["tip_opening_diameter"] / 2) ** 2)
    low, high = 0.001, 100.0
    for _ in range(80):
        slope = (low + high) / 2
        height = n["skirt_height"] + (outer - cap * math.sqrt(1 + slope * slope)) / slope + cut
        if height > g.nose_length_mm:
            low = slope
        else:
            high = slope
    n["slope"] = (low + high) / 2
    c["fin"].update(
        count=g.fin_count,
        thickness=g.fin_thickness_mm,
        mount_tail_z=g.fin_tail_inset_mm,
        root_chord=g.fin_root_mm,
        tip_chord=g.fin_tip_mm,
        span=g.fin_span_mm,
        tip_trailing_offset=g.fin_root_mm - g.fin_tip_mm - g.fin_sweep_mm,
        slot_centers=[0.2 * g.fin_root_mm, 0.78 * g.fin_root_mm],
        slot_height=min(8, 0.1 * g.fin_root_mm),
        print_rotation_y_deg=math.degrees(
            math.atan2(g.fin_root_mm - g.fin_tip_mm - g.fin_sweep_mm, g.fin_span_mm)
        ),
    )
    c["print_assumption"].update(
        bed_mm=[330, 240, 300], outer_brim_mm=20, material="UltiMaker Tough PLA Gray"
    )
    return c


def run(command: list[str], directory: Path, log: Path, timeout=180):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        with log.open("w", encoding="utf-8") as stream:
            subprocess.run(
                command,
                cwd=directory,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalRuntimeError(f"Local CAD/slice operation failed; inspect {log.name}") from exc


def centered_stl(source: Path, destination: Path, bed: list[float]) -> list[float]:
    data = source.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * count or not count:
        raise ValueError("Expected a nonempty inspected binary STL")
    dtype = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    records = np.frombuffer(data, dtype=dtype, offset=84).copy()
    vertices = records["vertices"]
    if not np.isfinite(vertices).all():
        raise ValueError("Non-finite mesh")
    low, high = vertices.min(axis=(0, 1)), vertices.max(axis=(0, 1))
    dimensions = high - low
    # Reserve the larger brim and clearance, rather than silently scaling/shrinking it.
    if any(float(dimensions[i]) + (44 if i < 2 else 0) > bed[i] for i in range(3)):
        raise ValueError("Part plus 20 mm brim does not fit the configured printer")
    vertices -= np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]])
    destination.write_bytes(data[:84] + records.tobytes())
    return dimensions.astype(float).tolist()


def write_model_3mf(source: Path):
    """Portable millimetre mesh, deliberately separate from machine-specific UFP."""
    data = source.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    model = ET.Element("model", xmlns=namespace, unit="millimeter")
    resources = ET.SubElement(model, "resources")
    obj = ET.SubElement(resources, "object", id="1", type="model", name=source.name)
    mesh = ET.SubElement(obj, "mesh")
    vertices = ET.SubElement(mesh, "vertices")
    triangles = ET.SubElement(mesh, "triangles")
    vertex_ids = {}
    for i in range(count):
        values = struct.unpack_from("<12fH", data, 84 + 50 * i)
        indices = []
        for j in range(3):
            point = tuple(values[3 + 3 * j : 6 + 3 * j])
            if point not in vertex_ids:
                vertex_ids[point] = len(vertex_ids)
                ET.SubElement(vertices, "vertex", **dict(zip("xyz", map(str, point), strict=True)))
            indices.append(str(vertex_ids[point]))
        ET.SubElement(triangles, "triangle", **dict(zip(("v1", "v2", "v3"), indices, strict=True)))
    ET.SubElement(ET.SubElement(model, "build"), "item", objectid="1")
    with zipfile.ZipFile(source.with_suffix(".3mf"), "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True)
        )
        content = ET.Element(
            "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
        )
        ET.SubElement(
            content,
            "Default",
            Extension="rels",
            ContentType="application/vnd.openxmlformats-package.relationships+xml",
        )
        ET.SubElement(
            content,
            "Default",
            Extension="model",
            ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        )
        archive.writestr("[Content_Types].xml", ET.tostring(content))
        relations = ET.Element(
            "Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships"
        )
        ET.SubElement(
            relations,
            "Relationship",
            Id="rel0",
            Target="/3D/3dmodel.model",
            Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel",
        )
        archive.writestr("_rels/.rels", ET.tostring(relations))


def remove_png_text(path: Path):
    """Drop path/date metadata without decoding or changing rendered pixels."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    cleaned = bytearray(data[:8])
    offset = 8
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        if data[offset + 4 : offset + 8] not in {b"tEXt", b"iTXt", b"zTXt", b"eXIf"}:
            cleaned.extend(data[offset:end])
        offset = end
    path.write_bytes(cleaned)


def slice_part(directory: Path, name: str, profile: dict, paths: dict[str, Path]) -> dict:
    work = directory / "work" / name
    work.mkdir(parents=True)
    dimensions = centered_stl(directory / f"{name}-mm.stl", work / "part.stl", profile["bed_mm"])
    settings = copy.deepcopy(profile["settings"])
    # Trial policy, not a mechanical proof: enlarge the removable footprint for tall fins.
    narrow = min(dimensions[:2])
    brim = max(20, math.ceil(dimensions[2] / 5)) if dimensions[2] / narrow > 2.5 else 20
    if brim > 35 or any(dimensions[i] + 2 * brim + 4 > profile["bed_mm"][i] for i in range(2)):
        raise ValueError("Tall part requires a different orientation or split before slicing")
    for group in ["global", "extruder.0"]:
        settings[group].update(brim_width=brim, brim_line_count=math.ceil(brim / 0.4), brim_gap=0)
    settings["part.stl"] = {"extruder_nr": 0}
    (work / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    run(
        [
            str(paths["engine"]),
            "slice",
            "-m4",
            "-r",
            str((work / "settings.json").resolve()),
            "-o",
            str((work / "raw.gcode").resolve()),
        ],
        work,
        work / "slice.log",
    )
    text = (work / "raw.gcode").read_text(encoding="utf-8")
    log = (work / "slice.log").read_text(encoding="utf-8")
    headers = re.findall(r";START_OF_HEADER\r?\n.*?;END_OF_HEADER", log, re.S)
    if not headers:
        raise ValueError("CuraEngine did not provide its completed header")
    header = headers[-1]
    if (
        re.search(r";SLICE_UUID:([^\r\n]+)", text)[1]
        != re.search(r";SLICE_UUID:([^\r\n]+)", header)[1]
    ):
        raise ValueError("Slice header UUID mismatch")
    text = re.sub(
        r";START_OF_HEADER\r?\n.*?;END_OF_HEADER", lambda _: header, text, count=1, flags=re.S
    )
    (directory / f"{name}-S5.gcode").write_text(text, encoding="utf-8")
    metadata = {
        "global": {"all_settings": settings["global"]},
        "extruder_0": {"all_settings": settings["extruder.0"]},
    }
    rels = "http://schemas.openxmlformats.org/package/2006/relationships"
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(
            f'<Default Extension="{ext}" ContentType="{kind}"/>'
            for ext, kind in [
                ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
                ("gcode", "text/x-gcode"),
                ("json", "application/json"),
                ("png", "image/png"),
                ("xml.fdm_material", "application/x-ultimaker-material-profile"),
            ]
        )
        + "</Types>"
    )
    machine = directory / f"{name}-S5.ufp"
    with zipfile.ZipFile(machine, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("/3D/model.gcode", text)
        archive.writestr("/Cura/slicemetadata.json", json.dumps(metadata))
        archive.writestr(
            "/Metadata/UFP_Global.json",
            json.dumps({"metadata": {"objects": [{"name": f"{name}-mm.stl"}]}}),
        )
        archive.writestr(
            "/Metadata/thumbnail.png", (directory / f"{name}-preview.png").read_bytes()
        )
        archive.writestr(
            "/Materials/ultimaker_tough_pla_gray.xml.fdm_material", paths["material"].read_bytes()
        )
        archive.writestr("/[Content_Types].xml", types)
        archive.writestr(
            "/_rels/.rels",
            f'<Relationships xmlns="{rels}"><Relationship Id="rel0" Target="/3D/model.gcode" Type="http://schemas.ultimaker.org/package/2018/relationships/gcode"/></Relationships>',
        )
        relationships = ET.Element("Relationships", xmlns=rels)
        for index, (target, kind) in enumerate(
            [
                ("/Metadata/thumbnail.png", f"{rels}/metadata/thumbnail"),
                (
                    "/Materials/ultimaker_tough_pla_gray.xml.fdm_material",
                    "http://schemas.ultimaker.org/package/2018/relationships/material",
                ),
            ]
        ):
            ET.SubElement(relationships, "Relationship", Id=f"rel{index}", Target=target, Type=kind)
        archive.writestr("/3D/_rels/model.gcode.rels", ET.tostring(relationships))
    review = inspect(machine, material_color="Gray")
    if review["generator_version"] != profile["engine_version"]:
        raise ValueError("The installed CuraEngine version differs from the resolved profile")
    if not review.get("all_print_paths_inside_s5", False):
        raise ValueError("Brim or part exceeds the printer bed")
    if max(review["extrusion_speed_max_mm_s_by_type"].values()) > 35.001:
        raise ValueError("Actual extrusion speed exceeds the 35 mm/s trial ceiling")
    review.update(
        part=name,
        dimensions_mm=dimensions,
        source_stl_sha256=sha(directory / f"{name}-mm.stl"),
        resolved_settings_sha256=sha(work / "settings.json"),
    )
    (directory / f"{name}-slice-check.json").write_text(
        json.dumps(review, indent=2), encoding="utf-8"
    )
    return review


def prepare_geometry(request: PrintRequest, directory: Path) -> tuple[dict, dict]:
    paths = tools()
    if not paths["blender"].is_file():
        raise LocalRuntimeError(
            "Install/configure local Blender, CuraEngine 5.12.0 and Cura materials"
        )
    c = parameters(request)
    directory.mkdir(parents=True, exist_ok=False)
    config_path = directory / "parameters.json"
    config_path.write_text(json.dumps(c, indent=2), encoding="utf-8")
    run(
        [
            str(paths["blender"]),
            "--background",
            "--factory-startup",
            "--python",
            str(ROOT / "scripts/build_print_parts.py"),
            "--",
            str(config_path.resolve()),
            str(directory.resolve()),
        ],
        ROOT,
        directory / "cad.log",
    )
    geometries = json.loads((directory / "geometry-check.json").read_text())
    for name in geometries:
        remove_png_text(directory / f"{name}-preview.png")
        write_model_3mf(directory / f"{name}-mm.stl")
    return c, geometries


def prepare(request: PrintRequest, directory: Path) -> dict:
    c, geometries = prepare_geometry(request, directory)
    config_path = directory / "parameters.json"
    paths = tools()
    profile = json.loads(PROFILE_PATH.read_text())
    reviews = [slice_part(directory, name, profile, paths) for name in geometries]
    for review in reviews:
        review["quantity_for_assembly"] = c["fin"]["count"] if review["part"] == "fin" else 1
        geometry = geometries[review["part"]]
        center = [(lo + hi) / 2 for lo, hi in zip(*geometry["bounds_mm"], strict=True)]
        bed_center = [
            profile["bed_mm"][i] / 2 + geometry["centroid_mm"][i] - center[i] for i in range(2)
        ]
        hull = review["bed_footprint_hull_xy_mm"]
        margins = []
        for a, b in zip(hull, hull[1:] + hull[:1], strict=True):
            dx, dy = b[0] - a[0], b[1] - a[1]
            margins.append(
                (dx * (bed_center[1] - a[1]) - dy * (bed_center[0] - a[0])) / math.hypot(dx, dy)
            )
        if len(hull) < 3 or min(margins) < 2:
            raise ValueError(
                "Solid-geometry centroid needs a wider support footprint or different pose"
            )
        review["solid_centroid_bed_xy_mm"] = bed_center
        review["solid_centroid_support_margin_mm"] = round(min(margins), 3)
        review["centroid_basis"] = (
            "Uniform solid geometry, not measured infill mass or adhesion strength"
        )
        review["print_rotation_y_deg"] = (
            c["fin"]["print_rotation_y_deg"] if review["part"] == "fin" else 0
        )
        (directory / f"{review['part']}-slice-check.json").write_text(
            json.dumps(review, indent=2), encoding="utf-8"
        )
    manifest = {
        "status": "slice_checked_physical_trial_pending",
        "printer": request.printer,
        "source_design": request.design.model_dump(mode="json"),
        "source_design_sha256": fingerprint(request.design.model_dump(mode="json")),
        "geometry_input": (
            request.geometry or PrintGeometry.from_design(request.design)
        ).model_dump(),
        "parameters_sha256": sha(config_path),
        "profile_sha256": sha(PROFILE_PATH),
        "engine_sha256": sha(paths["engine"]),
        "brim_width_mm": 20,
        "brim_gap_mm": 0,
        "physical_print_verified": False,
        "fit_measured": False,
        "flight_validation_current": False,
        "substitution_requires_mass_and_flight_reanalysis": True,
        "parts": reviews,
        "non_pressure_parts_only": True,
        "limitations": [
            "Larger attached brim is an unverified mitigation for the observed late tipping",
            "Printed PLA parts replace assumed sheet parts: weigh and reanalyse before flight",
            "Inspect adhesion, late-stage stability, fit and part quality on the physical printer",
        ],
    }
    (directory / "print-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Only reviewed, design-bound deliverables enter the download registry/archive.
    public = sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix in {".stl", ".3mf", ".ufp", ".gcode", ".png", ".json"}
    )
    with zipfile.ZipFile(directory / "print-package.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for p in public:
            archive.write(p, p.name)
    return manifest


class PrintStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(
            os.getenv("ROCKETWRIGHT_PRINT_ROOT", ROOT / "output/print-packages")
        )

    def directory(self, package_id: str):
        if not re.fullmatch(r"[a-f0-9]{32}", package_id):
            raise KeyError("Unknown print package")
        return self.root / package_id

    def create(self, request: PrintRequest):
        package_id = uuid.uuid4().hex
        directory = self.directory(package_id)
        manifest = prepare(request, directory)
        files = [
            {
                "name": p.name,
                "sha256": sha(p),
                "url": f"/manufacturing/packages/{package_id}/files/{p.name}",
            }
            for p in directory.iterdir()
            if p.is_file()
            and p.suffix in {".stl", ".3mf", ".ufp", ".gcode", ".png", ".json", ".zip"}
        ]
        result = {"id": package_id, "manifest": manifest, "files": files}
        (directory / "registry.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        return result

    def file(self, package_id: str, name: str):
        base = self.directory(package_id).resolve()
        try:
            record = json.loads((base / "registry.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError("Unknown print package") from exc
        row = next((f for f in record["files"] if f["name"] == name), None)
        path = (base / name).resolve()
        if row is None or not path.is_relative_to(base) or not path.is_file():
            raise KeyError("Unknown print file")
        if sha(path) != row["sha256"]:
            raise ValueError("Print artifact changed after verification")
        return path


DEFAULT_PRINT_STORE = PrintStore()
