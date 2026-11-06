"""Reuse a saved single-part Cura project, changing verified mesh geometry only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS = {"m": CORE}


def projects(template: Path, directory: Path) -> list[dict]:
    manifest = json.loads((directory / "mesh-manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(template) as archive:
        if archive.testzip() is not None:
            raise ValueError("Template CRC failed")
        entries = {name: archive.read(name) for name in archive.namelist()}
    model_name = next(name for name in entries if name.endswith(".model"))
    namespace_declarations = {
        prefix: uri
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(entries[model_name]), events=["start-ns"])
    }
    ET.register_namespace("", CORE)
    output = []
    for part in manifest["parts"][1:]:
        source = directory / part["file"]
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != part["sha256"]:
            raise ValueError("Trial mesh changed")
        model = ET.fromstring(entries[model_name])
        objects = model.findall("m:resources/m:object", NS)
        items = model.findall("m:build/m:item", NS)
        if model.get("unit") != "millimeter" or len(objects) != 1 or len(items) != 1:
            raise ValueError("A single-part millimeter Cura template is required")
        mesh = objects[0].find("m:mesh", NS)
        if mesh is None:
            raise ValueError("Template mesh is absent")
        triangles, vertices, lookup = [], [], {}
        count = struct.unpack_from("<I", data, 80)[0]
        if len(data) != 84 + 50 * count:
            raise ValueError("Invalid binary STL size")
        for index in range(count):
            values = struct.unpack_from("<12fH", data, 84 + 50 * index)
            face = []
            for offset in (3, 6, 9):
                point = tuple(values[offset : offset + 3])
                if point not in lookup:
                    lookup[point] = len(vertices)
                    vertices.append(point)
                face.append(lookup[point])
            triangles.append(face)
        low = [min(p[i] for p in vertices) for i in range(3)]
        high = [max(p[i] for p in vertices) for i in range(3)]
        center = [(low[i] + high[i]) / 2 for i in range(3)]
        size = [high[i] - low[i] for i in range(3)]
        if any(abs(a - b) > 0.001 for a, b in zip(size, part["dimensions_mm"], strict=True)):
            raise ValueError("Mesh dimensions changed")
        if any(size[i] > bound for i, bound in enumerate((330, 240, 300))):
            raise ValueError("Mesh is outside the S5 build volume")
        mesh.clear()
        points = ET.SubElement(mesh, f"{{{CORE}}}vertices")
        for x, y, z in vertices:
            # Cura stores centered Y-up mesh coordinates in its project and rotates
            # them into the core 3MF Z-up frame with the build-item transform.
            local = (x - center[0], z - center[2], -(y - center[1]))
            ET.SubElement(
                points, f"{{{CORE}}}vertex", dict(zip("xyz", map(repr, local), strict=True))
            )
        faces = ET.SubElement(mesh, f"{{{CORE}}}triangles")
        for face in triangles:
            ET.SubElement(
                faces, f"{{{CORE}}}triangle", {f"v{i + 1}": str(v) for i, v in enumerate(face)}
            )
        objects[0].set("name", part["file"])
        transform = [1, 0, 0, 0, 0, 1, 0, -1, 0, 165, 120, size[2] / 2]
        items[0].set("transform", " ".join(map(str, transform)))
        for prefix, uri in namespace_declarations.items():
            if prefix and prefix != "xml":
                model.set(f"xmlns:{prefix}", uri)
        rewritten = dict(entries)
        rewritten[model_name] = ET.tostring(model, encoding="utf-8", xml_declaration=True)
        # A previous part's thumbnail must not represent the new part.
        removed = {
            name
            for name in entries
            if name.lower().startswith("metadata/")
            and name.lower().endswith((".png", ".jpg", ".jpeg"))
        }
        for name in removed:
            rewritten.pop(name)
        for name in ("_rels/.rels", "[Content_Types].xml"):
            root = ET.fromstring(rewritten[name])
            for child in list(root):
                target = child.get("Target", child.get("PartName", "")).lstrip("/")
                if target in removed:
                    root.remove(child)
            rewritten[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        target = directory / (source.stem + "-S5-ToughPLA-AA04-project.3mf")
        if target.exists():
            raise ValueError(f"Refusing to replace existing Cura project: {target.name}")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in rewritten.items():
                archive.writestr(name, content)
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            reloaded = ET.fromstring(archive.read(model_name))
            assert len(reloaded.findall(".//m:triangle", NS)) == count
        output.append(
            {
                "project": target.name,
                "source_sha256": part["sha256"],
                "triangles": count,
                "dimensions_mm": size,
                "profile_template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                "sliced": False,
                "physical_print_started": False,
            }
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    result = projects(args.template, args.directory)
    (args.directory / "project-manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
