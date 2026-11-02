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
