"""Price the complete invalidated analysis chain before changing numerical settings."""

from rocketwright.analysis.aero_accuracy import holdout
from rocketwright.analysis.runtime import Runtime


def updated(runtime, action):
    r = runtime.model_dump()
    if action == "refine/cfd":
        r["cfd_cells_coarse"], r["cfd_cells_fine"] = (
            r["cfd_cells_fine"],
            min(32, r["cfd_cells_fine"] + 4),
        )
    elif action == "refine/fem":
        r["fem_level"] += 1
    elif action == "refine/averaging":
        r["cfd_times"] = min(100, r["cfd_times"] * 1.5)
    elif action == "refine/time":
        r["flight_step_s"] = max(0.0025, r["flight_step_s"] / 2)
    elif action == "refine/table":
        speed, angle = holdout(r["cfd_speeds"], r["cfd_angles"])
        r["cfd_speeds"] = sorted(set(r["cfd_speeds"]) | {speed})
        r["cfd_angles"] = sorted(set(r["cfd_angles"]) | {angle})
    elif action == "refine/domain":
        r["cfd_width"] = min(14, r["cfd_width"] + 2)
    elif action == "refine/lattice":
        r["cfd_lattice_speed"] = max(0.025, r["cfd_lattice_speed"] / 2)
    else:
        raise ValueError("Unregistered numerical refinement")
    return Runtime.model_validate(r)


def scale_cfd_action(key, action, runtime):
    """The same reservation estimate is used for planning and actual campaign steps."""
    cells = runtime.cfd_cells_coarse if key == "cfd_coarse" else runtime.cfd_cells_fine
    if key == "cfd_audit":
        cells += 4
    width = runtime.cfd_width + (2 if key == "cfd_audit" else 0)
    action.memory_gib = cells**3 * width**2 * 18 * 512 / 1024**3
    action.cost_s *= (
        (cells / 12) ** 4
        * runtime.cfd_times
        / 40
        * (width / 10) ** 2
        * 0.075
        / runtime.cfd_lattice_speed
    )
    if key != "cfd_audit":
        action.cost_s *= len(runtime.cfd_speeds) * len(runtime.cfd_angles) / 14


def followup(pool, runtime, action, *, available=None):
    next_runtime = updated(runtime, action)
    actions = {
        k: v.model_copy(deep=True)
        for k, v in pool.actions.items()
        if available is None or k in available
    }
    for key, item in actions.items():
        if key.startswith("cfd_"):
            scale_cfd_action(key, item, next_runtime)
    if action == "refine/fem":
        affected = {k for k in actions if k.startswith("fem_")}
    elif action == "refine/time":
        affected = set(actions) & {"screen", "flight", "refine", "stability", "confirm"}
    else:
        affected = {k for k in actions if k.startswith("cfd_")}
    while True:
        expanded = affected | {k for k, item in actions.items() if set(item.depends) & affected}
        if expanded == affected:
            break
        affected = expanded
    return dict(
        estimated_followup_cost_s=sum(actions[k].cost_s for k in affected),
        required_memory_gib=max((actions[k].memory_gib for k in affected), default=0),
        affected_actions=sorted(affected),
        required_actions=1 + len(affected),
        basis="Conservative campaign reservations through reconfirmation; not measured duration",
    )
