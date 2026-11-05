"""Host-owned, auditable selection of target/method/evaluation combinations.

The planner supplies an offered ID and a reason. Inputs, thresholds, runners and
resources belong to the host. Completed diagnostic calculations are not evidence
of numerical accuracy or hardware qualification.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Variable(Strict):
    unit: str
    role: Literal["design", "state", "numerical", "material"]
    bounds: tuple[float, float] | None = None
    invalidates: list[str]


class Target(Strict):
    label: str
    variables: list[str]


class Method(Strict):
    label: str
    layer: Literal["low", "middle", "high"]
    category: str
    phase: str
    inputs: list[str]
    outputs: list[str]
    scope: str
    capabilities: list[str] = []
    implementation: Literal["available", "planned"] = "available"


class Evaluation(Strict):
    label: str
    observables: list[str]
    rule: str
    evidence_level: Literal["diagnostic", "numerical", "model", "physical"]


class Action(Strict):
    target: str
    method: str
    evaluation: str
    parameters: dict = {}
    depends: list[str] = []
    uses: list[str]
    addresses: list[str]
    priority: int = Field(default=1, ge=0, le=100)
    cost_s: float = Field(gt=0)
    memory_gib: float = Field(default=0, ge=0)
    quality_requires: list[str] = []
    bounds: dict[str, tuple[float, float]] = {}
    max_attempts: int = Field(default=1, ge=1, le=3)


class Pool(Strict):
    version: int
    sources: dict[str, str]
    variables: dict[str, Variable]
    targets: dict[str, Target]
    methods: dict[str, Method]
    evaluations: dict[str, Evaluation]
    actions: dict[str, Action]

    @model_validator(mode="after")
    def consistent(self):
        for target in self.targets.values():
            if set(target.variables) - self.variables.keys():
                raise ValueError("Unknown target variable")
        for key, action in self.actions.items():
            if (
                action.target not in self.targets
                or action.method not in self.methods
                or action.evaluation not in self.evaluations
                or set(action.depends) - self.actions.keys()
                or key in action.depends
            ):
                raise ValueError(f"Invalid combination {key}")
        visiting, visited = set(), set()

        def visit(key):
            if key in visiting:
                raise ValueError("Dependency cycle")
            if key in visited:
                return
            visiting.add(key)
            for dep in self.actions[key].depends:
                visit(dep)
            visiting.remove(key)
            visited.add(key)

        for key in self.actions:
            visit(key)
        return self

    @classmethod
    def load(cls, path=None):
        path = path or Path(__file__).parent / "catalog/bottle_analysis.yaml"
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class Requirements(Strict):
    altitude_target_m: float = Field(default=30, gt=0)
    altitude_numerical_budget_m: float = Field(default=1.5, gt=0)
    fin_deflection_span_ratio: float = Field(default=0.05, gt=0, le=0.5)
    grid_relative_limit: float = Field(default=0.05, gt=0, le=0.2)
    interpolation_relative_limit: float = Field(default=0.1, gt=0, le=0.3)
    temporal_relative_limit: float = Field(default=0.03, gt=0, le=0.2)
    # Allocations sum to one; an engineering budget, not a probability model.
    aero_budget_fraction: float = Field(default=0.5, gt=0, le=1)
    status: str = "project screening assumptions; not certified requirements"

    def aero_relative_tolerance(self, sensitivity_m_per_relative_coefficient):
        s = abs(float(sensitivity_m_per_relative_coefficient))
        if not math.isfinite(s) or s < 1e-9:
            return None  # absence of demonstrated sensitivity is not unlimited tolerance
        return min(
            self.grid_relative_limit,
            self.altitude_numerical_budget_m * self.aero_budget_fraction / s,
        )


class Campaign:
    """Bounded selection/execution with dependency hashes and rejection reasons."""

    def __init__(
        self,
        output,
        *,
        inputs,
        runners,
        capabilities=(),
        memory_gib=0,
        budget_s=3600,
        requirements=None,
        pool=None,
    ):
        self.pool = pool or Pool.load()
        self.requirements = requirements or Requirements()
        self.inputs = copy.deepcopy(inputs)
        self.runners = dict(runners)
        self.capabilities = set(capabilities)
        self.memory_gib = float(memory_gib)
        self.remaining_s = float(budget_s)
        if not math.isfinite(self.remaining_s) or self.remaining_s <= 0:
            raise ValueError("A finite positive host budget is required")
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.results, self.history, self.metrics = {}, [], {}
        self._write("pool.json", self.pool.model_dump())
        self._write("requirements.json", self.requirements.model_dump())

    def _write(self, name, data):
        (self.output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    def fingerprint(self, key):
        action = self.pool.actions[key]
        return digest(
            {
                "action": action.model_dump(),
                "method": self.pool.methods[action.method].model_dump(),
                "inputs": {k: self.inputs.get(k) for k in action.uses},
                "dependencies": {
                    k: self.results.get(k, {}).get("artifact_hash") for k in action.depends
                },
            }
        )

    def current(self, key):
        result = self.results.get(key)
        return bool(
            result
            and result["fingerprint"] == self.fingerprint(key)
            and all(self.current(d) for d in self.pool.actions[key].depends)
        )

    def update_inputs(self, **inputs):
        self.inputs.update(copy.deepcopy(inputs))
        # Any result depending on modified data is rejected, transitively, by current().
        self._refresh_metrics()

    def _refresh_metrics(self):
        self.metrics = {}
        for key, result in self.results.items():
            if self.current(key) and result["execution_status"] == "completed":
                self.metrics.update(result["value"].get("metrics", {}))

    def options(self):
        offered, rejected = {}, {}
        for key, a in self.pool.actions.items():
            method = self.pool.methods[a.method]
            reasons = []
            if method.implementation != "available" or a.method not in self.runners:
                reasons.append("adapter_not_available")
            if not set(method.capabilities) <= self.capabilities:
                reasons.append("missing_capability")
            missing = [
                d
                for d in a.depends
                if not self.current(d) or self.results[d]["execution_status"] != "completed"
            ]
            if missing:
                reasons.append("dependency:" + ",".join(missing))
            absent = [k for k in a.uses if k not in self.inputs]
            if absent:
                reasons.append("missing_input:" + ",".join(absent))
            for metric in a.quality_requires:
                if self.metrics.get(metric) is not True:
                    reasons.append("quality:" + metric)
            for name, (lo, hi) in a.bounds.items():
                value = self.inputs.get(name)
                if (
                    not isinstance(value, (float, int))
                    or not math.isfinite(value)
                    or not lo <= value <= hi
                ):
                    reasons.append("outside_domain:" + name)
            if a.memory_gib > self.memory_gib:
                reasons.append("memory_budget")
            if a.cost_s > self.remaining_s:
                reasons.append("compute_budget")
            previous = [
                h
                for h in self.history
                if h["action"] == key and h["fingerprint"] == self.fingerprint(key)
            ]
            if self.current(key) and self.results[key]["execution_status"] == "completed":
                reasons.append("already_completed")
            elif len(previous) >= a.max_attempts:
                reasons.append("attempt_limit")
            if reasons:
                rejected[key] = reasons
                continue
            # Transparent engineering heuristic, not a learned value-of-information claim.
            urgency = sum(max(0, min(10, float(self.metrics.get(g, 1)))) for g in a.addresses)
            score = a.priority + 5 * urgency - math.log1p(a.cost_s)
            offered[key] = dict(
                target=a.target,
                method=a.method,
                evaluation=a.evaluation,
                layer=method.layer,
                score=score,
                cost_s=a.cost_s,
                addresses=a.addresses,
                parameters=a.parameters,
                scope=method.scope,
            )
        return dict(
            offered=dict(sorted(offered.items(), key=lambda pair: (-pair[1]["score"], pair[0]))),
            rejected=rejected,
            remaining_s=self.remaining_s,
            requirement_hash=digest(self.requirements.model_dump()),
        )

    def step(self, action_id, reason):
        choices = self.options()
        if action_id not in choices["offered"] or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Select an offered ID and provide a nonempty reason")
        a = self.pool.actions[action_id]
        fingerprint = self.fingerprint(action_id)
        folder = self.output / f"{len(self.history):02d}-{action_id}"
        folder.mkdir()
        start = time.monotonic()
        try:
            value = self.runners[a.method](copy.deepcopy(a.parameters), folder, self)
            digest(value)  # finite JSON contract before accepting any metrics
            status = "completed"
        except (RuntimeError, ValueError, FileNotFoundError, KeyError) as error:
            value, status = {"error": str(error)}, "failed"
        elapsed = time.monotonic() - start
        # Reserve at least the declared cost; repeated failures cannot evade the budget.
        self.remaining_s -= max(elapsed, a.cost_s)
        result = dict(
            execution_status=status,
            fingerprint=fingerprint,
            value=value,
            physical_qualification=False,
        )
        result["artifact_hash"] = digest(result)
        self.results[action_id] = result
        (folder / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        self.history.append(
            dict(
                action=action_id,
                reason=reason,
                fingerprint=fingerprint,
                decision=choices,
                elapsed_s=elapsed,
                execution_status=status,
                artifact_hash=result["artifact_hash"],
            )
        )
        self._refresh_metrics()
        self._write("history.json", self.history)
        self._write("results.json", self.results)
        return result

    def run(self, *, max_steps=20):
        for _ in range(max_steps):
            choices = self.options()["offered"]
            if not choices:
                break
            key = next(iter(choices))
            self.step(key, "Host baseline: highest eligible declared priority/cost score")
        final = self.options()
        final["stop_reason"] = "no_eligible_action" if not final["offered"] else "step_budget"
        final["physical_qualification"] = False
        self._write("next-actions.json", final)
        return self.results
