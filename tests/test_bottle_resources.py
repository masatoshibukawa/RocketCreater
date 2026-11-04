"""Planning resources must not masquerade as simulation parts or measured inventory."""

from rocketwright.agent.tools import execute_tool, get_tool_definitions


def search(kind="resources", query=None, tier="bottle"):
    return execute_tool("search_catalog", {"kind": kind, "query": query, "tier": tier}, "catalog")


def test_product_lookup_separates_nominal_fill_from_measured_geometry():
    [bottle] = search(query="コカコーラ 2L")["resources"]
    assert bottle["facts"] == {"market": "JP", "nominal_beverage_ml": 2000}
    assert "internal_volume_ml" in bottle["needs"]
    assert "documented_launcher_compatibility" in bottle["needs"]
    assert any(p["id"] == bottle["part_family_id"] for p in search("parts")["parts"])


def test_catalog_is_traversable_without_treating_fiber_as_a_fin():
    rows = search()["resources"]
    by_id = {row["id"]: row for row in rows}
    assert len(rows) == len(by_id)
    for row in rows:
        assert row["source"].startswith("https://") and row["needs"] and row["roles"]
        assert "parent_id" not in row or row["parent_id"] in by_id
    fin_ids = {row["id"] for row in search(query="fins")["resources"]}
    assert {"carton_fin", "pp_fin_075", "sn010_t_g", "fin_alignment_template"} <= fin_ids
    assert "toray_t700sc_12k_50c" not in fin_ids
    assert by_id["sn010_t_g"]["parent_id"] == "cfrp_plate"
    assert by_id["toray_t700sc_12k_50c"]["parent_id"] == "carbon_fiber"


def test_scale_catalog_can_distinguish_readability_and_range():
    rows = search(query="mass_measurement")["resources"]

    def matches(load_g, step_g):
        return {
            r["id"] for r in rows
            if r["facts"]["capacity_g"] >= load_g and r["facts"]["readability_g"] <= step_g
        }

    assert matches(60, 0.1) == {"and_hl_200i"}
    assert matches(350, 0.1) == set()
    assert matches(350, 1) == {"and_hl_2000i"}


def test_resources_filter_and_tool_contract():
    tool = next(tool for tool in get_tool_definitions() if tool["name"] == "search_catalog")
    assert "resources" in tool["input_schema"]["properties"]["kind"]["enum"]
    for tier in ["commercial", "amateur", "heavy"]:
        assert search(tier=tier)["resources"] == []
    response = search("all", "BMI270")
    assert response["count"] == 1 and not response["parts"]
    assert response["resources"][0]["roles"] == ["angular_rate", "acceleration", "vibration"]
    assert search(query="not-a-real-product")["count"] == 0
