"""Compare matched-budget fixed/variable-pressure studies without implying a global optimum."""

import argparse
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.worker import read


def compare(fixed_root, variable_root, fixed_public, variable_public, destination):
    fixed, variable = (read(p / "report.json") for p in (fixed_root, variable_root))
    old, new = read(fixed_public), read(variable_public)
    if (
        not fixed["source_unchanged"]
        or not variable["source_unchanged"]
        or fixed["source_hash"] != variable["source_hash"]
        or fixed["training_report_sha256"] != variable["training_report_sha256"]
        or fixed["seeds"] != variable["seeds"]
        or fixed["methods"] != variable["methods"]
        or fixed["objective"] != variable["objective"]
        or old["report_sha256"] != sha(fixed_root / "report.json")
        or new["report_sha256"] != sha(variable_root / "report.json")
    ):
        raise ValueError("Studies differ beyond the declared pressure extension")
    pairs = []
    for run in variable["runs"]:
        baseline = next(
            r for r in fixed["runs"] if all(r[k] == run[k] for k in ("method", "seed", "anchor"))
        )
        if (
            run["projected_initial_sha256"] != baseline["initial_sha256"]
            or run["evaluations"] != baseline["evaluations"]
            or run["evaluations"] != 512
        ):
            raise ValueError("Initial 13-coordinate projections or budgets differ")
        pairs.append(
            dict(
                method=run["method"],
                seed=run["seed"],
                anchor=run["anchor"],
                fixed_loss=baseline["best"]["loss"],
                variable_loss=run["best"]["loss"],
                variable_better=run["best"]["loss"] < baseline["best"]["loss"],
                selected_pressure_kpa=run["best"]["spec"]["design"]["initial_gauge_pressure_pa"]
                / 1000,
            )
        )
    methods = []
    for method in fixed["methods"]:
        a = next(r for r in old["methods"] if r["method"] == method)
        b = next(r for r in new["methods"] if r["method"] == method)
        methods.append(
            dict(
                method=method,
                wins_of_9=sum(p["variable_better"] for p in pairs if p["method"] == method),
                fixed_median_loss=a["median_best_loss"],
                variable_median_loss=b["median_best_loss"],
                fixed_native_height_m=a["native_best"]["metrics"]["apogee_m"]
                if a["native_best"]
                else None,
                variable_native_height_m=b["native_best"]["metrics"]["apogee_m"]
                if b["native_best"]
                else None,
            )
        )
    result = dict(
        source_hash=fixed["source_hash"],
        fixed_report_sha256=sha(fixed_public),
        variable_report_sha256=sha(variable_public),
        methods=methods,
        pairs=pairs,
        fixed_evaluations=old["evaluations"],
        variable_evaluations=new["evaluations"],
        projected_starts_match=True,
        training_models_match=True,
        limitation=(
            "Fourteen vs thirteen dimensions under finite equal budgets; pressure starts "
            "differ for half the population. Not an isolated causal estimate "
            "or proof of optimality."
        ),
        physical_qualification=False,
    )
    write_json(destination, result)
    print(methods, flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("fixed_root", "variable_root", "fixed_public", "variable_public", "destination"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    compare(a.fixed_root, a.variable_root, a.fixed_public, a.variable_public, a.destination)
