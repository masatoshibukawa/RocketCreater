"""Parts-based designs for the bottle and amateur tiers.

The agent chooses parts (`AmateurBuild` / `BottleBuild`, ids from rocketwright.parts and the
motor catalog); this module turns the choice into the `AmateurDesign` / `BottleDesign` the
physics consumes (`resolve_*`), with the mass, dimensions and cost computed from the parts
(`BuildBill`), and checks that the chosen parts can actually be assembled
(`check_buildability`). The physics models are untouched: they still see a plain design.

Mass roll-up (amateur): body tube mass x (chosen length / stock length) + nose cone + motor
mount + fins (trapezoid area x areal mass x count) + parachute + recovery hardware + launch lug,
plus an adhesive/paint allowance (`ALLOWANCES`, provisional). The motor is listed on the bill but
is not part of the dry mass (the design's `dry_mass_kg` excludes motor and payload, schema.py).
Bottle: bottle + nozzle + fin set + parachute; the launcher is bought but stays on the ground.

Buildability rules (`BUILD_THRESHOLDS`, each one a test in tests/test_build.py) are reported as
`BuildIssue(code, message, severity)`; an `error` means the rocket cannot be built or flown as
chosen, a `warning` is advice the physics may confirm or not.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from rocketwright.parts import PartsCatalog
from rocketwright.physics import recovery, solid, stability, water
from rocketwright.schema import AmateurDesign, BottleDesign, Env, FinSet

__all__ = [
    "ALLOWANCES",
    "BUILD_THRESHOLDS",
    "AmateurBuild",
    "BillRow",
    "BottleBuild",
    "Build",
    "BuildAdapter",
    "BuildBill",
    "BuildIssue",
    "FinGeometry",
    "check_buildability",
    "resolve",
    "resolve_amateur",
    "resolve_bottle",
]

# SIMPLIFICATION: glue, paint and small hardware are not catalog parts; they are added as a
# fraction of the summed part mass and a flat price. Both provisional.
ALLOWANCES: dict[str, dict[str, float | bool]] = {
    "adhesive_paint_mass_frac": {"value": 0.10, "provisional": True},
    "adhesive_paint_price_jpy": {"value": 300.0, "provisional": True},
    # Motor price for the bill: RASP files carry no price, so a provisional per-impulse rate
    # with a floor (an Estes C6 ~ 600 JPY, a G ~ 7,000 JPY, a J ~ 56,000 JPY).
    "motor_price_jpy_per_ns": {"value": 60.0, "provisional": True},
    "motor_price_min_jpy": {"value": 600.0, "provisional": True},
}

# Single place for the buildability rules. Flight thresholds are the physics modules' own.
BUILD_THRESHOLDS: dict[str, float] = {
    "diameter_tolerance_m": 0.0005,  # motor-vs-mount and nozzle-vs-neck matching
    "body_length_margin_calibers": 2.0,  # tube must hold motor + mount + 2 OD of chute space
    "fin_span_max_calibers": 2.5,  # wider fins are hard to build and to launch (warning)
    "min_static_margin_cal": solid.PASS_THRESHOLDS["min_stability_margin_cal"],
    "max_static_margin_cal": solid.PASS_THRESHOLDS["max_stability_margin_cal"],
    # SIMPLIFICATION: common launch-rail rule of thumb (NAR/Tripoli guidance quotes 5:1 on the
    # average thrust); below 3:1 the rocket may not clear the rod safely. Provisional.
    "liftoff_twr_error": 3.0,
    "liftoff_twr_warn": 5.0,
    "max_descent_speed_mps": solid.PASS_THRESHOLDS["max_descent_speed_mps"],
    "fill_frac_min": 0.2,
    "fill_frac_max": 0.6,
    "descent_check_altitude_m": 100.0,  # air density taken at the pad + half of this
}

_G0 = solid.G0_MPS2


def _load_motor(motor_id: str) -> solid.Motor:
    """Indirection so tests can point the build layer at a temporary motor directory."""
    return solid.load_motor(motor_id)


# --------------------------------------------------------------------------- builds


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FinGeometry(_Frozen):
    """Trapezoidal fin planform; the thickness comes from the fin material part."""

    count: int = Field(ge=3, le=8)
    root_chord_m: float = Field(gt=0)
    tip_chord_m: float = Field(ge=0)
    span_m: float = Field(gt=0)
    sweep_m: float = Field(default=0.0, ge=0)

    @property
    def area_m2(self) -> float:
        return 0.5 * (self.root_chord_m + self.tip_chord_m) * self.span_m


class AmateurBuild(_Frozen):
    tier: Literal["amateur"] = "amateur"
    body_tube_id: str = Field(min_length=1, description="body_tube part id (list_parts)")
    body_length_m: float = Field(gt=0, description="tube length cut from the stock tube")
    nose_cone_id: str = Field(min_length=1, description="nose_cone part id; must fit the tube")
    motor_mount_id: str = Field(
        min_length=1, description="motor_mount part id; must fit the tube and the motor diameter"
    )
    motor_id: str = Field(min_length=1, description="catalog/motors/*.eng id (search_catalog)")
    fin_material_id: str = Field(min_length=1, description="fin_material part id (sheet)")
    fins: FinGeometry
    parachute_id: str = Field(min_length=1, description="parachute part id; must pack in the tube")
    recovery_hardware_id: str | None = Field(default=None, description="recovery_hardware part id")
    launch_lug_id: str | None = Field(default=None, description="launch_lug part id")
    payload_mass_kg: float = Field(default=0.0, ge=0)
    deploy_delay_s: float = Field(
        default=0.0,
        ge=0,
        description="parachute delay after apogee; must be one of the motor's delay options",
    )


class BottleBuild(_Frozen):
    tier: Literal["bottle"] = "bottle"
    bottle_id: str = Field(min_length=1, description="bottle part id")
    water_fill_frac: float = Field(gt=0, lt=1)
    initial_gauge_pressure_pa: float = Field(gt=0)
    nozzle_id: str = Field(min_length=1, description="nozzle part id; must fit the bottle neck")
    fin_set_id: str | None = Field(default=None, description="bottle_fin_set part id or null")
    parachute_id: str | None = Field(default=None, description="parachute part id or null")
    launcher_id: str | None = Field(default=None, description="launcher part id or null")
    payload_mass_kg: float = Field(default=0.0, ge=0)


Build = Annotated[
    Union[AmateurBuild, BottleBuild],  # noqa: UP007 - Union keeps Annotated readable
    Field(discriminator="tier"),
]
BuildAdapter: TypeAdapter[Build] = TypeAdapter(Build)


# --------------------------------------------------------------------------- bill


class BillRow(_Frozen):
    part_id: str
    name: str
    qty: int = Field(ge=1)
    mass_kg: float = Field(ge=0)  # line total (qty included)
    price_jpy: float = Field(ge=0)  # line total
    provisional: bool
    # airframe: counted in the dry mass; motor: flown but not dry mass; allowance: glue/paint;
    # ground: bought but stays on the pad (bottle launcher).
    category: Literal["airframe", "motor", "allowance", "ground"] = "airframe"


class BuildBill(_Frozen):
    parts: list[BillRow]
    dry_mass_kg: float = Field(gt=0)
    cost_jpy: float = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class BuildIssue(_Frozen):
    code: str
    message: str
    severity: Literal["error", "warning"]


def _allow(key: str) -> float:
    return float(ALLOWANCES[key]["value"])


def _row(
    part, qty: int = 1, *, mass_kg: float | None = None, category: str = "airframe"
) -> BillRow:
    return BillRow(
        part_id=part.id,
        name=part.name,
        qty=qty,
        mass_kg=part.mass_kg * qty if mass_kg is None else mass_kg,
        price_jpy=part.price_jpy * qty,
        provisional=part.provisional,
        category=category,  # type: ignore[arg-type]
    )


def _motor_row(motor: solid.Motor) -> BillRow:
    price = max(
        _allow("motor_price_min_jpy"), _allow("motor_price_jpy_per_ns") * motor.total_impulse_ns
    )
    return BillRow(
        part_id=motor.id,
        name=f"motor {motor.name} ({motor.manufacturer})",
        qty=1,
        mass_kg=motor.total_mass_kg,
        price_jpy=price,
        provisional=True,
        category="motor",
    )


# --------------------------------------------------------------------------- resolve


def resolve_amateur(build: AmateurBuild, catalog: PartsCatalog) -> tuple[AmateurDesign, BuildBill]:
    """The design the solid model flies plus the bill of materials. Raises KeyError for an
    unknown id and ValueError for an id of the wrong kind (check_buildability reports both)."""
    tube = catalog.get(build.body_tube_id, kind="body_tube")
    nose = catalog.get(build.nose_cone_id, kind="nose_cone")
    mount = catalog.get(build.motor_mount_id, kind="motor_mount")
    material = catalog.get(build.fin_material_id, kind="fin_material")
    chute = catalog.get(build.parachute_id, kind="parachute")
    motor = _load_motor(build.motor_id)
    rows: list[BillRow] = [
        _row(tube, mass_kg=tube.mass_kg * build.body_length_m / tube.length_m),
        _row(nose),
        _row(mount),
        BillRow(
            part_id=material.id,
            name=f"{material.name} -> {build.fins.count} fins",
            qty=1,
            mass_kg=build.fins.count * build.fins.area_m2 * material.areal_mass_kgpm2,
            price_jpy=material.price_jpy,
            provisional=material.provisional,
        ),
        _row(chute),
    ]
    if build.recovery_hardware_id is not None:
        rows.append(_row(catalog.get(build.recovery_hardware_id, kind="recovery_hardware")))
    if build.launch_lug_id is not None:
        rows.append(_row(catalog.get(build.launch_lug_id, kind="launch_lug")))
    parts_mass = sum(r.mass_kg for r in rows)
    rows.append(
        BillRow(
            part_id="adhesive_paint_allowance",
            name="adhesive, paint and small hardware (allowance)",
            qty=1,
            mass_kg=parts_mass * _allow("adhesive_paint_mass_frac"),
            price_jpy=_allow("adhesive_paint_price_jpy"),
            provisional=True,
            category="allowance",
        )
    )
    dry_mass = sum(r.mass_kg for r in rows)
    rows.append(_motor_row(motor))
    notes = [
        f"tube mass pro-rated to {build.body_length_m:.3f} m of the {tube.length_m:.3f} m stock "
        f"(full tube bought); fins {build.fins.count} x {build.fins.area_m2 * 1e4:.1f} cm2 of "
        f"{material.name} ({material.areal_mass_kgpm2:g} kg/m2); glue/paint allowance "
        f"{_allow('adhesive_paint_mass_frac'):.0%} of the part mass (provisional); motor price "
        "from a provisional per-impulse rate",
    ]
    bill = BuildBill(
        parts=rows,
        dry_mass_kg=dry_mass,
        cost_jpy=sum(r.price_jpy for r in rows),
        notes=notes,
    )
    design = AmateurDesign(
        body_diameter_m=tube.outer_diameter_m,
        body_length_m=build.body_length_m,
        nose_shape=nose.shape,
        nose_length_m=nose.length_m,
        fins=FinSet(
            count=build.fins.count,
            root_chord_m=build.fins.root_chord_m,
            tip_chord_m=build.fins.tip_chord_m,
            span_m=build.fins.span_m,
            sweep_m=build.fins.sweep_m,
            thickness_m=material.thickness_m,
        ),
        motor_id=build.motor_id,
        dry_mass_kg=dry_mass,
        payload_mass_kg=build.payload_mass_kg,
        parachute_diameter_m=chute.diameter_m,
        deploy_delay_s=build.deploy_delay_s,
    )
    return design, bill


def resolve_bottle(build: BottleBuild, catalog: PartsCatalog) -> tuple[BottleDesign, BuildBill]:
    bottle = catalog.get(build.bottle_id, kind="bottle")
    nozzle = catalog.get(build.nozzle_id, kind="nozzle")
    rows: list[BillRow] = [_row(bottle), _row(nozzle)]
    fins = (
        None if build.fin_set_id is None else catalog.get(build.fin_set_id, kind="bottle_fin_set")
    )
    chute = (
        None if build.parachute_id is None else catalog.get(build.parachute_id, kind="parachute")
    )
    if fins is not None:
        rows.append(_row(fins))
    if chute is not None:
        rows.append(_row(chute))
    dry_mass = sum(r.mass_kg for r in rows)
    notes = ["dry mass = bottle + nozzle + fin set + parachute; the launcher stays on the ground"]
    if build.launcher_id is not None:
        rows.append(_row(catalog.get(build.launcher_id, kind="launcher"), category="ground"))
    # SIMPLIFICATION: the water model derives the bottle diameter from its volume; the part's
    # body_diameter_m is reported on the bill only.
    notes.append(
        f"bottle {bottle.name}: {bottle.volume_m3 * 1e3:.2f} L, {bottle.body_diameter_m * 1e3:.0f} "
        f"mm (the flight model uses the volume-derived diameter)"
    )
    bill = BuildBill(
        parts=rows,
        dry_mass_kg=dry_mass,
        cost_jpy=sum(r.price_jpy for r in rows),
        notes=notes,
    )
    design = BottleDesign(
        bottle_volume_m3=bottle.volume_m3,
        water_fill_frac=build.water_fill_frac,
        initial_gauge_pressure_pa=build.initial_gauge_pressure_pa,
        nozzle_diameter_m=nozzle.diameter_m,
        dry_mass_kg=dry_mass,
        payload_mass_kg=build.payload_mass_kg,
        has_fins=fins is not None,
        has_parachute=chute is not None,
        parachute_diameter_m=None if chute is None else chute.diameter_m,
    )
    return design, bill


def resolve(build: AmateurBuild | BottleBuild, catalog: PartsCatalog):
    if isinstance(build, AmateurBuild):
        return resolve_amateur(build, catalog)
    if isinstance(build, BottleBuild):
        return resolve_bottle(build, catalog)
    raise TypeError(f"unsupported build type {type(build).__name__}")


# --------------------------------------------------------------------------- buildability


def _issue(code: str, severity: str, message: str) -> BuildIssue:
    return BuildIssue(code=code, message=message, severity=severity)  # type: ignore[arg-type]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= BUILD_THRESHOLDS["diameter_tolerance_m"]


def _numeric_delays(motor: solid.Motor) -> list[float]:
    out: list[float] = []
    for d in motor.delays:
        try:
            out.append(float(d))
        except ValueError:
            continue  # "P" (plugged) and similar
    return out


def _check_amateur(build: AmateurBuild, catalog: PartsCatalog) -> list[BuildIssue]:
    th = BUILD_THRESHOLDS
    issues: list[BuildIssue] = []
    err = lambda code, msg: issues.append(_issue(code, "error", msg))  # noqa: E731
    warn = lambda code, msg: issues.append(_issue(code, "warning", msg))  # noqa: E731

    design, _ = resolve_amateur(build, catalog)
    tube = catalog.get(build.body_tube_id, kind="body_tube")
    nose = catalog.get(build.nose_cone_id, kind="nose_cone")
    mount = catalog.get(build.motor_mount_id, kind="motor_mount")
    material = catalog.get(build.fin_material_id, kind="fin_material")
    chute = catalog.get(build.parachute_id, kind="parachute")
    motor = _load_motor(build.motor_id)
    od = tube.outer_diameter_m
    fins = build.fins

    if not _close(motor.diameter_m, mount.motor_diameter_m):
        err(
            "motor_mount_diameter",
            f"motor {motor.id} is {motor.diameter_m * 1e3:.0f} mm but mount {mount.id} takes "
            f"{mount.motor_diameter_m * 1e3:.0f} mm motors: pick a matching mount or motor",
        )
    if tube.id not in mount.fits_tubes:
        err(
            "mount_fits_tube",
            f"mount {mount.id} fits tube(s) {sorted(mount.fits_tubes)}, not {tube.id!r}",
        )
    if nose.fits_tube_id != tube.id:
        err(
            "nose_fits_tube",
            f"nose cone {nose.id} fits tube {nose.fits_tube_id!r}, not {tube.id!r}",
        )
    if build.body_length_m > tube.length_m + 1e-9:
        err(
            "body_length_stock",
            f"body length {build.body_length_m:.3f} m exceeds the {tube.length_m:.3f} m stock "
            f"tube {tube.id}",
        )
    min_len = motor.length_m + mount.length_m + th["body_length_margin_calibers"] * od
    if build.body_length_m < min_len:
        err(
            "body_length_min",
            f"body length {build.body_length_m:.3f} m is too short to hold the motor "
            f"({motor.length_m:.3f} m), the mount ({mount.length_m:.3f} m) and the parachute "
            f"({th['body_length_margin_calibers']:g} x {od * 1e3:.1f} mm): need >= {min_len:.3f} m",
        )
    if fins.span_m > th["fin_span_max_calibers"] * od:
        warn(
            "fin_span",
            f"fin span {fins.span_m * 1e3:.0f} mm is over {th['fin_span_max_calibers']:g} body "
            f"diameters ({th['fin_span_max_calibers'] * od * 1e3:.0f} mm): fragile and hard "
            "to launch",
        )
    if fins.root_chord_m > build.body_length_m:
        err(
            "fin_root_chord",
            f"fin root chord {fins.root_chord_m:.3f} m is longer than the body "
            f"{build.body_length_m:.3f} m",
        )
    # Planform bounding box (span x chord-wise extent); fits the sheet in either orientation.
    extent = max(fins.root_chord_m, fins.sweep_m + fins.tip_chord_m)
    sheet = (material.sheet_width_m, material.sheet_height_m)
    fits = (fins.span_m <= sheet[0] and extent <= sheet[1]) or (
        fins.span_m <= sheet[1] and extent <= sheet[0]
    )
    if not fits:
        err(
            "fin_sheet",
            f"a {fins.span_m * 1e3:.0f} x {extent * 1e3:.0f} mm fin does not fit the "
            f"{sheet[0] * 1e3:.0f} x {sheet[1] * 1e3:.0f} mm sheet of {material.id}",
        )
    if chute.packed_diameter_m > tube.inner_diameter_m:
        err(
            "parachute_packed",
            f"parachute {chute.id} packs to {chute.packed_diameter_m * 1e3:.0f} mm, more than the "
            f"{tube.inner_diameter_m * 1e3:.1f} mm bore of {tube.id}",
        )
    delays = _numeric_delays(motor)
    if delays:
        if not any(math.isclose(build.deploy_delay_s, d, abs_tol=1e-6) for d in delays):
            err(
                "deploy_delay",
                f"deploy delay {build.deploy_delay_s:g} s is not one of motor {motor.id}'s "
                f"options {delays}",
            )
    else:
        warn(
            "deploy_delay",
            f"motor {motor.id} lists no delay options ({'-'.join(motor.delays)}): the "
            f"{build.deploy_delay_s:g} s deploy delay needs separate deployment electronics",
        )
    margin = stability.static_margin_cal(design, motor.total_mass_kg, motor_length_m=motor.length_m)
    if margin < th["min_static_margin_cal"]:
        err(
            "static_margin_low",
            f"static margin {margin:.2f} cal is below {th['min_static_margin_cal']:g} cal at "
            "liftoff: larger or further-aft fins, a longer body or nose ballast",
        )
    elif margin > th["max_static_margin_cal"]:
        warn(
            "static_margin_high",
            f"static margin {margin:.2f} cal is above {th['max_static_margin_cal']:g} cal: "
            "over-stable, it will weathercock into the wind",
        )
    liftoff = design.dry_mass_kg + design.payload_mass_kg + motor.total_mass_kg
    twr = motor.average_thrust_n / (liftoff * _G0)
    if twr < th["liftoff_twr_error"]:
        err(
            "liftoff_twr",
            f"liftoff thrust-to-weight {twr:.1f} (average thrust {motor.average_thrust_n:.1f} N, "
            f"{liftoff * 1e3:.0f} g) is below {th['liftoff_twr_error']:g}: a bigger motor or "
            "less mass",
        )
    elif twr < th["liftoff_twr_warn"]:
        warn(
            "liftoff_twr",
            f"liftoff thrust-to-weight {twr:.1f} is below the {th['liftoff_twr_warn']:g}:1 rail "
            "rule of thumb (provisional)",
        )
    landing = liftoff - motor.propellant_mass_kg
    descent = recovery.descend(
        landing, chute.diameter_m, Env(), th["descent_check_altitude_m"]
    ).descent_speed_mps
    if descent > th["max_descent_speed_mps"]:
        warn(
            "descent_speed",
            f"descent speed {descent:.1f} m/s under the {chute.diameter_m:.2f} m parachute with "
            f"{landing * 1e3:.0f} g landing is above {th['max_descent_speed_mps']:g} m/s: pick a "
            "larger parachute (the flight model judges this too)",
        )
    return issues


def _check_bottle(build: BottleBuild, catalog: PartsCatalog) -> list[BuildIssue]:
    th = BUILD_THRESHOLDS
    issues: list[BuildIssue] = []
    resolve_bottle(build, catalog)  # id / kind errors surface first
    bottle = catalog.get(build.bottle_id, kind="bottle")
    nozzle = catalog.get(build.nozzle_id, kind="nozzle")
    launcher = (
        None if build.launcher_id is None else catalog.get(build.launcher_id, kind="launcher")
    )
    if not _close(nozzle.fits_neck_diameter_m, bottle.neck_diameter_m):
        issues.append(
            _issue(
                "nozzle_fits_neck",
                "error",
                f"nozzle {nozzle.id} fits a {nozzle.fits_neck_diameter_m * 1e3:.1f} mm neck, the "
                f"bottle {bottle.id} has a {bottle.neck_diameter_m * 1e3:.1f} mm neck",
            )
        )
    caps = {
        bottle.id: bottle.max_gauge_pressure_pa,
        "physics cap": water.PASS_THRESHOLDS["max_gauge_pressure_pa"],
    }
    if launcher is not None:
        caps[launcher.id] = launcher.max_gauge_pressure_pa
    binding = min(caps, key=caps.get)  # type: ignore[arg-type]
    if build.initial_gauge_pressure_pa > caps[binding]:
        issues.append(
            _issue(
                "pressure_cap",
                "error",
                f"gauge pressure {build.initial_gauge_pressure_pa / 1e3:.0f} kPa exceeds the "
                f"{caps[binding] / 1e3:.0f} kPa limit of {binding}",
            )
        )
    if not th["fill_frac_min"] <= build.water_fill_frac <= th["fill_frac_max"]:
        issues.append(
            _issue(
                "fill_fraction",
                "warning",
                f"water fill {build.water_fill_frac:.0%} is outside the usual "
                f"{th['fill_frac_min']:.0%}-{th['fill_frac_max']:.0%} range",
            )
        )
    if build.payload_mass_kg > 0.0 and build.parachute_id is None:
        issues.append(
            _issue(
                "payload_needs_parachute",
                "warning",
                f"a {build.payload_mass_kg * 1e3:.0f} g payload without a parachute will land hard",
            )
        )
    return issues


def check_buildability(
    build: AmateurBuild | BottleBuild, catalog: PartsCatalog
) -> list[BuildIssue]:
    """Buildability issues of `build`; an unknown or wrong-kind part id is reported as a single
    `unknown_part` error instead of raising."""
    try:
        if isinstance(build, AmateurBuild):
            return _check_amateur(build, catalog)
        if isinstance(build, BottleBuild):
            return _check_bottle(build, catalog)
    except (KeyError, ValueError) as exc:
        return [_issue("unknown_part", "error", str(exc).strip("'\""))]
    raise TypeError(f"unsupported build type {type(build).__name__}")
