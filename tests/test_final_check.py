"""Tests for the code's own check of the final answer (no network)."""

from rocketwright.agent.final_check import check_design, split_checked_designs

SIM = {
    "source_id": "toolu_sim",
    "success": True,
    "metrics": {"apogee_m": 20.82259043340413, "max_speed_mps": 23.08},
    "cost_jpy": 1000.0,
}
PARTS = {"source_id": "toolu_parts", "sim": {**SIM, "source_id": None}}
DISPERSION = {
    "source_id": "toolu_disp",
    "success_rate": 0.9,
    "quantiles": {"apogee_m": {"p05": 19.04, "p50": 20.8, "p95": 22.66}},
}
RESULTS = [SIM, PARTS, DISPERSION]


def _row(**changes) -> dict:
    row = {
        "metrics": {"apogee_m": 20.82259043340413},
        "passed": True,
        "cost_jpy": 1000.0,
        "success_rate": 0.9,
        "sources": {
            "apogee_m": "toolu_sim",
            "cost_jpy": "toolu_sim",
            "success_rate": "toolu_disp",
        },
    }
    return {**row, **changes}


def test_a_row_copied_from_its_results_has_no_problems():
    assert check_design(_row(), RESULTS) == []


def test_a_rounded_value_still_matches_its_source():
    assert check_design(_row(metrics={"apogee_m": 20.8}), RESULTS) == []


def test_a_metric_named_by_the_model_matches_any_number_of_its_source():
    row = _row(
        metrics={"apogee_m": 20.82259043340413, "apogee_p05_m": 19.04},
        sources={**_row()["sources"], "apogee_p05_m": "toolu_disp"},
    )

    assert check_design(row, RESULTS) == []


def test_a_metric_without_its_own_source_is_read_against_the_row_s_other_sources():
    assert check_design(_row(metrics={"max_speed_mps": 23.08}), RESULTS) == []


def test_a_source_that_does_not_exist_is_a_problem():
    row = _row(sources={**_row()["sources"], "apogee_m": "toolu_made_up"})

    assert any("toolu_made_up" in problem for problem in check_design(row, RESULTS))


def test_a_row_without_sources_is_a_problem():
    assert check_design(_row(sources={}), RESULTS)


def test_a_number_that_differs_from_its_source_is_a_problem():
    problems = check_design(_row(metrics={"apogee_m": 30.1}), RESULTS)

    assert any("apogee_m" in problem for problem in problems)


def test_a_cost_or_success_rate_that_differs_is_a_problem():
    assert check_design(_row(cost_jpy=500.0), RESULTS)
    assert check_design(_row(success_rate=0.99), RESULTS)


def test_a_number_a_thousand_times_off_or_near_a_round_value_is_a_problem():
    assert check_design(_row(metrics={"apogee_m": 20822.59043340413}), RESULTS)
    assert check_design(_row(cost_jpy=1040), RESULTS)


def test_passed_must_agree_with_the_simulation():
    failed = {**SIM, "success": False}

    assert check_design(_row(), [failed, DISPERSION])
    assert check_design(_row(passed=False), RESULTS)
    assert check_design(_row(passed=False), [failed, DISPERSION]) == []


def test_passed_is_read_from_a_parts_result_too():
    row = _row(sources={"apogee_m": "toolu_parts", "cost_jpy": "toolu_parts"}, success_rate=None)

    assert check_design(row, RESULTS) == []


def test_a_pass_with_no_simulation_cited_is_a_problem():
    row = _row(metrics={}, cost_jpy=None, sources={"success_rate": "toolu_disp"})

    assert check_design(row, RESULTS)


def test_split_moves_only_the_rows_with_problems():
    good = _row()
    bad = _row(metrics={"apogee_m": 30.1})

    checked, rejected = split_checked_designs({"designs": [good, bad], "summary": "s"}, RESULTS)

    assert checked["designs"] == [good]
    assert checked["summary"] == "s"
    assert len(checked["rejected_by_check"]) == 1
    assert checked["rejected_by_check"][0]["passed"] is False
    assert checked["rejected_by_check"][0]["check_problems"]
    assert rejected == [{"index": 1, "problems": checked["rejected_by_check"][0]["check_problems"]}]


def test_split_returns_the_input_when_nothing_is_wrong():
    final = {"designs": [_row()]}

    assert split_checked_designs(final, RESULTS) == (final, [])
    assert split_checked_designs({"summary": "no designs"}, RESULTS)[1] == []
