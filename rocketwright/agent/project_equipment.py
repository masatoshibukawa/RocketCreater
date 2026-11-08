"""Project-owned manufacturing, procurement and operator inputs; unknown stays unknown."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Purchase(Strict):
    part: Literal["bottle", "fin", "nose", "fixing", "payload", "recovery", "soft_cap", "other"]
    quantity: int = Field(ge=1, le=100)
    unit_price_jpy: float | None = Field(default=None, ge=0, le=1000000)
    basis: Literal["unknown", "estimate", "quote", "paid"] = "unknown"
    source: str = Field(default="", max_length=1000)
    checked_on: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def priced_source(self):
        if self.basis != "unknown" and (self.unit_price_jpy is None or not self.source.strip()):
            raise ValueError("価格には金額と根拠が必要です。")
        return self


class Equipment(Strict):
    printer_profile: Literal["s5-gray-aa04"] = "s5-gray-aa04"
    printer_label: str = Field(default="実験室1 / UltiMaker-006707", max_length=100)
    print_core: Literal["AA 0.4"] = "AA 0.4"
    build_plate: Literal["glass"] = "glass"
    material_lot: str = Field(default="", max_length=120)
    print_orientation: Literal["host_validated_profile"] = "host_validated_profile"
    operator: str = Field(default="未指定", max_length=80)
    glove: str = Field(default="未指定", max_length=80)
    hand_width_mm: float | None = Field(default=None, gt=0, le=200)
    glove_allowance_mm: float | None = Field(default=None, ge=0, le=20)
    strap_width_mm: float | None = Field(default=None, gt=0, le=20)
    strap_thickness_mm: float | None = Field(default=None, gt=0, le=10)
    tool_radius_mm: float | None = Field(default=None, gt=0, le=100)
    required_force_n: float | None = Field(default=None, ge=0, le=1000)
    allowable_force_n: float | None = Field(default=None, gt=0, le=1000)
    tools: list[str] = Field(
        default_factory=lambda: ["ノギス", "はかり", "適合する固定材"], max_length=20
    )
    workbench_clear_width_mm: float | None = Field(default=None, gt=0, le=5000)
    procurement: list[Purchase] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_parts(self):
        if len({r.part for r in self.procurement}) != len(self.procurement):
            raise ValueError("同じ部品の価格行は一つにまとめてください。")
        if any(not item.strip() or len(item) > 120 for item in self.tools):
            raise ValueError("工具名は1〜120文字です。")
        return self


def procurement_summary(spec):
    required = dict(bottle=1, nose=1, soft_cap=1, fixing=1, other=1)
    if spec.design.has_fins:
        required["fin"] = spec.geometry.fin_count
    if spec.design.payload_mass_kg:
        required["payload"] = 1
    if spec.design.has_parachute:
        required["recovery"] = 1
    supplied = {row.part: row for row in spec.equipment.procurement}
    rows, pending, total = [], [], 0.0
    for part, quantity in required.items():
        row = supplied.get(part)
        confirmed = bool(
            row
            and row.quantity == quantity
            and row.unit_price_jpy is not None
            and row.basis in {"quote", "paid"}
            and row.source
            and row.checked_on
        )
        if not confirmed:
            pending.append(part)
        subtotal = (
            row.quantity * row.unit_price_jpy if row and row.unit_price_jpy is not None else None
        )
        if subtotal is not None:
            total += subtotal
        rows.append(
            dict(
                part=part,
                required_quantity=quantity,
                confirmed=confirmed,
                supplied=row.model_dump() if row else None,
                subtotal_jpy=subtotal,
            )
        )
    return dict(
        rows=rows,
        missing_or_unconfirmed=pending,
        total_jpy=total if not pending else None,
        known_subtotal_jpy=total,
        scope="prototype BOM; other covers tools, shipping and remaining project costs",
    )
