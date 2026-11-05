"""Generated nonlinear 3-D CalculiX decks. Solver is an optional external executable.

No solver binary is redistributed. Geometry, loads, support assumptions and the
solver hash travel with every result. Models do not establish hardware allowables.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import numpy as np

from .schema import AnalysisConfig, Material


def hex_mesh(counts, mapping):
    """Structured 20-node hexahedra, shared edge nodes and positive parametric Jacobian."""
    nodes, lookup, elements = {}, {}, []
    offsets = [
        (0, 0, 0),
        (2, 0, 0),
        (2, 2, 0),
        (0, 2, 0),
        (0, 0, 2),
        (2, 0, 2),
        (2, 2, 2),
        (0, 2, 2),
        (1, 0, 0),
        (2, 1, 0),
        (1, 2, 0),
        (0, 1, 0),
        (1, 0, 2),
        (2, 1, 2),
        (1, 2, 2),
        (0, 1, 2),
        (0, 0, 1),
        (2, 0, 1),
        (2, 2, 1),
        (0, 2, 1),
    ]
    for k in range(counts[2]):
        for j in range(counts[1]):
            for i in range(counts[0]):
                ids = []
                for di, dj, dk in offsets:
                    coord = tuple(
                        mapping(
                            (2 * i + di) / (2 * counts[0]),
                            (2 * j + dj) / (2 * counts[1]),
                            (2 * k + dk) / (2 * counts[2]),
                        )
                    )
                    key = tuple(round(x, 12) for x in coord)
                    if key not in lookup:
                        idx = len(nodes) + 1
                        lookup[key] = idx
                        nodes[idx] = coord
                    ids.append(lookup[key])
                elements.append((ids, (i, j, k)))
    return nodes, elements


def material_cards(p: Material, *, creep_rate=None, creep_stress=30e6, creep_n=3):
    if p.engineering_constants is not None:
        if creep_rate is not None:
            raise ValueError("This creep adapter supports isotropic material only")
        constants = list(p.engineering_constants)
        text = ["*MATERIAL,NAME=PART", "*ELASTIC,TYPE=ENGINEERING CONSTANTS"]
        for temperature, ratio in [(p.reference_c, 1), (p.warm_c, p.warm_ratio)]:
            scaled = [x * ratio if i in (0, 1, 2, 6, 7, 8) else x for i, x in enumerate(constants)]
            text += [",".join(f"{v:.9g}" for v in scaled[:8]), f"{scaled[8]:.9g},{temperature:.9g}"]
        return text + ["*DENSITY", f"{p.density:.9g}", "*EXPANSION,ZERO=20.", f"{p.cte:.9g}"]
    text = [
        "*MATERIAL,NAME=PART",
        "*ELASTIC",
        f"{p.young_pa:.9g},{p.poisson:.9g},{p.reference_c:.9g}",
        f"{p.young_pa * p.warm_ratio:.9g},{p.poisson:.9g},{p.warm_c:.9g}",
        "*DENSITY",
        f"{p.density:.9g}",
        "*EXPANSION,ZERO=20.",
        f"{p.cte:.9g}",
    ]
    if p.yield_pa is not None:
        text += ["*PLASTIC", f"{p.yield_pa:.9g},0.", f"{p.yield_pa + p.hardening_pa * 0.1:.9g},0.1"]
    if creep_rate is not None:
        text += ["*CREEP", f"{creep_rate / creep_stress**creep_n:.9g},{creep_n:.9g},0."]
    return text


def base_deck(nodes, elements, material, *, creep=None):
    lines = ["*HEADING", "Conditional bottle component analysis; SI units", "*NODE"]
    lines += [f"{i}," + ",".join(f"{x:.12g}" for x in xyz) for i, xyz in nodes.items()]
    lines += ["*ELEMENT,TYPE=C3D20R,ELSET=PART"]
    for i, (ids, _) in enumerate(elements, 1):
        lines += [f"{i}," + ",".join(map(str, ids[:15])) + ",", ",".join(map(str, ids[15:]))]
    lines += [
        "*NSET,NSET=ALL,GENERATE",
        f"1,{len(nodes)},1",
        "*SOLID SECTION,ELSET=PART,MATERIAL=PART",
    ]
    lines += material_cards(material, **(creep or {}))
    lines += ["*INITIAL CONDITIONS,TYPE=TEMPERATURE", "ALL,20."]
    return lines


def foundation(lines, node_ids, first_element, k_total, *, unilateral=False):
    """Distributed support; compression-only normal springs with tiny tensile regularisation."""
    eid = first_element
    for direction in (1, 2, 3):
        lines += [f"*ELEMENT,TYPE=SPRING1,ELSET=SUP{direction}"]
        for node in node_ids:
            lines.append(f"{eid},{node}")
            eid += 1
        spring = k_total / len(node_ids)
        if unilateral and direction == 3:
            lines += [
                f"*SPRING,ELSET=SUP{direction},NONLINEAR",
                str(direction),
                f"{-spring * 0.02:.9e},-0.02",
                "0.,0.",
                f"{spring * 1e-8:.9e},1.0e-8",
                f"{spring * (1e-8 + 1e-6 * 0.02):.9e},0.02",
            ]
        else:
            lines += [f"*SPRING,ELSET=SUP{direction}", str(direction), f"{spring:.9e}"]


def output_cards():
    return [
        "*NODE PRINT,NSET=ALL,FREQUENCY=999999",
        "U,RF",
        "*EL PRINT,ELSET=PART,FREQUENCY=999999",
        "S,E",
        "*NODE FILE,FREQUENCY=999999",
        "U",
        "*EL FILE,FREQUENCY=999999",
        "S,E",
        "*END STEP",
    ]


def run_deck(executable, folder, name, lines, *, timeout_s=240):
    exe = Path(executable).resolve()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if not exe.is_file():
        raise FileNotFoundError("Set a real CalculiX executable; missing solver is not a pass")
    deck = folder / f"{name}.inp"
    if deck.exists():
        raise FileExistsError(f"Use a new FEM output directory: {deck}")
    deck.write_text("\n".join(lines) + "\n", encoding="ascii")
    env = dict(os.environ, OMP_NUM_THREADS="2", NUMBER_OF_CPUS="2")
    p = subprocess.run(
        [str(exe), "-i", name],
        cwd=folder,
        env=env,
        text=True,
        errors="replace",
        capture_output=True,
        timeout=timeout_s,
    )
    log = p.stdout + "\n" + p.stderr
    (folder / f"{name}.log").write_text(log, encoding="utf-8")
    if p.returncode or "*ERROR" in log.upper() or "Job finished" not in log:
        raise RuntimeError(f"CalculiX {name} failed; see {name}.log\n{log[-1200:]}")
    data = (folder / f"{name}.dat").read_text(errors="replace")
    displacements, stresses, forces = {}, [], {}
    section = None
    for line in data.splitlines():
        low = line.lower()
        if "displacements (" in low:
            section = "u"
            displacements = {}
            continue
        if "forces (" in low:
            section = "f"
            forces = {}
            continue
        if "stresses (" in low:
            section = "s"
            stresses = []
            continue
        if "strains (" in low or "total force" in low:
            section = None
            continue
        fields = line.split()
        if not fields or not re.fullmatch(r"\d+", fields[0]):
            continue
        try:
            if section in ("u", "f") and len(fields) == 4:
                target = displacements if section == "u" else forces
                target[int(fields[0])] = [float(x.replace("D", "E")) for x in fields[1:]]
            elif section == "s" and len(fields) >= 8:
                stresses.append([float(x.replace("D", "E")) for x in fields[2:8]])
        except ValueError:
            continue
    if not displacements or not stresses:
        raise RuntimeError(f"Missing FEM fields in {name}.dat")
    stress = np.asarray(stresses)
    sxx, syy, szz, sxy, sxz, syz = stress.T
    vm = np.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3 * (sxy * sxy + sxz * sxz + syz * syz)
    )
    return {
        "completed": True,
        "solver": re.search(r"CalculiX Version [0-9.]+", log).group(0),
        "solver_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
        "node_displacements_m": displacements,
        "max_displacement_m": float(np.linalg.norm(list(displacements.values()), axis=1).max()),
        "max_integration_vm_pa": float(vm.max()),
        "p95_integration_vm_pa": float(np.quantile(vm, 0.95)),
        "integration_stress_pa": stress.tolist(),
        "nodal_force_sum_n": np.sum(list(forces.values()), axis=0).tolist(),
        "nodes": len(displacements),
        "strength_status": "unknown_without_matching_material_evidence",
    }


def fin_deck(
    assembly, cfg: AnalysisConfig, q_pa, *, resolution=1, temperature_c=20, incidence_deg=3
):
    g = assembly["dimensions_mm"]
    tab = g["fin_tab"] / 1000
    span = g["fin_span"] / 1000
    counts = (4 * resolution, 12 * resolution, 1 if resolution == 1 else 2)

    def shape(u, v, w):
        s = np.interp(v, [0, 1 / 12, 1], [-tab, 0, span])
        f = max(s, 0) / span
        chord = (g["fin_root"] + (g["fin_tip"] - g["fin_root"]) * f) / 1000
        return g["fin_sweep"] / 1000 * f + chord * u, s, (w - 0.5) * cfg.fin_thickness_m

    nodes, els = hex_mesh(counts, shape)
    lines = base_deck(nodes, els, cfg.fin_material or cfg.material)
    support = [i for i, xyz in nodes.items() if xyz[1] <= 0]
    foundation(lines, support, len(els) + 1, cfg.fin_root_k_n_m)
    force = (
        q_pa
        * assembly["fin_set_CNalpha_per_rad"]
        / 2
        * np.pi
        * (g["body_diameter"] / 2000) ** 2
        * np.deg2rad(incidence_deg)
    )
    area = (g["fin_root"] + g["fin_tip"]) * g["fin_span"] / 2e6
    lines += [
        "*STEP,NLGEOM,INC=300",
        "*STATIC",
        "0.05,1.,1e-7,0.1",
        "*TEMPERATURE",
        f"ALL,{temperature_c:.8g}",
        "*DLOAD",
    ]
    for e, (_, ijk) in enumerate(els, 1):
        i, j, k = ijk
        v = (j + 0.5) / counts[1]
        s = np.interp(v, [0, 1 / 12, 1], [-tab, 0, span])
        if k == counts[2] - 1 and s > 0:
            # Chord weighting puts the load centroid near quarter chord. Pressure follows
            # the deformed face; incidence feedback is assessed separately, not hidden here.
            a = i / counts[0]
            b = (i + 1) / counts[0]
            weight = ((1 - a) ** 3 - (1 - b) ** 3) / (b - a)
            lines.append(f"{e},P2,{-force / area * weight:.9g}")
    lines += output_cards()
    return (
        lines,
        nodes,
        els,
        {
            "scope": "nonlinear solid fin, compliant root and follower pressure",
            "force_target_n": force,
            "temperature_c": temperature_c,
            "q_pa": q_pa,
        },
    )


def collar_deck(assembly, cfg: AnalysisConfig, force_n, *, resolution=1, temperature_c=20):
    g = assembly["print_parts"]
    ri = g["collar_inner_mm"] / 2000
    ro = g["collar_outer_mm"] / 2000
    h = g["thickness_mm"] / 1000
    counts = (24 * resolution, 3 * resolution, 1 if resolution == 1 else 2)
    nodes, els = hex_mesh(
        counts,
        lambda u, v, w: (
            np.interp(v, [0, 1 / 3, 2 / 3, 1], [ri, ri + 0.003, ro - 0.002, ro])
            * np.cos(2 * np.pi * u),
            np.interp(v, [0, 1 / 3, 2 / 3, 1], [ri, ri + 0.003, ro - 0.002, ro])
            * np.sin(2 * np.pi * u),
            h * w,
        ),
    )
    # Parametric theta, radius, z has negative orientation: reverse theta to restore it.
    nodes = {i: (x, -y, z) for i, (x, y, z) in nodes.items()}
    lines = base_deck(nodes, els, cfg.collar_material or cfg.material)
    support = [
        i
        for i, (x, y, z) in nodes.items()
        if z < 1e-10 and np.hypot(x, y) >= ro - 0.002 and abs(np.cos(2 * np.arctan2(y, x))) > 0.7
    ]
    foundation(lines, support, len(els) + 1, cfg.collar_support_k_n_m, unilateral=True)
    load_faces = [
        (e, ijk)
        for e, (_, ijk) in enumerate(els, 1)
        if ijk[2] == counts[2] - 1 and ijk[1] < resolution
    ]
    band = ri + 0.003
    pressure = force_n / (np.pi * (band * band - ri * ri))
    lines += [
        "*STEP,NLGEOM,INC=300",
        "*STATIC",
        "0.05,1.,1e-7,0.1",
        "*TEMPERATURE",
        f"ALL,{temperature_c:.8g}",
        "*DLOAD",
    ]
    lines += [f"{e},P2,{pressure:.9g}" for e, _ in load_faces]
    lines += output_cards()
    return (
        lines,
        nodes,
        els,
        {
            "scope": "inner-band load, four support sectors with compression-only normal springs",
            "support_tensile_regularisation": 1e-6,
            "support_tensile_transition_m": 1e-8,
            "force_target_n": force_n,
            "temperature_c": temperature_c,
        },
    )


def body_deck(
    assembly,
    cfg: AnalysisConfig,
    pressure_pa,
    *,
    resolution=1,
    temperature_c=20,
    profile=None,
    axial_compression_n=0.0,
    transverse_n=0.0,
    ovality=0.0,
):
    g = assembly["dimensions_mm"]
    L = g["bottle_length"] / 1000
    radius = g["body_diameter"] / 2000
    if profile is None:
        # Surrogate: actual ribs, shoulder/base and thickness need measurements.
        profile = [[0, 0.012], [0.06 * L, 0.014], [0.22 * L, radius], [0.8 * L, radius], [L, 0.025]]
    profile = np.asarray(profile)
    counts = (24 * resolution, 12 * resolution, 1 if resolution == 1 else 2)

    def shape(u, v, w):
        z = v * L
        r = np.interp(z, profile[:, 0], profile[:, 1]) * (1 + ovality * np.cos(4 * np.pi * u))
        r += (w - 0.5) * cfg.body_thickness_m
        return r * np.cos(2 * np.pi * u), r * np.sin(2 * np.pi * u), z

    nodes, els = hex_mesh(counts, shape)
    creep = {
        "creep_rate": cfg.creep_reference_rate_per_s,
        "creep_stress": cfg.creep_reference_stress_pa,
        "creep_n": cfg.creep_exponent,
    }
    lines = base_deck(nodes, els, cfg.body_material or cfg.material, creep=creep)
    support = [i for i, (_, _, z) in nodes.items() if z < 1e-10]
    foundation(lines, support, len(els) + 1, 1e8)
    lines += [
        "*STEP,NLGEOM,INC=300",
        "*STATIC",
        "0.05,1.,1e-7,0.1",
        "*TEMPERATURE",
        f"ALL,{temperature_c:.8g}",
        "*DLOAD",
    ]
    lines += [f"{e},P1,{pressure_pa:.9g}" for e, (_, ijk) in enumerate(els, 1) if ijk[2] == 0]
    # Equivalent closures carry pressure resultants; local cap stress is unresolved.
    lines += ["*CLOAD"]
    for z, sign, r in ((0, -1, profile[0, 1]), (L, 1, profile[-1, 1])):
        ids = [i for i, xyz in nodes.items() if abs(xyz[2] - z) < 1e-10]
        force = pressure_pa * np.pi * (r - cfg.body_thickness_m / 2) ** 2
        lines += [f"{i},3,{sign * force / len(ids):.9g}" for i in ids]
        if z == L:
            # *CLOAD duplicates are added by CalculiX within a step.
            lines += [f"{i},3,{-axial_compression_n / len(ids):.9g}" for i in ids]
            lines += [f"{i},1,{transverse_n / len(ids):.9g}" for i in ids]
    lines += output_cards()
    if cfg.creep_reference_rate_per_s is not None and cfg.pressure_hold_s > 0:
        lines += [
            "*STEP,NLGEOM,INC=500",
            "*VISCO",
            f"0.1,{cfg.pressure_hold_s:.9g},1e-7,5.",
        ] + output_cards()
    return (
        lines,
        nodes,
        els,
        {
            "scope": "profiled pressure wall, equivalent end closures; ribs/caps absent",
            "profile_m": profile.tolist(),
            "pressure_pa": pressure_pa,
            "temperature_c": temperature_c,
            "creep_enabled": cfg.creep_reference_rate_per_s is not None,
            "axial_compression_n": axial_compression_n,
            "transverse_n": transverse_n,
            "ovality": ovality,
        },
    )
