"""Tests for cost.cost_breakdown, report.bom_rows and summary.design_summary (the payload of
POST /artifacts/summary)."""

import csv
import io
import json

import pytest

from rocketwright.cost import CostItem, cost_breakdown, estimate_cost_jpy, liftoff_mass_kg
from rocketwright.report import BOM_COLUMNS, bom_rows, export_bom_csv
from rocketwright.schema import UNIT_SUFFIXES, GoalKind, Requirement, Tier
from rocketwright.summary import design_summary
from tests.test_drawing import AMATEUR, BOTTLE, COMMERCIAL, HEAVY

ALL = [AMATEUR, BOTTLE, COMMERCIAL, HEAVY]
IDS = [d.tier for d in ALL]

# --------------------------------------------------------------------------- cost_breakdown


@pytest.mark.parametrize("design", ALL, ids=IDS)
def test_breakdown_sums_to_estimate(design):
    items = cost_breakdown(design)
    assert items and all(isinstance(i, CostItem) for i in items)
    assert sum(i.jpy for i in items) == pytest.approx(estimate_cost_jpy(design), rel=1e-12)
    for item in items:
        assert item.label and item.note
        assert item.jpy > 0
        assert item.provisional is True  # every COST_CONSTANTS entry is provisional today
        assert "円" in item.note


def test_breakdown_bottle_items_follow_options():
    labels = [i.label for i in cost_breakdown(BOTTLE)]
    assert any("ボトル" in label for label in labels)
    assert any("パラシュート" in label for label in labels)
    no_chute = BOTTLE.model_copy(update={"has_parachute": False, "parachute_diameter_m": None})
    labels2 = [i.label for i in cost_breakdown(no_chute)]
    assert not any("パラシュート" in label for label in labels2)
    assert sum(i.jpy for i in cost_breakdown(no_chute)) == pytest.approx(
        estimate_cost_jpy(no_chute)
    )


def test_breakdown_amateur_labels_and_notes():
    items = {i.label: i for i in cost_breakdown(AMATEUR)}
    for key in ("機体", "フィン", "モーター", "パラシュート", "電子機器"):
        assert any(key in label for label in items), (key, list(items))
    airframe = next(i for label, i in items.items() if label.startswith("機体"))
    assert airframe.jpy == pytest.approx(12000.0 * AMATEUR.dry_mass_kg)
    assert "12,000 円/kg" in airframe.note and "1.2 kg" in airframe.note
    fins = next(i for label, i in items.items() if label.startswith("フィン"))
    assert fins.jpy == pytest.approx(500.0 * 4)
    assert "× 4" in fins.note


def test_breakdown_multistage_splits_by_mass():
    items = cost_breakdown(HEAVY)
    labels = [i.label for i in items]
    assert any("第1段" in label for label in labels)
    assert any("第2段" in label for label in labels)
    assert any("フェアリング" in label for label in labels)
    assert any("ブースタ" in label for label in labels)
    assert all("25,000 円/kg" in i.note for i in items)
    # the stage item is per-kg price x (propellant + structure) of that stage
    s1 = HEAVY.stages[0]
    stage_mass = s1.propellant_mass_kg / (1.0 - s1.structural_fraction)
    stage1 = next(i for i in items if "第1段" in i.label)
    assert stage1.jpy == pytest.approx(25000.0 * stage_mass, rel=1e-9)
    assert sum(i.jpy for i in items) == pytest.approx(25000.0 * liftoff_mass_kg(HEAVY), rel=1e-12)
    # commercial: no booster row
    assert not any("ブースタ" in i.label for i in cost_breakdown(COMMERCIAL))


# --------------------------------------------------------------------------- bom_rows


@pytest.mark.parametrize("design", ALL, ids=IDS)
def test_bom_rows_match_csv(design):
    rows = bom_rows(design)
    assert len(rows) >= 3
    csv_rows = list(csv.DictReader(io.StringIO(export_bom_csv(design))))
    assert len(rows) == len(csv_rows)
    for row, csv_row in zip(rows, csv_rows, strict=True):
        assert tuple(row) == BOM_COLUMNS
        assert isinstance(row["qty"], int) and row["qty"] >= 1
        assert row["mass_kg"] is None or isinstance(row["mass_kg"], float)
        assert row["price_jpy"] is None or isinstance(row["price_jpy"], float)
        assert row["item_id"] == csv_row["item_id"]
        assert row["name"] == csv_row["name"]
        assert str(row["qty"]) == csv_row["qty"]
        assert (csv_row["mass_kg"] == "") == (row["mass_kg"] is None)
        assert (csv_row["price_jpy"] == "") == (row["price_jpy"] is None)
        assert row["source_or_provisional"] == csv_row["source_or_provisional"]
    json.dumps(rows)  # JSON-serialisable


# --------------------------------------------------------------------------- design_summary


