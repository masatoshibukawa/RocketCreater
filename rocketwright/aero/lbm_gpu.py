"""L2 backend: the team's GPU lattice-Boltzmann wind tunnel (scenarios/cfd/run_flow.py, D3Q19
LBM-LES in CUDA via CuPy), called unchanged as an external process, one run per angle.

run_flow.py reads an `assembly.json` with `dimensions_mm` {overall, body_diameter, nose_length,
fin_root, fin_tip, fin_span, fin_sweep, fin_tail_inset, skirt_length}, `loaded_cg_mm`, `key`
and `axial_cd`. We write that file from rocketwright.geometry's parameters, so any bottle or
amateur design maps onto it within the kernel's shape family:

* SIMPLIFICATION: the kernel's body is a nose plus a straight cylinder with a flat base
  (`--shape flat` = conical nose, `--shape rounded_flat` = half-ellipse nose; ogives use the
  rounded one). The bottle's rounded shoulder and neck are not represented.
* the kernel always draws four zero-thickness fins: other fin counts are not supported, and
  an assembled shape's fin thickness has no effect here.
* the domain is 15 body diameters plus the upstream gap: airframes longer than
  MAX_FINENESS diameters are refused.

It needs a Python with CuPy (CUDA 12) and NumPy: $ROCKETWRIGHT_LBM_PYTHON, else
~/tools/lbm-venv/bin/python (docs/aero.md shows how to create it). Outputs per angle:
case.json `mean` {Cd, Cl, Cx, Cy, Cz, Croll, Cpitch_y, Cm_z}; force coefficients on the body
frontal area, Cm_z about the loaded CG (positive = nose turned back into the wind).
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult
from rocketwright.geometry import AssembledShape, airframe
from rocketwright.schema import AmateurDesign, BottleDesign, Design

__all__ = ["LbmGpuBackend", "assembly_for", "parse_cases"]

RUN_FLOW = Path(__file__).resolve().parents[2] / "scenarios" / "cfd" / "run_flow.py"
DEFAULT_PYTHON = Path.home() / "tools" / "lbm-venv" / "bin" / "python"
DEFAULT_CELLS = 16  # cells per body diameter (the study's mid resolution)
MAX_FINENESS = 10.0
MAX_SPEED_MPS = 35.0  # run_flow.py's own limit
MAX_ALPHA_DEG = 15.0
DEFAULT_TIMEOUT_S = 30 * 60


def _python() -> str | None:
    env = os.environ.get("ROCKETWRIGHT_LBM_PYTHON")
    if env:
        return env
    return str(DEFAULT_PYTHON) if DEFAULT_PYTHON.exists() else None


@functools.lru_cache(maxsize=4)
def _probe(python: str) -> tuple[bool, str]:
    code = "import cupy, numpy; n = cupy.cuda.runtime.getDeviceCount(); print(n)"
    try:
        res = subprocess.run([python, "-c", code], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{python}: {exc}"
    if res.returncode != 0:
        return False, f"{python} cannot import cupy: {res.stderr.decode(errors='replace')[-200:]}"
    return True, f"{python} with CuPy, {res.stdout.decode().strip()} CUDA device(s)"


def _shape(params: dict[str, Any]) -> str:
    return "flat" if params["nose_shape"] == "conical" else "rounded_flat"


def _kernel_limits(p: dict[str, Any]) -> tuple[bool, str]:
    if p["fin_count"] not in (0, 4):
        return False, "the LBM kernel draws exactly four fins"
    if p["length_m"] / p["body_diameter_m"] > MAX_FINENESS:
        return False, f"longer than {MAX_FINENESS:g} body diameters (domain is 15 D)"
    return True, ""


def assembly_for(
    design: Design,
    cg_from_nose_m: float | None = None,
    shape: AssembledShape | None = None,
) -> dict[str, Any]:
    """run_flow.py's assembly.json for a design (millimetres)."""
    p = airframe(design, shape=shape).params
    cg = cg_from_nose_m if cg_from_nose_m is not None else p["cg_from_nose_m"]
    if cg is None:
        raise ValueError("the LBM run needs a CG (moment reference)")
    mm = 1000.0
    return {
        "key": f"rocketwright-{design.tier}",
        "dimensions_mm": {
            "overall": p["length_m"] * mm,
            "body_diameter": p["body_diameter_m"] * mm,
            "nose_length": p["nose_length_m"] * mm,
            "fin_root": p.get("fin_root_chord_m", 0.0) * mm,
            "fin_tip": p.get("fin_tip_chord_m", 0.0) * mm,
            "fin_span": p.get("fin_span_m", 0.0) * mm,
            "fin_sweep": p.get("fin_sweep_m", 0.0) * mm,
            "fin_tail_inset": p.get("fin_tail_inset_m", 0.0) * mm,
            "skirt_length": 0.0,
        },
        "loaded_cg_mm": cg * mm,
        "axial_cd": None,
        "rocketwright_shape": _shape(p),
    }


