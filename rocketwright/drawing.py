"""SVG side view of a design with dimension lines (CLAUDE.md section 5: `drawing.py`).

Pure string building, no external libraries, deterministic output (the same design always yields
the same SVG). All geometry is computed in SI metres and converted to pixels by a single scale
factor; labels are shown in mm for the bottle/amateur tiers and in m (2 decimals) for the
commercial/heavy tiers.

The vehicle is drawn horizontally, nose to the left, tail to the right, with dimension lines
below the body. Commercial/heavy drawings are concept sketches (CLAUDE.md section 4) and carry a
banner saying so.

Geometry simplifications (all documented in README "Simplifications"):

* SIMPLIFICATION: a bottle is drawn as a cylinder whose length is BOTTLE_ASPECT_RATIO times its
  diameter (d = (4 V / (pi * ratio))^(1/3)), plus a nose of 0.8 d and a neck of 0.3 d.
* SIMPLIFICATION: the amateur motor mount length comes from physics.solid.load_motor when that
  function exists; otherwise a placeholder of MOTOR_MOUNT_PLACEHOLDER_FRAC x body length.
* SIMPLIFICATION: each multistage stage is a cylinder of diameter
  DIAMETER_PER_CUBE_ROOT_KG * total_propellant^(1/3) (shared with physics.multistage when
  importable) and length = propellant mass / (PROPELLANT_BULK_DENSITY_KGPM3 * area); the
  fairing is FAIRING_LENGTH_DIAMETERS diameters long; boosters are drawn as BOOSTER_DIAMETER_FRAC
  x diameter cylinders alongside stage 1. Nozzles protrude beyond the dimensioned length.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any
from xml.sax.saxutils import escape

from rocketwright.schema import AmateurDesign, BottleDesign, Design, MultistageDesign

__all__ = [
    "BOTTLE_ASPECT_RATIO",
    "CONCEPT_BANNER",
    "DIAMETER_PER_CUBE_ROOT_KG_FALLBACK",
    "PROPELLANT_BULK_DENSITY_KGPM3",
    "render_side_view_svg",
]

# SIMPLIFICATION: PET bottle shape as a cylinder with this length/diameter ratio (a 1.5 L bottle
# comes out at ~82 mm x 286 mm; real bottles are ~90 mm x 300 mm).
BOTTLE_ASPECT_RATIO = 3.5
BOTTLE_NOSE_DIAMETERS = 0.8
BOTTLE_NECK_DIAMETERS = 0.3

# SIMPLIFICATION: used when physics.solid.load_motor is not available yet.
MOTOR_MOUNT_PLACEHOLDER_FRAC = 0.2

# SIMPLIFICATION: multistage sketch proportions (see module docstring).
DIAMETER_PER_CUBE_ROOT_KG_FALLBACK = 0.05
PROPELLANT_BULK_DENSITY_KGPM3 = 1000.0
FAIRING_LENGTH_DIAMETERS = 2.5
BOOSTER_DIAMETER_FRAC = 0.4
BOOSTER_LENGTH_FRAC = 0.6  # of stage-1 length when the booster catalog is unavailable
NOZZLE_LENGTH_DIAMETERS = 0.25
MAX_DRAWN_ENGINES = 9

CONCEPT_BANNER = "Concept sketch — not for manufacturing"

_FONT = 'font-family="Helvetica, Arial, sans-serif"'
_BODY_FILL = "#e8edf3"
_STROKE = "#1f2a37"
_DIM = "#c0392b"
_WATER = "#7fb3e6"
_MUTED = "#6b7785"

# Layout (pixels at width_px = 800; everything scales with width_px / 800).
_MARGIN_X = 70.0
_TOP = 44.0  # title + banner area
_DIM_GAP = 26.0  # vertical spacing between stacked dimension lines
_SCALE_BAR_H = 40.0


# --------------------------------------------------------------------------- primitives


def _f(x: float) -> str:
    """Fixed 1-decimal pixel formatting keeps the output short and deterministic."""
    return f"{x:.1f}"


class _Canvas:
    """Accumulates SVG elements; `y` grows downward."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke: str = _STROKE,
        w: float = 1.2,
        dash: str | None = None,
    ) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
            f'stroke="{stroke}" stroke-width="{w}"{d}/>'
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str = _BODY_FILL,
        rx: float = 0.0,
        stroke: str = _STROKE,
        dash: str | None = None,
        cls: str | None = None,
    ) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        c = f' class="{cls}"' if cls else ""
        r = f' rx="{_f(rx)}"' if rx else ""
        self.add(
            f'<rect{c} x="{_f(x)}" y="{_f(y)}" width="{_f(max(w, 0.0))}" height="{_f(max(h, 0.0))}"'
            f'{r} fill="{fill}" stroke="{stroke}" stroke-width="1.2"{d}/>'
        )

    def polygon(
        self,
        pts: Sequence[tuple[float, float]],
        fill: str = _BODY_FILL,
        stroke: str = _STROKE,
        cls: str | None = None,
    ) -> None:
        c = f' class="{cls}"' if cls else ""
        p = " ".join(f"{_f(x)},{_f(y)}" for x, y in pts)
        self.add(f'<polygon{c} points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')

    def path(
        self, d: str, fill: str = "none", stroke: str = _STROKE, cls: str | None = None
    ) -> None:
        c = f' class="{cls}"' if cls else ""
        self.add(f'<path{c} d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 11.0,
        anchor: str = "middle",
        fill: str = _STROKE,
        weight: str = "normal",
    ) -> None:
        self.add(
            f'<text x="{_f(x)}" y="{_f(y)}" font-size="{_f(size)}" text-anchor="{anchor}" '
            f'fill="{fill}" font-weight="{weight}" {_FONT}>{escape(s)}</text>'
        )

    def dim_h(
        self, x1: float, x2: float, y: float, label: str, ext_from: float | None = None
    ) -> None:
        """Horizontal dimension line between x1 and x2 at height y with extension lines."""
        if ext_from is not None:
            self.line(x1, ext_from, x1, y + 4, _DIM, 0.8)
            self.line(x2, ext_from, x2, y + 4, _DIM, 0.8)
        self.line(x1, y, x2, y, _DIM, 1.0)
        self._arrow(x1, y, +1)
        self._arrow(x2, y, -1)
        self.text((x1 + x2) / 2.0, y - 4, label, 11, fill=_DIM)

    def dim_v(
        self, x: float, y1: float, y2: float, label: str, ext_from: float | None = None
    ) -> None:
        """Vertical dimension line (label to the right of the line)."""
        if ext_from is not None:
            self.line(ext_from, y1, x + 4, y1, _DIM, 0.8)
            self.line(ext_from, y2, x + 4, y2, _DIM, 0.8)
        self.line(x, y1, x, y2, _DIM, 1.0)
        self._arrow_v(x, y1, +1)
        self._arrow_v(x, y2, -1)
        self.text(x + 6, (y1 + y2) / 2.0 + 4, label, 11, anchor="start", fill=_DIM)

    def _arrow(self, x: float, y: float, direction: int) -> None:
        s = 6.0 * direction
        self.polygon([(x, y), (x + s, y - 2.5), (x + s, y + 2.5)], fill=_DIM, stroke=_DIM)

    def _arrow_v(self, x: float, y: float, direction: int) -> None:
        s = 6.0 * direction
        self.polygon([(x, y), (x - 2.5, y + s), (x + 2.5, y + s)], fill=_DIM, stroke=_DIM)

    def mark(self, x: float, y: float, label: str, fill: str) -> None:
        """CP / CG style marker: a circle with a cross and a label above."""
        self.add(
            f'<circle cx="{_f(x)}" cy="{_f(y)}" r="6" fill="{fill}" '
            f'stroke="{_STROKE}" stroke-width="1"/>'
        )
        self.line(x - 6, y, x + 6, y, _STROKE, 1.0)
        self.line(x, y - 6, x, y + 6, _STROKE, 1.0)
        self.text(x, y - 9, label, 10, weight="bold")


