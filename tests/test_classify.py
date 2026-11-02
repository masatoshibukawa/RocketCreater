"""Tests for rule-based tier classification (CLAUDE.md section 3)."""

from rocketwright.classify import ClassifyResult, classify, load_tiers
from rocketwright.schema import GoalKind, Requirement, Tier


def test_tiers_config_entries_have_source_or_provisional():
    cfg = load_tiers()
    for tier_id, tier in cfg["tiers"].items():
        for key, entry in tier.items():
            if key == "notes":
                continue
            assert "value" in entry, (tier_id, key)
            assert entry.get("provisional") or entry.get("source"), (tier_id, key)


def test_altitude_50m_is_bottle():
    res = classify(Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50))
    assert isinstance(res, ClassifyResult)
    assert res.tier is Tier.BOTTLE
    assert res.required_tier is Tier.BOTTLE
    assert res.fallback is None
    assert res.warnings == []


def test_2km_and_1kg_is_amateur():
    res = classify(
        Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=2000, payload_mass_kg=1.0)
    )
    assert res.tier is Tier.AMATEUR
    assert res.required_tier is Tier.AMATEUR


def test_orbit_is_at_least_commercial():
    res = classify(
        Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=400_000, payload_mass_kg=150)
    )
    assert res.tier in (Tier.COMMERCIAL, Tier.HEAVY)
    assert res.tier is Tier.COMMERCIAL
    assert any("orbit" in r for r in res.reasons)


def test_heavy_payload_orbit_is_heavy():
    res = classify(
        Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=400_000, payload_mass_kg=5000)
    )
    assert res.tier is Tier.HEAVY


def test_payload_raises_tier_even_for_low_altitude():
    # 50 m but a 3 kg payload: bottle cannot lift it, amateur can.
    res = classify(
        Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50, payload_mass_kg=3.0)
    )
    assert res.tier is Tier.AMATEUR


def test_explicit_override_is_honoured_with_warning():
    res = classify(
        Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50, tier_override=Tier.AMATEUR)
    )
    assert res.tier is Tier.AMATEUR
    assert res.required_tier is Tier.BOTTLE
    assert any("override" in w for w in res.warnings)


def test_explicit_override_matching_result_has_no_warning():
    res = classify(
        Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50, tier_override=Tier.BOTTLE)
    )
    assert res.tier is Tier.BOTTLE
    assert res.warnings == []


def test_budget_conflict_returns_required_tier_and_fallback():
    req = Requirement(
        goal_kind=GoalKind.ORBIT,
        target_altitude_m=400_000,
        payload_mass_kg=150,
        budget_jpy=50_000,  # far below commercial.budget_min
        recovery_required=True,
        text="orbit on a shoestring",
    )
    res = classify(req)
    assert res.required_tier is Tier.COMMERCIAL
    assert res.tier is Tier.AMATEUR  # highest tier affordable with 50,000 JPY
    assert res.fallback is not None
    assert res.fallback.goal_kind is GoalKind.ALTITUDE
    assert (
        res.fallback.target_altitude_m
        == load_tiers()["tiers"]["amateur"]["target_altitude_max"]["value"]
    )
    assert res.fallback.target_apogee_m is None
    assert res.fallback.budget_jpy == 50_000
    assert res.fallback.recovery_required is True
    assert res.fallback.text == "orbit on a shoestring"
    assert any("budget" in w for w in res.warnings)


def test_budget_below_every_tier_falls_back_to_bottle():
    res = classify(Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=2000, budget_jpy=500))
    assert res.required_tier is Tier.AMATEUR
    assert res.tier is Tier.BOTTLE
    assert res.fallback is not None
    assert res.fallback.target_altitude_m <= 100


def test_large_budget_never_raises_tier():
    res = classify(Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50, budget_jpy=1e12))
    assert res.tier is Tier.BOTTLE


def test_override_wins_over_budget_fallback_with_warning():
    res = classify(
        Requirement(
            goal_kind=GoalKind.ORBIT,
            target_altitude_m=400_000,
            budget_jpy=50_000,
            tier_override=Tier.COMMERCIAL,
        )
    )
    assert res.tier is Tier.COMMERCIAL
    assert res.required_tier is Tier.COMMERCIAL
    assert any("budget" in w for w in res.warnings)
