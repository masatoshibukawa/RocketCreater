"""Human-readable dependency diffs and narrowly verified CAD reuse."""

import copy
import shutil
from pathlib import Path

from rocketwright.manufacturing import fingerprint


def flat(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flat(child, prefix + "." + key if prefix else key))
    else:
        result[prefix] = value
    return result


def difference(before, after):
    old, new = flat(before), flat(after)
    changes = [
        dict(path=key, before=old.get(key), after=new.get(key))
        for key in sorted(old.keys() | new.keys())
        if old.get(key) != new.get(key)
    ]
    groups = set()
    for row in changes:
        key = row["path"]
        if key.startswith("geometry.") or key == "design.has_fins":
            groups.update(
                ("CAD", "mass", "aero", "structure", "flight", "assembly", "manual", "video", "ZIP")
            )
        elif key == "material" or key.startswith("assumptions."):
            groups.update(("mass", "structure", "flight", "assembly", "manual", "video", "ZIP"))
        elif key.startswith(("design.", "env.", "other_dry_mass_g", "measured_printed_mass_g")):
            groups.update(("mass", "flight", "structure", "manual", "video", "ZIP"))
        elif key.startswith("requirement."):
            groups.update(("requirements", "confirmation", "manual", "video", "ZIP"))
        else:
            groups.update(("assembly", "requirements", "manual", "video", "ZIP"))
    return dict(
        changes=changes,
        invalidated=sorted(groups),
        preserved=[g for g in ("CAD", "mass", "aero", "structure", "flight") if g not in groups],
    )


def reuse_previous_cad(store, state, old, spec):
    """Copy only hash-checked CAD with matching geometry and generating implementation."""
    from rocketwright.agent.design_projects import implementation_fingerprint, sha

    analysis = old.get("analysis")
    previous = old["spec"]
    if (
        not analysis
        or analysis["implementation_sha256"] != implementation_fingerprint()
        or previous["geometry"] != spec["geometry"]
        or previous["design"]["has_fins"] != spec["design"]["has_fins"]
    ):
        return
    source = store.base(state["id"]) / f"v{old['version']}" / "cad"
    hashes = analysis.get("cad_sha256", {})
    if not hashes or any(
        name != Path(name).name or not (source / name).is_file() or sha(source / name) != expected
        for name, expected in hashes.items()
    ):
        return
    target = store.base(state["id"]) / f"v{state['version']}" / "cad"
    target.mkdir(parents=True, exist_ok=True)
    for name in hashes:
        shutil.copyfile(source / name, target / name)
    state["cad_reuse"] = dict(
        from_version=old["version"],
        cad_sha256=hashes,
        geometry_sha256=fingerprint(spec["geometry"]),
    )
    # Names and manufacturing/price metadata do not change the flight equations.
    def physical(s):
        return {k: v for k, v in s.items() if k not in {"name", "equipment"}}
    if physical(previous) == physical(spec):
        from rocketwright.agent.design_projects import DesignSpec
        from rocketwright.agent.project_requirements import assess_requirements
        from rocketwright.schema import SimResult

        state["analysis"] = copy.deepcopy(analysis)
        state["analysis"]["input_sha256"] = fingerprint(spec)
        state["analysis"]["requirements"] = assess_requirements(
            DesignSpec.model_validate(spec), SimResult.model_validate(analysis["result"])
        )
        state["analysis"]["reused_from_version"] = old["version"]
        store.register_files(state, target, "cad")
