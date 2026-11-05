import numpy as np
import pytest

from scenarios.cfd.surface_loads import body_samples, reduce_line


def test_line_reduction_preserves_force_and_moment_at_arbitrary_origin():
    rng = np.random.default_rng(823)
    xyz = rng.uniform([-0.001, -0.2, -0.2], [0.6, 0.2, 0.2], (437, 3))
    forces = rng.normal(size=xyz.shape)
    result = reduce_line(xyz, forces, 0.6, 0.09, 37)
    station = np.column_stack([result["station_m"], np.zeros((37, 2))])
    origin = np.array([0.29, 0.02, -0.01])
    reduced_force = np.asarray(result["force_coeff"])
    reduced_couple = np.asarray(result["couple_coeff_at_station"]) * 0.09
    assert reduced_force.sum(0) == pytest.approx(forces.sum(0))
    assert (np.cross(station - origin, reduced_force) + reduced_couple).sum(0) == pytest.approx(
        np.cross(xyz - origin, forces).sum(0)
    )


def test_rotated_sample_coordinates_and_loads_share_the_same_frame():
    ids = np.array([221, 435])
    stats = np.array([[0.1, 0.2], [1, 2], [3, 4], [5, 6]])
    a, f = body_samples(ids, stats, (20, 8, 8), 4, 2, 0.09, 0.3, 0, False)
    b, g = body_samples(ids, stats, (20, 8, 8), 4, 2, 0.09, 0.3, 90, True)
    transform = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    ref = np.array([0.3, 0, 0])
    assert b == pytest.approx((a - ref) @ transform.T + ref)
    assert g == pytest.approx(f @ transform.T)
    assert np.cross(b - ref, g) == pytest.approx(np.cross(a - ref, f) @ transform.T)