def _label_mm(value_m: float) -> str:
    return f"{value_m * 1000.0:.0f} mm"


def _label_m(value_m: float) -> str:
    return f"{value_m:.2f} m"


def _nice_scale_bar_m(total_length_m: float) -> float:
    """A 1-2-5 series length roughly a quarter of the vehicle length."""
    target = total_length_m / 4.0
    exp = math.floor(math.log10(target)) if target > 0 else 0
    for mult in (1.0, 2.0, 5.0, 10.0):
        candidate = mult * 10.0**exp
        if candidate >= target:
            return candidate
    return 10.0**exp


def _nose_points(
    x0: float, length: float, radius: float, cy: float, shape: str, n: int = 24
) -> list[tuple[float, float]]:
    """Outline of a nose cone with the tip at x0 and the base at x0 + length (top half then
    bottom half, closed by the caller)."""
    top: list[tuple[float, float]] = []
    for i in range(n + 1):
        s = length * i / n  # distance from the tip
        if shape == "conical":
            r = radius * s / length
        elif shape == "elliptical":
            u = (length - s) / length
            r = radius * math.sqrt(max(0.0, 1.0 - u * u))
        else:  # tangent ogive
            rho = (radius**2 + length**2) / (2.0 * radius)
            r = math.sqrt(max(0.0, rho**2 - (length - s) ** 2)) + radius - rho
        top.append((x0 + s, cy - r))
    bottom = [(x, cy + (cy - y)) for x, y in reversed(top[:-1])]
    return top + bottom


