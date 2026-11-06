"""L0 backend: today's constants and Barrowman formulas behind the AeroBackend interface.

* cd: physics.water.DEFAULT_CD (or the design's own axial_drag_coefficient) for bottles and
  physics.solid.DEFAULT_CD for amateur rockets, referenced to the flight model's drag area,
  so passing it to simulate(cd=...) reproduces today's flight exactly.
* amateur: C_N_alpha and x_cp from physics.stability (nose + fins, Barrowman).
* bottle: the same Barrowman nose + fin terms on rocketwright.geometry's representative bottle
  shape (half-ellipse nose, four fins) or on the query's assembled shape.
  SIMPLIFICATION: the representative bottle's aft shoulder and neck are ignored.
"""

from __future__ import annotations

import math

from rocketwright.aero.base import AeroCase, AeroQuery, AeroResult, physics_ref_diameter_m
from rocketwright.geometry import airframe
from rocketwright.physics import solid, stability, water
from rocketwright.schema import AmateurDesign, BottleDesign, Design, FinSet

__all__ = ["BarrowmanBackend"]


class BarrowmanBackend:
    name = "barrowman"
    fidelity = "L0"
    cacheable = False

    def available(self) -> tuple[bool, str]:
        return True, "closed-form, always available"

    def supports(self, design: Design) -> tuple[bool, str]:
        if isinstance(design, AmateurDesign | BottleDesign):
            return True, ""
        return False, "aero covers the bottle and amateur tiers only"

    def evaluate(self, query: AeroQuery) -> AeroResult:
        design = query.design
        ok, why = self.supports(design)
        if not ok:
            raise ValueError(why)
        geo = airframe(design, shape=query.shape).params
        cg = query.cg_from_nose_m if query.cg_from_nose_m is not None else geo["cg_from_nose_m"]
        d_phys = physics_ref_diameter_m(design)
        notes: list[str] = []
        if isinstance(design, AmateurDesign):
            cd = solid.DEFAULT_CD
            cn_n, _ = stability.nose_normal_force(design)
            cn_f, _ = stability.fin_normal_force(design)
            cn_alpha = cn_n + cn_f
            x_cp = stability.center_of_pressure_m(design)
            source = "physics.solid.DEFAULT_CD + physics.stability (Barrowman)"
        else:
            cd = design.axial_drag_coefficient or water.DEFAULT_CD
            if design.axial_drag_coefficient:
                notes.append("cd is the design's own axial_drag_coefficient")
            d_geo = geo["body_diameter_m"]
            cn_n = stability.NOSE_CN
            x_n = stability.NOSE_CP_FRACTION[geo["nose_shape"]] * geo["nose_length_m"]
            cn_f, x_f = 0.0, 0.0
            if geo["fin_count"]:
                fins = FinSet(
                    count=geo["fin_count"],
                    root_chord_m=geo["fin_root_chord_m"],
                    tip_chord_m=geo["fin_tip_chord_m"],
                    span_m=geo["fin_span_m"],
                    sweep_m=geo["fin_sweep_m"],
                )
                cn_f, x_f = stability.trapezoidal_fin_force(
                    d_geo, fins, geo["fin_root_le_from_nose_m"]
                )
            x_cp = (cn_n * x_n + cn_f * x_f) / (cn_n + cn_f)
            # Barrowman's C_N is per pi d_geo^2 / 4: re-reference to the drag area.
            cn_alpha = (cn_n + cn_f) * (d_geo / d_phys) ** 2
            source = "physics.water.DEFAULT_CD + Barrowman nose/fins on geometry.py's bottle shape"
            if query.shape is None:
                notes.append(
                    "bottle shoulder and neck ignored in C_N_alpha / x_cp (SIMPLIFICATION)"
                )
        margin = None if cg is None else (x_cp - cg) / d_phys
        cases = [
            AeroCase(
                speed_mps=query.speed_mps,
                alpha_deg=a,
                cd=cd,
                cn=cn_alpha * math.radians(a),
                cm=cn_alpha * math.radians(a) * x_cp / d_phys,
            )
            for a in query.alphas_deg
        ]
        notes.append("subsonic, small angle, speed-independent")
        return AeroResult(
            cd=cd,
            cn_alpha_per_rad=cn_alpha,
            x_cp_from_nose_m=x_cp,
            static_margin_cal=margin,
            cg_from_nose_m=cg,
            ref_diameter_m=d_phys,
            per_case=cases,
            backend=self.name,
            fidelity="L0",
            provisional=True,
            notes=notes,
            source=source,
            wall_time_s=0.0,
        )
