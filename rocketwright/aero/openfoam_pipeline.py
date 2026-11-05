"""L2 backend: steady RANS (OpenFOAM simpleFoam, k-omega SST) through the external
Model-Rocket-CFD-Pipeline (`rocketcfd`, https://github.com/LouiseMcMahon/Model-Rocket-CFD-Pipeline).

LICENSE NOTE: that repository has no license file, so none of its code is copied into this MIT
repository. It is cloned into a local Docker image at build time
(tools/aero/openfoam-pipeline.Dockerfile) and called only as a separate process:

    docker run ... rocketwright/openfoam-pipeline:2412 rocketcfd run /case/config.yaml

Input: rocketwright.geometry's STL (metres, nose at the origin pointing -x) and a YAML config
in a fresh case directory. Output parsed: `results.csv` (CD, CN, Cm_nose per case) and
`centre_of_pressure.json` (slope of moment vs normal force). The report, plots and logs are
copied to `<aero cache>/artifacts/<id>/`; the OpenFOAM case itself is deleted afterwards.

Environment: ROCKETWRIGHT_OPENFOAM_IMAGE, ROCKETWRIGHT_OPENFOAM_CPUS (default 8),
ROCKETWRIGHT_OPENFOAM_TIMEOUT_S (default 2700), ROCKETWRIGHT_AERO_KEEP_RUNS=1 keeps the case.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult
from rocketwright.geometry import airframe, write_stl
from rocketwright.schema import AmateurDesign, BottleDesign, Design

__all__ = [
    "DEFAULT_IMAGE",
    "PIPELINE_COMMIT",
    "OpenFoamPipelineBackend",
    "docker_command",
    "parse_results",
    "write_case",
]

DEFAULT_IMAGE = "rocketwright/openfoam-pipeline:2412"
PIPELINE_COMMIT = "b43605c90280fae8db47fd4b7822236df6b78516"  # pinned in the Dockerfile
DEFAULT_CPUS = 8
DEFAULT_TIMEOUT_S = 45 * 60
# Coarse defaults (docs/aero.md): a quick look, NOT grid-converged.
DEFAULTS: dict[str, Any] = {"mesh_preset": "coarse", "iterations": 800, "average_last": 150}
# Above this the incompressible solver is not trusted (the pipeline refuses Mach > 0.6).
INCOMPRESSIBLE_MAX_MPS = 100.0
STL_NAME = "airframe.stl"
RUN_NAME = "rw"
_ARTIFACTS = ("report.md", "results.csv", "centre_of_pressure.json", "mesh.json", "pipeline.log")


def _option(query: AeroQuery, key: str) -> Any:
    return query.extra.get(key, DEFAULTS[key])


def write_case(case_dir: Path, query: AeroQuery, *, nprocs: int = DEFAULT_CPUS) -> dict[str, Any]:
    """Write `airframe.stl` and `config.yaml` for `rocketcfd run` into case_dir. Paths inside
    the config are the container's (/case is the mounted case_dir)."""
    frame = airframe(query.design)
    p = frame.params
    cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else p["cg_from_nose_m"]
    case_dir.mkdir(parents=True, exist_ok=True)
    write_stl(case_dir / STL_NAME, frame)
    regime = "incompressible" if query.speed_mps <= INCOMPRESSIBLE_MAX_MPS else "compressible"
    geometry: dict[str, Any] = {
        "units": "m",
        "nose_direction": "-x",
        "roll_deg": 0,
        "ref_diameter": round(p["ref_diameter_m"], 6),
    }
    if cg is not None:
        geometry["cg_from_nose"] = round(cg, 6)
    config = {
        "model": STL_NAME,
        "name": RUN_NAME,
        "regime": regime,
        "geometry": geometry,
        "mesh": {"preset": _option(query, "mesh_preset")},
        "solver": {
            "iterations": int(_option(query, "iterations")),
            "average_last": int(_option(query, "average_last")),
            "nprocs": int(nprocs),
        },
        "sweeps": {
            "speed": None,
            "aoa": {"speed": float(query.speed_mps), "angles": list(query.alphas_deg)},
        },
        "visualize": True,
        "render_3d": False,
        "openfoam": {"runner": "native", "work_dir": "/case/foam"},
        "output_dir": "out",
    }
    (case_dir / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), "utf-8")
    return config