def _header(c: _Canvas, width: float, title: str, subtitle: str, banner: bool) -> None:
    c.text(_MARGIN_X / 2.0, 18, title, 14, anchor="start", weight="bold")
    c.text(_MARGIN_X / 2.0, 34, subtitle, 10, anchor="start", fill=_MUTED)
    if banner:
        c.text(
            width - _MARGIN_X / 2.0, 18, CONCEPT_BANNER, 12, anchor="end", fill=_DIM, weight="bold"
        )


def _scale_bar(
    c: _Canvas, x: float, y: float, scale: float, total_length_m: float, metric: bool
) -> None:
    bar_m = _nice_scale_bar_m(total_length_m)
    w = bar_m * scale
    c.line(x, y, x + w, y, _STROKE, 2.0)
    c.line(x, y - 4, x, y + 4, _STROKE, 1.0)
    c.line(x + w, y - 4, x + w, y + 4, _STROKE, 1.0)
    label = _label_m(bar_m) if metric else _label_mm(bar_m)
    c.text(x + w / 2.0, y - 6, f"Scale bar {label}", 10, fill=_MUTED)


def _finish(c: _Canvas, width: float, height: float, title: str) -> str:
    body = "\n".join(c.parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" style="max-width:100%;height:auto" role="img">\n'
        f"<title>{escape(title)}</title>\n"
        f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>\n'
        f"{body}\n</svg>\n"
    )


# --------------------------------------------------------------------------- optional physics hooks


def _motor_info(design: AmateurDesign) -> tuple[float, float | None, bool]:
    """(length_m, mass_kg or None, from_catalog). Lazy import: physics.solid may be a stub."""
    try:
        from rocketwright.physics import solid

        loader = getattr(solid, "load_motor", None)
        if loader is not None:
            motor: Any = loader(design.motor_id)

            def attr(name: str) -> float | None:
                v = motor.get(name) if isinstance(motor, dict) else getattr(motor, name, None)
                return float(v) if isinstance(v, (int, float)) and v > 0 else None

            length = attr("length_m")
            if length is None and attr("length_mm") is not None:
                length = (attr("length_mm") or 0.0) / 1000.0
            if length is not None:
                return length, attr("total_mass_kg") or attr("mass_kg"), True
    except Exception:
        pass
    return MOTOR_MOUNT_PLACEHOLDER_FRAC * design.body_length_m, None, False


