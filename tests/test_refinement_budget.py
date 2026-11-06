import copy

import pytest

from rocketwright.analysis import catalog, refinement
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.schema import Precision
from tests.test_analysis_harness import started


def test_cfd_refinement_prices_all_invalidated_layers_and_preserves_input():
    r = Runtime(cfd_cells_coarse=16, cfd_cells_fine=20)
    before = r.model_dump()
    plan = refinement.followup(catalog.pool(Precision()), r, "refine/cfd")
    assert {"cfd_coarse", "cfd_fine", "cfd_audit", "flight", "fem_fine", "confirm"} <= set(
        plan["affected_actions"]
    )
    assert not {"geometry", "thermal", "propulsion", "screen"} & set(plan["affected_actions"])
    assert plan["estimated_followup_cost_s"] > 4700
    assert plan["required_memory_gib"] > 24
    assert r.model_dump() == before
    assert refinement.updated(r, "refine/cfd").cfd_cells_fine == 24


def test_fem_refinement_preserves_unaffected_flow_cost():
    plan = refinement.followup(catalog.pool(Precision()), Runtime(), "refine/fem")
    assert set(plan["affected_actions"]) == {"fem_coarse", "fem_fine", "confirm"}
    assert plan["estimated_followup_cost_s"] == 110
    assert plan["required_actions"] == 4
    with pytest.raises(ValueError):
        refinement.updated(Runtime(), "refine/unregistered")


def test_nonstandard_starting_resolution_stays_within_host_refinement_bounds():
    assert refinement.updated(Runtime(flight_step_s=0.003), "refine/time").flight_step_s == 0.0025
    assert refinement.updated(Runtime(cfd_cells_fine=30), "refine/cfd").cfd_cells_fine == 32


def test_unfinishable_refinement_is_removed_without_discarding_confirmation(tmp_path):
    _, h, state = started(tmp_path, budget_s=4700, memory_gib=24)
    state["adaptive"]["precision"] = Precision().model_dump()
    state["adaptive"]["runtime"].update(cfd_enabled=True, cfd_cells_coarse=16, cfd_cells_fine=20)
    c, s, p, limits = h._campaign(state)
    confirmation = dict(unmet=["aero_grid"], metrics=dict(criteria_met=False))
    original = h.data
    h.data = lambda campaign, key: confirmation if key == "confirm" else original(campaign, key)
    before = copy.deepcopy(state)
    choices, _, returned = h._choices(c, s, p, limits)
    assert "refine/cfd" not in choices["offered"]
    assert {"refinement_completion_budget", "refinement_completion_memory"} <= set(
        choices["rejected"]["refine/cfd"]
    )
    assert choices["refinement_plans"]["refine/cfd"]["estimated_followup_cost_s"] > c.remaining_s
    assert returned == confirmation
    assert state["adaptive"]["runtime"] == before["adaptive"]["runtime"]


def test_selection_time_cannot_consume_the_followup_reserve(tmp_path, monkeypatch):
    from rocketwright.analysis import planner

    _, h, state = started(tmp_path, budget_s=10)
    before = copy.deepcopy(state["adaptive"]["runtime"])
    h._choices = lambda *args: (
        dict(
            offered={"refine/time": dict(cost_s=1, estimated_followup_cost_s=9)},
            rejected={},
            unmet=[],
            precision_pending=[],
            confirmation_reserve_s=1,
        ),
        {},
        None,
    )
    monkeypatch.setattr(
        planner,
        "choose",
        lambda *args, **kwargs: dict(
            action="refine/time", reason="test", planner="fixture", elapsed_s=1, errors=[]
        ),
    )
    h._one(state)
    assert state["adaptive"]["status"] == "budget_exhausted"
    assert state["adaptive"]["runtime"] == before
    assert "followup_budget_after_selection" in state["adaptive"]["decisions"][-1]["errors"]
