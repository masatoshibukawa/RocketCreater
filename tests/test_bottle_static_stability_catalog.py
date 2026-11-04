from rocketwright.agent.tools import execute_tool, get_tool_definitions


def test_static_margin_is_a_planned_bottle_assessment():
    catalog = execute_tool(
        "search_catalog", {"tier": "bottle", "kind": "parts", "query": "fins"}, "cat"
    )
    planned = catalog["planned"]
    method = planned["analysis_methods"]["phase_static_margin"]
    score = planned["evaluation_functions"]["minimum_static_margin_cal"]
    assert score["method"] == "phase_static_margin"
    assert set(score["uses"]) <= method["outputs"].keys()
    assert set(method["references"]) <= catalog["references"].keys()
    assert score["unit"] == "cal"
    assert "phase_static_margin" not in {tool["name"] for tool in get_tool_definitions()}
    for tier, query in [("amateur", None), ("bottle", "no-such-part")]:
        other = execute_tool("search_catalog", {"tier": tier, "kind": "parts", "query": query}, "x")
        assert "phase_static_margin" not in other.get("planned", {}).get("analysis_methods", {})