def _cp_cg_m(
    design: AmateurDesign, motor_mass_kg: float | None, motor_length_m: float
) -> tuple[float | None, float | None]:
    """Centre of pressure / gravity from the nose tip when physics.stability exposes them.
    The CG needs the motor mass (stability.center_of_gravity_m); without a catalog motor it is
    omitted rather than guessed."""
    try:
        from rocketwright.physics import stability
    except Exception:
        return None, None
    cp: float | None = None
    cg: float | None = None
    fn = getattr(stability, "center_of_pressure_m", None)
    if fn is not None:
        try:
            cp = float(fn(design))
        except Exception:
            cp = None
    fn = getattr(stability, "center_of_gravity_m", None)
    if fn is not None and motor_mass_kg is not None:
        try:
            cg = float(fn(design, motor_mass_kg, motor_length_m=motor_length_m))
        except Exception:
            cg = None
    return cp, cg


def _multistage_diameter_const() -> float:
    try:
        from rocketwright.physics import multistage

        return float(
            getattr(multistage, "DIAMETER_PER_CUBE_ROOT_KG", DIAMETER_PER_CUBE_ROOT_KG_FALLBACK)
        )
    except Exception:
        return DIAMETER_PER_CUBE_ROOT_KG_FALLBACK


def _booster_propellant_kg(booster_id: str) -> float | None:
    try:
        from rocketwright.physics import multistage

        spec = multistage.get_engine(booster_id, kind="booster")
        v = getattr(spec, "propellant_mass_kg", None)
        return float(v) if isinstance(v, (int, float)) and v > 0 else None
    except Exception:
        return None


# --------------------------------------------------------------------------- tiers