def parse_results(
    out_dir: Path,
    query: AeroQuery,
    *,
    ref_diameter_m: float,
    cg_from_nose_m: float | None,
    wall_time_s: float | None = None,
    artifacts_dir: str | None = None,
) -> AeroResult:
    """AeroResult from a finished `rocketcfd` output folder (results.csv and, with two or more
    angles, centre_of_pressure.json)."""
    with (out_dir / "results.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError(f"no cases in {out_dir / 'results.csv'}")
    cases = [
        AeroCase(
            speed_mps=float(r["speed_mps"]),
            alpha_deg=float(r["aoa_deg"]),
            cd=float(r["CD"]),
            cn=float(r["CN"]),
            cm=float(r["Cm_nose"]),
            cm_ref_from_nose_m=0.0,
        )
        for r in rows
    ]
    at_speed = [c for c in cases if math.isclose(c.speed_mps, query.speed_mps)] or cases
    zero = min(at_speed, key=lambda c: abs(c.alpha_deg))
    small = [c for c in at_speed if abs(c.alpha_deg) <= 6.0]
    cn_alpha = None
    if len({c.alpha_deg for c in small}) >= 2:
        a = np.radians([c.alpha_deg for c in small])
        cn_alpha = float(np.polyfit(a, [c.cn for c in small], 1)[0])
    x_cp = None
    cp_file = out_dir / "centre_of_pressure.json"
    if cp_file.exists():
        x_cp = float(json.loads(cp_file.read_text(encoding="utf-8"))["xcp_m"])
    margin = None
    if x_cp is not None and cg_from_nose_m is not None:
        margin = (x_cp - cg_from_nose_m) / ref_diameter_m
    notes = [
        "steady RANS k-omega SST, fully turbulent, wall functions",
        f"mesh preset {_option(query, 'mesh_preset')}: not grid-converged, precision not claimed",
    ]
    for r in rows:
        if str(r.get("converged", "")).lower() != "true":
            notes.append(
                f"alpha {float(r['aoa_deg']):g} deg not converged "
                f"(CD swing {float(r.get('cd_fluctuation') or 0):.2%} over the averaging window)"
            )
    if x_cp is None:
        notes.append("x_cp unavailable: needs two angles with a changing normal force")
    return AeroResult(
        cd=zero.cd,
        cn_alpha_per_rad=cn_alpha,
        x_cp_from_nose_m=x_cp,
        static_margin_cal=margin,
        cg_from_nose_m=cg_from_nose_m,
        ref_diameter_m=ref_diameter_m,
        per_case=cases,
        backend=OpenFoamPipelineBackend.name,
        fidelity="L2",
        provisional=True,
        notes=notes,
        source=(
            f"Model-Rocket-CFD-Pipeline {PIPELINE_COMMIT[:7]} (external, unlicensed: not "
            "vendored) / OpenFOAM v2412 simpleFoam"
        ),
        wall_time_s=wall_time_s,
        artifacts_dir=artifacts_dir,
    )


def _tail(path: Path, n: int = 15) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def docker_command(image: str, case_dir: Path, container: str, cpus: int) -> list[str]:
    """CPU-limited, network-less run as the calling user, so outputs stay deletable."""
    return [
        "docker", "run", "--rm", "--name", container,
        f"--cpus={cpus}", "--network=none",
        f"--user={os.getuid()}:{os.getgid()}",
        "-e", "HOME=/case", "-e", "MPLCONFIGDIR=/tmp",
        "-v", f"{case_dir}:/case", "-w", "/case",
        image, "rocketcfd", "run", "/case/config.yaml",
    ]  # fmt: skip


class OpenFoamPipelineBackend:
    name = "openfoam_pipeline"
    fidelity = "L2"
    cacheable = True

    def __init__(self, image: str | None = None) -> None:
        self._image = image

    @property
    def image(self) -> str:
        return self._image or os.environ.get("ROCKETWRIGHT_OPENFOAM_IMAGE", DEFAULT_IMAGE)

    def available(self) -> tuple[bool, str]:
        docker = shutil.which("docker")
        if docker is None:
            return False, "docker not found on PATH"
        try:
            res = subprocess.run(
                [docker, "image", "inspect", self.image],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"docker not usable: {exc}"
        if res.returncode != 0:
            return False, (
                f"image {self.image} not built: docker build -t {DEFAULT_IMAGE} "
                "-f tools/aero/openfoam-pipeline.Dockerfile tools/aero"
            )
        return True, f"docker image {self.image}"

    def supports(self, design: Design) -> tuple[bool, str]:
        if isinstance(design, AmateurDesign | BottleDesign):
            return True, ""
        return False, "aero covers the bottle and amateur tiers only"

    def evaluate(self, query: AeroQuery) -> AeroResult:
        cpus = int(os.environ.get("ROCKETWRIGHT_OPENFOAM_CPUS", DEFAULT_CPUS))
        timeout_s = float(os.environ.get("ROCKETWRIGHT_OPENFOAM_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        frame = airframe(query.design)
        p = frame.params
        cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else p["cg_from_nose_m"]
        run_id = hashlib.sha256(
            frame.stl_bytes()
            + json.dumps([query.speed_mps, query.alphas_deg, query.extra], default=str).encode()
        ).hexdigest()[:16]
        case_dir = Path(tempfile.mkdtemp(prefix=f"rw-openfoam-{run_id}-"))
        write_case(case_dir, query, nprocs=cpus)
        container = f"rw-aero-{run_id}-{os.getpid()}"
        cmd = docker_command(self.image, case_dir, container, cpus)
        out_dir = case_dir / "out" / RUN_NAME
        start = time.monotonic()
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container], capture_output=True)
            raise RuntimeError(
                f"OpenFOAM pipeline timed out after {timeout_s:.0f} s (case kept in {case_dir}); "
                f"last log lines:\n{_tail(out_dir / 'pipeline.log')}"
            ) from None
        wall = time.monotonic() - start
        if res.returncode != 0 or not (out_dir / "results.csv").exists():
            raise RuntimeError(
                f"rocketcfd failed (exit {res.returncode}, case kept in {case_dir}): "
                f"{res.stderr.decode(errors='replace')[-1500:]}"
            )
        from rocketwright.aero.registry import cache_dir

        artifacts = cache_dir() / "artifacts" / run_id
        artifacts.mkdir(parents=True, exist_ok=True)
        for name in _ARTIFACTS:
            if (out_dir / name).exists():
                shutil.copy2(out_dir / name, artifacts / name)
        for png in sorted(out_dir.glob("*.png")) + sorted(out_dir.glob("flow/*.png")):
            target = artifacts / png.relative_to(out_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, target)
        result = parse_results(
            out_dir,
            query,
            ref_diameter_m=p["ref_diameter_m"],
            cg_from_nose_m=cg,
            wall_time_s=wall,
            artifacts_dir=str(artifacts),
        )
        if os.environ.get("ROCKETWRIGHT_AERO_KEEP_RUNS") != "1":
            shutil.rmtree(case_dir, ignore_errors=True)
        return result
