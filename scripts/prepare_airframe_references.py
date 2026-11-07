"""Convert the two licensed STEP reference bottles to fitted visualization assets (Gmsh 4.15.2).

python FILE --libs CONVERTER_LIB_DIRECTORY
Neither the source STEP nor a bottle pressure-vessel print mesh is modified/exported.
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--libs", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.libs.resolve()))
import gmsh  # noqa: E402 -- Isolated optional conversion runtime.

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from rocketwright.agent.video_cache import atomic_json, file_sha  # noqa: E402

folder = root / "rocketwright/catalog/airframes/reference"
gmsh.initialize(readConfigFiles=False)
try:
    for name in ("kirin-lemon-15l", "soda-2l"):
        gmsh.clear()
        source = folder / (name + ".step")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.Algorithm", 5)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 1.2)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.model.mesh.generate(2)
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        points = np.asarray(coordinates).reshape(-1, 3)
        low, high = points.min(axis=0), points.max(axis=0)
        axis = int(np.argmax(high - low))
        radial = [(axis + 1) % 3, (axis + 2) % 3]  # Right-handed axis permutation.
        p = points[:, radial + [axis]].copy()
        p[:, :2] -= (low[radial] + high[radial]) / 2
        p[:, 2] -= low[axis]
        height = float(high[axis] - low[axis])
        radius = np.linalg.norm(p[:, :2], axis=1)
        neck_at_high = np.percentile(radius[p[:, 2] > height * 0.95], 90) < np.percentile(
            radius[p[:, 2] < height * 0.05], 90
        )
        if neck_at_high:
            p[:, 2] = height - p[:, 2]
            p[:, 0] *= -1  # Flip with a proper rotation, preserving face orientation.
        maximum = float(radius.max())
        p[:, :2] /= maximum
        p[:, 2] /= height
        lookup = {int(tag): point for tag, point in zip(tags, p, strict=True)}
        types, _, nodes = gmsh.model.mesh.getElements(2)
        triangles = []
        for kind, node_tags in zip(types, nodes, strict=True):
            if kind != 2:
                raise ValueError("Expected linear triangular reference surface")
            triangles.extend(
                [[lookup[int(i)] for i in row] for row in np.asarray(node_tags).reshape(-1, 3)]
            )
        data = bytearray(b"Reference visualization, normalized radius=1 height=1".ljust(80, b" "))
        data += struct.pack("<I", len(triangles))
        for triangle in triangles:
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            norm = np.linalg.norm(normal)
            if norm == 0:
                raise ValueError("Degenerate reference triangle")
            data += struct.pack("<12fH", *(normal / norm), *np.asarray(triangle).ravel(), 0)
        target = folder / (name + "-visual.stl")
        target.write_bytes(data)
        # A radial envelope is used only for illustrative liquid placement.
        profile = []
        liquid_profile = []
        for z in np.linspace(0, 1, 129):
            mask = abs(p[:, 2] - z) < 0.015
            if np.any(mask):
                profile.append([float(np.linalg.norm(p[mask, :2], axis=1).max()), float(z)])
                liquid_profile.append(
                    [float(np.percentile(np.linalg.norm(p[mask, :2], axis=1), 10)), float(z)]
                )
        volumes = sum(gmsh.model.occ.getMass(dim, tag) for dim, tag in gmsh.model.getEntities(3))
        ratio = volumes / (np.pi * maximum**2 * height)
        atomic_json(
            folder / (name + "-visual.json"),
            dict(
                source_sha256=file_sha(source),
                mesh_sha256=file_sha(target),
                converter="Gmsh 4.15.2",
                reference_extent_mm=(high - low).tolist(),
                source_axis=axis,
                neck_flipped=bool(neck_at_high),
                normalized_radius=1,
                normalized_height=1,
                triangles=len(triangles),
                source_volume_to_cylinder_ratio=float(ratio),
                add_illustrative_wall=bool(ratio > 0.2),
                outer_profile=profile,
                liquid_profile=liquid_profile,
                physical_validation="unmeasured; visualization asset only",
                method_source="https://gmsh.info/doc/texinfo/#gmsh_002fmodel_002focc_002fimportShapes",
            ),
        )
        print(name, len(triangles), (high - low).tolist(), "volume ratio", ratio, flush=True)
finally:
    gmsh.finalize()
