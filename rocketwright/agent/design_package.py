"""Production files of one design, without a workbench project.

The workbench exports a project that went through the 1.5 L recipe: `assembly()` fixes the bays,
skirt, fins and parts, and overwrites the mass and Cd to match. A free design carries none of
that, so feeding it to the recipe would describe another vehicle. This package holds what the
design, its bill and a repeat of its simulation support, and names what it cannot give.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from rocketwright.agent.design_sheet import render_design_sheet
from rocketwright.agent.store import (
    DEFAULT_STORE,
    Artifact,
    ResultStore,
    store_drawing,
    store_report,
)
from rocketwright.agent.tools import DISPERSION_DEFAULT_N, execute_tool
from rocketwright.bottle_candidates import CONFIRMATION_SEED
from rocketwright.build import AmateurBuild, BottleBuild
from rocketwright.report import BOM_COLUMNS, _csv_cells
from rocketwright.schema import (
    BottleDesign,
    Design,
    DesignAdapter,
    DispersionResult,
    Env,
    Requirement,
    SimResult,
)
from rocketwright.summary import design_summary, design_summary_from_build

__all__ = ["design_package"]

_NO_RECIPE = (
    "この案は機体の構成を定めていません。1.5 L の製作例の値を使うと別の機体の資料になります"
)
UNAVAILABLE_BOTTLE = (
    {"item": "組立手順の文章", "reason": _NO_RECIPE},
    {"item": "原寸フィン型紙", "reason": "案にフィンの翼根・翼端・後退の寸法がありません"},
    {
        "item": "購入計画",
        "reason": "製作例の部材と店の価格に結びついた資料で、この案の部材ではありません",
    },
    {
        "item": "搭載部カラーと位置決め治具の STL",
        "reason": "搭載室と胴体の実寸がありません。フィンとノーズは下の印刷データで作れます",
    },
)
UNAVAILABLE_AMATEUR = (
    {"item": "製作票 PDF", "reason": "製作票はボトルの案だけです"},
    {"item": "3D プリント用データ", "reason": "印刷データの生成はボトルの案だけです"},
)
FILE_LABELS = {
    "sheet": "製作票 PDF",
    "report": "設計レポート（Markdown）",
    "json": "設計レポート（JSON）",
    "bom": "部品表（CSV）",
    "drawing": "側面図（SVG）",
}


def _tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    result = execute_tool(name, tool_input, "design-package")
    if "error" in result:
        raise ValueError(result["error"])
    return result


def _bom_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BOM_COLUMNS)
    writer.writerows(_csv_cells(row) for row in rows)
    return buffer.getvalue()


def _from_build(
    build: AmateurBuild | BottleBuild, common: dict[str, Any], requirement: Requirement | None
) -> tuple[Design, SimResult, dict[str, Any]]:
    out = _tool("design_from_parts", {"build": build.model_dump(mode="json"), **common})
    if out["sim"] is None:
        raise ValueError(out.get("note") or "the build was not simulated")
    summary = design_summary_from_build(build, requirement=requirement)
    return DesignAdapter.validate_python(out["design"]), SimResult(**out["sim"]), summary


def design_package(
    design: Design,
    *,
    build: AmateurBuild | BottleBuild | None = None,
    requirement: Requirement | None = None,
    env: Env | None = None,
    seed: int | None = None,
    n: int | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    """Repeat the design's simulation and dispersion, then store its files. `seed` and `n`
    default to the workbench's confirmation seed and the agent's sample count. Whether the
    design passed is reported, not assumed: the screen offers this only for a passing one."""
    st = store or DEFAULT_STORE
    common = {
        "env": (env or Env()).model_dump(mode="json"),
        "requirement": None if requirement is None else requirement.model_dump(mode="json"),
    }
    if build is None:
        out = _tool("simulate_design", {"design": design.model_dump(mode="json"), **common})
        result = SimResult.model_validate(out)
        summary = design_summary(design, requirement)
        cost, bom_csv = None, None
    else:
        design, result, summary = _from_build(build, common, requirement)
        cost, bom_csv = summary["cost_jpy"], _bom_csv(summary["bom"])

    spread = _tool(
        "run_dispersion",
        {
            "design": design.model_dump(mode="json"),
            "seed": CONFIRMATION_SEED if seed is None else seed,
            "n": DISPERSION_DEFAULT_N if n is None else n,
            "cost_jpy": cost,
            **common,
        },
    )
    dispersion = DispersionResult.model_validate(
        {k: v for k, v in spread.items() if k in DispersionResult.model_fields}
    )
    report = store_report(
        design, result, requirement=requirement, dispersion=dispersion, store=st, bom_csv=bom_csv
    )
    drawing = store_drawing(design, store=st)
    urls = {
        "report": report["download"]["report"],
        "json": report["download"]["json"],
        "bom": report["download"]["bom"],
        "drawing": drawing["download"]["svg"],
    }
    if isinstance(design, BottleDesign):
        sheet = render_design_sheet(design, result, summary, dispersion)
        urls = {"sheet": st.put(Artifact(st.next_id("pkg"), "pdf", sheet)).path, **urls}
    return {
        "tier": design.tier,
        "passed": result.success,
        "failure_reasons": list(result.failure_reasons),
        "success_rate": dispersion.success_rate,
        "files": [{"kind": k, "label": FILE_LABELS[k], "url": url} for k, url in urls.items()],
        "unavailable": list(
            UNAVAILABLE_BOTTLE if isinstance(design, BottleDesign) else UNAVAILABLE_AMATEUR
        ),
    }
