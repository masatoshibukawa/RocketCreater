"""Resume after a proved Windows path failure, preserving source, history and residual budget."""

import argparse
import copy
import os
import uuid
from pathlib import Path

from rocketwright.agent.design_projects import DesignProjects, sha, write_json
from rocketwright.analysis.service import Harness, code_hash
from scripts.run_learning_stages import execute, finish_stage6, read


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("adapter", type=Path)
    p.add_argument("proof", type=Path)
    args = p.parse_args()
    root = args.root.resolve()
    report = read(root / "report.json")
    if code_hash() != report["source_hash"]:
        raise ValueError("Numerical source changed")
    project = next((root / "stage6/projects").glob("*/state.json")).parent
    store = DesignProjects(project.parent)
    state = store.get(project.name)
    a = state["adaptive"]
    build = read(args.adapter.parent / "build.json")
    proof = read(args.proof)
    old_solver = Path(a["runtime"]["calculix"])
    old_build = old_solver.parent / "build.json"
    old_native_hash = (
        read(old_build)["native_solver_sha256"] if old_build.exists() else sha(old_solver)
    )
    if (
        a["status"] != "unresolved"
        or a["results"]["fem_coarse"]["execution_status"] != "failed"
        or "CalculiX fin-0 failed" not in a["results"]["fem_coarse"]["value"]["error"]
        or not proof["finished"]
        or proof["returncode"] != 0
        or proof["original_deck_sha256"] != proof["replayed_deck_sha256"]
        or build["native_solver_sha256"] != old_native_hash
        or build["adapter_sha256"] != sha(args.adapter)
        or build["adapter_sha256"] != proof.get("adapter_sha256")
        or not proof.get("native_dat_identical")
        or build["native_solver_sha256"] != sha(Path(os.environ["ROCKETWRIGHT_CALCULIX_NATIVE"]))
    ):
        raise ValueError("Recovery proof/runtime does not match this failure")
    if not any(
        sha(q) == proof["original_deck_sha256"] for q in project.rglob("*fem_coarse/fin-0.inp")
    ):
        raise ValueError("Proof does not use this project's failed input deck")
    recovery = project / ("transport-recovery-" + uuid.uuid4().hex[:8])
    recovery.mkdir(exist_ok=False)
    write_json(recovery / "before-state.json", state)
    h = Harness(store)
    before, _, _, _ = h._campaign(copy.deepcopy(state))
    valid = [key for key in before.results if before.current(key)]
    successful = [k for k in valid if before.results[k]["execution_status"] == "completed"]

    def change(current):
        saved = current["adaptive"]
        saved["runtime"]["calculix"] = str(args.adapter.resolve())
        saved["remaining_s"] -= proof["elapsed_s"]
        saved["status"] = "running"
        check, _, _, _ = h._campaign(copy.deepcopy(current))
        if not all(check.current(k) for k in successful):
            raise ValueError("Transport change invalidated an unrelated completed result")
        if "fem_coarse" not in check.options()["offered"]:
            raise ValueError("Corrected native runtime cannot retry under the remaining budget")

    state = store._run(state["id"], state["revision"], "native_solver_transport", change)
    write_json(
        recovery / "audit.json",
        dict(
            source_hash=code_hash(),
            before_state_sha256=sha(recovery / "before-state.json"),
            build=build,
            proof=proof,
            preserved_completed_actions=successful,
            old_failures_preserved=True,
            budget_before_s=a["remaining_s"],
            diagnostic_charge_s=proof["elapsed_s"],
            budget_after_s=state["adaptive"]["remaining_s"],
            limits_unchanged=state["adaptive"]["limits"] == a["limits"],
            precision_unchanged=state["adaptive"]["precision"] == a["precision"],
        ),
    )
    execute(h, store, state, code_hash())
    finish_stage6(report, root, code_hash())


if __name__ == "__main__":
    main()
