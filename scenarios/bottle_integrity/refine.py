"""Extend only failed mesh checks, retaining original results and calculation provenance."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rocketwright.physics.bottle_integrity import aeroelastic, fem  # noqa: E402
from rocketwright.physics.bottle_integrity.harness import IntegrityHarness, write_json  # noqa: E402
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig  # noqa: E402


def extend(directory, solver, maximum_level=4):
    directory = Path(directory)
    original = directory / "results.json"
    packet = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    results = json.loads(original.read_text(encoding="utf-8"))
    package = Path(fem.__file__).parent
    for name, expected in packet["implementation_sha256"].items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Implementation changed: {name}. Recalculate affected models first.")
    target = directory / "assessment_results.json"
    if target.exists():
        raise FileExistsError("The extended assessment already exists")
    cfg = AnalysisConfig(**packet["config"])
    cfg.maximum_mesh_level = maximum_level
    harness = object.__new__(IntegrityHarness)
    harness.config = cfg
    harness.solver = Path(solver).resolve()
    assembly = packet["assembly"]
    structure = results["structure"]
    if structure["execution_status"] != "completed":
        raise ValueError("Resolve failed structural methods before extending refinement")
    added = []
    for key, case in structure["cases"].items():
        level = len(case["meshes"])
        while not case["mesh_check"]["pass"] and level < maximum_level:
            level += 1
            print(key, "refinement", level, flush=True)
            meta = case["meshes"][-1]["metadata"]
            folder = directory / "refinement" / f"{key}-{level}"
            common = {"resolution": level, "temperature_c": meta["temperature_c"]}
            if key.startswith("fin-"):
                r = aeroelastic.coupled_fin(
                    harness.solver, folder, assembly, cfg, meta["q_pa"], **common
                )
                coarse = case["meshes"][-1]["fem"]
                fine = r["fem"]
            else:
                if key.startswith("collar-"):
                    deck = fem.collar_deck(assembly, cfg, meta["force_target_n"], **common)
                else:
                    deck = fem.body_deck(
                        assembly,
                        cfg,
                        meta["pressure_pa"],
                        profile=meta["profile_m"],
                        axial_compression_n=meta["axial_compression_n"],
                        transverse_n=meta["transverse_n"],
                        ovality=meta["ovality"],
                        **common,
                    )
                r = harness._fem_case(folder, key, deck)
                coarse = case["meshes"][-1]
                fine = r
            case["meshes"].append(r)
            case["mesh_check"] = harness._mesh_change(coarse, fine)
            added.append(
                {
                    "case": key,
                    "level": level,
                    "check": case["mesh_check"],
                    "deck_sha256": fine["deck_sha256"],
                }
            )
    results["verdict"]["numerical_checks"]["all_structural_mesh_observables"] = all(
        c["mesh_check"]["pass"] for c in structure["cases"].values()
    )
    results["refinement_provenance"] = {
        "parent_results_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "maximum_level": maximum_level,
        "added": added,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "unchanged physical models and previous solutions; extended mesh budget only",
    }
    write_json(target, results)
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--solver", required=True, type=Path)
    parser.add_argument("--maximum-level", type=int, default=4, choices=[3, 4])
    args = parser.parse_args()
    extend(args.directory, args.solver, args.maximum_level)
