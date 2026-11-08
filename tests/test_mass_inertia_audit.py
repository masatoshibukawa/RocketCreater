from itertools import product

import numpy as np
import pytest
from scipy.spatial import ConvexHull

from scripts.audit_mass_inertia import moments


def test_cuboid_integrals_and_rigid_coordinate_changes():
    dimensions = np.array([2.0, 3.0, 4.0])
    points = np.array(list(product((-0.5, 0.5), repeat=3))) * dimensions
    faces = points[ConvexHull(points).simplices].copy()
    normals = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
    inward = np.einsum("ij,ij->i", normals, faces.mean(axis=1)) < 0
    faces[inward] = faces[inward, ::-1]
    expected = (np.sum(dimensions**2) - dimensions**2) / 12
    result = moments(faces)
    assert result["volume"] == pytest.approx(np.prod(dimensions))
    np.testing.assert_allclose(result["centroid"], 0, atol=1e-14)
    np.testing.assert_allclose(result["inertia_per_mass"], np.diag(expected), atol=1e-14)
    angle = 0.73
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    offset = np.array([1000.0, -3000.0, 2000.0])
    transformed = moments(faces @ rotation.T + offset)
    np.testing.assert_allclose(transformed["centroid"], offset, atol=1e-10)
    np.testing.assert_allclose(
        transformed["inertia_per_mass"], rotation @ np.diag(expected) @ rotation.T, atol=1e-10
    )
    with pytest.raises(ValueError):
        moments(faces[:, ::-1])
