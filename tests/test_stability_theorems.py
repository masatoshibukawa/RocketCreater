import numpy as np
import pytest

from rocketwright.physics.stability_theorems import (
    barbalat_eligibility,
    gronwall_bound,
    lasalle_pitch,
)


def test_lasalle_rejects_missing_restoring_or_damping():
    assert lasalle_pitch(1, 2, 3)["largest_invariant_set"] == "{0}"
    assert not lasalle_pitch(1, 2, 3)["qualified_for_full_flight"]
    assert lasalle_pitch(1, 0, 3)["status"].startswith("origin_not_asymptotic")
    assert lasalle_pitch(1, 2, 0)["status"].startswith("stable_not_asymptotic")
    assert lasalle_pitch(1, -1, 3)["status"] == "unstable_linear_model"


def test_gronwall_matches_exact_scalar_decay_and_disturbance():
    result = gronwall_bound([0, 0.3, 1], [-2 * np.eye(2)] * 3, disturbance_bound=0.4)
    assert 10 ** result["log10_homogeneous_gain"][-1] == pytest.approx(np.exp(-2))
    assert result["additive_disturbance_bound"][-1] == pytest.approx(0.2 * (1 - np.exp(-2)))
    assert result["all_intervals_contracting"]
    # Stable eigenvalues alone cannot imply Euclidean contraction for a non-normal matrix.
    nonnormal = np.array([[-1, 10], [0, -1]])
    result = gronwall_bound([0, 1], [nonnormal] * 2)
    assert result["log10_homogeneous_gain"][-1] > 0


def test_barbalat_never_certifies_a_finite_trace_or_state_from_W_alone():
    assumptions = dict(
        infinite_horizon=True,
        bounded_below_V=True,
        nonpositive_Vdot=True,
        uniformly_continuous_W=True,
        detects_state_origin=False,
    )
    assert barbalat_eligibility(**assumptions)["W_to_zero_proved"]
    assert not barbalat_eligibility(**assumptions)["state_to_origin_proved"]
    assumptions["infinite_horizon"] = False
    assert not barbalat_eligibility(**assumptions)["W_to_zero_proved"]


def test_pitch_screen_uses_air_incidence_opposite_to_attitude_error():
    from types import SimpleNamespace

    from rocketwright.physics.stability_theorems import flight_screen

    table = SimpleNamespace(
        speeds=[8, 30],
        area=0.01,
        evaluate=lambda v, q, cg: {"moment_nm": [0, 2 * np.arctan2(v[0], v[2]), 0]},
    )
    mass = SimpleNamespace(properties=lambda t: (1, 0.3, np.ones(3)))
    tr = dict(
        rail_exit_s=0,
        apogee_s=3,
        load_samples=[dict(time_s=t, air_velocity_body_mps=[0, 0, 10]) for t in (0.1, 1, 2)],
    )
    value = flight_screen(
        {"dimensions_mm": {"overall": 500}}, tr, table, mass, SimpleNamespace(pitch_damping=2)
    )
    assert value["frozen_asymptotic_count"] == 3
    assert value["frozen_checks"][0]["stiffness_nm_rad"] == pytest.approx(2)
    assert not value["full_flight_stability_proved"]
