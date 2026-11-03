"""Static contract checks between web/app (TypeScript, not buildable here: Node >= 18 needed)
and the Python backend. The TS sources are read with regexes; nothing is compiled."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import get_args

import pytest

from rocketwright.agent.events import EventType
from rocketwright.agent.fake_client import DEMO_PASSING_INDEX, DEMO_REQUIREMENTS, demo_designs
from rocketwright.agent.tools import _parse_design, _simulate_dispatch
from rocketwright.schema import Env, Requirement

ROOT = Path(__file__).resolve().parent.parent
WEB_APP = ROOT / "web" / "app"
TS_FILES = sorted(WEB_APP.rglob("*.ts")) + sorted(WEB_APP.rglob("*.tsx"))
TYPES_TS = (WEB_APP / "lib" / "types.ts").read_text(encoding="utf-8")
FORMAT_TS = (WEB_APP / "lib" / "format.ts").read_text(encoding="utf-8")
PAGE_TSX = (WEB_APP / "page.tsx").read_text(encoding="utf-8")

_IMPORT_RE = re.compile(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s+['"]([^'"]+)['"]""", re.M)
_HOOK_RE = re.compile(r"\buse[A-Z]\w*\(")


def _ts_string_array(src: str, name: str) -> list[str]:
    m = re.search(rf"export const {name}\b[^=]*=\s*\[(.*?)\];", src, re.S)
    assert m, f"{name} not found"
    return re.findall(r'"([^"]+)"', m.group(1))


def _ts_union(src: str, name: str) -> list[str]:
    m = re.search(rf"export type {name} =\s*(.*?);", src, re.S)
    assert m, f"{name} not found"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_event_types_match_backend_literal():
    backend = list(get_args(EventType))
    assert _ts_string_array(TYPES_TS, "EVENT_TYPES") == backend
    assert _ts_union(TYPES_TS, "EventType") == backend


def test_tier_list_matches_backend():
    from rocketwright.schema import Tier

    assert _ts_string_array(TYPES_TS, "TIERS") == [t.value for t in Tier]


@cache
def _real_metrics(tier: str) -> set[str]:
    # the first demo design meant to pass (seeded from the reference catalog; commercial tunes
    # its pitch program once, a few seconds)
    design = _parse_design(demo_designs(tier)[DEMO_PASSING_INDEX[tier]])
    env = Env(launch_latitude_deg=35.0, launch_altitude_m=20.0, wind_speed_mps=2.0)
    req = Requirement(**{**DEMO_REQUIREMENTS[tier], "text": "x"})
    return set(_simulate_dispatch(design, env, 1, req).metrics)


def _key_metrics_block(branch: str) -> list[str]:
    """Keys of the `keyMetrics(tier)` return list for `branch` (orbital / bottle / default)."""
    body = FORMAT_TS[FORMAT_TS.index("export function keyMetrics") :]
    body = body[: body.index("\n}\n") + 3]
    markers = {
        "orbital": "if (isOrbital(tier))",
        "bottle": 'if (tier === "bottle")',
        "default": "  return [",
    }
    start = body.index(markers[branch])
    if branch == "default":  # the final return: skip the two guarded ones
        start = body.rindex("  return [")
    chunk = body[start:]
    chunk = chunk[: chunk.index("];") + 2]
    return re.findall(r'key: "([^"]+)"', chunk)


@pytest.mark.parametrize(
    ("branch", "tier"), [("bottle", "bottle"), ("default", "amateur"), ("orbital", "commercial")]
)
def test_key_metrics_exist_in_real_sim_results(branch, tier):
    keys = _key_metrics_block(branch)
    assert len(keys) == 4
    missing = set(keys) - _real_metrics(tier)
    assert not missing, f"keyMetrics({tier}) cites metrics the physics never produce: {missing}"


def test_metric_labels_name_real_metrics():
    m = re.search(r"const METRIC_LABELS: Record<string, string> = \{(.*?)\};", FORMAT_TS, re.S)
    assert m
    labelled = set(re.findall(r"^\s*(\w+):", m.group(1), re.M))
    produced = _real_metrics("bottle") | _real_metrics("amateur") | _real_metrics("commercial")
    unknown = labelled - produced
    assert not unknown, f"METRIC_LABELS has keys no physics model produces: {unknown}"


def test_relative_imports_resolve():
    bad: list[str] = []
    for f in TS_FILES:
        for spec in _IMPORT_RE.findall(f.read_text(encoding="utf-8")):
            if not spec.startswith("."):
                continue
            target = (f.parent / spec).resolve()
            candidates = [target] + [target.with_suffix(s) for s in (".ts", ".tsx", ".css")]
            candidates += [target / "index.ts", target / "index.tsx"]
            if not any(c.is_file() for c in candidates):
                bad.append(f"{f.relative_to(ROOT)} -> {spec}")
    assert not bad, bad