def _unit_keys_ok(d: dict) -> None:
    for k in d:
        assert k.endswith(UNIT_SUFFIXES), k


@pytest.mark.parametrize("design", ALL, ids=IDS)
def test_summary_shape_mass_and_dimensions(design):
    out = design_summary(design)
    assert out["tier"] == design.tier
    assert out["cost_jpy"] == pytest.approx(estimate_cost_jpy(design))
    assert sum(i["jpy"] for i in out["cost_breakdown"]) == pytest.approx(out["cost_jpy"], rel=1e-12)
    assert set(out["cost_breakdown"][0]) == {"label", "jpy", "note", "provisional"}
    assert len(out["bom"]) >= 3 and tuple(out["bom"][0]) == BOM_COLUMNS
    assert out["drawing"] is None

    mass = out["mass"]
    _unit_keys_ok(mass)
    for key in ("liftoff_mass_kg", "dry_mass_kg", "payload_mass_kg", "propellant_mass_kg"):
        assert key in mass
        assert mass[key] >= 0
    assert mass["liftoff_mass_kg"] > 0 and mass["dry_mass_kg"] > 0
    assert mass["liftoff_mass_kg"] >= (
        mass["dry_mass_kg"] + mass["payload_mass_kg"] + mass["propellant_mass_kg"] - 1e-9
    )

    dims = out["dimensions"]
    _unit_keys_ok(dims)
    assert dims["length_m"] > 0 and dims["diameter_m"] > 0
    assert dims["length_m"] > dims["diameter_m"]
    json.dumps(out)


def test_summary_amateur_mass_and_length():
    out = design_summary(AMATEUR)
    dims = out["dimensions"]
    assert dims["length_m"] == pytest.approx(AMATEUR.nose_length_m + AMATEUR.body_length_m)
    assert dims["diameter_m"] == pytest.approx(AMATEUR.body_diameter_m)
    mass = out["mass"]
    assert mass["dry_mass_kg"] == pytest.approx(AMATEUR.dry_mass_kg)
    assert mass["payload_mass_kg"] == pytest.approx(AMATEUR.payload_mass_kg)
    # dummy-H128 is not a catalog id: the motor is unknown, the summary says so and keeps going
    assert mass["propellant_mass_kg"] == 0.0
    assert any("dummy-H128" in w for w in out["warnings"])

    from rocketwright.physics.solid import load_motor

    known = AMATEUR.model_copy(update={"motor_id": "dummy_H128"})
    motor = load_motor("dummy_H128")
    m2 = design_summary(known)["mass"]
    assert m2["propellant_mass_kg"] == pytest.approx(motor.propellant_mass_kg)
    assert m2["motor_mass_kg"] == pytest.approx(motor.total_mass_kg)
    assert m2["liftoff_mass_kg"] == pytest.approx(
        known.dry_mass_kg + known.payload_mass_kg + motor.total_mass_kg
    )
    assert design_summary(known)["warnings"] == []


def test_summary_bottle_water_and_dimensions():
    from rocketwright.drawing import BOTTLE_ASPECT_RATIO
    from rocketwright.physics.water import bottle_diameter_m

    out = design_summary(BOTTLE)
    mass = out["mass"]
    water = BOTTLE.water_fill_frac * BOTTLE.bottle_volume_m3 * 1000.0
    assert mass["propellant_mass_kg"] == pytest.approx(water)
    assert mass["liftoff_mass_kg"] == pytest.approx(
        BOTTLE.dry_mass_kg + BOTTLE.payload_mass_kg + water
    )
    d = bottle_diameter_m(BOTTLE.bottle_volume_m3)
    assert out["dimensions"]["diameter_m"] == pytest.approx(d)
    assert out["dimensions"]["length_m"] > BOTTLE_ASPECT_RATIO * d


def test_summary_multistage_mass_and_dimensions():
    out = design_summary(HEAVY)
    mass = out["mass"]
    assert mass["liftoff_mass_kg"] == pytest.approx(liftoff_mass_kg(HEAVY))
    assert mass["propellant_mass_kg"] == pytest.approx(
        sum(s.propellant_mass_kg for s in HEAVY.stages)
    )
    assert mass["liftoff_mass_kg"] == pytest.approx(
        mass["dry_mass_kg"] + mass["payload_mass_kg"] + mass["propellant_mass_kg"]
    )
    assert mass["booster_mass_kg"] > 0
    dims = out["dimensions"]
    assert dims["length_m"] > 10.0 and 1.0 < dims["diameter_m"] < 10.0


def test_summary_requirement_tier_mismatch_raises():
    req = Requirement(
        goal_kind=GoalKind.ALTITUDE,
        target_altitude_m=50.0,
        tier_override=Tier.BOTTLE,
    )
    with pytest.raises(ValueError, match="tier"):
        design_summary(AMATEUR, req)
    ok = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=1500.0)
    assert design_summary(AMATEUR, ok)["tier"] == "amateur"
