"""Tests for rocketwright.report: Markdown / JSON reports and the BOM CSV."""

import csv
import io
import json

import pytest

from rocketwright.report import (
    display_quantity,
    export_bom_csv,
    export_report_json,
    export_report_markdown,
)
from rocketwright.schema import (
    DispersionResult,
    Ellipse95,
    GoalKind,
    LandingScatter,
    OrbitInsertionStats,
    Quantiles,
    Requirement,
    SimResult,
    Tier,
)
from tests.test_drawing import AMATEUR, BOTTLE, COMMERCIAL, HEAVY

REQ_ALT = Requirement(
    goal_kind=GoalKind.ALTITUDE,
    target_altitude_m=1500.0,
    payload_mass_kg=0.5,
    budget_jpy=80_000,
    recovery_required=True,
    text="1.5 km with a 500 g payload",
)
REQ_ORBIT = Requirement(
    goal_kind=GoalKind.ORBIT,
    target_altitude_m=500_000.0,
    payload_mass_kg=150.0,
    text="150 kg to 500 km",
)

AMATEUR_RESULT = SimResult(
    tier=Tier.AMATEUR,
    success=False,
    failure_reasons=["apogee 1200.0 m outside +-10% of target 1500.0 m"],
    metrics={
        "apogee_m": 1200.0,
        "max_speed_mps": 150.2,
        "stability_margin_cal": 1.8,
        "descent_speed_mps": 4.5,
    },
    cost_jpy=45_000.0,
    warnings=["DUMMY PHYSICS: values are placeholders"],
    source_id="toolu_sim_1",
)

COMMERCIAL_RESULT = SimResult(
    tier=Tier.COMMERCIAL,
    success=True,
    metrics={"perigee_m": 505_000.0, "apogee_m": 520_000.0, "payload_margin_kg": 12.0},
    cost_jpy=1.2e9,
    source_id="toolu_sim_2",
)

AMATEUR_DISPERSION = DispersionResult(
    tier=Tier.AMATEUR,
    n=100,
    seed=7,
    success_rate=0.87,
    quantiles={"apogee_m": Quantiles(p05=1100.0, p50=1200.0, p95=1300.0)},
    failure_counts={"apogee outside tolerance": 13},
    landing=LandingScatter(
        points=[],
        ellipse_95=Ellipse95(
            center_east_m=10.0,
            center_north_m=-5.0,
            semi_major_m=50.0,
            semi_minor_m=30.0,
            angle_deg=0.0,
        ),
    ),
    source_id="toolu_disp_1",
)

COMMERCIAL_DISPERSION = DispersionResult(
    tier=Tier.COMMERCIAL,
    n=50,
    seed=1,
    success_rate=0.9,
    quantiles={"perigee_m": Quantiles(p05=480_000.0, p50=505_000.0, p95=530_000.0)},
    orbit_insertion=OrbitInsertionStats(
        perigee_error_m=Quantiles(p05=-8000.0, p50=0.0, p95=8000.0),
        apogee_error_m=Quantiles(p05=-13_000.0, p50=0.0, p95=13_000.0),
        payload_margin_kg=Quantiles(p05=5.0, p50=12.0, p95=20.0),
    ),
    source_id="toolu_disp_2",
)


def _bottle_result(success: bool) -> SimResult:
    return SimResult(
        tier=Tier.BOTTLE,
        success=success,
        failure_reasons=[] if success else ["descent speed 9.00 m/s above 6.0 m/s"],
        metrics={"apogee_m": 32.5, "descent_speed_mps": 9.0},
        cost_jpy=2300.0,
        source_id="toolu_sim_b",
    )


