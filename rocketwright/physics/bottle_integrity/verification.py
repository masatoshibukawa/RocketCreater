"""Independent FEM limit cases, using the same deck writer/parser as the actual cases."""

import numpy as np

from .fem import base_deck, hex_mesh, output_cards, run_deck
from .schema import Material


def fem_limits(executable, output):
    results = {}
    material = Material()
    nodes, elements = hex_mesh((4, 2, 2), lambda u, v, w: (0.1 * u, 0.01 * v, 0.01 * w))
    base = base_deck(nodes, elements, material)
    base += ["*BOUNDARY"]
    for i, xyz in nodes.items():
        for j, coordinate in enumerate(xyz):
            if abs(coordinate) < 1e-10:
                base.append(f"{i},{j + 1},{j + 1},0.")
    for name in ["tension", "expansion"]:
        lines = base + ["*STEP", "*STATIC"]
        if name == "tension":
            lines += ["*DLOAD"] + [
                f"{e},P4,-1000." for e, (_, index) in enumerate(elements, 1) if index[0] == 3
            ]
            expected = 0.1 * 1000 / material.young_pa
        else:
            lines += ["*TEMPERATURE", "ALL,50."]
            expected = 0.1 * 30 * material.cte
        result = run_deck(executable, output / name, name, lines + output_cards())
        measured = np.mean(
            [u[0] for i, u in result["node_displacements_m"].items() if nodes[i][0] > 0.09999]
        )
        error = abs(measured / expected - 1)
        results[name] = {
            "expected_m": expected,
            "computed_m": float(measured),
            "relative_error": float(error),
            "pass": bool(error < 1e-5),
        }
    beam = []
    for refinement in [1, 2]:
        counts = (2 * refinement, 20 * refinement, refinement)
        nodes, elements = hex_mesh(counts, lambda u, v, w: (0.01 * u, 0.1 * v, 0.002 * w))
        lines = base_deck(nodes, elements, material) + ["*BOUNDARY"]
        lines += [f"{i},1,3,0." for i, xyz in nodes.items() if xyz[1] < 1e-10]
        lines += ["*STEP", "*STATIC", "*DLOAD"]
        lines += [
            f"{e},P2,-100." for e, (_, index) in enumerate(elements, 1) if index[2] == counts[2] - 1
        ]
        r = run_deck(executable, output / f"beam{refinement}", "beam", lines + output_cards())
        computed = float(
            np.mean([u[2] for i, u in r["node_displacements_m"].items() if nodes[i][1] > 0.09999])
        )
        ei = material.young_pa * 0.01 * 0.002**3 / 12
        ga = material.young_pa / (2 * (1 + material.poisson)) * 0.01 * 0.002 * 5 / 6
        expected = 100 * 0.01 * 0.1**4 / (8 * ei) + 100 * 0.01 * 0.1**2 / (2 * ga)
        beam.append(
            {
                "nodes": len(nodes),
                "computed_m": computed,
                "expected_m": expected,
                "relative_error": abs(computed / expected - 1),
            }
        )
    results["beam"] = {"meshes": beam, "pass": beam[-1]["relative_error"] < 0.02}
    results["passed"] = all(r["pass"] for r in results.values())
    return results
