"""Persistent, version-aware analysis/LLM/redesign controller for saved design projects."""

import copy
import sys
import time
import uuid
from pathlib import Path

from rocketwright.adaptive import Campaign, Requirements, digest
from rocketwright.agent.design_projects import DesignSpec, sha, write_json
from rocketwright.agent.workbench import Conflict
from rocketwright.analysis import catalog, planner, policy
from rocketwright.analysis.record import scopes
from rocketwright.analysis.runtime import Runtime, run
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.worker import read

ROOT = Path(__file__).resolve().parents[2]


def code_hash():
    paths = list((ROOT / "rocketwright").rglob("*.py"))
    paths += list((ROOT / "scenarios/cfd").glob("*.py"))
    paths += list((ROOT / "scenarios/cfd").glob("*.cu"))
    paths += list((ROOT / "scenarios/cfd").glob("*.cuh"))
    paths += [
        ROOT / "scripts/build_print_parts.py",
        ROOT / "3d model/prototypes/pet-rocket-coke-2l/build.py",
    ]
    paths += list((ROOT / "rocketwright/catalog").rglob("*.json"))
    paths += [ROOT / "3d model/prototypes/pet-rocket-coke-2l/parameters.json"]
    return digest({p.relative_to(ROOT).as_posix(): sha(p) for p in paths})


