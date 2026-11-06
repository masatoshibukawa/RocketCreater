"""Requirement checks shared by persistence, calculation and exported prototype records."""

import math

from rocketwright.agent.project_equipment import procurement_summary


def validate_requirements(spec):
    req = spec.requirement
    if req is None:
        return
    if not math.isclose(req.payload_mass_kg, spec.design.payload_mass_kg, abs_tol=1e-9):
        raise ValueError("要求の搭載質量と計算する搭載質量を同じ値にしてください。")
    if req.recovery_required and not spec.design.has_parachute:
        raise ValueError("回収を要求した案件には回収装置の入力が必要です。")


def assess_requirements(spec, result):
    validate_requirements(spec)
    req = spec.requirement
    rows = [
        dict(
            id="flight",
            label="飛行の数値スクリーニング",
            status="pass" if result.success else "fail",
            reason="保存した質量・環境・目標で計算",
            observed=result.metrics,
        )
    ]
    if req:
        observed = result.metrics["apogee_m"]
        passed = (
            observed >= req.target_altitude_m
            if spec.altitude_rule == "minimum"
            else abs(observed - req.target_altitude_m) <= 0.1 * req.target_altitude_m
        )
        rows.append(
            dict(
                id="altitude_goal",
                label="高度の要求",
                status="pass" if passed else "fail",
                required=req.target_altitude_m,
                observed=observed,
                unit="m",
                reason="指定した最低高度で判定"
                if spec.altitude_rule == "minimum"
                else "目標の±10%以内で判定",
            )
        )
    rows.append(
        dict(
            id="payload",
            label="搭載質量",
            status="pass",
            unit="kg",
            required=req.payload_mass_kg if req else None,
            observed=spec.design.payload_mass_kg,
            reason="要求と計算入力を照合済み",
        )
    )
    rows.append(
        dict(
            id="recovery",
            label="回収の入力",
            status="pass" if req and req.recovery_required else "not_required",
            observed=spec.design.has_parachute,
            reason="装置の入力と降下計算を確認。実際の開傘・保持は別の検証",
        )
    )
    cost = procurement_summary(spec)
    budget_status = "not_required"
    if req and req.budget_jpy:
        budget_status = (
            "not_evaluated"
            if cost["total_jpy"] is None
            else ("pass" if cost["total_jpy"] <= req.budget_jpy else "fail")
        )
    rows.append(
        dict(
            id="budget",
            label="予算",
            status=budget_status,
            required=req.budget_jpy if req else None,
            observed=cost["total_jpy"],
            unit="JPY",
            reason=("数量・価格根拠・確認日が不足: " + ", ".join(cost["missing_or_unconfirmed"]))
            if cost["missing_or_unconfirmed"]
            else "全部材・固定材・その他費用の入力済み調達記録で比較",
        )
    )
    if req is None or req.target_altitude_m is None:
        rows.append(
            dict(
                id="altitude_target",
                label="高度の要求",
                status="not_evaluated",
                reason="目標高度は未指定。飛行計算の成功を要求達成とは扱いません",
            )
        )
    return dict(
        scope="prototype_screening",
        checks=rows,
        all_requirements_passed=all(r["status"] in {"pass", "not_required"} for r in rows),
        physical_validation="not_performed",
    )