def _render_amateur(design: AmateurDesign, width: float) -> str:
    c = _Canvas()
    fins = design.fins
    total_m = design.nose_length_m + design.body_length_m
    radius_m = design.body_diameter_m / 2.0
    draw_w = width - 2 * _MARGIN_X
    scale = draw_w / total_m  # px per m
    half_h = (radius_m + fins.span_m) * scale
    cy = _TOP + 30 + max(half_h, 30.0)
    x0 = _MARGIN_X
    x_nose_base = x0 + design.nose_length_m * scale
    x_tail = x0 + total_m * scale
    r = radius_m * scale
    body_top = cy - r
    body_bot = cy + r

    _header(
        c,
        width,
        "Amateur rocket — side view",
        f"nose {design.nose_shape}, {fins.count} fins, motor {design.motor_id}",
        banner=False,
    )
    # fins (two visible in side view)
    x_r0 = x_tail - fins.root_chord_m * scale
    sweep = fins.sweep_m * scale
    tip = fins.tip_chord_m * scale
    span = fins.span_m * scale
    for sign in (-1, 1):
        y_root = body_top if sign < 0 else body_bot
        y_tip = y_root + sign * span
        c.polygon(
            [(x_r0, y_root), (x_r0 + sweep, y_tip), (x_r0 + sweep + tip, y_tip), (x_tail, y_root)],
            fill="#cfd8e3",
            cls="fin",
        )
    # body tube and nose
    c.rect(x_nose_base, body_top, x_tail - x_nose_base, 2 * r, cls="body")
    c.polygon(
        _nose_points(x0, design.nose_length_m * scale, r, cy, design.nose_shape),
        cls=f"nose {design.nose_shape}",
    )
    # motor mount (dashed) at the aft end
    motor_len_m, motor_mass_kg, from_catalog = _motor_info(design)
    motor_len_m = min(motor_len_m, design.body_length_m)
    mr = min(r * 0.7, r - 2.0)
    c.rect(
        x_tail - motor_len_m * scale,
        cy - mr,
        motor_len_m * scale,
        2 * mr,
        fill="none",
        dash="4 3",
        cls="motor-mount",
    )
    # CP / CG marks when physics.stability provides positions (measured from the nose tip)
    cp, cg = _cp_cg_m(design, motor_mass_kg, motor_len_m)
    if cg is not None and 0 <= cg <= total_m:
        c.mark(x0 + cg * scale, cy, "CG", "#f4d35e")
    if cp is not None and 0 <= cp <= total_m:
        c.mark(x0 + cp * scale, cy, "CP", "#ee964b")

    # dimension lines below
    y = cy + half_h + 24
    c.dim_h(x_r0, x_tail, y, _label_mm(fins.root_chord_m), ext_from=body_bot + span)
    y += _DIM_GAP
    c.dim_h(x_nose_base, x_tail, y, _label_mm(design.body_length_m), ext_from=body_bot)
    y += _DIM_GAP
    c.dim_h(x0, x_nose_base, y, _label_mm(design.nose_length_m), ext_from=cy)
    y += _DIM_GAP
    c.dim_h(x0, x_tail, y, _label_mm(total_m), ext_from=cy)
    # fin tip chord above the top fin
    y_top_tip = body_top - span
    c.dim_h(
        x_r0 + sweep,
        x_r0 + sweep + tip,
        y_top_tip - 10,
        _label_mm(fins.tip_chord_m),
        ext_from=y_top_tip,
    )
    # vertical dimensions on the right: diameter and fin span
    xd = x_tail + 18
    c.dim_v(xd, body_top, body_bot, _label_mm(design.body_diameter_m), ext_from=x_tail)
    c.dim_v(xd + 2, body_bot, body_bot + span, _label_mm(fins.span_m), ext_from=x_tail)

    # legend
    y += 18
    legend = [
        f"Fins x{fins.count} (two shown), sweep {_label_mm(fins.sweep_m)}, "
        f"thickness {_label_mm(fins.thickness_m)}",
        f"Motor mount {design.motor_id}: {_label_mm(motor_len_m)}"
        + ("" if from_catalog else " (placeholder length)"),
        f"Parachute Ø {design.parachute_diameter_m:.2f} m (packed, not drawn), "
        f"deploy delay {design.deploy_delay_s:.1f} s",
        f"Dry mass {design.dry_mass_kg:.3f} kg, payload {design.payload_mass_kg:.3f} kg",
    ]
    for s in legend:
        c.text(_MARGIN_X / 2.0, y, s, 10, anchor="start", fill=_MUTED)
        y += 14
    y += 10
    _scale_bar(c, _MARGIN_X, y + 14, scale, total_m, metric=False)
    return _finish(c, width, y + _SCALE_BAR_H, f"Amateur rocket side view, motor {design.motor_id}")