class Harness:
    def __init__(self, store, *, runtime=None, director=None):
        self.store = store
        self.runtime = runtime or Runtime.installed()
        self.director = director

    def start(self, project_id, revision, precision=None, limits=None):
        precision, limits = precision or Precision(), limits or SearchLimits()

        def work(state):
            if state["adopted"] or state.get("adaptive"):
                raise Conflict("A saved campaign already exists or this version is adopted")
            spec = DesignSpec.model_validate(state["spec"])
            if spec.requirement is None:
                raise ValueError("Set an altitude requirement before starting adaptive design")
            state["adaptive"] = dict(
                id=uuid.uuid4().hex,
                precision=precision.model_dump(),
                limits=limits.model_dump(),
                runtime=self.runtime.model_dump(),
                starting_version=state["version"],
                status="running",
                remaining_s=limits.budget_s,
                results={},
                history=[],
                decisions=[],
                revisions=[],
                visited=[policy.identity(spec)],
                pending=None,
                physical_qualification=False,
                accepted_spec_hash=None,
            )

        return self.store._run(project_id, revision, "adaptive_start", work)

    def _valid(self, value):
        path = Path(value["artifact"])
        base = self.store.base(self.state["id"]).resolve()
        if not path.resolve().is_relative_to(base) or path.is_symlink():
            return False
        try:
            manifest_path = path.parent / "manifest.json"
            if sha(path) != value["sha256"] or sha(manifest_path) != value["manifest_sha256"]:
                return False
            manifest = read(manifest_path)
            for key, expected in manifest.items():
                child = (path.parent / key).resolve()
                if not child.is_relative_to(path.parent.resolve()) or child.is_symlink():
                    return False
                if sha(child) != expected:
                    return False
            return True
        except (OSError, ValueError, KeyError):
            return False

    def _campaign(self, state):
        self.state = state
        a = state.get("adaptive")
        if not a:
            raise Conflict("Start a campaign first")
        spec = DesignSpec.model_validate(state["spec"])
        precision = Precision.model_validate(a["precision"])
        limits = SearchLimits.model_validate(a["limits"])
        runtime = Runtime.model_validate(a["runtime"])
        inputs = scopes(spec, precision=precision, code_hash=code_hash())
        inputs["fin_count"] = spec.geometry.fin_count
        inputs["body_length_diameters"] = spec.geometry.overall_mm / spec.geometry.body_diameter_mm
        inputs["fin_radius_diameters"] = (
            0.5 + spec.geometry.fin_span_mm / spec.geometry.body_diameter_mm
        )
        inputs["fem_numerics"] = digest(
            dict(
                level=runtime.fem_level,
                solver_sha256=sha(Path(runtime.calculix))
                if runtime.calculix and Path(runtime.calculix).is_file()
                else None,
            )
        )
        inputs["cfd_numerics"] = digest(
            runtime.model_dump(include={"cfd_cells_coarse", "cfd_cells_fine", "cfd_times"})
        )
        inputs["flight_numerics"] = digest(runtime.flight_step_s)
        p = catalog.pool(precision)
        for key, action in p.actions.items():
            if key != "geometry":
                action.uses.append("requirements")
            if key.startswith("fem_"):
                action.uses.append("fem_numerics")
            if key in {"screen", "flight", "refine", "stability", "confirm"}:
                action.uses.append("flight_numerics")
            if key.startswith("cfd_"):
                action.uses.append("cfd_numerics")
                cells = runtime.cfd_cells_fine if key.endswith("fine") else runtime.cfd_cells_coarse
                # Conservative arrays/workspace estimate, recomputed for size and numerical level.
                action.memory_gib = cells**3 * 100 * 18 * 512 / 1024**3
                action.cost_s *= (cells / 12) ** 3 * runtime.cfd_times / 40
                action.bounds["air_speed_mps"] = (0, 35)
                action.uses.append("air_speed_mps")
                action.bounds.update(body_length_diameters=(0, 12), fin_radius_diameters=(0, 4.25))
                action.uses += ["body_length_diameters", "fin_radius_diameters"]
        requirement = Requirements(
            altitude_target_m=spec.requirement.target_altitude_m,
            altitude_numerical_budget_m=precision.altitude_error_m,
            aero_budget_fraction=precision.aero_allocation,
        )
        folder = self.store.base(state["id"]) / f"v{state['version']}/adaptive" / uuid.uuid4().hex
        c = Campaign(
            folder,
            inputs=inputs,
            runners={k: self._runner(k) for k in p.methods},
            capabilities=runtime.capabilities(),
            memory_gib=limits.memory_gib,
            budget_s=max(a["remaining_s"], 0.001),
            requirements=requirement,
            pool=p,
        )
        c.remaining_s = a["remaining_s"]
        c.results, c.history = copy.deepcopy(a["results"]), copy.deepcopy(a["history"])
        # Never trust the mere presence of a result file after restart or manual edits.
        for key, result in list(c.results.items()):
            if result["execution_status"] == "completed" and not self._valid(result["value"]):
                del c.results[key]
                for h in c.history:
                    if h["action"] == key:
                        h["fingerprint"] = "invalidated-artifact:" + h["fingerprint"]
                a["decisions"].append(dict(event="invalidated_artifact", action=key))
        c._refresh_metrics()
        inputs_speed = c.metrics.get("max_air_speed_mps")
        c.inputs["air_speed_mps"] = inputs_speed
        c._refresh_metrics()
        return c, spec, precision, limits

    def _runner(self, kind):
        def execute(_parameters, folder, campaign):
            a = self.state["adaptive"]
            artifacts = {
                k: r["value"]["artifact"]
                for k, r in campaign.results.items()
                if campaign.current(k) and r["execution_status"] == "completed"
            }
            timeout = max(0.1, min(campaign.remaining_s, 1800))
            context = dict(
                spec=self.state["spec"],
                precision=a["precision"],
                artifacts=artifacts,
                runtime=a["runtime"],
                timeout_s=max(0.1, timeout - 5),
            )
            write_json(folder / "input.json", context)
            try:
                run(
                    [
                        sys.executable,
                        "-m",
                        "rocketwright.analysis.worker",
                        str(folder / "input.json"),
                        str(folder / "data.json"),
                        kind,
                    ],
                    cwd=ROOT,
                    log=folder / "worker.log",
                    timeout=timeout,
                )
                data = read(folder / "data.json")
            except (OSError, ValueError) as exc:
                raise RuntimeError(str(exc)) from exc
            return dict(
                artifact=str((folder / "data.json").resolve()),
                sha256=sha(folder / "data.json"),
                manifest_sha256=sha(folder / "manifest.json"),
                metrics=data.get("metrics", {}),
            )

        return execute

    @staticmethod
    def data(c, key):
        if c.current(key) and c.results[key]["execution_status"] == "completed":
            return read(c.results[key]["value"]["artifact"])
        return None

    def _choices(self, c, spec, precision, limits):
        choices = c.options()
        a = self.state["adaptive"]
        unmet = []
        confirmation = self.data(c, "confirm")
        if confirmation:
            unmet = confirmation["unmet"]
        else:
            screen = self.data(c, "screen")
            if screen and screen["apogee_m"] < spec.requirement.target_altitude_m:
                unmet = ["altitude"]
        # Numerical uncertainty must be reduced before optimizing against an unreliable prediction.
        numerical = set(unmet) & {"aero_grid", "aero_averaging", "fem_mesh", "temporal"}
        proposals = {} if numerical else policy.proposals(spec, limits, unmet, a["visited"])
        if self.state["version"] - a["starting_version"] + 1 >= limits.max_versions:
            proposals = {}
            choices["rejected"]["redesign"] = ["version_budget"]
        for key, proposal in proposals.items():
            choices["offered"][key] = dict(
                target=proposal["change"],
                method="new_design_revision",
                evaluation="recalculate affected analyses",
                layer="high",
                score=proposal["score"],
                cost_s=1,
                addresses=unmet,
                scope=proposal["reason"],
            )
        runtime = Runtime.model_validate(a["runtime"])
        if "aero_grid" in numerical and runtime.cfd_cells_fine < 32:
            choices["offered"]["refine/cfd"] = dict(
                target="airframe flow",
                method="increase_grid",
                evaluation="force/moment grid and altitude budget",
                layer="low",
                score=100,
                cost_s=1,
                addresses=["aero_grid"],
                scope="Refine both grids within the host maximum",
            )
        if "fem_mesh" in numerical and runtime.fem_level < 4:
            choices["offered"]["refine/fem"] = dict(
                target="fin solid",
                method="increase_mesh",
                evaluation="deflection and p95 stress",
                layer="middle",
                score=100,
                cost_s=1,
                addresses=["fem_mesh"],
                scope="Increase FEM resolutions within the host maximum",
            )
        if "aero_averaging" in numerical and runtime.cfd_times < 100:
            choices["offered"]["refine/averaging"] = dict(
                target="unsteady flow",
                method="longer_averaging",
                evaluation="split-window force/moment differences",
                layer="low",
                score=105,
                cost_s=1,
                addresses=["aero_averaging"],
                scope="Increase flow duration within the host maximum",
            )
        if "temporal" in numerical and runtime.flight_step_s > 0.0025:
            choices["offered"]["refine/time"] = dict(
                target="flight integration",
                method="halve_time_step",
                evaluation="height difference and allocated budget",
                layer="high",
                score=100,
                cost_s=1,
                addresses=["temporal"],
                scope="Decrease flight step within the host minimum",
            )
        if len(a["decisions"]) >= limits.max_actions or a["remaining_s"] <= 0:
            for key in choices["offered"]:
                choices["rejected"][key] = ["campaign_budget"]
            choices["offered"] = {}
        choices["offered"] = dict(
            sorted(choices["offered"].items(), key=lambda kv: (-kv[1]["score"], kv[0]))
        )
        choices["unmet"] = unmet
        return choices, proposals, confirmation

    def _persist(self, c):
        a = self.state["adaptive"]
        a.update(results=c.results, history=c.history, remaining_s=c.remaining_s, pending=None)
        self.store._write(self.state)

    def _fork(self, proposal, decision, c):
        state, a = self.state, self.state["adaptive"]
        old = state["version"]
        self._persist(c)
        self.store.new_version(state, DesignSpec.model_validate(proposal["spec"]))
        a["visited"].append(policy.identity(DesignSpec.model_validate(state["spec"])))
        a["revisions"].append(
            dict(
                from_version=old,
                to_version=state["version"],
                action=decision["action"],
                reason=decision["reason"],
                change=proposal["change"],
            )
        )
        a.update(status="running", accepted_spec_hash=None)
        # Result fingerprints are checked against the new scopes before they can be reused.
        state["adaptive"] = a

    def _one(self, state):
        if state["adopted"]:
            raise Conflict("Edit the adopted design into a new version before further analysis")
        c, spec, precision, limits = self._campaign(state)
        a = state["adaptive"]
        if a["pending"]:
            # An interrupted calculation has no accepted result; retain the reserved cost/attempt.
            pending = a["pending"]
            c.remaining_s -= max(
                0, min(time.time() - pending["at"], pending["timeout_s"]) - pending["reserved_s"]
            )
            c.history.append(
                dict(
                    action=pending["action"],
                    fingerprint=pending["fingerprint"],
                    execution_status="interrupted",
                    reason="process restart",
                )
            )
            a["pending"] = None
        choices, proposals, confirmation = self._choices(c, spec, precision, limits)
        a["last_choices"] = choices
        if confirmation and confirmation["metrics"]["criteria_met"]:
            a["status"] = (
                "model_criteria_met"
                if precision.require_cfd and precision.require_fem
                else "screening_criteria_met"
            )
            a["accepted_spec_hash"] = policy.identity(spec)
            a["accepted_code_hash"] = code_hash()
            self._persist(c)
            return
        if not choices["offered"]:
            a["status"] = (
                "budget_exhausted"
                if c.remaining_s <= 0 or len(a["decisions"]) >= limits.max_actions
                else "unresolved"
            )
            self._persist(c)
            return
        decision = planner.choose(
            choices,
            dict(
                version=state["version"],
                metrics=c.metrics,
                unmet=choices["unmet"],
                recent_decisions=[
                    {k: d.get(k) for k in ("action", "reason", "planner")}
                    for d in a["decisions"][-4:]
                ],
                requirement=spec.requirement.model_dump(),
                precision=precision.model_dump(),
            ),
            limits,
            director=self.director,
            remaining_s=c.remaining_s,
        )
        c.remaining_s -= decision["elapsed_s"]
        decision.update(
            version=state["version"], offered=list(choices["offered"]), rejected=choices["rejected"]
        )
        a["decisions"].append(decision)
        key = decision["action"]
        if key is None:
            a["status"] = "planner_failed"
            self._persist(c)
            return
        if c.remaining_s < choices["offered"][key]["cost_s"]:
            a["status"] = "budget_exhausted"
            self._persist(c)
            return
        if key in proposals:
            c.remaining_s -= 1
            self._fork(proposals[key], decision, c)
        elif key.startswith("refine/"):
            r = a["runtime"]
            if key == "refine/cfd":
                r["cfd_cells_coarse"], r["cfd_cells_fine"] = (
                    r["cfd_cells_fine"],
                    r["cfd_cells_fine"] + 4,
                )
            elif key == "refine/fem":
                r["fem_level"] += 1
            elif key == "refine/averaging":
                r["cfd_times"] = min(100, r["cfd_times"] * 1.5)
            elif key == "refine/time":
                r["flight_step_s"] /= 2
            c.remaining_s -= 1
            self._persist(c)
        else:
            reserve = c.pool.actions[key].cost_s
            a["pending"] = dict(
                action=key,
                fingerprint=c.fingerprint(key),
                at=time.time(),
                reserved_s=reserve,
                timeout_s=min(c.remaining_s, 1800),
            )
            a["remaining_s"] = c.remaining_s - reserve
            self.store._write(state)
            c.step(key, decision["reason"])
            self._persist(c)
        a["status"] = "running"

    def step(self, project_id, revision, *, started_event=None):
        return self.store._run(
            project_id, revision, "adaptive_step", self._one, started_event=started_event
        )

    def run(self, project_id, revision, *, started_event=None):
        def work(state):
            a = state.get("adaptive")
            if not a:
                raise Conflict("Start a campaign first")
            a["status"] = "running"
            while a["status"] == "running":
                self._one(state)

        return self.store._run(
            project_id, revision, "adaptive_run", work, started_event=started_event
        )

    def options(self, project_id):
        # Use a private copy: inspection must not accept or invalidate persisted evidence.
        state = copy.deepcopy(self.store.get(project_id))
        c, spec, precision, limits = self._campaign(state)
        return self._choices(c, spec, precision, limits)[0]
