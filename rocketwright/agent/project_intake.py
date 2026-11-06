"""Japanese intake with an installed local model and finite host-generated candidates."""

import copy
import json
import re
import time
import unicodedata
import uuid
from typing import Literal

from pydantic import Field

from rocketwright.agent.design_projects import DesignSpec, write_json
from rocketwright.agent.local_runtime import LocalDirector
from rocketwright.agent.project_equipment import Strict
from rocketwright.agent.project_jobs import file_lock
from rocketwright.agent.workbench import Conflict
from rocketwright.manufacturing import PrintGeometry
from rocketwright.schema import BottleDesign, Requirement


class Intent(Strict):
    name: str = Field(min_length=1, max_length=80)
    target_altitude_m: float | None = Field(default=None, gt=0, le=150)
    payload_g: float | None = Field(default=None, ge=0, le=2000)
    bottle_l: float | None = Field(default=None, ge=0.3, le=3)
    budget_jpy: float | None = Field(default=None, gt=0, le=1000000)
    recovery_required: bool | None = None
    pressure_kpa: float | None = Field(default=None, ge=100, le=400)
    water_fill_pct: float | None = Field(default=None, ge=15, le=40)
    nozzle_mm: float | None = Field(default=None, ge=3, le=22)
    fin_span_mm: float | None = Field(default=None, ge=15, le=150)
    fin_thickness_mm: float | None = Field(default=None, ge=1.2, le=6)
    altitude_rule: Literal["band_10pct", "minimum"] | None = None
    reason: str = Field(min_length=1, max_length=500)