# --------------------------------------------------------------------------- display units


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("apogee_m", 1200.0, "1.20 km"),
        ("body_length_m", 1.2, "1.20 m"),
        ("nose_length_m", 0.3, "300 mm"),
        ("body_diameter_m", 0.08, "80 mm"),
        ("perigee_m", 505_000.0, "505.00 km"),
        ("dry_mass_kg", 0.5, "500 g"),
        ("payload_mass_kg", 150.0, "150.0 kg"),
        ("initial_gauge_pressure_pa", 500_000.0, "500 kPa"),
        ("cost_jpy", 45_000.0, "4.5 万円"),
        ("cost_jpy", 2300.0, "2,300 円"),
        ("water_fill_frac", 0.35, "35 %"),
        ("max_speed_mps", 150.2, "150.2 m/s"),
        ("stability_margin_cal", 1.8, "1.80 cal"),
        ("bottle_volume_m3", 0.0015, "1.50 L"),
        ("engine_count", 9, "9"),
    ],
)
def test_display_quantity(key, value, expected):
    assert display_quantity(key, value) == expected


# --------------------------------------------------------------------------- markdown


def test_markdown_amateur_has_tier_metrics_sources_and_failures():
    md = export_report_markdown(
        AMATEUR, AMATEUR_RESULT, requirement=REQ_ALT, dispersion=AMATEUR_DISPERSION
    )
    assert "amateur" in md
    assert "アマチュア" in md
    assert "1.20 km" in md and "toolu_sim_1" in md
    assert "apogee 1200.0 m outside" in md
    assert "FAIL" in md
    assert "DUMMY PHYSICS" in md
    assert "87.0 %" in md and "toolu_disp_1" in md
    assert "p05" in md and "p95" in md
    assert "Checklist" in md and "not legal advice" in md
    assert "dummy-H128" in md
    assert "1.5 km with a 500 g payload" in md
    assert "README" in md
    assert "not for manufacturing" not in md


def test_markdown_commercial_is_concept_level():
    md = export_report_markdown(
        COMMERCIAL, COMMERCIAL_RESULT, requirement=REQ_ORBIT, dispersion=COMMERCIAL_DISPERSION
    )
    assert "commercial" in md and "企業級" in md
    assert "not for manufacturing" in md
    assert "PASS" in md
    assert "505.00 km" in md and "toolu_sim_2" in md
    assert "rutherford" in md
    assert "perigee_error_m" in md
    assert "Checklist" in md


def test_markdown_sources_override_and_heavy():
    md = export_report_markdown(HEAVY, COMMERCIAL_RESULT, sources={"perigee_m": "toolu_override"})
    assert "toolu_override" in md
    assert "heavy" in md and "重工級" in md
    assert "gem_63" in md


def test_markdown_bottle_without_requirement():
    md = export_report_markdown(BOTTLE, _bottle_result(True))
    assert "bottle" in md and "ペットボトル" in md
    assert "32.50 m" in md
    assert "Checklist" in md


# --------------------------------------------------------------------------- json


@pytest.mark.parametrize(
    "design,result,req,disp",
    [
        (AMATEUR, AMATEUR_RESULT, REQ_ALT, AMATEUR_DISPERSION),
        (BOTTLE, _bottle_result(False), None, None),
        (COMMERCIAL, COMMERCIAL_RESULT, REQ_ORBIT, COMMERCIAL_DISPERSION),
        (HEAVY, COMMERCIAL_RESULT, None, None),
    ],
    ids=["amateur", "bottle", "commercial", "heavy"],
)
def test_json_round_trips(design, result, req, disp):
    data = export_report_json(design, result, requirement=req, dispersion=disp)
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    assert json.loads(text) == data
    assert data["tier"] == design.tier
    assert data["design"]["tier"] == design.tier
    assert data["passed"] == result.success
    assert data["failure_reasons"] == result.failure_reasons
    for m in data["metrics"]:
        assert m["source_id"] == result.source_id
        assert "display" in m and "value" in m
    assert isinstance(data["checklist"], list) and data["checklist"]
    if disp is not None:
        assert data["dispersion"]["success_rate"] == disp.success_rate
        assert data["dispersion"]["source_id"] == disp.source_id
    else:
        assert data["dispersion"] is None
    if req is not None:
        assert data["requirement"]["goal_kind"] == req.goal_kind.value
    assert data["concept_level"] == (design.tier in ("commercial", "heavy"))


