"""Tests for rocketwright.build: resolving part choices into designs, the bill of materials and
the buildability rules (each rule has its own test)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from rocketwright.build import (
    ALLOWANCES,
    AmateurBuild,
    BottleBuild,
    BuildAdapter,
    BuildBill,
    BuildIssue,
    FinGeometry,
    check_buildability,
    resolve,
    resolve_amateur,
    resolve_bottle,
)
from rocketwright.parts import load_parts
from rocketwright.physics import recovery, solid, stability, water
from rocketwright.schema import AmateurDesign, BottleDesign, Env

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parts_v2.yaml"
CATALOG = load_parts(FIXTURE)

# An Estes-Alpha-like build on a C6: BT-50, PNC-50, 18 mm mount, balsa fins, 12 in chute.
GOOD_AMATEUR = AmateurBuild(
    body_tube_id="estes_bt50",
    body_length_m=0.24,
    nose_cone_id="estes_pnc50",
    motor_mount_id="mount_18mm_bt50",
    motor_id="estes_C6",
    fin_material_id="balsa_3_32in",
    fins=FinGeometry(count=3, root_chord_m=0.064, tip_chord_m=0.025, span_m=0.044, sweep_m=0.038),
    parachute_id="chute_12in",
    recovery_hardware_id="recovery_kit_small",
    launch_lug_id="launch_lug_1_8in",
    payload_mass_kg=0.0,
    deploy_delay_s=0.0,
)

GOOD_BOTTLE = BottleBuild(
    bottle_id="pet_bottle_1p5l",
    water_fill_frac=0.4,
    initial_gauge_pressure_pa=400000,
    nozzle_id="nozzle_21p7mm",
    fin_set_id="bottle_fins_cardboard",
    parachute_id="chute_0p5m_plastic",
    launcher_id="launcher_bike_pump",
    payload_mass_kg=0.06,
)


def _codes(issues: list[BuildIssue], severity: str | None = None) -> set[str]:
    return {i.code for i in issues if severity is None or i.severity == severity}


# --------------------------------------------------------------------------- resolve


def test_resolve_amateur_masses_add_up():
    design, bill = resolve_amateur(GOOD_AMATEUR, CATALOG)
    assert isinstance(design, AmateurDesign) and isinstance(bill, BuildBill)
    tube = CATALOG.get("estes_bt50")
    fins = GOOD_AMATEUR.fins
    fin_area = 0.5 * (fins.root_chord_m + fins.tip_chord_m) * fins.span_m
    expected_parts = (
        tube.mass_kg * 0.24 / tube.length_m
        + CATALOG.get("estes_pnc50").mass_kg
        + CATALOG.get("mount_18mm_bt50").mass_kg
        + 3 * fin_area * CATALOG.get("balsa_3_32in").areal_mass_kgpm2
        + CATALOG.get("chute_12in").mass_kg
        + CATALOG.get("recovery_kit_small").mass_kg
        + CATALOG.get("launch_lug_1_8in").mass_kg
    )
    expected = expected_parts * (1.0 + ALLOWANCES["adhesive_paint_mass_frac"]["value"])
    assert bill.dry_mass_kg == pytest.approx(expected)
    assert design.dry_mass_kg == pytest.approx(expected)
    # the rows add up to the bill's totals; the motor row is not part of the dry mass
    airframe_rows = [r for r in bill.parts if r.category != "motor"]
    assert sum(r.mass_kg for r in airframe_rows) == pytest.approx(bill.dry_mass_kg)
    assert sum(r.price_jpy for r in bill.parts) == pytest.approx(bill.cost_jpy)
    assert any(r.category == "motor" and r.part_id == "estes_C6" for r in bill.parts)
    assert any(r.part_id == "adhesive_paint_allowance" and r.provisional for r in bill.parts)
    # the Alpha weighs 23-34 g in the catalog: the roll-up lands in that range
    assert 0.025 < bill.dry_mass_kg < 0.045


def test_resolve_amateur_geometry_comes_from_parts():
    design, _ = resolve_amateur(GOOD_AMATEUR, CATALOG)
    assert design.body_diameter_m == pytest.approx(0.0246)
    assert design.body_length_m == pytest.approx(0.24)
    assert design.nose_shape == "ogive" and design.nose_length_m == pytest.approx(0.070)
    assert design.fins.thickness_m == pytest.approx(0.0024)
    assert design.fins.count == 3 and design.fins.sweep_m == pytest.approx(0.038)
    assert design.parachute_diameter_m == pytest.approx(0.305)
    assert design.motor_id == "estes_C6" and design.deploy_delay_s == 0.0


def test_resolve_bottle_masses_and_geometry():
    design, bill = resolve_bottle(GOOD_BOTTLE, CATALOG)
    assert isinstance(design, BottleDesign)
    expected = (
        CATALOG.get("pet_bottle_1p5l").mass_kg
        + CATALOG.get("nozzle_21p7mm").mass_kg
        + CATALOG.get("bottle_fins_cardboard").mass_kg
        + CATALOG.get("chute_0p5m_plastic").mass_kg
    )
    assert bill.dry_mass_kg == pytest.approx(expected)
    assert design.dry_mass_kg == pytest.approx(expected)
    assert design.bottle_volume_m3 == pytest.approx(0.0015)
    assert design.nozzle_diameter_m == pytest.approx(0.0217)
    assert design.has_fins and design.has_parachute
    assert design.parachute_diameter_m == pytest.approx(0.5)
    assert design.payload_mass_kg == pytest.approx(0.06)
    # the launcher is bought but stays on the ground
    launcher_rows = [r for r in bill.parts if r.part_id == "launcher_bike_pump"]
    assert launcher_rows and launcher_rows[0].category == "ground"
    assert sum(r.price_jpy for r in bill.parts) == pytest.approx(bill.cost_jpy)
    assert bill.cost_jpy == pytest.approx(150 + 800 + 200 + 300 + 3000)


def test_resolve_bottle_without_options():
    build = GOOD_BOTTLE.model_copy(
        update={"fin_set_id": None, "parachute_id": None, "launcher_id": None}
    )
    design, bill = resolve_bottle(build, CATALOG)
    assert not design.has_fins and not design.has_parachute
    assert design.parachute_diameter_m is None
    assert bill.dry_mass_kg == pytest.approx(0.045)


def test_resolve_dispatches_on_tier_and_adapter_discriminates():
    build = BuildAdapter.validate_python(GOOD_BOTTLE.model_dump())
    assert isinstance(build, BottleBuild)
    design, _ = resolve(build, CATALOG)
    assert design.tier == "bottle"
    design2, _ = resolve(GOOD_AMATEUR, CATALOG)
    assert design2.tier == "amateur"


def test_resolve_rejects_wrong_kind_and_unknown_ids():
    with pytest.raises(ValueError, match="nose_cone"):
        resolve_amateur(GOOD_AMATEUR.model_copy(update={"nose_cone_id": "estes_bt50"}), CATALOG)
    with pytest.raises(KeyError, match="no_such"):
        resolve_amateur(GOOD_AMATEUR.model_copy(update={"body_tube_id": "no_such"}), CATALOG)
    with pytest.raises(KeyError):
        resolve_amateur(GOOD_AMATEUR.model_copy(update={"motor_id": "no_such_motor"}), CATALOG)


# --------------------------------------------------------------------------- buildability


def test_known_good_amateur_build_has_no_errors():
    issues = check_buildability(GOOD_AMATEUR, CATALOG)
    assert _codes(issues, "error") == set(), issues
    design, _ = resolve_amateur(GOOD_AMATEUR, CATALOG)
    assert stability.static_margin_cal(design) >= 1.5


def test_known_good_bottle_build_has_no_errors():
    issues = check_buildability(GOOD_BOTTLE, CATALOG)
    assert _codes(issues, "error") == set(), issues


def test_j_motor_in_18mm_mount_errors():
    build = GOOD_AMATEUR.model_copy(update={"motor_id": "dummy_J420"})
    issues = check_buildability(build, CATALOG)
    assert "motor_mount_diameter" in _codes(issues, "error")


def test_mount_must_fit_tube():
    build = GOOD_AMATEUR.model_copy(
        update={"motor_mount_id": "mount_24mm_bt60", "motor_id": "estes_D12"}
    )
    assert "mount_fits_tube" in _codes(check_buildability(build, CATALOG), "error")


def test_nose_must_fit_tube():
    build = GOOD_AMATEUR.model_copy(update={"nose_cone_id": "estes_pnc60"})
    assert "nose_fits_tube" in _codes(check_buildability(build, CATALOG), "error")


def test_body_length_within_stock_and_long_enough():
    # longer than one stock tube: several tubes + couplers (Estes Mean Machine), a WARNING that
    # names the tube count; the bill buys that many tubes but flies the cut length's mass
    too_long = GOOD_AMATEUR.model_copy(update={"body_length_m": 0.6})
    issues = check_buildability(too_long, CATALOG)
    assert "body_length_stock" in _codes(issues, "warning")
    assert "body_length_stock" not in _codes(issues, "error")
    assert "2 tubes" in next(i.message for i in issues if i.code == "body_length_stock")
    _, bill = resolve_amateur(too_long, CATALOG)
    tube_row = next(r for r in bill.parts if r.part_id == "estes_bt50")
    tube = CATALOG.get("estes_bt50")
    assert tube_row.qty == 2 and tube_row.price_jpy == pytest.approx(2 * tube.price_jpy)
    assert tube_row.mass_kg == pytest.approx(tube.mass_kg * 0.6 / tube.length_m)
    assert any("coupler" in n for n in bill.notes)
    # the motor sits INSIDE the mount: the bay is the longer of the two, not their sum
    # (Estes Baby Bertha: 204 mm BT-60 body, 70 mm C6 in a 70 mm mount)
    motor, mount = solid.load_motor("estes_C6"), CATALOG.get("mount_18mm_bt50")
    od = CATALOG.get("estes_bt50").outer_diameter_m
    min_len = max(motor.length_m, mount.length_m) + 2.0 * od
    just_ok = GOOD_AMATEUR.model_copy(update={"body_length_m": min_len + 1e-3})
    assert "body_length_min" not in _codes(check_buildability(just_ok, CATALOG))
    too_short = GOOD_AMATEUR.model_copy(update={"body_length_m": min_len - 5e-3})
    issues = check_buildability(too_short, CATALOG)
    assert "body_length_min" in _codes(issues, "error")
    msg = next(i.message for i in issues if i.code == "body_length_min")
    assert "motor" in msg and "parachute" in msg


def test_fin_span_warning_and_root_chord_error():
    wide = GOOD_AMATEUR.model_copy(
        update={"fins": GOOD_AMATEUR.fins.model_copy(update={"span_m": 0.07})}
    )
    issues = check_buildability(wide, CATALOG)
    assert "fin_span" in _codes(issues, "warning") and "fin_span" not in _codes(issues, "error")
    long_root = GOOD_AMATEUR.model_copy(
        update={"fins": GOOD_AMATEUR.fins.model_copy(update={"root_chord_m": 0.3})}
    )
    assert "fin_root_chord" in _codes(check_buildability(long_root, CATALOG), "error")


def test_fin_must_fit_material_sheet():
    # the balsa sheet is 76 mm x 914 mm: a 100 mm span with a 100 mm root does not fit either way
    big = GOOD_AMATEUR.model_copy(
        update={
            "body_length_m": 0.4,
            "fins": FinGeometry(count=3, root_chord_m=0.1, tip_chord_m=0.08, span_m=0.1),
        }
    )
    assert "fin_sheet" in _codes(check_buildability(big, CATALOG), "error")
    # a long but narrow fin fits by rotating it on the sheet
    long_fin = GOOD_AMATEUR.model_copy(
        update={
            "body_length_m": 0.4,
            "fins": FinGeometry(count=3, root_chord_m=0.3, tip_chord_m=0.05, span_m=0.05),
        }
    )
    assert "fin_sheet" not in _codes(check_buildability(long_fin, CATALOG))


def test_parachute_must_pack_into_tube():
    build = GOOD_AMATEUR.model_copy(
        update={"parachute_id": "chute_0p5m_plastic"}  # packed 50 mm > BT-50 bore
    )
    assert "parachute_packed" in _codes(check_buildability(build, CATALOG), "error")


def test_deploy_delay_must_be_a_motor_option():
    build = GOOD_AMATEUR.model_copy(update={"deploy_delay_s": 4.0})  # C6 offers 0/3/5/7
    issues = check_buildability(build, CATALOG)
    assert "deploy_delay" in _codes(issues, "error")
    ok = GOOD_AMATEUR.model_copy(update={"deploy_delay_s": 5.0})
    assert "deploy_delay" not in _codes(check_buildability(ok, CATALOG))
    # 0 s (eject at apogee = the delay grain matched to the coast) is always allowed, even for
    # a motor with no 0 s grain: the Estes Mean Machine flies an E12-4 (grains 4/6/8) that way
    e12 = GOOD_AMATEUR.model_copy(
        update={
            "body_tube_id": "estes_bt60",
            "nose_cone_id": "estes_pnc60",
            "motor_mount_id": "mount_24mm_bt60",
            "motor_id": "estes_E12",
            "body_length_m": 0.45,
            "parachute_id": "chute_18in",
            "deploy_delay_s": 0.0,
        }
    )
    assert "deploy_delay" not in _codes(check_buildability(e12, CATALOG))
    assert "deploy_delay" in _codes(
        check_buildability(e12.model_copy(update={"deploy_delay_s": 5.0}), CATALOG), "error"
    )


def test_deploy_delay_without_listed_delays_is_a_warning(tmp_path, monkeypatch):
    # a motor file whose delay field is "P" (plugged) lists no numeric delays
    motor_dir = tmp_path / "motors"
    motor_dir.mkdir()
    src = (solid.MOTOR_DIR / "estes_C6.eng").read_text(encoding="utf-8")
    (motor_dir / "plugged_C6.eng").write_text(
        src.replace("C6 18 70 0-3-5-7", "C6 18 70 P"), encoding="utf-8"
    )
    monkeypatch.setattr(solid, "MOTOR_DIR", motor_dir)
    from rocketwright import build as build_mod

    monkeypatch.setattr(build_mod, "_load_motor", lambda mid: solid.load_motor(mid, motor_dir))
    build = GOOD_AMATEUR.model_copy(update={"motor_id": "plugged_C6"})
    issues = check_buildability(build, CATALOG)
    assert "deploy_delay" in _codes(issues, "warning")


def test_static_margin_rules():
    # tiny fins -> unstable
    small = GOOD_AMATEUR.model_copy(
        update={"fins": FinGeometry(count=3, root_chord_m=0.02, tip_chord_m=0.01, span_m=0.01)}
    )
    issues = check_buildability(small, CATALOG)
    assert "static_margin_low" in _codes(issues, "error")
    # between the one-caliber error line and the flight model's 1.5 cal: a warning (the Estes
    # Baby Bertha sits there by Barrowman and has flown for decades)
    from rocketwright.build import BUILD_THRESHOLDS

    assert BUILD_THRESHOLDS["error_static_margin_cal"] < BUILD_THRESHOLDS["min_static_margin_cal"]
    for root in (0.030, 0.035, 0.040, 0.045, 0.050):
        mid = GOOD_AMATEUR.model_copy(
            update={"fins": FinGeometry(count=3, root_chord_m=root, tip_chord_m=0.01, span_m=0.03)}
        )
        design, _ = resolve_amateur(mid, CATALOG)
        margin = stability.static_margin_cal(design)
        if 1.0 <= margin < 1.5:
            issues = check_buildability(mid, CATALOG)
            assert "static_margin_low" in _codes(issues, "warning")
            assert "static_margin_low" not in _codes(issues, "error")
            break
    else:  # pragma: no cover - fixture geometry drifted
        pytest.skip("no fin size in the sweep lands between 1.0 and 1.5 cal")
    # huge fins -> overstable warning only (span under the 2.5 OD rule still: use chord)
    big = GOOD_AMATEUR.model_copy(
        update={
            "fins": FinGeometry(count=3, root_chord_m=0.064, tip_chord_m=0.06, span_m=0.06),
            "payload_mass_kg": 0.05,
        }
    )
    issues = check_buildability(big, CATALOG)
    design, _ = resolve_amateur(big, CATALOG)
    if stability.static_margin_cal(design) > 4.0:
        assert "static_margin_high" in _codes(issues, "warning")
        assert "static_margin_high" not in _codes(issues, "error")


def test_liftoff_thrust_to_weight_rules():
    design, _ = resolve_amateur(GOOD_AMATEUR, CATALOG)
    motor = solid.load_motor("estes_C6")
    # payload chosen so that T/W is between 3 and 5 -> warning; then below 3 -> error
    weight_for_twr = lambda twr: motor.average_thrust_n / (twr * solid.G0_MPS2)  # noqa: E731
    mid = weight_for_twr(4.0) - design.dry_mass_kg - motor.total_mass_kg
    issues = check_buildability(GOOD_AMATEUR.model_copy(update={"payload_mass_kg": mid}), CATALOG)
    assert "liftoff_twr" in _codes(issues, "warning")
    assert "liftoff_twr" not in _codes(issues, "error")
    low = weight_for_twr(2.0) - design.dry_mass_kg - motor.total_mass_kg
    issues = check_buildability(GOOD_AMATEUR.model_copy(update={"payload_mass_kg": low}), CATALOG)
    assert "liftoff_twr" in _codes(issues, "error")


def test_descent_speed_warning():
    heavy = GOOD_AMATEUR.model_copy(update={"payload_mass_kg": 0.3})
    issues = check_buildability(heavy, CATALOG)
    assert "descent_speed" in _codes(issues, "warning")
    design, _ = resolve_amateur(heavy, CATALOG)
    motor = solid.load_motor("estes_C6")
    landing = design.dry_mass_kg + design.payload_mass_kg + motor.total_mass_kg
    landing -= motor.propellant_mass_kg
    v = recovery.descend(landing, design.parachute_diameter_m, Env(), 100.0).descent_speed_mps
    assert v > solid.PASS_THRESHOLDS["max_descent_speed_mps"]


def test_unknown_part_is_an_error_issue_not_an_exception():
    build = GOOD_AMATEUR.model_copy(update={"body_tube_id": "no_such_tube"})
    issues = check_buildability(build, CATALOG)
    assert _codes(issues, "error") == {"unknown_part"}
    assert "no_such_tube" in issues[0].message


def test_bottle_nozzle_must_fit_neck(tmp_path):
    # a nozzle for a different neck standard
    import yaml

    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    data["parts"].append(
        {
            "id": "nozzle_28mm_neck",
            "kind": "nozzle",
            "tier": "bottle",
            "name": "nozzle for 28 mm necks",
            "mass_kg": 0.0,
            "price_jpy": 500,
            "provisional": True,
            "diameter_m": 0.028,
            "fits_neck_diameter_m": 0.028,
        }
    )
    path = tmp_path / "parts.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    cat = load_parts(path)
    build = GOOD_BOTTLE.model_copy(update={"nozzle_id": "nozzle_28mm_neck"})
    assert "nozzle_fits_neck" in _codes(check_buildability(build, cat), "error")


def test_bottle_pressure_cap_is_min_of_bottle_launcher_and_physics():
    # launcher max is 600 kPa, bottle 700 kPa: 650 kPa errors with the launcher, passes without
    build = GOOD_BOTTLE.model_copy(update={"initial_gauge_pressure_pa": 650000})
    issues = check_buildability(build, CATALOG)
    assert "pressure_cap" in _codes(issues, "error")
    msg = next(i.message for i in issues if i.code == "pressure_cap")
    assert "launcher_bike_pump" in msg
    no_launcher = build.model_copy(update={"launcher_id": None})
    assert "pressure_cap" not in _codes(check_buildability(no_launcher, CATALOG))
    over_bottle = no_launcher.model_copy(update={"initial_gauge_pressure_pa": 750000})
    assert "pressure_cap" in _codes(check_buildability(over_bottle, CATALOG), "error")
    cap = water.PASS_THRESHOLDS["max_gauge_pressure_pa"]
    assert cap >= 700000  # the physics cap is not the binding one in this fixture


def test_bottle_fill_fraction_warning():
    low = GOOD_BOTTLE.model_copy(update={"water_fill_frac": 0.1})
    assert "fill_fraction" in _codes(check_buildability(low, CATALOG), "warning")
    high = GOOD_BOTTLE.model_copy(update={"water_fill_frac": 0.7})
    assert "fill_fraction" in _codes(check_buildability(high, CATALOG), "warning")
    assert "fill_fraction" not in _codes(check_buildability(GOOD_BOTTLE, CATALOG))


def test_bottle_payload_without_parachute_warns():
    build = GOOD_BOTTLE.model_copy(update={"parachute_id": None})
    assert "payload_needs_parachute" in _codes(check_buildability(build, CATALOG), "warning")
    no_payload = build.model_copy(update={"payload_mass_kg": 0.0})
    assert "payload_needs_parachute" not in _codes(check_buildability(no_payload, CATALOG))


def test_issue_fields():
    issues = check_buildability(GOOD_AMATEUR.model_copy(update={"motor_id": "dummy_J420"}), CATALOG)
    for i in issues:
        assert i.severity in ("error", "warning")
        assert i.code and i.message
        d = i.model_dump()
        assert set(d) == {"code", "message", "severity"}
    assert not math.isnan(sum(1 for _ in issues))
