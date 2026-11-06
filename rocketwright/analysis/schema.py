"""Host-owned assumptions and limits shared by analysis, planning and revisions."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# Constitutive scenarios, not certified printed-material allowables. The manufacturer's
# filament name does not establish a strength or stiffness for a particular printed part.
STOCKS = {
    "UltiMaker Tough PLA Gray": dict(density=1240.0, young_pa=2e9, warm_ratio=0.5),
    "Prusament PETG": dict(density=1270.0, young_pa=1.5e9, warm_ratio=0.53),
}
MOUNTS = {
    "standard": dict(root_k_n_m=5e5, additional_mass_g=0.0),
    "reinforced": dict(root_k_n_m=2e6, additional_mass_g=5.0),
}


class Assumptions(Strict):
    mount: Literal["standard", "reinforced"] = "standard"
    root_capture_mm: float = Field(default=10.5, gt=0, le=30)
    other_mass_station_fraction: float = Field(default=0.55, gt=0, lt=1)
    payload_station_fraction: float = Field(default=0.15, gt=0, lt=1)
    solar_w_m2: float = Field(default=800, ge=0, le=1400)
    warm_wait_s: float = Field(default=120, ge=0, le=3600)
    pitch_damping: float = Field(default=10, ge=0, le=30)
    initial_tilt_deg: float = Field(default=1, ge=0, le=10)
    gust_mps: float = Field(default=1, ge=0, le=20)
    opening_s: float = Field(default=0.15, gt=0, le=5)
    evidence: dict[str, str] = Field(default_factory=dict)


class Precision(Strict):
    altitude_error_m: float = Field(default=1.5, gt=0, le=20)
    attitude_error_deg: float = Field(default=1, gt=0, le=10)
    aero_allocation: float = Field(default=0.5, gt=0, lt=1)
    grid_relative_limit: float = Field(default=0.05, gt=0, le=0.2)
    temporal_relative_limit: float = Field(default=0.03, gt=0, le=0.2)
    structure_relative_limit: float = Field(default=0.05, gt=0, le=0.2)
    deflection_span_limit: float = Field(default=0.05, gt=0, le=0.2)
    maximum_incidence_deg: float = Field(default=15, gt=0, le=30)
    minimum_static_margin_cal: float = Field(default=1, gt=0, le=3)
    require_cfd: bool = True
    require_aero_audit: bool = True
    require_fem: bool = True


class SearchLimits(Strict):
    # Fixed before the run. The planner cannot expand these or edit precision rules.
    pressure_kpa: tuple[Annotated[float, Field(gt=0, le=1000)], ...] = (200, 250, 300, 350, 400)
    fills: tuple[Annotated[float, Field(gt=0, lt=1)], ...] = (0.20, 0.25, 0.30, 0.35)
    nozzle_mm: tuple[Annotated[float, Field(ge=1, le=40)], ...] = (7, 9, 11)
    allow_material_change: bool = True
    allow_geometry_change: bool = True
    max_versions: int = Field(default=6, ge=1, le=30)
    max_actions: int = Field(default=40, ge=1, le=200)
    budget_s: float = Field(default=3600, gt=0, le=86400)
    memory_gib: float = Field(default=8, gt=0, le=128)
    planner: Literal["local_llm", "baseline"] = "local_llm"
    fallback: Literal["stop", "baseline"] = "stop"
    planner_timeout_s: float = Field(default=90, gt=0, le=180)
