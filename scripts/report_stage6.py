"""Verify native evidence and export a portable stage-6 summary and observed-flow figure."""

import argparse
import json
from pathlib import Path

import numpy as np

from rocketwright.agent.design_projects import sha, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(project):
    state = read(project / "state.json")
    records, locations, manifests = {}, {}, {}
    for key, item in state["adaptive"]["results"].items():
        if item["execution_status"] != "completed":
            continue
        path = Path(item["value"]["artifact"]).resolve()
        if not path.is_relative_to(project.resolve()):
            raise ValueError("Artifact outside the selected project")
        manifest = path.parent / "manifest.json"
        if (
            sha(path) != item["value"]["sha256"]
            or sha(manifest) != item["value"]["manifest_sha256"]
        ):
            raise ValueError(f"Changed result or manifest: {key}")
        for name, expected in read(manifest).items():
            child = (path.parent / name).resolve()
            if not child.is_relative_to(path.parent) or sha(child) != expected:
                raise ValueError(f"Changed raw evidence: {key}/{name}")
        records[key] = read(path)
        locations[key] = path.parent
        manifests[key] = dict(
            artifact=path.relative_to(project.resolve()).as_posix(),
            sha256=sha(path),
            manifest_sha256=sha(manifest),
            files=len(read(manifest)),
        )
    return state, records, locations, manifests


def summary(project, source_commit):
    state, data, locations, manifests = evidence(project)
    required = {
        "cfd_coarse",
        "cfd_fine",
        "cfd_audit",
        "flight",
        "refine",
        "modes",
        "stability",
        "fem_fine",
        "confirm",
    }
    if not required.issubset(data):
        raise ValueError("Incomplete verification: " + ", ".join(sorted(required - data.keys())))
    campaign = state["adaptive"]
    confirmation = data["confirm"]
    settings = read(locations["confirm"] / "input.json")["runtime"]
    settings.pop("calculix", None)
    solver = Path(read(locations["fem_fine"] / "input.json")["runtime"]["calculix"])
    cfg = read(locations["confirm"] / "record.json")
    flight_keys = (
        "apogee_m",
        "ascent_incidence_deg",
        "max_q_pa",
        "impact_speed_mps",
        "peak_roll_rad_s",
    )
    cases = []
    for action in ("cfd_coarse", "cfd_fine", "cfd_audit"):
        for path in sorted(locations[action].rglob("case.json")):
            c = read(path)
            cases.append(
                dict(
                    action=action,
                    case=path.parent.name,
                    cells=c["d"],
                    speed_mps=c["speed_mps"],
                    angle_deg=c["angle_deg"],
                    width_D=c["width_D"],
                    lattice_Ma=c["lattice_Ma"],
                    averaging_tU_D=c["averaging_tU_D"],
                    mean=c["mean"],
                    seconds=c["seconds"],
                    sha256=sha(path),
                )
            )
    propagation = {
        k: v for k, v in data["refine"]["grid_propagation"].items() if k != "coarse_flight"
    }
    return (
        dict(
            source_commit=source_commit,
            project_id=state["id"],
            spec=state["spec"],
            completed_runtime=settings,
            current_runtime={k: v for k, v in campaign["runtime"].items() if k != "calculix"},
            precision=campaign["precision"],
            limits=campaign["limits"],
            status=campaign["status"],
            solver_sha256=sha(solver),
            physical_qualification=False,
            checks=confirmation["checks"],
            unmet=confirmation["unmet"],
            static_margin_cal=confirmation["static_margin_cal"],
            mass_g=cfg["assembly"]["dry_mass_g"],
            material=cfg["material"],
            temperature_c=data["thermal"]["final_c"],
            flight={key: {k: data[key][k] for k in flight_keys} for key in ("screen", "flight")},
            confirmation={k: confirmation["flight"][k] for k in flight_keys},
            grid_propagation=propagation,
            cfd=dict(
                grid_relative_change=data["cfd_fine"]["grid_relative_change"],
                averaging_relative_change=data["cfd_fine"]["averaging_relative_change"],
                audit={k: v for k, v in data["cfd_audit"].items() if k != "cases"},
                cases=cases,
            ),
            fem=dict(
                cases=[
                    {
                        k: v
                        for k, v in c.items()
                        if k not in {"node_displacements_m", "integration_stress_pa"}
                    }
                    for c in data["fem_fine"]["cases"]
                ],
                **{
                    k: data["fem_fine"][k]
                    for k in (
                        "max_displacement_m",
                        "p95_integration_vm_pa",
                        "metrics",
                        "load_scope",
                    )
                },
            ),
            modes=data["modes"],
            stability={k: v for k, v in data["stability"].items() if k != "perturbed_flight"},
            decisions=[
                {k: d.get(k) for k in ("action", "planner", "model", "reason", "errors")}
                for d in campaign["decisions"]
            ],
            executions=[
                {k: h.get(k) for k in ("action", "execution_status", "error")}
                for h in campaign["history"]
            ],
            manifests=manifests,
            raw_evidence_verified=True,
            limitations=[
                "unmeasured material and mount",
                "meridional CFD, omitted attachment detail",
                "reconstructed fin pressure, omitted tangential traction",
                "one off-table ascent condition",
                "no experimental validation or full-flight stability proof",
            ],
        ),
        data,
        locations,
    )


