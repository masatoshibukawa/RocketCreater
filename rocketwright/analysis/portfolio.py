"""Bounded multi-start screening followed by an unchanged high-fidelity confirmation."""

import copy
import time
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignProjects, DesignSpec, write_json
from rocketwright.analysis import experience, seeds
from rocketwright.analysis.schema import Precision, SearchLimits
from rocketwright.analysis.service import Harness, code_hash


def starts(template):
    result = {"provided": template.model_copy(deep=True)}
    for key in seeds.options():
        result[key] = seeds.import_seed(key, template)
    # Independent lighter geometry, explicitly generated rather than attributed to literature.
    data = copy.deepcopy(template.model_dump(mode="json"))
    data["geometry"].update(
        fin_span_mm=80,
        fin_root_mm=90,
        fin_tip_mm=30,
        fin_sweep_mm=35,
        fin_thickness_mm=1.6,
        nose_wall_mm=1.2,
    )
    data["assumptions"]["other_mass_station_fraction"] = 0.25
    data["measured_printed_mass_g"] = None
    data["assumptions"]["evidence"]["initial_source_scope"] = "independent host geometry scenario"
    result["independent-light"] = DesignSpec.model_validate(data)
    return result


def rank(row, precision, target):
    m = row["metrics"]
    return (
        max(0, (target - m["apogee_m"]) / target)
        + max(
            0,
            (precision.minimum_static_margin_cal - m["static_margin_cal"])
            / precision.minimum_static_margin_cal,
        )
        + max(0, m["incidence_deg"] / precision.maximum_incidence_deg - 1)
    )


def run(template, root, *, runtime, precision=None, limits=None, max_starts=5, emit=print):
    """One global wall/time budget; restart never resets persisted child campaigns.

    A new output directory is required to avoid accidental replay as a fresh budget.
    Individual saved projects remain resumable through run_adaptive_design.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    precision, limits = precision or Precision(), limits or SearchLimits()
    start_time, source = time.monotonic(), code_hash()
    candidates = list(starts(template).items())[:max_starts]
    if not candidates:
        raise ValueError("At least one start required")
    # Change only the fidelity flags for a clearly labeled screening phase.
    screen_precision = precision.model_copy(update={"require_cfd": False, "require_fem": False})
    exploration_budget = limits.budget_s * (1 - limits.reserve_confirmation_fraction)
    share = exploration_budget / len(candidates)
    memory, observations, campaigns, datasets = [], [], [], []
    store = DesignProjects(root / "projects")

    def execute(label, specification, p, budget, versions, prior):
        if code_hash() != source:
            raise RuntimeError("Source changed during portfolio; do not combine solver versions")
        h = Harness(store, runtime=runtime, prior_experience=prior)
        s = store.create(specification)
        child = limits.model_copy(update={"budget_s": budget, "max_versions": versions})
        s = h.start(s["id"], s["revision"], p, child)
        for _ in range(child.max_actions + 1):
            if time.monotonic() - start_time >= limits.budget_s:
                break
            s = h.step(s["id"], s["revision"])
            a = s["adaptive"]
            last = a["decisions"][-1] if a["decisions"] else {}
            emit(
                dict(
                    start=label,
                    project=s["id"],
                    version=s["version"],
                    status=a["status"],
                    action=last.get("action"),
                    remaining_s=round(a["remaining_s"], 2),
                )
            )
            if a["status"] != "running":
                break
        a = s["adaptive"]
        # Record terminal failures too, but never use them as measured gains.
        if a.get("outcome_pending"):
            a["observations"].append(
                dict(a["outcome_pending"], status="incomplete", stop_status=a["status"])
            )
        write_json(
            root / (s["id"] + "-learning.json"),
            experience.training_rows(a["decisions"], a.get("observations", [])),
        )
        campaigns.append(
            dict(
                label=label,
                project_id=s["id"],
                version=s["version"],
                status=a["status"],
                limits=a["limits"],
                precision=a["precision"],
                spent_s=budget - a["remaining_s"],
                decisions=len(a["decisions"]),
            )
        )
        datasets.extend(
            dict(row, project_id=s["id"], seed=label, solver_hash=source)
            for row in experience.training_rows(a["decisions"], a.get("observations", []))
        )
        return s, h

    for label, specification in candidates:
        available = min(share, limits.budget_s - (time.monotonic() - start_time))
        if available <= 1:
            break
        s, h = execute(
            label, specification, screen_precision, available, limits.max_versions, memory
        )
        a = s["adaptive"]
        memory.extend(r for r in a.get("observations", []) if experience.verified(r))
        for row in a.get("design_observations", []):
            if experience.verified(dict(evidence=row["evidence"])):
                observations.append(dict(row, start=label, project_id=s["id"]))
        write_json(
            root / "progress.json",
            dict(source_hash=source, campaigns=campaigns, observations=observations),
        )
    if not observations:
        raise RuntimeError("No verified screening observation; no final candidate selected")
    observations.sort(
        key=lambda row: (
            rank(row, precision, template.requirement.target_altitude_m),
            -row["metrics"]["apogee_m"],
        )
    )
    selected = observations[0]
    # Saved-time costs are charged as well as wall time; neither budget is reset.
    spent = sum(c["spent_s"] for c in campaigns)
    available = min(limits.budget_s - spent, limits.budget_s - (time.monotonic() - start_time))
    final = None
    if available > 1:
        final_spec = DesignSpec.model_validate(selected["spec"])
        s, h = execute("detailed-confirmation", final_spec, precision, available, 1, [])
        c, _, _, _ = h._campaign(s)
        final = dict(
            project_id=s["id"],
            status=s["adaptive"]["status"],
            confirmation=h.data(c, "confirm"),
            unresolved_precision=s["adaptive"].get("quality_pending", []),
            last_choices=s["adaptive"].get("last_choices"),
            accepted_spec_hash=s["adaptive"].get("accepted_spec_hash"),
        )
    result = dict(
        source_hash=source,
        requirement_hash=digest(template.requirement.model_dump()),
        precision=precision.model_dump(),
        limits=limits.model_dump(),
        campaigns=campaigns,
        selected=selected,
        observations=observations,
        final=final,
        elapsed_s=time.monotonic() - start_time,
        learned_outcomes=len(memory),
        physical_qualification=False,
        selection_scope="provisional ranking; detailed acceptance is separate",
    )
    write_json(root / "learning.json", datasets)
    write_json(root / "report.json", result)
    return result
