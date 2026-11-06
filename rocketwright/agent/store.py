"""In-process artifact store shared by the agent tools and the API.

`render_drawing` / `export_report` (agent/tools.py) and `POST /artifacts/render` (api/main.py)
generate SVG / Markdown / CSV / JSON artifacts, keep them here under ids such as `svg_1` and
`rep_1`, and hand the model (or the UI) only the ids and download paths. `GET /artifacts/{id}.{ext}`
serves the stored content. The store is bounded (oldest entries are evicted) and thread-safe.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from rocketwright.drawing import render_side_view_svg
from rocketwright.report import export_bom_csv, export_report_json, export_report_markdown
from rocketwright.schema import Design, DispersionResult, Requirement, SimResult

__all__ = [
    "ARTIFACTS_PREFIX",
    "DEFAULT_STORE",
    "MEDIA_TYPES",
    "Artifact",
    "ResultStore",
    "store_drawing",
    "store_report",
]

ARTIFACTS_PREFIX = "/artifacts"

MEDIA_TYPES: dict[str, str] = {
    "svg": "image/svg+xml",
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "pdf": "application/pdf",
}


@dataclass(frozen=True)
class Artifact:
    artifact_id: str  # e.g. "svg_1"
    ext: str  # "svg" | "md" | "csv" | "json" | "pdf"
    content: str | bytes

    @property
    def key(self) -> str:
        return f"{self.artifact_id}.{self.ext}"

    @property
    def media_type(self) -> str:
        return MEDIA_TYPES.get(self.ext, "text/plain; charset=utf-8")

    @property
    def path(self) -> str:
        return f"{ARTIFACTS_PREFIX}/{self.key}"


class ResultStore:
    """Bounded dict keyed by `<id>.<ext>` with per-prefix id counters."""

    def __init__(self, max_items: int = 500) -> None:
        self._items: OrderedDict[str, Artifact] = OrderedDict()
        self._counters: dict[str, int] = {}
        self._max = max_items
        self._lock = threading.Lock()

    def next_id(self, prefix: str) -> str:
        with self._lock:
            n = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = n
            return f"{prefix}_{n}"

    def put(self, artifact: Artifact) -> Artifact:
        with self._lock:
            self._items[artifact.key] = artifact
            self._items.move_to_end(artifact.key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return artifact

    def get(self, key: str) -> Artifact | None:
        with self._lock:
            return self._items.get(key)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._counters.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


DEFAULT_STORE = ResultStore()


def store_drawing(
    design: Design, *, width_px: int = 800, store: ResultStore | None = None
) -> dict[str, Any]:
    """Render the side view, keep it in the store and describe it (no SVG text in the result)."""
    st = store or DEFAULT_STORE
    svg = render_side_view_svg(design, width_px=width_px)
    art = st.put(Artifact(st.next_id("svg"), "svg", svg))
    return {
        "id": art.artifact_id,
        "tier": design.tier,
        "svg_chars": len(svg),
        "download": {"svg": art.path},
        "note": "SVG side view with dimension lines; fetch it from the download path",
    }


def store_report(
    design: Design,
    result: SimResult,
    *,
    requirement: Requirement | None = None,
    dispersion: DispersionResult | None = None,
    sources: dict[str, str] | None = None,
    store: ResultStore | None = None,
    bom_csv: str | None = None,
) -> dict[str, Any]:
    """Generate Markdown + JSON report and BOM CSV, store them under one `rep_<n>` id. `bom_csv`
    replaces the design's estimated BOM (a parts build has a real bill)."""
    st = store or DEFAULT_STORE
    rep_id = st.next_id("rep")
    md = export_report_markdown(
        design, result, requirement=requirement, dispersion=dispersion, sources=sources
    )
    data = export_report_json(
        design, result, requirement=requirement, dispersion=dispersion, sources=sources
    )
    bom = export_bom_csv(design) if bom_csv is None else bom_csv
    st.put(Artifact(rep_id, "md", md))
    st.put(Artifact(rep_id, "json", json.dumps(data, ensure_ascii=False, indent=2)))
    st.put(Artifact(rep_id, "csv", bom))
    return {
        "id": rep_id,
        "tier": design.tier,
        "passed": result.success,
        "markdown_chars": len(md),
        "bom_rows": max(bom.count("\n") - 1, 0),
        "metric_count": len(data["metrics"]),
        "concept_level": bool(data["concept_level"]),
        "download": {
            "report": f"{ARTIFACTS_PREFIX}/{rep_id}.md",
            "json": f"{ARTIFACTS_PREFIX}/{rep_id}.json",
            "bom": f"{ARTIFACTS_PREFIX}/{rep_id}.csv",
        },
    }