def figure(data, locations, destination):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from skimage.measure import marching_cubes

    from scenarios.cfd.flow_preview import body_faces, wake_view

    path = locations["cfd_fine"] / "tunnel/v35-a000"
    case, volume, section = (
        read(path / "case.json"),
        np.load(path / "volume.npz"),
        np.load(path / "slice.npz"),
    )
    dims = case["dimensions_mm"]
    d, length = dims["body_diameter"], dims["overall"]
    dx, stride = d / case["d"], int(volume["stride"])
    field, solid = volume["ux_U"].copy(), volume["solid"]
    field[solid] = 1
    groups = body_faces(dims, case["shape"], 0)
    vertices, faces, _, _ = marching_cubes(field, 0.8, mask=~solid, allow_degenerate=False)
    xyz = vertices[:, ::-1] * stride * dx + [
        -case["upstream_D"] * d + 0.5 * dx,
        (0.5 - case["grid"][1] / 2) * dx,
        (0.5 - case["grid"][2] / 2) * dx,
    ]
    triangles = xyz[faces]
    keep = (triangles[:, :, 0].min(1) >= -0.5 * d) & (triangles[:, :, 0].max(1) <= length + 4 * d)
    groups.append((xyz[faces[keep]], "#459eb0", 0.3))
    fig = Figure(figsize=(12, 9), dpi=150, layout="constrained", facecolor="#f7fafb")
    grid = fig.add_gridspec(3, 2, height_ratios=[1.4, 1, 1])
    ax = fig.add_subplot(grid[0, :])
    wake_view(ax, groups)
    ax.set_xlim(-d, length + 4 * d)
    ax.set_ylim(-2.5 * d, 2.5 * d)
    ax.set_title(f"Observed 3D wake: u/U = 0.80 | 35 m/s, 0 deg | {case['d']} cells/D")
    ax = fig.add_subplot(grid[1, 0])
    im = ax.imshow(
        np.ma.array(section["ux_U"], mask=section["solid"]),
        origin="lower",
        cmap=matplotlib.colormaps["viridis"].with_extremes(bad="#394752"),
        vmin=-0.25,
        vmax=1.25,
        extent=[
            -case["upstream_D"] * d,
            (case["grid"][0] / case["d"] - case["upstream_D"]) * d,
            -case["width_D"] * d / 2,
            case["width_D"] * d / 2,
        ],
    )
    ax.set_xlim(-0.5 * d, length + 4 * d)
    ax.set_ylim(-2 * d, 2 * d)
    ax.set(
        title="Velocity section (same case)", xlabel="Axial position (mm)", ylabel="Lateral (mm)"
    )
    fig.colorbar(im, ax=ax, label="u / U", shrink=0.75)
    ax = fig.add_subplot(grid[1, 1])
    audit = data["cfd_audit"]
    for key in ("Cx", "Cy", "Cm_z"):
        ax.plot(
            audit["cells"],
            [audit["cases"][str(c)]["mean"][key] for c in audit["cells"]],
            "o-",
            label=key,
        )
    c = audit["condition"]
    ax.set(
        title=f"Independent point: {c['speed_mps']} m/s, {c['angle_deg']} deg",
        xlabel="Cells per diameter",
        ylabel="Coefficient",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    for index, (key, label) in enumerate(
        (("position_m", "Altitude (m)"), ("incidence_deg", "Incidence (deg)"))
    ):
        ax = fig.add_subplot(grid[2, index])
        for name, item in (
            ("Analytic", data["screen"]),
            ("Coarse CFD", data["refine"]["grid_propagation"]["coarse_flight"]),
            ("Fine CFD", data["flight"]),
        ):
            t = np.asarray(item["trace"]["time_s"])
            y = np.asarray(item["trace"][key])
            if y.ndim == 2:
                y = y[:, 2]
            keep = t <= item["apogee_s"]
            if key == "incidence_deg":
                keep &= (t > item["rail_exit_s"]) & (np.asarray(item["trace"]["q_pa"]) > 10)
            ax.plot(t[keep], y[keep], label=name)
        ax.set(xlabel="Time (s)", ylabel=label)
        if key == "incidence_deg":
            ax.set_title("Free ascent with q > 10 Pa")
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle("Stage 6 numerical verification | Unqualified physical design", fontsize=15)
    fig.savefig(destination)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("project", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--figure", type=Path)
    args = p.parse_args()
    result, data, locations = summary(args.project.resolve(), args.source_commit)
    write_json(args.output, result)
    if args.figure:
        figure(data, locations, args.figure)
    print(
        json.dumps(
            dict(
                status=result["status"], checks=result["checks"], cases=len(result["cfd"]["cases"])
            )
        )
    )


if __name__ == "__main__":
    main()