def test_use_client_where_hooks_are_used():
    bad: list[str] = []
    for f in TS_FILES:
        src = f.read_text(encoding="utf-8")
        if _HOOK_RE.search(src) and f.name != "designState.ts":
            first = src.lstrip().splitlines()[0]
            if first.strip() not in ('"use client";', "'use client';"):
                bad.append(str(f.relative_to(ROOT)))
    assert not bad, f"hooks used without a 'use client' directive: {bad}"


def test_page_components_have_default_exports():
    used = re.findall(r'^import (\w+) from "\./components/(\w+)";', PAGE_TSX, re.M)
    assert used, "page.tsx imports no components"
    for name, module in used:
        path = WEB_APP / "components" / f"{module}.tsx"
        assert path.is_file(), path
        src = path.read_text(encoding="utf-8")
        assert re.search(rf"export default function {name}\b", src), f"{module}: no default {name}"
        assert re.search(rf"<{name}\b", PAGE_TSX), f"{name} imported but not rendered"


def test_single_chart_library():
    libs = {
        lib
        for f in TS_FILES
        for lib in _IMPORT_RE.findall(f.read_text(encoding="utf-8"))
        if lib in ("recharts", "plotly.js", "react-plotly.js")
    }
    assert libs == {"recharts"}


def _ts(path: str) -> str:
    return (WEB_APP / path).read_text(encoding="utf-8")


def test_chain_tools_are_labelled_and_reduced():
    """The staged design chain reaches the UI: tool labels, auto_design as an attempt row with
    its resolved design, design_stage results kept in time order for 「設計の決定順」."""
    from rocketwright.agent.tools import TOOL_NAMES

    labels = dict(
        re.findall(
            r"^\s*(\w+): \"([^\"]+)\",$",
            FORMAT_TS[FORMAT_TS.index("const TOOL_LABELS") :].split("};", 1)[0],
            re.M,
        )
    )
    assert set(labels) == set(TOOL_NAMES), set(TOOL_NAMES) ^ set(labels)
    assert labels["auto_design"] == "自動設計"
    assert labels["design_stage"] == "段階の候補"
    assert labels["design_from_parts"] == "部品から設計"
    state = _ts("lib/designState.ts")
    for case in ('case "auto_design"', 'case "design_stage"', 'case "design_from_parts"'):
        assert case in state, case
    assert "chain: ChainStep[]" in state
    assert "export function certificationNotes" in state
    assert "ChainStep" in TYPES_TS and "ChainCandidate" in TYPES_TS
    details = _ts("components/DetailsPanel.tsx")
    assert "DesignChainPanel" in details
    chain_panel = _ts("components/DesignChainPanel.tsx")
    assert "設計の決定順" in chain_panel
    for field in ("funnel", "alternatives", "invalidated", "why"):
        assert field in chain_panel, field
    assert "notes={" in PAGE_TSX and "chain={" in PAGE_TSX
    assert "notes" in _ts("components/ModelViewer.tsx")


def test_certification_notes_match_backend_warning_texts():
    """The amber note under the 3D view picks the build warnings by these fragments; they must
    occur in the real build.check_buildability messages."""
    state = _ts("lib/designState.ts")
    body = state[state.index("export function certificationNotes") :]
    frags = re.findall(r'"([^"]+)"', body[: body.index("\n}\n")])
    assert {"Level 1", "Level 2", "coupler"} <= set(frags)
    src = (ROOT / "rocketwright" / "build.py").read_text(encoding="utf-8")
    assert "certification" in src and "coupler" in src and "Level 2 (J-L)" in src


def test_ogive_nose_points_up_in_the_3d_model():
    """model3d.noseProfile runs from the base (x = 0) to the tip (x = L): the ogive radius must
    fall monotonically from R to 0, so noses and fairings point away from the body (the old
    profile put r = 0 at the base: an upside-down fairing). The TS expression is evaluated."""
    import math

    src = _ts("lib/model3d.ts")
    body = src[src.index("function noseProfile") :]
    body = body[body.index("tangent ogive") :]
    expr = re.search(r"\br = (Math\.sqrt\(.*?);\n", body).group(1)
    py = expr.replace("Math.sqrt", "math.sqrt").replace("Math.max", "max")
    radius, length = 0.5, 1.4
    rho = (radius * radius + length * length) / (2 * radius)
    rs = [
        max(0.0, eval(py, {"math": math, "max": max, "rho": rho, "radius": radius, "x": x}))
        for x in (length * i / 20 for i in range(21))
    ]
    assert math.isclose(rs[0], radius, rel_tol=1e-9)
    assert rs[-1] < 1e-9
    assert all(a >= b for a, b in zip(rs, rs[1:], strict=False))
