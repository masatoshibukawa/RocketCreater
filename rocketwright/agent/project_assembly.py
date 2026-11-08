"""Bounded assembly access screening and version-bound human observations."""

import math
from typing import Literal

from pydantic import Field, model_validator

from rocketwright.agent.project_equipment import Strict
from rocketwright.manufacturing import PrintRequest, parameters

STEP_IDS = ("parts", "finish", "fin_mount", "nose_fit", "recovery", "measure")


class Observation(Strict):
    step: Literal["parts", "finish", "fin_mount", "nose_fit", "recovery", "measure"]
    status: Literal["unconfirmed", "needs_change", "observed"] = "unconfirmed"
    operator: str = Field(default="", max_length=80)
    observed_on: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=2000)
    measured_values: dict[str, float] = Field(default_factory=dict, max_length=20)
    evidence: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def attributed(self):
        if self.status != "unconfirmed" and not (
            self.operator.strip() and self.observed_on.strip() and self.note.strip()
        ):
            raise ValueError("観察結果には担当、日付、観察内容が必要です。")
        if any(len(k) > 80 or not math.isfinite(v) for k, v in self.measured_values.items()):
            raise ValueError("測定名と有限の測定値を入力してください。")
        return self


def assembly_assessment(spec):
    """Simple geometric rejection, not a dexterous-hand or contact-force simulation."""
    g, e = spec.geometry, spec.equipment
    c = parameters(PrintRequest(design=spec.design, geometry=g))
    gap = 2 * (g.body_diameter_mm / 2 + c["fin"]["root_web"]) * math.sin(math.pi / g.fin_count)
    gap -= g.fin_thickness_mm
    checks = []

    def check(key, label, available, needed, assumption):
        checks.append(
            dict(
                id=key,
                label=label,
                available=available,
                required=needed,
                status="not_evaluated"
                if needed is None
                else "screen_pass"
                if available >= needed
                else "interference",
                unit="N" if key == "force" else "mm",
                assumption=assumption,
            )
        )

    check(
        "strap_width",
        "固定材のスロット通過幅",
        c["fin"]["slot_width"],
        e.strap_width_mm,
        "CADの公称寸法比較。印刷誤差と曲げは未評価",
    )
    check(
        "strap_thickness",
        "固定材のスロット通過厚さ",
        c["fin"]["slot_height"],
        e.strap_thickness_mm,
        "スロットの公称高さ。進入・離脱は同じ逆経路",
    )
    tool = None if e.tool_radius_mm is None else 2 * e.tool_radius_mm
    check(
        "tool_access",
        "隣接フィン間の工具包絡",
        gap,
        tool,
        "等配フィン間の直線通路。固定材・指の関節を省略した保守的幅比較",
    )
    hand = (
        None
        if e.hand_width_mm is None or e.glove_allowance_mm is None
        else (e.hand_width_mm + 2 * e.glove_allowance_mm)
    )
    check(
        "hand_access",
        "手袋を含む作業包絡",
        gap,
        hand,
        "入力した手幅の剛体包絡。個人の作業能力を示さない",
    )
    check(
        "workbench",
        "仮組みの作業台幅",
        e.workbench_clear_width_mm or 0,
        None if e.workbench_clear_width_mm is None else g.body_diameter_mm + 2 * g.fin_span_mm,
        "横置き機体の投影幅。保持具と周辺部品は現物確認",
    )
    check(
        "force",
        "保持・操作力",
        e.allowable_force_n or 0,
        e.required_force_n if e.allowable_force_n is not None else None,
        "入力した測定値の比較。接着・締結強度の保証ではない",
    )
    radius = g.body_diameter_mm / 2
    reach = radius + g.fin_span_mm + (hand or tool or 0) / 2 + 20
    paths = []
    for i in range(g.fin_count if spec.design.has_fins else 0):
        angle = (i + 0.5) * 2 * math.pi / g.fin_count

        def point(r, angle=angle):
            return [
                r * math.cos(angle),
                r * math.sin(angle),
                g.fin_tail_inset_mm + 0.5 * g.fin_root_mm,
            ]

        entry = [point(reach), point(radius + c["fin"]["root_web"])]
        paths.append(
            dict(
                id=f"fin_gap_{i + 1}",
                approach_mm=entry,
                retreat_mm=list(reversed(entry)),
                scope="straight rigid-envelope access",
            )
        )
    return dict(
        schema_version=1,
        checks=checks,
        paths=paths,
        cad_parameters=c,
        observation_status="unconfirmed",
        holding="record_required",
        visibility="record_required",
        disassembly="record_required",
        approximation=(
            "nominal dimensions and straight rigid envelopes; "
            "no articulated hand/contact simulation"
        ),
        physical_qualification=False,
    )
