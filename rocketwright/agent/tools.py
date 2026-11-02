"""Tool definitions (JSON Schema) handed to Claude and their implementations.

Implemented in phase 1 (prompt 1B).
"""

TOOL_NAMES: tuple[str, ...] = (
    "classify_requirement",
    "search_catalog",
    "simulate_design",
    "run_dispersion",
    "estimate_cost",
    "render_drawing",
    "export_report",
)


def get_tool_definitions() -> list[dict]:
    raise NotImplementedError("tools.get_tool_definitions: implemented in phase 1 (prompt 1B)")
