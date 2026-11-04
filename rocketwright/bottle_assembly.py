"""Material selection, geometry and conditional stability for the egg prototype."""

from __future__ import annotations

import math
from functools import cache
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field
from scipy.linalg import eigvalsh, solve_continuous_lyapunov

from rocketwright.physics.stability import trapezoidal_fin_force
from rocketwright.physics.water import DEFAULT_CD
from rocketwright.schema import FinSet


@cache
def catalog():
    directory = Path(__file__).with_name("catalog")
    recipe = yaml.safe_load((directory / "bottle_build.yaml").read_text(encoding="utf-8"))
    resources = yaml.safe_load((directory / "bottle_resources.yaml").read_text(encoding="utf-8"))
    return recipe, {r["id"]: r for r in resources["items"]} | recipe["extra_resources"]


class BenchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    article_id: str = Field(min_length=1)
    record: str = Field(min_length=1)
    dry_mass_g: float = Field(gt=0)
    dry_cg_from_tip_mm: float = Field(gt=0)
    # Lower bound for both identified modes, with this payload, specimen and fixing.
    modal_zeta_lower: float | None = Field(default=None, ge=0, lt=1)


class Workshop(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    unavailable: set[str] = Field(default_factory=set)
    nozzle_options_mm: list[Literal[9, 22]] = Field(default_factory=lambda: [9, 22], min_length=1)
    pressure_ceiling_kpa: float = Field(default=500, gt=0, le=500)
    # construction key = architecture/nozzle/material variant (independent of fill and pressure)
    articles: dict[str, BenchRecord] = Field(default_factory=dict)

    def check_ids(self, architectures):
        recipe, resources = catalog()
        unknown = self.unavailable - resources.keys()
        valid = {f"{a}/{n}/{v}" for a in architectures for n in (9, 22) for v in recipe["variants"]}
        if unknown or self.articles.keys() - valid:
            raise ValueError("unknown workshop resource or construction key")


def assembly(design, architecture, nozzle_mm, variant, workshop):
    recipe, resources = catalog()
    kit = recipe["variants"][variant]
    g = dict(recipe["geometry_mm"])
    base_span = g["fin_span"]
    g["fin_span"] = kit.get("span_mm", base_span)
    length = sum(
        g[key]
        for key in (
            "nose_length",
            "egg_bay_length",
            "canopy_bay_length",
            "bottle_length",
            "skirt_overhang",
        )
    )
    bore = "open_neck" if nozzle_mm == 22 else "insert"
    film = recipe["film"]
    area = math.pi * (design.parachute_diameter_m / 2) ** 2
    groups = [
        *recipe["common"],
        *[(r, *recipe["options"][r]) for r in (kit["fin"], kit["pad"], bore)],
        (
            film["resource"],
            "正八角形1枚",
            area * film["density_g_m2_assumed"],
            film["purchase_jpy"],
            film["station_mm"],
        ),
    ]
    bill = [
        dict(
            id=r,
            name=resources[r]["name"],
            quantity=qty,
            mass_g=round(m * g["fin_span"] / base_span if r == kit["fin"] else m, 4),
            allowance_jpy=jpy,
            station_mm=x,
            basis=resources[r].get("source") or resources[r].get("basis"),
        )
        for r, qty, m, jpy, x in groups
    ]
    key = f"{architecture}/{nozzle_mm}/{variant}"
    record = workshop.articles.get(key)
    estimated = sum(row["mass_g"] for row in bill)
    mass = record.dry_mass_g if record else estimated
    dry_cg = (
        record.dry_cg_from_tip_mm
        if record
        else sum(row["mass_g"] * row["station_mm"] for row in bill) / mass
    )
    egg_g = design.payload_mass_kg * 1000
    egg_x = g["nose_length"] + g["egg_bay_length"] / 2
    dry_loaded_cg = (mass * dry_cg + egg_g * egg_x) / (mass + egg_g)
    water_g = design.bottle_volume_m3 * 1e6 * design.water_fill_frac
    wet_cg = ((mass + egg_g) * dry_loaded_cg + water_g * (length - 65)) / (mass + egg_g + water_g)
    f = FinSet(
        count=4,
        root_chord_m=g["fin_root"] / 1000,
        tip_chord_m=g["fin_tip"] / 1000,
        span_m=g["fin_span"] / 1000,
        sweep_m=g["fin_sweep"] / 1000,
    )
    cn, fin_cp = trapezoidal_fin_force(
        g["body_diameter"] / 1000, f, (length - g["fin_tail_inset"] - g["fin_root"]) / 1000
    )
    cp = (2 * g["nose_length"] * 2 / 3 + cn * fin_cp * 1000) / (2 + cn)
    # Reference Cd includes the original four fins. Add only extra wetted area,
    # using assumed skin friction Cf=0.006. Flight also brackets the assembled Cd.
    extra_area = 4 * (g["fin_root"] + g["fin_tip"]) * (g["fin_span"] - base_span)
    cd = DEFAULT_CD + 0.006 * extra_area / (math.pi * (g["body_diameter"] / 2) ** 2)
    mount = recipe["mount"]
    z = mount["modal_zeta"][kit["pad"]]
    if record and record.modal_zeta_lower is not None:
        z = record.modal_zeta_lower
    k, b = mount["pad_n_m"], mount["wall_n_m"]
    omegas = np.sqrt(
        eigvalsh([[b + k, -k], [-k, k]], np.diag([mount["support_g"] / 1000, egg_g / 1000]))
    )
    residual = math.sqrt((1 + z) / (1 - z)) * math.exp(-z * omegas[0] * mount["deadline_s"])
    arm = (cp - dry_loaded_cg) / 1000
    inertia = (mass + egg_g) / 1000 * (length / 1000) ** 2 / 12  # slender rod surrogate
    pitch_rate = None
    if arm > 0:
        w = math.sqrt(
            0.5
            * 1.2
            * 15**2
            * math.pi
            * (g["body_diameter"] / 2000) ** 2
            * (2 + cn)
            * arm
            / inertia
        )

        def matrix(stiff, damping):
            return w * np.array([[0.0, 1.0], [-stiff, -0.30 * damping]])

        nominal = matrix(1, 1)
        p = solve_continuous_lyapunov(nominal.T, -np.eye(2))
        if min(eigvalsh(p)) > 0:
            rates = []
            for speed_k in (14 / 15, 16 / 15):
                for speed_c in (14 / 15, 16 / 15):
                    a = matrix(speed_k**2, speed_c)
                    rates.append(min(eigvalsh(-(a.T @ p + p @ a), p)) / 2)
            pitch_rate = float(min(rates))
    ground = [*recipe["ground"]]
    if mass + egg_g > resources["and_hl_200i"]["facts"]["capacity_g"]:
        ground[ground.index("and_hl_200i")] = "and_hl_2000i"  # dry loaded mass to 1 g
    unavailable = sorted(({row["id"] for row in bill} | set(ground)) & workshop.unavailable)
    checks = {
        "resources_available_to_plan": not unavailable,
        "dry_cg_inside_vehicle": 0 < dry_cg < length,
        "payload_fits": (
            g["dummy_width"] + 2 * g["padding"] + g["fit_allowance"] <= g["bay_clear_diameter"]
            and g["dummy_length"] + 2 * g["padding"] + g["fit_allowance"] <= g["egg_bay_length"]
        ),
        # Check a further 15 mm aft water-centroid error, a design allowance.
        "static_restoring_dry_and_wet": cp
        > max(dry_loaded_cg, wet_cg + 15 * water_g / (mass + egg_g + water_g)),
        "pitch_common_certificate": pitch_rate is not None and pitch_rate > 0,
        "mount_settles": residual <= mount["residual_limit"],
    }
    return dict(
        key=key,
        variant=variant,
        bill=bill,
        ground=ground,
        unavailable=unavailable,
        dimensions_mm=g | {"overall": length},
        nozzle_interface=bore,
        canopy_side_mm=1000 * math.sqrt(area / (2 * (1 + math.sqrt(2)))),
        estimated_dry_mass_g=estimated,
        dry_mass_g=mass,
        estimated_outlay_jpy=sum(r["allowance_jpy"] for r in bill),
        dry_cg_mm=dry_cg,
        loaded_cg_mm=dry_loaded_cg,
        wet_cg_mm=wet_cg,
        cp_mm=cp,
        axial_cd=cd,
        mode_hz=(omegas / (2 * math.pi)).tolist(),
        zeta=z,
        mount_bound=residual,
        pitch_rate_per_s=pitch_rate,
        checks=checks,
        specimen=record.model_dump() if record else None,
    )