def _render_bottle(design: BottleDesign, width: float) -> str:
    c = _Canvas()
    d_m = (4.0 * design.bottle_volume_m3 / (math.pi * BOTTLE_ASPECT_RATIO)) ** (1.0 / 3.0)
    body_m = BOTTLE_ASPECT_RATIO * d_m
    nose_m = BOTTLE_NOSE_DIAMETERS * d_m
    neck_m = BOTTLE_NECK_DIAMETERS * d_m
    if design.geometry:
        d_m = design.geometry.body_diameter_mm / 1000
        body_m = design.geometry.nose_base_mm / 1000
        nose_m = design.geometry.nose_length_mm / 1000
        neck_m = 0
    total_m = nose_m + body_m + neck_m
    fin_span_m = 0.8 * d_m if design.has_fins else 0.0  # SIMPLIFICATION: representative fin size
    if design.geometry and design.has_fins:
        fin_span_m = design.geometry.fin_span_mm / 1000
    draw_w = width - 2 * _MARGIN_X
    scale = draw_w / total_m
    r = d_m / 2.0 * scale
    half_h = r + fin_span_m * scale + (30.0 if design.has_parachute else 0.0)
    cy = _TOP + 30 + max(half_h, 30.0)
    x0 = _MARGIN_X
    x_body0 = x0 + nose_m * scale
    x_body1 = x_body0 + body_m * scale
    x_tail = x_body1 + neck_m * scale
    body_top, body_bot = cy - r, cy + r

    _header(
        c,
        width,
        "Water rocket (PET bottle) — side view",
        f"{design.bottle_volume_m3 * 1000:.2f} L bottle, "
        f"{design.water_fill_frac * 100:.0f} % water, "
        f"{design.initial_gauge_pressure_pa / 1000:.0f} kPa gauge",
        banner=False,
    )
    # fins
    if design.has_fins:
        root = 1.0 * d_m * scale
        tail = x_body1
        sweep, tip = 0.65 * root, 0.35 * root
        if design.geometry:
            root = design.geometry.fin_root_mm / 1000 * scale
            tail = x_tail - design.geometry.fin_tail_inset_mm / 1000 * scale
            sweep = design.geometry.fin_sweep_mm / 1000 * scale
            tip = design.geometry.fin_tip_mm / 1000 * scale
        span = fin_span_m * scale
        for sign in (-1, 1):
            y_root = body_top if sign < 0 else body_bot
            c.polygon(
                [
                    (tail - root, y_root),
                    (tail - root + sweep, y_root + sign * span),
                    (tail - root + sweep + tip, y_root + sign * span),
                    (tail, y_root),
                ],
                fill="#cfd8e3",
                cls="fin",
            )
    # bottle body (rounded) and water level (water sits at the nozzle end while standing on the pad)
    c.rect(x_body0, body_top, x_body1 - x_body0, 2 * r, rx=r * 0.35, cls="body")
    water_w = (x_body1 - x_body0) * design.water_fill_frac
    c.rect(
        x_body1 - water_w,
        body_top + 1.5,
        water_w,
        2 * r - 3.0,
        fill=_WATER,
        stroke="none",
        cls="water",
    )
    c.line(x_body1 - water_w, body_top, x_body1 - water_w, body_bot, "#2c6fb0", 1.0, dash="3 2")
    c.text(
        x_body1 - water_w / 2.0,
        cy + 4,
        f"water {design.water_fill_frac * 100:.0f} %",
        10,
        fill="#1b4f7f",
    )
    # nose cone (half-ellipse)
    c.polygon(_nose_points(x0, nose_m * scale, r, cy, "elliptical"), cls="nose")
    # neck and nozzle
    nr = max(design.nozzle_diameter_m / 2.0 * scale, 1.5)
    neck_r = min(r * 0.45, max(nr * 2.0, 4.0))
    c.rect(x_body1, cy - neck_r, x_tail - x_body1, 2 * neck_r, cls="neck")
    c.rect(
        x_tail - 0.35 * (x_tail - x_body1),
        cy - nr,
        0.35 * (x_tail - x_body1),
        2 * nr,
        fill="#9aa7b5",
        cls="nozzle",
    )
    # parachute icon above the nose
    if design.has_parachute:
        px, py = x0 + nose_m * scale * 0.6, body_top - 22
        c.path(
            f"M {_f(px - 16)} {_f(py)} A 16 16 0 0 1 {_f(px + 16)} {_f(py)} Z",
            fill="#f6c7a6",
            cls="parachute",
        )
        for dx in (-16, 0, 16):
            c.line(px + dx, py, px, py + 14, _STROKE, 0.8)
        c.text(
            px + 24,
            py - 2,
            f"Parachute Ø {design.parachute_diameter_m or 0:.2f} m",
            10,
            anchor="start",
            fill=_MUTED,
        )

    # dimensions
    y = cy + half_h + 24
    c.dim_h(x_body0, x_body1, y, _label_mm(body_m), ext_from=body_bot)
    y += _DIM_GAP
    c.dim_h(x0, x_tail, y, _label_mm(total_m), ext_from=cy)
    xd = x_tail + 18
    c.dim_v(xd, body_top, body_bot, _label_mm(d_m), ext_from=x_body1)
    c.dim_v(xd + 2, cy - nr, cy + nr, _label_mm(design.nozzle_diameter_m), ext_from=x_tail)
    c.text(xd + 6, cy + nr + 26, "nozzle", 9, anchor="start", fill=_MUTED)

    y += 18
    legend = [
        f"Bottle length estimated from volume with aspect ratio {BOTTLE_ASPECT_RATIO:.1f} "
        "(SIMPLIFICATION)",
        f"Dry mass {design.dry_mass_kg:.3f} kg, payload {design.payload_mass_kg:.3f} kg, "
        f"fins: {'yes' if design.has_fins else 'no'}, "
        f"parachute: {'yes' if design.has_parachute else 'no'}",
    ]
    for s in legend:
        c.text(_MARGIN_X / 2.0, y, s, 10, anchor="start", fill=_MUTED)
        y += 14
    y += 10
    _scale_bar(c, _MARGIN_X, y + 14, scale, total_m, metric=False)
    return _finish(c, width, y + _SCALE_BAR_H, "Water rocket side view")


