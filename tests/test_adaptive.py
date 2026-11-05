import copy

import pytest

from rocketwright.adaptive import Campaign, Pool, Requirements


def campaign(tmp_path):
    pool = Pool.load()
    pool.actions = {k: pool.actions[k] for k in ["diagnose", "fin-candidates", "fin-confirm"]}

    def result(parameters, output, host):
        return {"metrics": {"fin_flexibility": 2.0}}

    return Campaign(
        tmp_path / "run",
        pool=pool,
        inputs={
            "prior": "old",
            "geometry": "g1",
            "code": "v1",
            "material": "m1",
            "requirements": "r1",
            "fin_span_m": 0.14,
        },
        runners={k: result for k in ["audit", "fin_screen", "fin_nonlinear"]},
        capabilities=["calculix"],
        budget_s=1000,
    )


def test_dependencies_stale_transitively_and_no_unlisted_choice(tmp_path):
    h = campaign(tmp_path)
    assert list(h.options()["offered"]) == ["diagnose"]
    with pytest.raises(ValueError):
        h.step("fin-confirm", "skip dependencies")
    h.step("diagnose", "inspect")
    h.step("fin-candidates", "screen")
    assert "fin-confirm" in h.options()["offered"]
    h.update_inputs(material="m2")
    assert h.current("diagnose") and not h.current("fin-candidates")
    assert "fin-confirm" not in h.options()["offered"]
    assert "fin-candidates" in h.options()["offered"]
    h.update_inputs(geometry="g2")
    assert not h.current("diagnose")
    assert not h.metrics


def test_failure_not_completion_budget_and_retry_are_bounded(tmp_path):
    h = campaign(tmp_path)

    def fail(*args):
        raise RuntimeError("solver failed")

    h.runners["audit"] = fail
    h.step("diagnose", "inspect")
    assert not h.options()["offered"]
    assert "attempt_limit" in h.options()["rejected"]["diagnose"]
    assert h.remaining_s <= 998
    assert not h.results["diagnose"]["physical_qualification"]


def test_resource_domain_quality_and_planned_methods_fail_closed(tmp_path):
    h = campaign(tmp_path)
    h.step("diagnose", "inspect")
    h.update_inputs(fin_span_m=0.3)
    assert "outside_domain:fin_span_m" in h.options()["rejected"]["fin-candidates"]
    h.update_inputs(fin_span_m=0.14)
    h.pool.actions["fin-candidates"].memory_gib = 10
    assert "memory_budget" in h.options()["rejected"]["fin-candidates"]
    h.memory_gib = 11
    h.pool.actions["fin-candidates"].quality_requires = ["numerical_pass"]
    assert "quality:numerical_pass" in h.options()["rejected"]["fin-candidates"]
    h.pool.methods["fin_screen"].implementation = "planned"
    assert "adapter_not_available" in h.options()["rejected"]["fin-candidates"]


def test_requirements_change_lower_layer_accuracy_and_pool_cycle_rejected():
    loose = Requirements(altitude_numerical_budget_m=2)
    tight = Requirements(altitude_numerical_budget_m=0.2)
    assert tight.aero_relative_tolerance(12) < loose.aero_relative_tolerance(12)
    assert tight.aero_relative_tolerance(0) is None
    data = copy.deepcopy(Pool.load().model_dump())
    data["actions"]["diagnose"]["depends"] = ["compare-aero"]
    with pytest.raises(ValueError, match="cycle"):
        Pool.model_validate(data)
