"""The code's check of the final answer against the tool results it cites.

`designs[]` is written by the model, so nothing in it is taken on trust: every cited source id
must exist, every reported number must be in a cited result, and `passed` must agree with the
simulation. A row that does not hold up leaves `designs` for `rejected_by_check`.

provenance.py reads the prose; this reads the structured rows.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from rocketwright.agent.provenance import collect_result_values

__all__ = ["check_design", "split_checked_designs"]


def _is_in(value: float, results: list[dict[str, Any]]) -> bool:
    """Whether a number, as written and perhaps rounded, is a value of `results`."""
    decimals = max(0, -Decimal(repr(value)).as_tuple().exponent)
    target = abs(value)
    return any(
        math.isclose(abs(round(found, decimals)), target, rel_tol=1e-9, abs_tol=1e-12)
        for found in collect_result_values(results)
    )


def _verdicts(results: list[dict[str, Any]]) -> list[bool]:
    found = []
    for result in results:
        holder = result if "success" in result else result.get("sim")
        if isinstance(holder, dict) and isinstance(holder.get("success"), bool):
            found.append(holder["success"])
    return found


def _number_problem(
    key: str, value: Any, source: str | None, by_id: dict[str, Any], cited: list[Any]
) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    results = [by_id[source]] if source in by_id else cited
    if _is_in(value, results):
        return None
    return f"{key} = {value} is not in {source or 'the cited results'}"


def check_design(row: dict[str, Any], tool_results: list[dict[str, Any]]) -> list[str]:
    """What is wrong with one `designs[]` row. Empty when it agrees with what it cites."""
    by_id = {result.get("source_id"): result for result in tool_results}
    sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
    problems = [
        f"{key}: source {sid} does not exist" for key, sid in sources.items() if sid not in by_id
    ]
    cited = [by_id[sid] for sid in sources.values() if sid in by_id]
    if not cited:
        return [*problems, "no source that exists is cited"]

    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    reported = {**metrics, "cost_jpy": row.get("cost_jpy"), "success_rate": row.get("success_rate")}
    for key, value in reported.items():
        problem = _number_problem(key, value, sources.get(key), by_id, cited)
        if problem:
            problems.append(problem)

    verdicts = _verdicts(cited)
    if row.get("passed") and True not in verdicts:
        problems.append("passed is true, but no cited simulation passed")
    if not row.get("passed") and verdicts and False not in verdicts:
        problems.append("passed is false, but the cited simulation passed")
    return problems


def split_checked_designs(
    final_result: dict[str, Any], tool_results: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Move every row with a problem out of `designs` into `rejected_by_check`. Pure: returns a
    new dict and what was found; unchanged input is returned as is."""
    designs = final_result.get("designs")
    if not isinstance(designs, list):
        return final_result, []
    kept: list[Any] = []
    rejected: list[dict[str, Any]] = []
    found: list[dict[str, Any]] = []
    for index, row in enumerate(designs):
        problems = check_design(row, tool_results) if isinstance(row, dict) else ["not an object"]
        if not problems:
            kept.append(row)
            continue
        found.append({"index": index, "problems": problems})
        if isinstance(row, dict):
            rejected.append({**row, "passed": False, "check_problems": problems})
    if not found:
        return final_result, []
    return {**final_result, "designs": kept, "rejected_by_check": rejected}, found