def _render_multistage(design: MultistageDesign, width: float) -> str:
    c = _Canvas()
    k = _multistage_diameter_const()
    booster_prop = 0.0
    booster_len_m: float | None = None
    for b in design.boosters:
        per = _booster_propellant_kg(b.booster_id)
        if per is not None:
            booster_prop += per * b.count
    total_prop = sum(s.propellant_mass_kg for s in design.stages) + booster_prop
    d_m = k * total_prop ** (1.0 / 3.0)
    area = math.pi * d_m**2 / 4.0
    stage_len_m = [
        s.propellant_mass_kg / (PROPELLANT_BULK_DENSITY_KGPM3 * area) for s in design.stages
    ]
    fairing_m = FAIRING_LENGTH_DIAMETERS * d_m
    total_m = fairing_m + sum(stage_len_m)
    nozzle_m = NOZZLE_LENGTH_DIAMETERS * d_m
    if design.boosters:
        bd_m = BOOSTER_DIAMETER_FRAC * d_m
        per = _booster_propellant_kg(design.boosters[0].booster_id)
        if per is not None:
            booster_len_m = per / (PROPELLANT_BULK_DENSITY_KGPM3 * math.pi * bd_m**2 / 4.0)
        else:
            booster_len_m = BOOSTER_LENGTH_FRAC * stage_len_m[0]
        booster_len_m = min(booster_len_m, stage_len_m[0])
    else:
        bd_m = 0.0

    draw_w = width - 2 * _MARGIN_X
    scale = draw_w / (total_m + nozzle_m)
    r = d_m / 2.0 * scale
    br = bd_m / 2.0 * scale
    half_h = r + (2 * br + 4 if design.boosters else 0.0)
    cy = _TOP + 30 + max(half_h, 40.0)
    x0 = _MARGIN_X
    body_top, body_bot = cy - r, cy + r

    tier_name = "Heavy-lift" if design.tier == "heavy" else "Commercial"
    _header(
        c,
        width,
        f"{tier_name} launch vehicle — side view",
        f"{len(design.stages)} stages, payload {design.payload_mass_kg:.0f} kg, "
        f"fairing {design.fairing_mass_kg:.0f} kg",
        banner=True,
    )
    # stages from the tail (right) to the fairing (left): stage 1 is at the tail
    x_tail = x0 + total_m * scale
    x = x_tail
    stage_x: list[tuple[float, float]] = []
    for i, length_m in enumerate(stage_len_m):
        w = length_m * scale
        stage_x.append((x - w, x))
        fill = "#e8edf3" if i % 2 == 0 else "#d9e1ea"
        c.rect(x - w, body_top, w, 2 * r, fill=fill, cls=f"stage stage-{i + 1}")
        c.text(
            (x - w + x) / 2.0,
            cy + 4,
            f"Stage {i + 1}: {design.stages[i].engine_id} x{design.stages[i].engine_count}",
            10,
        )
        # engine bells at the aft end of each stage (count capped; label carries the real count)
        n = min(design.stages[i].engine_count, MAX_DRAWN_ENGINES)
        bell_w = nozzle_m * scale
        pitch = (2 * r) / max(n, 1)
        for j in range(n):
            yc = body_top + pitch * (j + 0.5)
            bh = min(pitch * 0.8, r * 0.6)
            c.polygon(
                [
                    (x, yc - bh * 0.35),
                    (x + bell_w, yc - bh / 2.0),
                    (x + bell_w, yc + bh / 2.0),
                    (x, yc + bh * 0.35),
                ],
                fill="#9aa7b5",
                cls="engine",
            )
        x -= w
    x_fairing_base = x
    # fairing (ogive) with the payload hint inside
    c.polygon(_nose_points(x0, fairing_m * scale, r, cy, "ogive"), fill="#f3f6f9", cls="fairing")
    c.text(x0 + fairing_m * scale * 0.55, cy + 4, "fairing", 10, fill=_MUTED)
    # boosters alongside stage 1 (one drawn on each side; label has the count)
    if design.boosters and booster_len_m is not None:
        bw = booster_len_m * scale
        bx0 = x_tail - bw
        label = ", ".join(f"{b.booster_id} x{b.count}" for b in design.boosters)
        for sign in (-1, 1):
            yb = body_top - 2 * br - 2 if sign < 0 else body_bot + 2
            c.rect(bx0, yb, bw, 2 * br, fill="#d9e1ea", rx=br * 0.5, cls="booster")
            c.polygon(
                [
                    (bx0 + bw, yb + br * 0.6),
                    (bx0 + bw + br * 0.8, yb + br * 0.3),
                    (bx0 + bw + br * 0.8, yb + br * 1.7),
                    (bx0 + bw, yb + br * 1.4),
                ],
                fill="#9aa7b5",
                cls="engine",
            )
        c.text(bx0 + bw / 2.0, body_top - 2 * br - 8, f"Boosters: {label}", 10, fill=_MUTED)

    # dimensions
    y = cy + half_h + 24
    for i, (xa, xb) in enumerate(stage_x):
        c.dim_h(xa, xb, y, f"Stage {i + 1} {_label_m(stage_len_m[i])}", ext_from=body_bot)
        y += _DIM_GAP
    c.dim_h(x0, x_fairing_base, y, f"Fairing {_label_m(fairing_m)}", ext_from=cy)
    y += _DIM_GAP
    c.dim_h(x0, x_tail, y, f"Total length {_label_m(total_m)} (excluding nozzles)", ext_from=cy)
    xd = x_tail + nozzle_m * scale + 14
    c.dim_v(xd, body_top, body_bot, f"Diameter {_label_m(d_m)}", ext_from=x_tail)

    y += 18
    legend = [
        f"Diameter = {k:.3f} m x (total propellant {total_prop:.0f} kg)^(1/3); stage length from "
        f"propellant mass at {PROPELLANT_BULK_DENSITY_KGPM3:.0f} kg/m3 (SIMPLIFICATION)",
        f"Fairing {FAIRING_LENGTH_DIAMETERS:.1f} diameters long; "
        f"pitch kick {design.initial_pitch_deg:.2f} deg at {design.pitch_start_s:.1f} s "
        "(open-loop gravity turn)",
    ]
    for s in legend:
        c.text(_MARGIN_X / 2.0, y, s, 10, anchor="start", fill=_MUTED)
        y += 14
    y += 10
    _scale_bar(c, _MARGIN_X, y + 14, scale, total_m, metric=True)
    return _finish(
        c, width, y + _SCALE_BAR_H, f"{tier_name} launch vehicle side view (concept sketch)"
    )


# --------------------------------------------------------------------------- entry point


def render_side_view_svg(design: Design, *, width_px: int = 800) -> str:
    """Dimensioned SVG side view. Deterministic: the same design yields byte-identical output."""
    if width_px < 200:
        raise ValueError("width_px must be >= 200")
    width = float(width_px)
    if isinstance(design, AmateurDesign):
        svg = _render_amateur(design, width)
    elif isinstance(design, BottleDesign):
        svg = _render_bottle(design, width)
    elif isinstance(design, MultistageDesign):
        svg = _render_multistage(design, width)
    else:
        raise TypeError(f"unsupported design type {type(design).__name__}")
    return svg
