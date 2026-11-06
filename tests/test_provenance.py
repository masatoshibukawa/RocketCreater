"""Tests for the unsourced-number check applied to the agent's final explanation."""

import pytest

from rocketwright.agent.provenance import extract_numbers, find_unsourced_numbers

RESULTS = [
    {
        "source_id": "toolu_01",
        "tier": "amateur",
        "metrics": {"apogee_m": 2468.0, "max_speed_mps": 187.3, "stability_margin_cal": 1.82},
        "cost_jpy": 48500,
        "success": True,
    },
    {
        "source_id": "toolu_02",
        "n": 100,
        "success_rate": 0.95,
        "quantiles": {"apogee_m": {"p50": 2440.0}},
    },
]


def test_sourced_numbers_pass():
    text = "Apogee 2468 m, max speed 187.3 m/s, stability 1.82 cal, cost 48,500 JPY."
    assert find_unsourced_numbers(text, RESULTS) == []


def test_rounded_km_matches_metres():
    assert find_unsourced_numbers("Reaches about 2.47 km.", RESULTS) == []
    assert find_unsourced_numbers("Reaches about 2.5km.", RESULTS) == []


def test_percent_matches_fraction():
    assert find_unsourced_numbers("Success rate 95% over 100 runs.", RESULTS) == []


def test_invented_number_fails():
    bad = find_unsourced_numbers("Apogee 3100 m and cost 48,500 JPY.", RESULTS)
    assert bad == ["3100 m"]


def test_small_counts_years_and_ids_are_ignored():
    text = "Design 2 of 3 (2026) uses 4 fins; see toolu_01 and attempt #7."
    assert find_unsourced_numbers(text, RESULTS) == []


def test_scientific_notation_and_thousands():
    assert find_unsourced_numbers("1.873e2 m/s and 2,468 m", RESULTS) == []


def test_extract_numbers_handles_units():
    found = extract_numbers("2.47 km, 95%, 1,234.5 kg, 1.2e3 m")
    values = {n.text: (n.value, n.unit) for n in found}
    assert values["2.47 km"] == (2.47, "km")
    assert values["95%"] == (95.0, "%")
    assert values["1,234.5 kg"] == (1234.5, "kg")
    assert values["1.2e3 m"] == (1200.0, "m")


def test_numbers_quoted_from_tool_text_are_sourced():
    """design_stage `why` strings and buildability messages are code-written text: a number
    quoted from them (with its unit or tolerance) is sourced, an invented one still is not."""
    results = [
        {
            "candidates": [
                {
                    "option": "motor_mount_38mm_98",
                    "why": "motor_mount_38mm_98: 38 mm motor, 356 mm: apogee 941 m (target "
                    "2,000 m +-10%), 2.1 cal, 34,720 JPY; fails: apogee off target",
                    "metrics": {"apogee_m": 941.2},
                }
            ]
        }
    ]
    quoted = "The 98 mm option (38 mm motor, 356 mm mount) fails: 941 m vs 2,000 m +-10%."
    assert find_unsourced_numbers(quoted.replace("98 mm option", "option"), results) == []
    assert find_unsourced_numbers("It needs 4,400 mm of tube.", results) == ["4,400"]


# --- Japanese prose (2026-11-07 audit: numbers glued to Japanese text used to be skipped)

JA_RESULTS = [
    {
        "metrics": {"apogee_m": 9999.0, "perigee_m": -2911442.95},
        "cost_jpy": 130479000.0,
        "success_rate": 0.873,
        "env": {"launch_latitude_deg": -39.26},
        "failure_counts": {"max_q": 28},
    }
]


@pytest.mark.parametrize(
    "text",
    [
        "高度9999mです",
        "費用は約1.3億円",
        "成功率は87.3%です",
        "不合格は28件",
        "近地点も \u22122911 km でした",
        "近地点も -2911 km でした",
        "打上げ地点は南緯 39.26° です",
    ],
)
def test_japanese_prose_numbers_that_come_from_results_pass(text):
    assert find_unsourced_numbers(text, JA_RESULTS) == []


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("高度8888mです", ["8888m"]),
        ("費用は約2.4億円", ["2.4億円"]),
        ("成功率は99.9%です", ["99.9%"]),
        ("不合格は52件", ["52"]),
    ],
)
def test_japanese_prose_numbers_without_a_source_are_flagged(text, flagged):
    assert find_unsourced_numbers(text, JA_RESULTS) == flagged


@pytest.mark.parametrize("text", ["toolu_01AB23", "H3 ロケット", "3U の衛星", "1.5L のボトル"])
def test_identifiers_are_still_not_numbers(text):
    assert extract_numbers(text) == []
