import numpy as np
import pytest

from rocketwright.physics.flight_loads import envelopes, section_resultants
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


def test_cut_convention_matches_tip_loaded_cantilever():
    cuts = np.array([0.0, 0.2, 0.4, 0.8])
    r = section_resultants([0.0], [[0, 7, 0]], [[0, 0, 0]], cuts)
    assert r[1:, 1] == pytest.approx(-7)
    assert r[1:, 3] == pytest.approx(7 * cuts[1:])
    assert r[0] == pytest.approx(np.zeros(6))


def test_pressure_pair_produces_tension_and_zero_global_force():
    r = section_resultants(
        [0.2, 0.5], [[0, 0, 100], [0, 0, -100]], np.zeros((2, 3)), [0.0, 0.3, 0.6]
    )
    assert r[:, 2] == pytest.approx([0, -100, 0])
    assert r[:, 3:] == pytest.approx(np.zeros((3, 3)))


def test_envelope_retains_concurrent_loads_and_event():
    values = np.zeros((2, 2, 6))
    values[0, 1] = [3, 4, 10, 0, 2, 1]
    values[1, 1] = [0, 2, -20, 4, 3, 2]
    case = {"cuts_m": [0.0, 0.4], "time_s": [1.0, 2.0], "resultants": values}
    result = envelopes({"nominal": case}, design_factor=1.5)["envelopes"]
    assert result["compression_n"][1]["time_s"] == 1
    assert result["tension_n"][1]["design"] == 30
    assert result["bending_nm"][1]["concurrent_vector"] == values[1, 1].tolist()
