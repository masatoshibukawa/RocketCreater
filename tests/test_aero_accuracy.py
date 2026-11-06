import numpy as np
import pytest

from rocketwright.analysis.aero_accuracy import grid_order, holdout, relative_change
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.runtime import Runtime
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.physics.fin_load_map import resultant_deck
from rocketwright.physics.flight_loads import TunnelDatabase
from tests.test_analysis_record import VOLUMES, spec


def test_three_grid_order_recovers_known_solution_and_rejects_oscillation():
    cells = [12, 18, 24]
    values = 2 + 30 / np.asarray(cells, dtype=float) ** 2
    result = grid_order(cells, values)
    assert result["observed_order"] == pytest.approx(2)
    assert result["fine_gci"] > 0
    assert not result["asymptotic_range_verified"]
    assert grid_order(cells, [2, 1, 1.5])["classification"] == "oscillatory"
    assert grid_order(cells, [1, 2, 4])["observed_order"] is None


def test_holdout_stays_outside_lookup_nodes_after_refinement():
    speeds, angles = [1, 35], [0, 5, 15, 45, 90, 135, 180]
    first = holdout(speeds, angles)
    assert first == (18, 10)
    speeds, angles = sorted(speeds + [first[0]]), sorted(angles + [first[1]])
    second = holdout(speeds, angles)
    assert second[0] not in speeds and second[1] not in angles
    with pytest.raises(ValueError):
        Runtime(cfd_speeds=(1, 35, 18))
    with pytest.raises(ValueError):
        relative_change([np.nan], [1])


def test_fin_transform_preserves_local_forces_and_root_moments():
    table = TunnelDatabase.__new__(TunnelDatabase)
    table.speeds, table.angles = np.array([1, 35]), np.array([0, 180])
    table.scale, table.area, table.diameter = 1, 2, 0.1
    table.fin_table = np.zeros((2, 2, 4, 6))
    table.fin_table[..., 1, :] = [0, -3, 0, 4, 0, -5]
    local = table.fin_resultants(18, 10, 10)[1]
    np.testing.assert_allclose(local, [0, 0, 60, 8, -10, 0])


@pytest.mark.parametrize(
    "load", [[0, 0, 2, 0.12, -0.08, 0], [0, 0, 0, 0.1, -0.03, 0], [1, 2, -2, -0.12, 0.08, 0.2]]
)
def test_signed_pressure_preserves_force_and_couples_on_different_meshes(load):
    record = compile_record(spec(), VOLUMES)
    for level in (1, 2, 3):
        lines, _, _, mapping = resultant_deck(
            record["assembly"],
            AnalysisConfig(**record["config"]),
            load,
            resolution=level,
            temperature_c=40,
        )
        np.testing.assert_allclose(
            mapping["mapped_normal_resultant"], np.asarray(load)[[2, 3, 4]], atol=1e-10
        )
        np.testing.assert_allclose(
            mapping["omitted_tangential_resultant"], np.asarray(load)[[0, 1, 5]]
        )
        assert "*DLOAD" in lines
