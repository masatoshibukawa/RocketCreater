import numpy as np
import pytest

from rocketwright.bottle_assembly import Workshop
from rocketwright.bottle_search import Action, Search
from rocketwright.physics.bottle_integrity.loads import propulsion
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from rocketwright.physics.concrete_fin import build, polygon_moments
from rocketwright.physics.flight_loads import MassDistribution
from rocketwright.schema import BottleDesign


def test_polygon_moments_match_a_translated_rectangle():
    area, mean, second = polygon_moments([(2, 3), (6, 3), (6, 5), (2, 5)])
    assert area == pytest.approx(8)
    np.testing.assert_allclose(mean, [4, 4])
    np.testing.assert_allclose(second - mean**2, [4**2 / 12, 2**2 / 12])


def test_concrete_assembly_preserves_payload_and_reservoir_and_invalidates_evidence():
    search = Search("references", Workshop())
    action = Action("component", "D02", 9, 400, 25, "carton_wide")
    design = search.design(action)
    assembly = search.plan(action, design)
    cfg = AnalysisConfig()
    packet = dict(design=design.model_dump(), assembly=assembly, config=cfg.model_dump())
    result = build(packet)
    updated = BottleDesign(**result["design"])
    actual = result["assembly"]
    assert sum(b["mass_g"] for b in actual["bill"]) / 1000 == pytest.approx(updated.dry_mass_kg)
    assert updated.dry_mass_kg > design.dry_mass_kg
    before = MassDistribution(design, assembly, propulsion(design, cfg.loads))
    after = MassDistribution(updated, actual, propulsion(updated, cfg.loads))
    assert after.bottom == pytest.approx(before.bottom)
    assert after.dry_station[-1] == pytest.approx(before.dry_station[-1])
    fin_index = next(i for i, b in enumerate(actual["bill"]) if b["id"] == "carton_fin")
    np.testing.assert_allclose(
        after.local_dry[fin_index], actual["bill"][fin_index]["local_inertia_kg_m2"]
    )
    assert "holdout" not in actual
    assert actual["checks"] == {
        "previous_evidence_invalidated": True,
        "physical_qualification": False,
    }
    assert result["config"]["fin_material"]["tensile_allowable_pa"] is None
    assert result["specification"]["fin"]["strength_allowable_pa"] is None
    assert assembly["dimensions_mm"]["fin_span"] == 140  # input untouched


def test_normal_load_mapping_preserves_force_and_both_initial_moments():
    from rocketwright.physics.fin_load_map import deck

    search = Search("references", Workshop())
    action = Action("component", "D02", 9, 400, 25, "carton_wide")
    design = search.design(action)
    assembly = search.plan(action, design)
    assembly["fin_set_CNalpha_per_rad"] = 12
    cfg = AnalysisConfig()
    for level in (1, 2, 3):
        _, _, _, metadata = deck(
            assembly, cfg, 2.3, [0.04, 0.06], resolution=level, temperature_c=45
        )
        assert metadata["force_mapped_n"] == pytest.approx(2.3)
        np.testing.assert_allclose(metadata["centroid_mapped_m"], [0.04, 0.06], atol=1e-9)
    with pytest.raises(ValueError):
        deck(assembly, cfg, 2.3, [0.04, 0.3], resolution=1, temperature_c=45)


def test_uniform_centroid_load_accepts_a_zero_residual_root():
    from rocketwright.analysis.record import compile_record
    from rocketwright.physics.fin_load_map import deck
    from tests.test_analysis_record import VOLUMES, spec

    s = spec()
    g = s.geometry
    record = compile_record(s, VOLUMES)
    _, center, _ = polygon_moments(
        np.array(
            [
                [0, 0],
                [g.fin_root_mm, 0],
                [g.fin_sweep_mm + g.fin_tip_mm, g.fin_span_mm],
                [g.fin_sweep_mm, g.fin_span_mm],
            ]
        )
        / 1000
    )
    _, _, _, result = deck(
        record["assembly"],
        AnalysisConfig(**record["config"]),
        2,
        center,
        resolution=1,
        temperature_c=25,
    )
    np.testing.assert_allclose(result["centroid_mapped_m"], center, atol=1e-10)
    assert result["force_mapped_n"] == pytest.approx(2)
