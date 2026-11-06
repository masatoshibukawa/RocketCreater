"""Executable combinations; the host owns dependencies, domains and cost estimates."""

from rocketwright.adaptive import Action, Evaluation, Method, Pool, Target, Variable


def pool(precision):
    physical = ["geometry", "material", "mass", "assumptions", "operation", "environment", "code"]
    rows = [
        ("geometry", "low", "CAD and mass", [], 20, 0, []),
        ("thermal", "low", "five-node heat network", ["geometry"], 5, 0, []),
        ("propulsion", "middle", "dry-gas discharge", ["thermal"], 5, 0, []),
        ("screen", "high", "rigid 6DOF screening", ["propulsion"], 10, 0, []),
        ("survey", "high", "counterfactual axial/mass sensitivity survey", ["screen"], 60, 0, []),
    ]
    flight = "screen"
    if precision.require_benchmarks:
        rows.append(
            ("benchmarks", "low", "exact and published reference comparisons", [], 15, 0, [])
        )
    if precision.require_cfd:
        rows += [
            ("cfd_coarse", "low", "3D interpolated-wall LBM", ["screen"], 120, 3, ["cfd"]),
            ("cfd_fine", "low", "3D LBM grid comparison", ["cfd_coarse"], 180, 4, ["cfd"]),
            ("flight", "high", "CFD-driven 6DOF and section loads", ["cfd_fine"], 15, 0, []),
        ]
        flight = "flight"
        if precision.require_aero_audit:
            rows.append(
                (
                    "cfd_audit",
                    "low",
                    "independent CFD accuracy checks",
                    ["cfd_fine"],
                    120,
                    4,
                    ["cfd"],
                )
            )
            rows = [
                (k, layer, name, ["cfd_audit"] if k == "flight" else deps, cost, mem, caps)
                for k, layer, name, deps, cost, mem, caps in rows
            ]
    rows += [
        ("refine", "high", "time-step and drag-sensitivity check", [flight], 30, 0, []),
        ("modes", "middle", "warm tapered beam and root foundation", [flight], 5, 0, []),
        ("stability", "high", "frozen LaSalle and finite-flight perturbation", [flight], 20, 0, []),
    ]
    deps = ["refine", "modes", "stability"]
    if precision.require_benchmarks:
        deps.append("benchmarks")
    if precision.require_fem:
        rows += [
            ("fem_coarse", "middle", "warm solid fin FEM", [flight, "thermal"], 30, 1, ["fem"]),
            ("fem_fine", "middle", "solid FEM mesh comparison", ["fem_coarse"], 60, 1, ["fem"]),
        ]
        deps.append("fem_fine")
    rows += [("confirm", "high", "independent coupled criterion check", deps, 20, 0, [])]
    variables = {
        v: Variable(unit="scoped SI/mm record", role="state", invalidates=[v])
        for v in physical + ["requirements"]
    }
    targets, methods, evaluations, actions = {}, {}, {}, {}
    for key, layer, label, depends, cost, memory, capabilities in rows:
        targets[key] = Target(label=label, variables=list(variables))
        methods[key] = Method(
            label=label,
            layer=layer,
            category=key,
            phase="design",
            inputs=physical,
            outputs=[key],
            capabilities=capabilities,
            scope="Conditional numerical model; no material or hardware qualification",
        )
        evaluations[key] = Evaluation(
            label=label,
            observables=[key],
            rule="Host evaluation against saved precision and requirements",
            evidence_level="diagnostic" if key in {"screen", "survey"} else "numerical",
        )
        actions[key] = Action(
            target=key,
            method=key,
            evaluation=key,
            depends=depends,
            uses=["geometry", "code"] if key == "geometry" else physical,
            addresses=[key + "_gap"],
            cost_s=cost,
            memory_gib=memory,
            priority=50,
            max_attempts=2,
        )
        if key.startswith("cfd"):
            actions[key].uses += ["fin_count"]
            actions[key].bounds = {"fin_count": (4, 4)}
        if key == "confirm":
            actions[key].uses += ["requirements"]
        if key == "benchmarks":
            actions[key].uses = ["code"]
    return Pool(
        version=1,
        sources={"implementation": "rocketwright/analysis/worker.py"},
        variables=variables,
        targets=targets,
        methods=methods,
        evaluations=evaluations,
        actions=actions,
    )
