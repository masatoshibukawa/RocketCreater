from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class LoadConfig(Strict):
    ambient_pa: float = Field(default=101085, gt=0)
    initial_k: float = Field(default=293.15, gt=200, lt=400)
    ambient_k: float = Field(default=293.15, gt=200, lt=400)
    gamma: float = Field(default=1.4, gt=1, lt=2)
    gas_r: float = Field(default=287.05, gt=0)
    discharge_coefficient: float = Field(default=0.9, gt=0, le=1)
    gas_wall_h: float = Field(default=30, ge=0)
    outside_h: float = Field(default=10, ge=0)
    wall_area_m2: float = Field(default=0.08, gt=0)
    wall_capacity_j_k: float = Field(default=54, gt=0)
    initial_wall_k: float = Field(default=293.15, gt=200, lt=400)
    max_time_s: float = Field(default=5, gt=0, le=60)


class ContactConfig(Strict):
    support_kg: float = Field(default=0.02, gt=0)
    wall_k: float = Field(default=2500, gt=0)
    wall_c: float = Field(default=1.0, ge=0)
    pad_k: float = Field(default=600, gt=0)
    pad_c: float = Field(default=0.6, ge=0)
    pad_cubic: float = Field(default=1e6, ge=0)
    gap_m: float = Field(default=0.008, gt=0)
    stop_k: float = Field(default=2e6, gt=0)
    stop_c: float = Field(default=200, ge=0)
    contact_area_m2: float = Field(default=0.0003, gt=0)
    max_step_s: float = Field(default=0.0002, gt=0, le=0.01)


class Material(Strict):
    young_pa: float = Field(default=2e9, gt=0)
    poisson: float = Field(default=0.3, gt=-1, lt=0.5)
    density: float = Field(default=1200, gt=0)
    cte: float = Field(default=6e-5, ge=0)
    warm_ratio: float = Field(default=0.5, gt=0, le=1)
    reference_c: float = 20
    warm_c: float = 55
    yield_pa: float | None = Field(default=None, gt=0)
    hardening_pa: float = Field(default=1e8, gt=0)
    # These values remain absent until an actual applicable material record exists.
    tensile_allowable_pa: float | None = Field(default=None, gt=0)
    compressive_allowable_pa: float | None = Field(default=None, gt=0)
    evidence_id: str | None = None
    # E1,E2,E3,nu12,nu13,nu23,G12,G13,G23 in fixed part-coordinate axes.
    engineering_constants: (
        tuple[float, float, float, float, float, float, float, float, float] | None
    ) = None

    @model_validator(mode="after")
    def ordered_temperature(self):
        if self.warm_c <= self.reference_c:
            raise ValueError("warm_c must exceed reference_c")
        if self.engineering_constants is not None:
            import numpy as np

            e1, e2, e3, n12, n13, n23, g12, g13, g23 = self.engineering_constants
            if min(e1, e2, e3, g12, g13, g23) <= 0:
                raise ValueError("Orthotropic moduli must be positive")
            compliance = np.array(
                [
                    [1 / e1, -n12 / e1, -n13 / e1],
                    [-n12 / e1, 1 / e2, -n23 / e2],
                    [-n13 / e1, -n23 / e2, 1 / e3],
                ]
            )
            if min(np.linalg.eigvalsh(compliance)) <= 0 or self.yield_pa is not None:
                raise ValueError("Invalid orthotropy or unsupported anisotropic plasticity")
        return self


class FlightConfig(Strict):
    wind_mps: float = Field(default=2, ge=0, le=30)
    gust_mps: float = Field(default=1, ge=0, le=20)
    cant_deg: float = Field(default=0.5, ge=-5, le=5)
    initial_tilt_deg: float = Field(default=1, ge=0, le=10)
    rail_m: float = Field(default=1.5, gt=0)
    pitch_damping: float = Field(default=10, ge=0)
    opening_s: float = Field(default=0.15, gt=0, le=5)
    deployment_delay_s: float = Field(default=0, ge=0, le=10)
    stop_distance_m: float = Field(default=0.015, gt=0)
    maximum_time_s: float = Field(default=60, gt=1, le=300)
    aero_angle_limit_deg: float = Field(default=15, gt=0, le=30)
    sample_count: int = Field(default=8, ge=1, le=64)
    seed: int = 64731


class AnalysisConfig(Strict):
    loads: LoadConfig = Field(default_factory=LoadConfig)
    contact: ContactConfig = Field(default_factory=ContactConfig)
    material: Material = Field(default_factory=Material)
    fin_material: Material | None = None
    body_material: Material | None = None
    collar_material: Material | None = None
    flight: FlightConfig = Field(default_factory=FlightConfig)
    fin_thickness_m: float = Field(default=0.001, gt=0, le=0.02)
    fin_root_k_n_m: float = Field(default=5e5, gt=0)
    body_thickness_m: float = Field(default=0.0003, gt=0, le=0.01)
    collar_support_k_n_m: float = Field(default=2e6, gt=0)
    surface_absorptivity: float = Field(default=0.8, ge=0, le=1)
    solar_w_m2: float = Field(default=800, ge=0)
    warm_wait_s: float = Field(default=600, ge=0, le=3600)
    pressure_hold_s: float = Field(default=60, ge=0, le=3600)
    creep_reference_rate_per_s: float | None = Field(default=None, ge=0)
    creep_reference_stress_pa: float = Field(default=30e6, gt=0)
    creep_exponent: float = Field(default=3, ge=1, le=10)
    observable_relative_tolerance: float = Field(default=0.05, gt=0, le=0.2)
    maximum_mesh_level: int = Field(default=3, ge=2, le=4)
