"""Independently verify single-solid binary STL files (millimetres).

Requires numpy and scipy. Example:
    python verify_stl.py --directory improved --out stl-verification.json

This checks digital geometry only; it does not qualify printing, fit or flight.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def triangle_intersects(a, b, epsilon):
    """Separating-axis test, including axes needed for coplanar triangles.

    Unit axes make epsilon a distance in model units, rather than a mixture
    of length and area tolerances. Extra in-plane axes handle coplanar faces
    without constructing an ill-conditioned intersection of nearly parallel
    planes. Degenerate faces are rejected separately before this routine.
    """
    ea = np.roll(a, -1, axis=0) - a
    eb = np.roll(b, -1, axis=0) - b
    na = np.cross(ea[0], ea[1])
    nb = np.cross(eb[0], eb[1])
    axes = np.concatenate((
        np.array([na, nb]),
        np.cross(ea[:, None, :], eb[None, :, :]).reshape(-1, 3),
        np.cross(na, ea),
        np.cross(nb, eb),
    ))
    lengths = np.linalg.norm(axes, axis=1)
    axes = axes[lengths > 1e-15] / lengths[lengths > 1e-15, None]
    # Centering reduces cancellation when a part is translated far from zero.
    origin = (a.mean(axis=0) + b.mean(axis=0)) / 2
    pa, pb = (a - origin) @ axes.T, (b - origin) @ axes.T
    separated = (pa.max(axis=0) < pb.min(axis=0) - epsilon) | (pb.max(axis=0) < pa.min(axis=0) - epsilon)
    return not bool(np.any(separated))


def nonadjacent_intersections(triangles, face_indices, epsilon):
    low, high = triangles.min(axis=1), triangles.max(axis=1)
    order = np.argsort(low[:, 0], kind='stable')
    low, high = low[order], high[order]
    tri, face = triangles[order], face_indices[order]
    candidates, pairs = 0, []
    for i in range(len(tri)):
        end = np.searchsorted(low[:, 0], high[i, 0] + epsilon, side='right')
        candidate = np.arange(i + 1, end)
        if not len(candidate):
            continue
        overlap = np.all((high[candidate] >= low[i] - epsilon) & (low[candidate] <= high[i] + epsilon), axis=1)
        candidate = candidate[overlap]
        shared_vertex = np.any(face[candidate, :, None] == face[i, None, :], axis=(1, 2))
        for j in candidate[~shared_vertex]:
            candidates += 1
            if triangle_intersects(tri[i], tri[j], epsilon):
                pairs.append([int(order[i]), int(order[j])])
    return candidates, pairs


def bad_vertex_links(faces, vertex_count):
    incidence = [[] for _ in range(vertex_count)]
    for face in faces:
        for vertex in face:
            incidence[int(vertex)].append(face[face != vertex])
    bad = 0
    for links in incidence:
        graph = {}
        for edge in links:
            if len(edge) != 2:
                bad += 1
                break
            i, j = map(int, edge)
            graph.setdefault(i, []).append(j)
            graph.setdefault(j, []).append(i)
        else:
            if not graph or any(len(neighbors) != 2 for neighbors in graph.values()):
                bad += 1
                continue
            unseen = set(graph)
            todo = [unseen.pop()]
            while todo:
                for neighbor in graph[todo.pop()]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        todo.append(neighbor)
            if unseen:
                bad += 1
    return bad


def verify_file(path, intersection_epsilon, minimum_area):
    blob = path.read_bytes()
    result = {'file': path.name, 'sha256': hashlib.sha256(blob).hexdigest(), 'valid': False}
    if len(blob) < 84:
        result['errors'] = ['Not a complete binary STL file']
        return result
    count = struct.unpack_from('<I', blob, 80)[0]
    if not count or len(blob) != 84 + count * 50:
        result['errors'] = ['Binary STL length/count mismatch or empty mesh; ASCII STL is not supported']
        return result
    dtype = np.dtype([('normal', '<f4', (3,)), ('triangle', '<f4', (3, 3)), ('attribute', '<u2')])
    rows = np.frombuffer(blob, dtype=dtype, count=count, offset=84)
    tri, normals = rows['triangle'].astype(np.float64), rows['normal'].astype(np.float64)
    if not np.isfinite(tri).all() or not np.isfinite(normals).all():
        result['errors'] = ['Nonfinite STL coordinates or stored normals']
        return result
    vertices, indices = np.unique(tri.reshape(-1, 3), axis=0, return_inverse=True)
    faces = indices.reshape(-1, 3)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    twice_area = np.linalg.norm(cross, axis=1)
    directed_edges = np.stack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=1).reshape(-1, 2)
    edges, inverse, counts = np.unique(np.sort(directed_edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    directions = np.where(directed_edges[:, 0] < directed_edges[:, 1], 1, -1)
    balance = np.bincount(inverse, weights=directions, minlength=len(edges))
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(vertices), len(vertices)))
    components = connected_components(graph, directed=False, return_labels=False)
    volume_terms = np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6
    volume = float(volume_terms.sum())
    centroid = (np.einsum('i,ij->j', volume_terms, tri.sum(axis=1) / 4) / volume).tolist() if volume else None
    normal_dot = np.einsum('ij,ij->i', normals, cross / np.maximum(twice_area[:, None], 1e-100))
    duplicate_count = len(faces) - len(np.unique(np.sort(faces, axis=1), axis=0))
    degenerate_count = int(np.sum(twice_area <= 2 * minimum_area))
    checks = {
        'non_two_incidence_edges': int(np.sum(counts != 2)),
        'inconsistent_directed_edges': int(np.sum(balance != 0)),
        'nonmanifold_vertex_links': bad_vertex_links(faces, len(vertices)),
        'degenerate_triangles': degenerate_count,
        'duplicate_triangles': int(duplicate_count),
        'opposed_stored_normals': int(np.sum(normal_dot < 0)),
    }
    if degenerate_count:
        candidate_count, intersection_pairs = None, None
    else:
        candidate_count, intersection_pairs = nonadjacent_intersections(tri, faces, intersection_epsilon)
        checks['nonadjacent_intersection_pairs'] = len(intersection_pairs)
    errors = [name for name, number in checks.items() if number]
    if components != 1:
        errors.append('expected_one_connected_component')
    if volume <= 0:
        errors.append('nonpositive_signed_volume')
    result.update({
        'valid': not errors, 'errors': errors,
        'vertices': len(vertices), 'triangles': count, 'edges': len(edges),
        'connected_components': int(components),
        'euler_characteristic': int(len(vertices) - len(edges) + len(faces)),
        **checks,
        'nonadjacent_bbox_candidates': candidate_count,
        'intersection_pair_indices': intersection_pairs,
        'zero_length_stored_normals': int(np.sum(np.linalg.norm(normals, axis=1) == 0)),
        'volume_mm3': volume,
        'surface_area_mm2': float(twice_area.sum() / 2),
        'volume_centroid_mm': centroid,
        'bounds_mm': [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
        'dimensions_mm': np.ptp(vertices, axis=0).tolist(),
        'minimum_triangle_area_mm2': float(twice_area.min() / 2),
        'minimum_edge_length_mm': float(np.linalg.norm(vertices[edges[:, 1]] - vertices[edges[:, 0]], axis=1).min()),
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='Directory containing binary STL files (not recursive)')
    parser.add_argument('--out', type=Path, required=True, help='Output JSON report filename')
    parser.add_argument('--intersection-epsilon-mm', type=float, default=1e-9, help='SAT projection distance tolerance in mm (default: 1e-9)')
    parser.add_argument('--minimum-area-mm2', type=float, default=1e-9, help='Reject triangles at or below this area (default: 1e-9)')
    args = parser.parse_args()
    for value in (args.intersection_epsilon_mm, args.minimum_area_mm2):
        if not math.isfinite(value) or value < 0:
            parser.error('Tolerances must be finite and nonnegative')
    if not args.directory.is_dir():
        parser.error('--directory must exist and be a directory')
    paths = sorted((p for p in args.directory.iterdir() if p.is_file() and p.suffix.lower() == '.stl'), key=lambda p: p.name)
    results = []
    for path in paths:
        try:
            result = verify_file(path, args.intersection_epsilon_mm, args.minimum_area_mm2)
        except Exception as exc:
            result = {'file': path.name, 'valid': False, 'errors': [f'{type(exc).__name__}: {exc}']}
            try:
                result['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                result['sha256'] = None
        results.append(result)
    report = {
        'valid': bool(results) and all(r['valid'] for r in results),
        'units_assumed': 'mm',
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'dependencies': {'numpy': np.__version__, 'scipy': scipy.__version__},
        'tolerances': {'intersection_epsilon_mm': args.intersection_epsilon_mm, 'minimum_triangle_area_mm2': args.minimum_area_mm2},
        'method': 'Exact-coordinate vertex weld; edge incidence/direction; single-cycle vertex links; signed tetrahedral volume; AABB broad phase and separating-axis triangle intersection test',
        'limitations': [
            'Binary STL only; unit metadata is absent from STL and millimetres are assumed.',
            'Each file is required to contain one connected positive-volume solid.',
            'Only exactly equal STL vertices are welded; no gap repair is performed.',
            'Intersection tests skip any pair of triangles sharing a vertex; overlaps beyond the shared feature in such pairs are not exhaustively tested.',
            'SAT epsilon expands projection intervals; contacts within epsilon may be reported as intersections. Float32 export precision is inherited.',
            'Zero stored normals are counted but not rejected; topology and face-direction checks use geometry.',
            'This does not check different files against one another or qualify printing, material strength, physical fit, attachment, stability or flight.',
        ],
        'errors': [] if results else ['No STL files found'],
        'files': results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    for result in results:
        print(('PASS' if result['valid'] else 'FAIL') + ' ' + result['file'])
    print(f"{'PASS' if report['valid'] else 'FAIL'} {len(results)} STL files; report: {args.out.name}")
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    sys.exit(main())