# --------------------------------------------------------------------------- bom


HEADER = ["item_id", "name", "qty", "mass_kg", "price_jpy", "source_or_provisional"]


@pytest.mark.parametrize("design", [AMATEUR, BOTTLE, COMMERCIAL, HEAVY], ids=lambda d: d.tier)
def test_bom_csv_parses_with_header_and_rows(design):
    text = export_bom_csv(design)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == HEADER
    body = rows[1:]
    assert len(body) >= 3
    for row in body:
        assert len(row) == len(HEADER)
        assert row[0] and row[1]
        assert int(row[2]) >= 1
        if row[3]:
            assert float(row[3]) >= 0
        assert row[5]
    assert export_bom_csv(design) == text  # deterministic


def test_bom_amateur_rows():
    rows = list(csv.DictReader(io.StringIO(export_bom_csv(AMATEUR))))
    ids = [r["item_id"] for r in rows]
    # rows come from catalog/parts.yaml when a part matches (ids like nose_cone_54mm_ogive),
    # else the generic fallback id
    for expected in ("nose", "tube", "fin", "motor", "parachute", "payload"):
        assert any(expected in i for i in ids), (expected, ids)
    fins = next(r for r in rows if "fin" in r["item_id"])
    assert fins["qty"] == "4"
    motor = next(r for r in rows if r["item_id"] == "motor")
    assert "dummy-H128" in motor["name"]


def test_bom_bottle_rows():
    rows = list(csv.DictReader(io.StringIO(export_bom_csv(BOTTLE))))
    ids = [r["item_id"] for r in rows]
    for expected in ("bottle", "nozzle", "fin", "parachute", "payload"):
        assert any(expected in i for i in ids), (expected, ids)
    no_chute = BOTTLE.model_copy(update={"has_parachute": False, "parachute_diameter_m": None})
    ids2 = [r["item_id"] for r in csv.DictReader(io.StringIO(export_bom_csv(no_chute)))]
    assert not any("parachute" in i for i in ids2)


def test_bom_multistage_is_concept_level():
    rows = list(csv.DictReader(io.StringIO(export_bom_csv(HEAVY))))
    ids = [r["item_id"] for r in rows]
    assert "stage1_structure" in ids and "stage1_propellant" in ids and "stage1_engines" in ids
    assert "boosters" in ids and "fairing" in ids and "payload" in ids
    engines = next(r for r in rows if r["item_id"] == "stage1_engines")
    assert engines["qty"] == "9"
    assert engines["price_jpy"] == ""
    assert all(
        "concept" in r["source_or_provisional"]
        for r in rows
        if r["item_id"] not in ("cost_estimate", "payload")
    )
    assert any(r["item_id"] == "cost_estimate" and r["price_jpy"] for r in rows)


def test_bottle_bom_names_the_parts_of_this_design_only():
    small = BOTTLE.model_copy(
        update={
            "bottle_volume_m3": 0.0005,
            "nozzle_diameter_m": 0.015,
            "has_parachute": True,
            "parachute_diameter_m": 0.5,
        }
    )
    rows = list(csv.DictReader(io.StringIO(export_bom_csv(small))))
    text = " ".join(r["name"] for r in rows)
    assert "500 mL" in text and "15 mm" in text and "50 cm" in text
    # No part the design does not say it uses: fins stay unnamed without a parts build.
    assert "1.5 L" not in text and "段ボール" not in text and "corrugated" not in text


def test_bottle_bom_keeps_a_size_the_catalog_does_not_have():
    odd = BOTTLE.model_copy(update={"bottle_volume_m3": 0.0007})
    rows = list(csv.DictReader(io.StringIO(export_bom_csv(odd))))
    assert any("0.70 L" in r["name"] and r["price_jpy"] == "" for r in rows), rows