def grounded_fields(data, text):
    """The model maps meaning; the host rejects quantities absent from the new request."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    units = {
        "target_altitude_m": {"m": 1, "メートル": 1, "cm": 0.01},
        "payload_g": {"g": 1, "グラム": 1, "kg": 1000},
        "bottle_l": {"l": 1, "リットル": 1, "ml": 0.001},
        "budget_jpy": {"円": 1},
        "pressure_kpa": {"kpa": 1, "pa": 0.001},
        "water_fill_pct": {"%": 1},
        "nozzle_mm": {"mm": 1, "cm": 10},
        "fin_span_mm": {"mm": 1, "cm": 10},
        "fin_thickness_mm": {"mm": 1, "cm": 10},
    }
    accepted = dict(data)
    for field, conversions in units.items():
        value = accepted.get(field)
        if value is None:
            continue
        matches = []
        for unit, scale in conversions.items():
            matches.extend(
                float(m) * scale
                for m in re.findall(r"(\d+(?:\.\d+)?)\s*" + re.escape(unit) + r"(?![a-z])", text)
            )
        if not any(abs(v - value) < 1e-7 for v in matches):
            accepted[field] = None
    if not re.search("パラシュート|回収|傘", text):
        accepted["recovery_required"] = None
    if not re.search(r"\d+(?:\.\d+)?\s*(?:m|メートル|cm)(?![a-z])", text):
        accepted["altitude_rule"] = None
    return accepted


def propose(store, text, project_id=None, director=None):
    current = store.get(project_id) if project_id else None
    director = director or LocalDirector()
    director.api.timeout = 90
    schema = Intent.model_json_schema()
    for row in schema["properties"].values():
        row.pop("default", None)
        alternatives = row.pop("anyOf", None)
        if alternatives:
            concrete = next(r for r in alternatives if r.get("type") != "null")
            row.update(concrete)
            row["type"] = [concrete["type"], "null"]
    schema["required"] = list(schema["properties"])
    data, model = director.generate(
        dict(
            request=text,
            current=current["spec"] if current else None,
            instructions=(
                "Extract explicit new facts only; null otherwise. "
                "Fields carry display units (g, L, mm, kPa, percent)."
            ),
        ),
        schema,
        "日本語の依頼から、明示された数値と回収条件を各フィールドへ抽出してください。"
        "入力requestを必ず最後まで読み、数字をnameやreasonへ書くだけでなく対応する数値欄へ入れます。"
        "例：『1.5 L、80 g、15 m以上、傘回収、300 kPa、予算5000円』なら、"
        "target_altitude_m=15,payload_g=80,bottle_l=1.5,budget_jpy=5000,"
        'recovery_required=true,pressure_kpa=300,altitude_rule="minimum"。'
        "『20 m程度』ならtarget_altitude_m=20,altitude_rule=band_10pctです。"
        "『パラシュートで回収』はrecovery_required=trueです。"
        '出力例：{"name":"試作","target_altitude_m":20,"payload_g":60,'
        '"bottle_l":2,"budget_jpy":null,"recovery_required":true,'
        '"pressure_kpa":300,"water_fill_pct":null,"nozzle_mm":null,'
        '"fin_span_mm":null,"fin_thickness_mm":null,"altitude_rule":"band_10pct",'
        '"reason":"依頼の高度・搭載・回収を抽出"}。例は形式の参考、値はrequestに合わせる。'
        "変更の依頼では新しく明示された条件だけ抽出し、その他はnull。"
        "nameは短い案件名、reasonは抽出の説明です。指定されない値を推測しない。"
        "パス、コマンド、合否を出さず、指定されたJSONだけを返してください。",
    )
    raw_intent = Intent.model_validate(data)
    intent = Intent.model_validate(grounded_fields(raw_intent.model_dump(), text))
    previous = DesignSpec.model_validate(current["spec"]) if current else None
    target = intent.target_altitude_m or (
        previous.requirement.target_altitude_m if previous and previous.requirement else None
    )
    payload = (
        intent.payload_g
        if intent.payload_g is not None
        else (previous.design.payload_mass_kg * 1000 if previous else None)
    )
    recovery = (
        intent.recovery_required
        if intent.recovery_required is not None
        else (previous.design.has_parachute if previous else None)
    )
    missing = []
    if target is None:
        missing.append("目標高度をmで入力してください。")
    if payload is None:
        missing.append("搭載質量をgで入力してください（なしは0 g）。")
    if recovery is None:
        missing.append("パラシュートで回収するかを指定してください。")
    ticket = dict(
        id=uuid.uuid4().hex,
        text=text,
        model=model,
        raw_intent=raw_intent.model_dump(),
        intent=intent.model_dump(),
        project_id=project_id,
        revision=current["revision"] if current else None,
        created_at=time.time(),
        questions=missing,
        candidates=[],
    )
    if not missing:
        design = (
            previous.design.model_dump()
            if previous
            else dict(
                bottle_volume_m3=0.002,
                water_fill_frac=0.3,
                initial_gauge_pressure_pa=350000,
                nozzle_diameter_m=0.009,
                dry_mass_kg=0.15,
                has_fins=True,
                parachute_diameter_m=0.7,
            )
        )
        design.update(payload_mass_kg=payload / 1000, has_parachute=recovery)
        for key, value in (
            (
                "initial_gauge_pressure_pa",
                None if intent.pressure_kpa is None else intent.pressure_kpa * 1000,
            ),
            (
                "water_fill_frac",
                None if intent.water_fill_pct is None else intent.water_fill_pct / 100,
            ),
            ("nozzle_diameter_m", None if intent.nozzle_mm is None else intent.nozzle_mm / 1000),
        ):
            if value is not None:
                design[key] = value
        if intent.bottle_l is not None:
            design["bottle_volume_m3"] = intent.bottle_l / 1000
        if recovery and not design.get("parachute_diameter_m"):
            design["parachute_diameter_m"] = 0.7
        design = BottleDesign.model_validate(design)
        changed_capacity = previous and design.bottle_volume_m3 != previous.design.bottle_volume_m3
        geometry = (
            previous.geometry
            if previous and not changed_capacity
            else PrintGeometry.from_design(design.model_copy(update={"geometry": None}))
        )
        updates = {
            key: value
            for key, value in (
                ("fin_span_mm", intent.fin_span_mm),
                ("fin_thickness_mm", intent.fin_thickness_mm),
            )
            if value is not None
        }
        if updates:
            geometry = PrintGeometry.model_validate(
                {**geometry.model_dump(), **updates, "dimensions_measured": False}
            )
        budget = (
            intent.budget_jpy
            if intent.budget_jpy is not None
            else (previous.requirement.budget_jpy if previous and previous.requirement else None)
        )
        name = intent.name
        if name in {"試作", "ロケット", "ペットボトルロケット"}:
            name = f"{design.bottle_volume_m3 * 1000:g} L・{payload:g} g・目標{target:g} m"
        spec = DesignSpec(
            name=name,
            design=design,
            geometry=geometry,
            requirement=Requirement(
                goal_kind="altitude",
                target_altitude_m=target,
                payload_mass_kg=payload / 1000,
                budget_jpy=budget,
                recovery_required=recovery,
                text=text,
            ),
            altitude_rule=intent.altitude_rule
            or (previous.altitude_rule if previous else "band_10pct"),
            measured_printed_mass_g=previous.measured_printed_mass_g
            if previous and not changed_capacity and not updates
            else None,
            other_dry_mass_g=previous.other_dry_mass_g if previous else 80,
            material=previous.material if previous else "UltiMaker Tough PLA Gray",
            env=previous.env if previous else {},
            assumptions=previous.assumptions if previous else {},
            equipment=previous.equipment if previous else {},
        )
        for key, label, multiplier in [
            ("base", "同じ基本条件", 1),
            ("wide_fin", "フィンを少し広げる案", 1.1),
        ]:
            variant = copy.deepcopy(spec.model_dump(mode="json"))
            if multiplier != 1:
                variant["geometry"]["fin_span_mm"] *= multiplier
                variant["geometry"]["dimensions_measured"] = False
                variant["measured_printed_mass_g"] = None
            try:
                candidate = DesignSpec.model_validate(variant)
            except ValueError:
                continue
            ticket["candidates"].append(
                dict(
                    id=key,
                    label=label,
                    spec=candidate.model_dump(mode="json"),
                    status="unanalysed",
                    assumptions=[
                        "未指定の外形は容量からの仮定。保存前に寸法を確認・編集できます。",
                        "圧力・充填率・ノズルは登録済みの計算シナリオ。機材の使用許可値ではありません。",
                        "合否と質量は採用候補のCAD・解析で決めます。価格未入力は予算未評価。",
                    ],
                )
            )
    write_json(store.root / "intents" / (ticket["id"] + ".json"), ticket)
    return ticket


def accept(store, ticket_id, candidate_id):
    if not re.fullmatch(r"[a-f0-9]{32}", ticket_id):
        raise KeyError("Unknown intent")
    with file_lock(store.root / "intents" / (ticket_id + ".lock")):
        return _accept(store, ticket_id, candidate_id)


def _accept(store, ticket_id, candidate_id):
    if not re.fullmatch(r"[a-f0-9]{32}", ticket_id):
        raise KeyError("Unknown intent")
    ticket = json.loads(
        (store.root / "intents" / (ticket_id + ".json")).read_text(encoding="utf-8")
    )
    row = next((c for c in ticket["candidates"] if c["id"] == candidate_id), None)
    if not row:
        raise KeyError("Unknown offered candidate")
    if not ticket["project_id"] and ticket.get("accepted_project_id"):
        return store.get(ticket["accepted_project_id"])
    spec = DesignSpec.model_validate(row["spec"])
    if ticket["project_id"]:
        current = store.get(ticket["project_id"])
        if current["revision"] != ticket["revision"]:
            raise Conflict("提案後に設計が変わりました。変更を再提案してください。")
        state = store.edit(current["id"], current["revision"], spec)
    else:
        state = store.create(spec)

    def record(state):
        state.setdefault("intake", []).append(
            {k: v for k, v in ticket.items() if k != "candidates"}
        )
        state["intake"][-1]["selected_candidate"] = candidate_id
        directory = store.directory(state["id"]) / "intake"
        write_json(directory / "intake.json", state["intake"])
        store.register_files(state, directory, "intake")

    result = store._run(state["id"], state["revision"], "accept_local_intent", record)
    ticket["accepted_project_id"] = state["id"]
    write_json(store.root / "intents" / (ticket_id + ".json"), ticket)
    return result
