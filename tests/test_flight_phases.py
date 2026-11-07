import pytest

from rocketwright.analysis.flight_phases import diagnose, exploration_score


def fixture():
    assembly = dict(cp_mm=300, dimensions_mm=dict(body_diameter=100))
    flight = dict(
        rail_exit_s=1,
        apogee_s=3,
        rail_exit_speed_mps=15,
        load_samples=[
            dict(
                time_s=t,
                cg_m=cg,
                rail_force_n=[3, 4, 0] if t < 1 else [0, 0, 0],
                rail_moment_nm=[0, 0.2, 0],
            )
            for t, cg in [(0, 0.35), (0.5, 0.26), (1.5, 0.10), (3, 0.12)]
        ],
    )
    return assembly, flight


def test_guided_diagnostic_retains_unstable_initial_and_unverified_guide():
    a, f = fixture()
    r = diagnose(a, f)
    assert r["initial_with_gas_margin_cal"] == pytest.approx(-0.5)
    assert r["exit_margin_cal"] == pytest.approx(1.2)
    assert r["free_ascent_min_margin_cal"] == pytest.approx(1.2)
    assert r["maximum_guide_force_n"] == 5
    assert not r["guide_capacity_verified"]
    assert not r["acceptance_changed"]
    f["rail_exit_s"] = 0
    with pytest.raises(ValueError):
        diagnose(a, f)


def test_guided_search_cannot_hide_missing_departure_or_excessive_bending():
    metrics = dict(
        scenario_height_m=[32, 35],
        static_margin_cal=-0.3,
        axial_free_margin_cal=1.2,
        conservative_beam_ratio=0.04,
    )
    assert exploration_score(metrics, 30)[0] > 0
    assert exploration_score(metrics, 30, "guided")[0] == 0
    metrics["conservative_beam_ratio"] = 0.2
    assert exploration_score(metrics, 30, "guided")[0] > 0
    metrics["axial_free_margin_cal"] = None
    assert exploration_score(metrics, 30, "guided")[0] == float("inf")
