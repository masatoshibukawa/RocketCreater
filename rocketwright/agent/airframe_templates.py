"""Registered editable starting airframes; models select IDs, host code owns dimensions and CAD."""

import copy
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rocketwright.agent.design_projects import DesignSpec
from rocketwright.agent.local_runtime import LocalDirector
from rocketwright.manufacturing import PrintGeometry
from rocketwright.schema import BottleDesign

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "rocketwright/catalog/airframes/catalog.json"
TemplateID = Literal["pet-1l", "pet-15l", "pet-2l"]


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: TemplateID
    geometry: PrintGeometry | None = None
    payload_g: float = Field(default=60, ge=0, le=2000)
    recovery: bool = True


class TemplateChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: TemplateID
    reason: str = Field(min_length=1, max_length=500)


def catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def make_spec(request: TemplateRequest):
    row = next(r for r in catalog()["templates"] if r["id"] == request.template_id)
    design = BottleDesign(
        bottle_volume_m3=row["litres"] / 1000,
        water_fill_frac=0.3,
        initial_gauge_pressure_pa=350000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.15,
        payload_mass_kg=request.payload_g / 1000,
        has_parachute=request.recovery,
        parachute_diameter_m=0.7 if request.recovery else None,
    )
    geometry = request.geometry or PrintGeometry.from_design(design)
    if request.geometry is None and row["visual"]["kind"] == "reference-mesh":
        metadata = json.loads((CATALOG.parent / row["visual"]["profile"]).read_text())
        extent, axis = metadata["reference_extent_mm"], metadata["source_axis"]
        geometry = PrintGeometry.model_validate(
            geometry.model_dump()
            | {
                "body_height_mm": extent[axis],
                "body_diameter_mm": max(size for i, size in enumerate(extent) if i != axis),
            }
        )
    return DesignSpec(name=row["label"], design=design, geometry=geometry, other_dry_mass_g=80)


def create(store, request: TemplateRequest):
    from rocketwright.agent.airframe_parts import seed_parts

    state = store.create(make_spec(request))
    row = next(r for r in catalog()["templates"] if r["id"] == request.template_id)
    state["airframe_template"] = dict(
        id=row["id"],
        label=row["label"],
        catalog_revision=catalog()["revision"],
        shape_basis="reference CAD fitted to editable envelope; unmeasured",
    )
    seed_parts(store, state)
    store._write(state)
    return store.get(state["id"])


def visual_recipe(state):
    origin = state.get("airframe_template")
    if not origin:
        return None
    row = next((r for r in catalog()["templates"] if r["id"] == origin["id"]), None)
    if not row:
        raise ValueError("Unknown saved airframe template")
    from rocketwright.agent.video_cache import file_sha

    visual = copy.deepcopy(row["visual"])
    visual["asset_sha256"] = {
        visual[k]: file_sha(CATALOG.parent / visual[k])
        for k in ("mesh", "profile", "source_file")
        if k in visual
    }
    return visual | {"id": row["id"], "basis": origin["shape_basis"]}


def recommend(text, director=None):
    data, model = (director or LocalDirector()).generate(
        {
            "request": text,
            "registered_templates": catalog()["templates"],
            "role": "Select a registered starting configuration, not a verified design",
        },
        TemplateChoice.model_json_schema(),
        "依頼の容量や用途に合う登録済みの機体テンプレートIDを1つ選び、理由を日本語で返す。"
        "寸法・解析結果・パス・コードを生成しない。選択は未解析の出発案です。JSONだけ返す。",
    )
    return TemplateChoice.model_validate(data).model_dump() | {
        "model": model,
        "status": "unanalysed",
    }
