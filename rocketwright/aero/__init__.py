"""Pluggable aerodynamics layer: L0 closed-form coefficients and external CFD backends behind
one interface (docs/aero.md). Backends register here in order of preference for "auto"."""

from rocketwright.aero import live
from rocketwright.aero.barrowman import BarrowmanBackend
from rocketwright.aero.base import (
    AeroBackend,
    AeroCase,
    AeroQuery,
    AeroResult,
    cd_for_physics,
    physics_ref_diameter_m,
)
from rocketwright.aero.flow_images import flow_image_path, flow_images
from rocketwright.aero.lbm_gpu import LbmGpuBackend
from rocketwright.aero.loop import (
    AeroLoopResult,
    AeroLoopRound,
    AmateurAeroResult,
    AmateurAeroRound,
    run_aero_loop,
    run_amateur_aero_loop,
)
from rocketwright.aero.openfoam_pipeline import OpenFoamPipelineBackend
from rocketwright.aero.registry import (
    BACKEND_NAMES,
    backends,
    cache_dir,
    cache_key,
    evaluate,
    get_backend,
    register,
    status,
)

__all__ = [
    "live",
    "BACKEND_NAMES",
    "AeroBackend",
    "AeroCase",
    "AeroLoopResult",
    "AeroLoopRound",
    "AeroQuery",
    "AeroResult",
    "AmateurAeroResult",
    "AmateurAeroRound",
    "BarrowmanBackend",
    "LbmGpuBackend",
    "OpenFoamPipelineBackend",
    "backends",
    "cache_dir",
    "cache_key",
    "cd_for_physics",
    "evaluate",
    "flow_image_path",
    "flow_images",
    "get_backend",
    "physics_ref_diameter_m",
    "register",
    "run_aero_loop",
    "run_amateur_aero_loop",
    "status",
]

# Preference order for backend="auto": RANS first, then the GPU LBM, L0 last.
register(OpenFoamPipelineBackend(), replace=True)
register(LbmGpuBackend(), replace=True)
register(BarrowmanBackend(), replace=True)