def parse_cases(
    case_files: list[Path],
    query: AeroQuery,
    *,
    ref_diameter_m: float,
    cg_from_nose_m: float,
    wall_time_s: float | None = None,
    artifacts_dir: str | None = None,
) -> AeroResult:
    cases = []
    for f in case_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        mean = data["mean"]
        cases.append(
            AeroCase(
                speed_mps=float(data.get("speed_mps") or query.speed_mps),
                alpha_deg=float(data["angle_deg"]),
                cd=float(mean["Cd"]),
                cn=float(mean["Cy"]),  # body frame: the body stays on x, the inflow turns
                cm=float(mean["Cm_z"]),
                cm_ref_from_nose_m=cg_from_nose_m,
            )
        )
    cases.sort(key=lambda c: c.alpha_deg)
    zero = min(cases, key=lambda c: abs(c.alpha_deg))
    cn_alpha = x_cp = margin = None
    if len({c.alpha_deg for c in cases}) >= 2:
        a = np.radians([c.alpha_deg for c in cases])
        cn_alpha = float(np.polyfit(a, [c.cn for c in cases], 1)[0])
        cn = np.array([c.cn for c in cases])
        if np.ptp(cn) > 0.05:
            slope = float(np.polyfit(cn, [c.cm for c in cases], 1)[0])
            x_cp = cg_from_nose_m + slope * ref_diameter_m
            margin = slope
    return AeroResult(
        cd=zero.cd,
        cn_alpha_per_rad=cn_alpha,
        x_cp_from_nose_m=x_cp,
        static_margin_cal=margin,
        cg_from_nose_m=cg_from_nose_m,
        ref_diameter_m=ref_diameter_m,
        per_case=cases,
        backend=LbmGpuBackend.name,
        fidelity="L2",
        provisional=True,
        notes=[
            "D3Q19 LBM-LES (scenarios/cfd), staircase body, zero-thickness fins",
            "simplified shape: nose + cylinder + flat base, 4 fins",
            "team's own wind-tunnel check: Cd about 3x the measured 0.253 (results.md)",
        ],
        source="scenarios/cfd/run_flow.py (GPU lattice Boltzmann, CuPy)",
        wall_time_s=wall_time_s,
        artifacts_dir=artifacts_dir,
    )


class LbmGpuBackend:
    name = "lbm_gpu"
    fidelity = "L2"
    cacheable = True

    def available(self) -> tuple[bool, str]:
        if not RUN_FLOW.exists():
            return False, f"{RUN_FLOW} missing"
        python = _python()
        if python is None:
            return False, "set ROCKETWRIGHT_LBM_PYTHON to a Python with CuPy (CUDA 12)"
        return _probe(python)

    def supports(self, design: Design) -> tuple[bool, str]:
        if not isinstance(design, AmateurDesign | BottleDesign):
            return False, "aero covers the bottle and amateur tiers only"
        return _kernel_limits(airframe(design).params)

    def evaluate(self, query: AeroQuery) -> AeroResult:
        if query.speed_mps > MAX_SPEED_MPS:
            raise ValueError(f"run_flow.py accepts speeds up to {MAX_SPEED_MPS:g} m/s")
        if max(abs(a) for a in query.alphas_deg) > MAX_ALPHA_DEG:
            raise ValueError(f"run_flow.py accepts |alpha| <= {MAX_ALPHA_DEG:g} deg")
        p = airframe(query.design, shape=query.shape).params
        ok, why = _kernel_limits(p)  # supports() sees only the design, not an assembled shape
        if not ok:
            raise ValueError(why)
        python = _python() or sys.executable
        cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else p["cg_from_nose_m"]
        asm = assembly_for(query.design, cg, query.shape)
        cells = int(query.extra.get("cells", DEFAULT_CELLS))
        work = Path(tempfile.mkdtemp(prefix="rw-lbm-"))
        (work / "assembly.json").write_text(json.dumps(asm, indent=2), encoding="utf-8")
        files, start = [], time.monotonic()
        for alpha in query.alphas_deg:
            out = work / f"a{alpha:+g}"
            cmd = [
                python, str(RUN_FLOW), str(work / "assembly.json"), str(out),
                "--shape", asm["rocketwright_shape"], "--cells", str(cells),
                "--speed", f"{query.speed_mps:g}", "--angle", f"{alpha:g}", "--no-preview",
            ]  # fmt: skip
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=DEFAULT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"LBM case alpha={alpha:g} timed out ({work})") from None
            if res.returncode != 0 or not (out / "case.json").exists():
                raise RuntimeError(
                    f"run_flow.py failed for alpha={alpha:g} (exit {res.returncode}, {work}): "
                    f"{res.stderr.decode(errors='replace')[-1500:]}"
                )
            files.append(out / "case.json")
        wall = time.monotonic() - start
        from rocketwright.aero.registry import cache_dir

        artifacts = cache_dir() / "artifacts" / f"lbm-{work.name}"
        artifacts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work / "assembly.json", artifacts / "assembly.json")
        for f in files:
            shutil.copy2(f, artifacts / f"{f.parent.name}-case.json")
        result = parse_cases(
            files,
            query,
            ref_diameter_m=p["body_diameter_m"],
            cg_from_nose_m=cg,
            wall_time_s=wall,
            artifacts_dir=str(artifacts),
        )
        shutil.rmtree(work, ignore_errors=True)
        return result
