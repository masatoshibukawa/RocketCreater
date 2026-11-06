"""Rule-based tier classification of a Requirement (CLAUDE.md section 3).

Boundaries live in config/tiers.yaml (every value carries `source` or `provisional`).
Rules:
  * the tier needed by the target (altitude ceiling; orbit => commercial or above) and the tier
    needed by the payload mass are computed separately and the higher one wins;
  * a budget below the required tier's `budget_min` does NOT change what is required: the result
    carries `required_tier` plus a `fallback` Requirement scaled to the highest affordable tier;
  * an explicit `tier_override` always wins, with a warning when it conflicts.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from rocketwright.schema import GoalKind, Requirement, Tier

__all__ = ["TIER_ORDER", "ClassifyResult", "classify", "load_tiers", "tiers_config_path"]

TIER_ORDER: tuple[Tier, ...] = (Tier.BOTTLE, Tier.AMATEUR, Tier.COMMERCIAL, Tier.HEAVY)
_RANK = {t: i for i, t in enumerate(TIER_ORDER)}


class ClassifyResult(BaseModel):
    """Outcome of classify(). `tier` is the tier the agent should design for right now;
    `required_tier` is what the request actually needs (differs only on budget conflict or
    explicit override); `fallback` is the budget-compatible alternative requirement, if any."""

    model_config = ConfigDict(frozen=True)

    tier: Tier
    required_tier: Tier
    fallback: Requirement | None = None
    warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def tiers_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "tiers.yaml"


@lru_cache(maxsize=1)
def load_tiers() -> dict[str, Any]:
    """Load and cache config/tiers.yaml."""
    with tiers_config_path().open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _limit(tier: Tier, key: str) -> float | None:
    """Numeric limit for a tier, or None when the key is absent or unbounded (null)."""
    entry = load_tiers()["tiers"][tier.value].get(key)
    if entry is None:
        return None
    return entry.get("value")


def _covers(tier: Tier, key: str, value: float) -> bool:
    limit = _limit(tier, key)
    return limit is None or value <= limit


def _lowest_tier_covering(key: str, value: float) -> Tier:
    for tier in TIER_ORDER:
        if _covers(tier, key, value):
            return tier
    return TIER_ORDER[-1]


def _max_tier(a: Tier, b: Tier) -> Tier:
    return a if _RANK[a] >= _RANK[b] else b


def _highest_affordable(budget_jpy: float) -> Tier:
    """Highest tier whose budget_min fits the budget (bottle when nothing fits)."""
    best = TIER_ORDER[0]
    for tier in TIER_ORDER:
        floor = _limit(tier, "budget_min")
        if floor is None or budget_jpy >= floor:
            best = tier
    return best


def _fallback_requirement(req: Requirement, tier: Tier) -> Requirement:
    """Scale the request down to what `tier` can do (altitude goal, capped altitude/payload)."""
    alt_cap = _limit(tier, "target_altitude_max")
    payload_cap = _limit(tier, "payload_mass_max")
    target_altitude_m = req.target_altitude_m
    if req.goal_kind is GoalKind.ORBIT or (alt_cap is not None and target_altitude_m > alt_cap):
        target_altitude_m = alt_cap if alt_cap is not None else target_altitude_m
    payload = req.payload_mass_kg
    if payload_cap is not None and payload > payload_cap:
        payload = payload_cap
    return Requirement(
        goal_kind=GoalKind.ALTITUDE,
        target_altitude_m=target_altitude_m,
        target_apogee_m=None,
        payload_mass_kg=payload,
        budget_jpy=req.budget_jpy,
        recovery_required=req.recovery_required,
        bottle_volume_m3=req.bottle_volume_m3,
        tier_override=tier,
        text=req.text,
    )


def classify(requirement: Requirement) -> ClassifyResult:
    req = requirement
    reasons: list[str] = []
    warnings: list[str] = []

    # --- tier required by the target
    if req.goal_kind is GoalKind.ORBIT:
        by_target = Tier.COMMERCIAL
        reasons.append("orbit goal requires at least tier 'commercial'")
        apogee = req.target_apogee_m if req.target_apogee_m is not None else req.target_altitude_m
        if not _covers(Tier.COMMERCIAL, "target_altitude_max", apogee):
            by_target = Tier.HEAVY
            reasons.append(
                f"orbit apogee {apogee:.0f} m exceeds commercial.target_altitude_max -> 'heavy'"
            )
    else:
        by_target = _lowest_tier_covering("target_altitude_max", req.target_altitude_m)
        reasons.append(
            f"target altitude {req.target_altitude_m:.0f} m -> lowest covering tier "
            f"'{by_target.value}'"
        )

    # --- tier required by the payload mass
    by_payload = _lowest_tier_covering("payload_mass_max", req.payload_mass_kg)
    reasons.append(
        f"payload {req.payload_mass_kg:g} kg -> lowest covering tier '{by_payload.value}'"
    )

    required = _max_tier(by_target, by_payload)
    reasons.append(f"required tier = max(target, payload) = '{required.value}'")

    alt_min = _limit(required, "target_altitude_min")
    if (
        req.goal_kind is GoalKind.ALTITUDE
        and alt_min is not None
        and req.target_altitude_m < alt_min
    ):
        warnings.append(
            f"target altitude {req.target_altitude_m:.0f} m is below the "
            f"'{required.value}' floor of {alt_min:.0f} m; the tier is oversized for the goal"
        )

    # --- budget check: a small budget yields a fallback, a large budget never raises the tier
    tier = required
    fallback: Requirement | None = None
    budget_floor = _limit(required, "budget_min")
    if req.budget_jpy is not None and budget_floor is not None and req.budget_jpy < budget_floor:
        affordable = _highest_affordable(req.budget_jpy)
        warnings.append(
            f"budget {req.budget_jpy:,.0f} JPY is below the '{required.value}' floor of "
            f"{budget_floor:,.0f} JPY (provisional); falling back to '{affordable.value}'"
        )
        tier = affordable
        fallback = _fallback_requirement(req, affordable)
        reasons.append(
            f"fallback: tier '{affordable.value}', altitude goal "
            f"{fallback.target_altitude_m:.0f} m, payload {fallback.payload_mass_kg:g} kg"
        )

    # --- explicit user choice wins
    if req.tier_override is not None and req.tier_override is not tier:
        warnings.append(
            f"tier_override '{req.tier_override.value}' conflicts with computed tier "
            f"'{tier.value}' (required '{required.value}'); honouring the override"
        )
        tier = req.tier_override

    return ClassifyResult(
        tier=tier,
        required_tier=required,
        fallback=fallback,
        warnings=warnings,
        reasons=reasons,
    )
