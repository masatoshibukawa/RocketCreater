import numpy as np
import pytest

from rocketwright.physics.fin_candidates import beam, reconcile_mass


def test_beam_uniform_load_matches_closed_form_with_compliant_root():
    span, chord, thickness, young, spring, tab, force = 0.14, 0.06, 0.002, 2e9, 5e5, 0.01, 3.0
    ei = young * chord * thickness**3 / 12
    root = np.linalg.solve(
        spring * np.array([[1, -tab / 2], [-tab / 2, tab * tab / 3]]), [force, force * span / 2]
    )
    expected = force * span**3 / (8 * ei) + root @ [1, span]
    value = beam(span, chord, chord, thickness, young, 1200, spring, force, tab=tab)
    assert value["tip_m"] == pytest.approx(expected, rel=1e-6)
    assert value["root_force_n"] == pytest.approx(force, rel=1e-6)
    assert value["relative_equilibrium_residual"] < 1e-7
    assert min(value["first_modes_hz"]) > 0


def test_tapered_beam_refinement_and_thickness_tradeoff():
    args = [0.14, 0.07, 0.035, 0.001, 2e9, 1200, 5e5, 3]
    coarse, fine = beam(*args, n=20), beam(*args, n=40)
    assert abs(coarse["tip_m"] / fine["tip_m"] - 1) < 0.005
    args[3] *= 2
    thick = beam(*args)
    assert thick["mass_one_fin_kg"] == pytest.approx(2 * fine["mass_one_fin_kg"])
    assert thick["tip_m"] < fine["tip_m"]
    assert thick["first_modes_hz"][0] > fine["first_modes_hz"][0]


def test_fin_mass_update_preserves_payload_and_liquid_location(tmp_path):
    from rocketwright.bottle_assembly import Workshop
    from rocketwright.bottle_search import Action, Search
    from rocketwright.physics.bottle_integrity.loads import propulsion
    from rocketwright.physics.bottle_integrity.schema import LoadConfig
    from rocketwright.physics.flight_loads import MassDistribution

    search = Search("references", Workshop())
    action = Action("component", "D02", 9, 400, 25, "carton_wide")
    design = search.design(action)
    assembly = search.plan(action, design)
    changed, article = reconcile_mass(design, assembly, 0.05)
    original = MassDistribution(design, assembly, propulsion(design, LoadConfig()))
    updated = MassDistribution(changed, article, propulsion(changed, LoadConfig()))
    assert updated.bottom == pytest.approx(original.bottom)
    assert updated.dry_station[-1] == pytest.approx(original.dry_station[-1])
    assert sum(b["mass_g"] for b in article["bill"]) / 1000 == pytest.approx(changed.dry_mass_kg)
    assert changed.dry_mass_kg > design.dry_mass_kg
    assert article["loaded_cg_mm"] > assembly["loaded_cg_mm"]
