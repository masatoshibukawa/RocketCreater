from rocketwright.adaptive import Requirements
from rocketwright.bottle_assembly import Workshop
from rocketwright.bottle_search import Action, Search
from scenarios.adaptive_analysis.repair import geometry_candidates


def test_geometry_repair_recomputes_mass_cp_and_never_reuses_old_aero():
    search = Search("references", Workshop())
    action = Action("component", "D02", 9, 400, 25, "carton_wide")
    design = search.design(action)
    assembly = search.plan(action, design)
    # The existing assembly stores CP but the integrity adapter supplies CNalpha.
    assembly["fin_set_CNalpha_per_rad"] = 12.445815565142087
    packet = dict(design=design.model_dump(), assembly=assembly)
    prior = {
        "fin-candidates": {
            "value": {
                "load_event": {"force_one_fin_n": 2.385627411987717},
                "temperature_c": 44.84,
            }
        }
    }
    result = geometry_candidates(packet, prior, Requirements())
    assert len(result["candidates"]) == 192
    assert result["lightest"]["screen_pass"]
    assert result["lightest"]["id"] in result["pareto_ids"]
    for row in result["candidates"]:
        assert row["CFD_invalidated"] and row["nonlinear_FEM_required"]
        assert row["assembly"]["dimensions_mm"]["fin_span"] == row["span_mm"]
        assert row["assembly"]["cost_status"].startswith("invalidated")
        if row["screen_pass"]:
            assert row["wet_margin_with_water_shift_mm"] > 0
            assert row["deflection_span_ratio"] <= 0.05
