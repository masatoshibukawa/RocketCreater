"""Static margin of a bottle rocket, with water loaded and empty (Barrowman, L0).

The flight model (`physics.water`) is a point mass and reports no margin, so without this the
design path never sees whether the vehicle restores itself. A fin part gives the real fin
count and span; the chords stay the representative ones because the catalog has no chords.
"""

from __future__ import annotations

from dataclasses import dataclass

from rocketwright import aero
from rocketwright.geometry import AssembledShape, airframe
from rocketwright.parts import BottleFinSet
from rocketwright.schema import BottleDesign, FinSet

__all__ = ["BottleStability", "bottle_stability"]

_QUERY_SPEED_MPS = 15.0  # Barrowman is speed independent; AeroQuery needs a value
_QUERY_ALPHAS_DEG = (0.0, 4.0)


@dataclass(frozen=True)
class BottleStability:
    wet_margin_cal: float
    dry_margin_cal: float
    x_cp_from_nose_m: float
    wet_cg_from_nose_m: float
    dry_cg_from_nose_m: float
    fins: str

    def warnings(self) -> list[str]:
        out = [f"stability: Barrowman estimate on {self.fins}; CG is estimated, not measured"]
        if self.wet_margin_cal <= 0:
            out.append(
                f"stability: margin {self.wet_margin_cal:.2f} cal with water loaded: "
                "the vehicle does not restore itself at liftoff"
            )
        if self.dry_margin_cal <= 0:
            out.append(
                f"stability: margin {self.dry_margin_cal:.2f} cal when empty: "
                "the vehicle does not restore itself during the coast"
            )
        return out


def _shape(design: BottleDesign, fin_set: BottleFinSet) -> AssembledShape:
    geo = airframe(design).params
    return AssembledShape(
        body_diameter_m=geo["body_diameter_m"],
        nose_length_m=geo["nose_length_m"],
        length_m=geo["length_m"],
        nose_shape=geo["nose_shape"],
        fins=FinSet(
            count=max(fin_set.count, 3),
            root_chord_m=geo["fin_root_chord_m"],
            tip_chord_m=geo["fin_tip_chord_m"],
            span_m=fin_set.span_m,
            sweep_m=geo["fin_sweep_m"],
        ),
    )


def _dry_cg_m(design: BottleDesign, length_m: float, nose_length_m: float) -> float:
    """geometry._bottle_cg without the water: dry mass spread evenly, payload at the nose base."""
    moment = design.dry_mass_kg * length_m / 2.0 + design.payload_mass_kg * nose_length_m
    return moment / (design.dry_mass_kg + design.payload_mass_kg)


def bottle_stability(
    design: BottleDesign, fin_set: BottleFinSet | None = None
) -> BottleStability | None:
    """None without fins: a finless bottle tumbles and physics.water models it that way."""
    if not design.has_fins:
        return None
    shape = None if fin_set is None else _shape(design, fin_set)
    geo = airframe(design, shape=shape).params

    def margin(cg_m: float) -> aero.AeroResult:
        query = aero.AeroQuery(
            design=design,
            speed_mps=_QUERY_SPEED_MPS,
            alphas_deg=_QUERY_ALPHAS_DEG,
            cg_from_nose_m=cg_m,
            shape=shape,
        )
        return aero.evaluate(query, backend="barrowman")

    dry_cg = _dry_cg_m(design, geo["length_m"], geo["nose_length_m"])
    wet, dry = margin(geo["cg_from_nose_m"]), margin(dry_cg)
    return BottleStability(
        wet_margin_cal=wet.static_margin_cal,
        dry_margin_cal=dry.static_margin_cal,
        x_cp_from_nose_m=wet.x_cp_from_nose_m,
        wet_cg_from_nose_m=geo["cg_from_nose_m"],
        dry_cg_from_nose_m=dry_cg,
        fins="representative fins" if fin_set is None else f"catalog fins {fin_set.id}",
    )
