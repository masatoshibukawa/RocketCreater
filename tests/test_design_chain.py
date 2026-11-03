"""Tests for rocketwright.design_chain: the staged, code-enumerated design chain of the bottle and
amateur tiers (stage order and invalidation, candidate compatibility, the default rules, the
greedy auto design on the demo requirements, ground truth against the reference kits,
determinism and speed)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from rocketwright.build import BUILD_THRESHOLDS, check_buildability, resolve
from rocketwright.design_chain import (
    AMATEUR_STAGES,
    BOTTLE_STAGES,
    CHAIN_RULES,
    auto_design,
    candidates_for,
    complete_build,
    design_stage,
    invalidated_stages,
)
from rocketwright.parts import load_parts
from rocketwright.physics import recovery, solid, stability
from rocketwright.references import load_references
from rocketwright.schema import Env, Requirement

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_parts()


def _scenario_env(name: str) -> Env:
    data = yaml.safe_load((ROOT / "scenarios" / f"{name}.yaml").read_text(encoding="utf-8"))
    return Env.model_validate(data["env"])


# The demo requirements as the agent normalises them (scenarios/demo_*.yaml request texts).
AMATEUR_REQ = Requirement(
    goal_kind="altitude",
    target_altitude_m=2000,
    payload_mass_kg=1.0,
    budget_jpy=50000,
    recovery_required=True,
)
AMATEUR_ENV = _scenario_env("demo_amateur")
BOTTLE_REQ = Requirement(
    goal_kind="altitude",
    target_altitude_m=30,
    payload_mass_kg=0.06,
    budget_jpy=3000,
    recovery_required=True,
)
BOTTLE_ENV = _scenario_env("demo_bottle")


@pytest.fixture(scope="module")
def amateur_result():
    return auto_design(AMATEUR_REQ, AMATEUR_ENV, CATALOG, tier="amateur")


@pytest.fixture(scope="module")
def bottle_result():
    return auto_design(BOTTLE_REQ, BOTTLE_ENV, CATALOG, tier="bottle")


# --------------------------------------------------------------------------- order


def test_stage_orders():
    assert AMATEUR_STAGES == (
        "motor",
        "mount",
        "body_tube",
        "nose_cone",
        "body_length",
        "fins",
        "parachute",
        "deploy_delay",
    )
    assert BOTTLE_STAGES == ("bottle", "nozzle", "water_fill", "pressure", "fins", "parachute")


def test_invalidated_stages_are_the_downstream_ones():
    chosen = {s: "x" for s in AMATEUR_STAGES}
    assert invalidated_stages("amateur", "motor", chosen) == list(AMATEUR_STAGES[1:])
    assert invalidated_stages("amateur", "fins", chosen) == ["parachute", "deploy_delay"]
    assert invalidated_stages("amateur", "deploy_delay", chosen) == []
    assert invalidated_stages("bottle", "nozzle", {"bottle": "b", "pressure": "1"}) == ["pressure"]
    with pytest.raises(ValueError):
        invalidated_stages("amateur", "bottle", {})
    with pytest.raises(ValueError):
        invalidated_stages("amateur", "motor", {"nozzle": "x"})


def test_changing_the_motor_invalidates_everything_downstream(amateur_result):
    chosen = {t.stage: t.option for t in amateur_result.trace}
    res = design_stage(AMATEUR_REQ, AMATEUR_ENV, chosen, "motor", CATALOG, tier="amateur", k=3)
    assert res.invalidated == list(AMATEUR_STAGES[1:])
    assert res.next_stage == "mount"
    assert 1 <= len(res.candidates) <= 3
    # a different motor gets its own mount, tube, ... (the old downstream choices are dropped)
    other = next(c for c in res.candidates if c.value != chosen["motor"])
    mount = CATALOG.get(other.build.motor_mount_id)
    assert mount.motor_diameter_m == pytest.approx(
        solid.load_motor(other.build.motor_id).diameter_m, abs=5e-4
    )


# --------------------------------------------------------------------------- compatibility


@pytest.mark.parametrize("motor_id", ["estes_C6", "estes_E12", "aerotech_G80T", "dummy_J420"])
def test_mount_candidates_take_the_motor_diameter(motor_id):
    cands = candidates_for("mount", AMATEUR_REQ, AMATEUR_ENV, {"motor": motor_id}, CATALOG)
    assert cands
    motor = solid.load_motor(motor_id)
    for c in cands:
        mount = CATALOG.get(c.value, kind="motor_mount")
        assert abs(mount.motor_diameter_m - motor.diameter_m) <= 5e-4
        assert c.build.motor_mount_id == c.value


def test_tube_nose_fin_and_chute_candidates_are_compatible():
    chosen = {"motor": "estes_C6", "mount": "motor_mount_18mm"}
    req = Requirement(goal_kind="altitude", target_altitude_m=300)
    tubes = candidates_for("body_tube", req, Env(), chosen, CATALOG)
    mount = CATALOG.get("motor_mount_18mm")
    assert {c.value for c in tubes} == set(mount.fits_tubes)
    chosen["body_tube"] = "estes_bt60_tube"
    noses = candidates_for("nose_cone", req, Env(), chosen, CATALOG)
    assert noses and all(CATALOG.get(c.value).fits_tube_id == "estes_bt60_tube" for c in noses)
    chosen["nose_cone"] = noses[0].value
    fins = candidates_for("fins", req, Env(), chosen, CATALOG)
    assert len(fins) >= 10
    for c in fins:
        codes = {i.code for i in c.issues}
        assert "fin_sheet" not in codes
        b = c.build
        mat = CATALOG.get(b.fin_material_id)
        extent = max(b.fins.root_chord_m, b.fins.sweep_m + b.fins.tip_chord_m)
        sheet = sorted((mat.sheet_width_m, mat.sheet_height_m))
        assert sorted((b.fins.span_m, extent))[0] <= sheet[0] + 1e-9
    chosen["fins"] = fins[0].option
    chutes = candidates_for("parachute", req, Env(), chosen, CATALOG)
    tube = CATALOG.get("estes_bt60_tube")
    assert chutes
    for c in chutes:
        assert CATALOG.get(c.value).packed_diameter_m <= tube.inner_diameter_m


def test_bottle_nozzles_fit_the_neck_and_pressures_include_the_solved_one():
    chosen = {"bottle": "pet_bottle_1p5l"}
    nozzles = candidates_for("nozzle", BOTTLE_REQ, BOTTLE_ENV, chosen, CATALOG)
    bottle = CATALOG.get("pet_bottle_1p5l")
    assert nozzles
    for c in nozzles:
        assert CATALOG.get(c.value).fits_neck_diameter_m == pytest.approx(bottle.neck_diameter_m)
    chosen.update(nozzle="bottle_nozzle_full_bore_22mm", water_fill="0.35")
    res = design_stage(BOTTLE_REQ, BOTTLE_ENV, chosen, "pressure", CATALOG, tier="bottle", k=10)
    labels = " ".join(c.label for c in res.candidates)
    assert "solved" in labels and "cap" in labels
    rounded = [c.value for c in res.candidates if "rounded" in c.label]
    assert rounded and all(p % CHAIN_RULES["pressure_round_pa"] == 0 for p in rounded)


# --------------------------------------------------------------------------- defaults


def test_complete_build_defaults_amateur():
    req = Requirement(goal_kind="altitude", target_altitude_m=300)
    env = Env(rail_length_m=1.0)
    build = complete_build(req, env, {"motor": "estes_C6"}, CATALOG, tier="amateur")
    assert not [i for i in check_buildability(build, CATALOG) if i.severity == "error"]
    design, bill = resolve(build, CATALOG)
    motor = solid.load_motor("estes_C6")
    tube = CATALOG.get(build.body_tube_id)
    mount = CATALOG.get(build.motor_mount_id)
    # narrowest tube that takes an 18 mm mount
    assert build.body_tube_id == "estes_bt20_tube"
    # body = buildability minimum + 1 caliber
    min_len = (
        max(motor.length_m, mount.length_m)
        + BUILD_THRESHOLDS["body_length_margin_calibers"] * tube.outer_diameter_m
    )
    assert build.body_length_m == pytest.approx(min_len + tube.outer_diameter_m, abs=1.5e-3)
    margin = stability.static_margin_cal(design, motor.total_mass_kg, motor_length_m=motor.length_m)
    assert margin >= CHAIN_RULES["default_static_margin_cal"]
    landing = bill.dry_mass_kg + motor.total_mass_kg - motor.propellant_mass_kg
    v = recovery.descend(landing, design.parachute_diameter_m, env, 100.0).descent_speed_mps
    assert v <= CHAIN_RULES["default_descent_speed_mps"] + 0.2
    assert build.deploy_delay_s == 0.0


def test_complete_build_drops_the_launcher_when_the_budget_excludes_it():
    chosen = {"bottle": "pet_bottle_1p5l", "pressure": "300000"}
    tight = complete_build(BOTTLE_REQ, BOTTLE_ENV, chosen, CATALOG, tier="bottle")
    assert tight.launcher_id is None
    free = BOTTLE_REQ.model_copy(update={"budget_jpy": None})
    loose = complete_build(free, BOTTLE_ENV, chosen, CATALOG, tier="bottle")
    assert loose.launcher_id == "launcher_bicycle_pump"  # cheapest that holds 300 kPa


# --------------------------------------------------------------------------- auto design


def _assert_passing(result, req):
    assert result.sim.success, result.sim.failure_reasons
    assert not [i for i in check_buildability(result.build, CATALOG) if i.severity == "error"]
    assert result.bill.cost_jpy <= req.budget_jpy
    tgt = req.target_altitude_m
    assert abs(result.sim.metrics["apogee_m"] - tgt) <= 0.10 * tgt


def test_auto_design_amateur_demo_passes(amateur_result):
    _assert_passing(amateur_result, AMATEUR_REQ)
    assert [t.stage for t in amateur_result.trace] == list(AMATEUR_STAGES)
    for t in amateur_result.trace:
        assert t.why and t.enumerated >= 1
    assert amateur_result.build.payload_mass_kg == AMATEUR_REQ.payload_mass_kg
    targets = amateur_result.derived_targets
    assert targets["total_impulse_ns"] > 0 and targets["motor_class_letter"]


def test_auto_design_bottle_demo_passes(bottle_result):
    _assert_passing(bottle_result, BOTTLE_REQ)
    assert [t.stage for t in bottle_result.trace] == list(BOTTLE_STAGES)
    assert bottle_result.build.parachute_id is not None  # the egg needs one
    assert bottle_result.build.launcher_id is None  # 3,000 JPY cannot buy the pump too
    assert "gauge_pressure_pa" in bottle_result.derived_targets


def test_auto_design_is_deterministic(amateur_result, bottle_result):
    again = auto_design(AMATEUR_REQ, AMATEUR_ENV, CATALOG, tier="amateur")
    assert again.build == amateur_result.build
    assert [t.option for t in again.trace] == [t.option for t in amateur_result.trace]
    b2 = auto_design(BOTTLE_REQ, BOTTLE_ENV, CATALOG, tier="bottle")
    assert b2.build == bottle_result.build


@pytest.mark.parametrize(
    ("req", "env", "tier"),
    [(AMATEUR_REQ, AMATEUR_ENV, "amateur"), (BOTTLE_REQ, BOTTLE_ENV, "bottle")],
)
def test_auto_design_is_fast(req, env, tier):
    t0 = time.perf_counter()
    auto_design(req, env, CATALOG, tier=tier)
    assert time.perf_counter() - t0 < 3.0


def test_one_stage_is_fast():
    for stage in AMATEUR_STAGES:
        t0 = time.perf_counter()
        design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, stage, CATALOG, tier="amateur")
        assert time.perf_counter() - t0 < 1.0, stage


def test_motor_stage_ranks_the_derived_class_first():
    res = design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, "motor", CATALOG, tier="amateur", k=None)
    assert res.enumerated == len(solid.list_motor_ids())
    assert res.simulated == sum(
        1 for c in res.candidates if not any(i.severity == "error" for i in c.issues)
    )  # the motor stage is never pruned
    # derive: 2 km with 1 kg is class J; the window is I..K
    assert res.derived_targets["motor_class_letter"] == "J"
    window = {c.value for c in res.candidates if c.in_class_window}
    assert window == {"aerotech_I200W", "dummy_I200", "dummy_J420"}
    # within the same pass status, every in-window motor ranks before every other motor
    buildable = [c for c in res.candidates if not any(i.severity == "error" for i in c.issues)]
    for status in (True, False):
        flags = [c.in_class_window for c in buildable if c.passed is status]
        assert flags == sorted(flags, reverse=True)
    assert res.candidates[0].in_class_window
    assert "derive: class J" in res.candidates[0].why
    # a passing motor outside the window still beats a failing one inside it
    small = Requirement(goal_kind="altitude", target_altitude_m=300)
    low = design_stage(small, Env(), {}, "motor", CATALOG, tier="amateur", k=None)
    first = low.candidates[0]
    assert first.passed or not any(c.passed for c in low.candidates)


def test_funnel_counts_are_consistent(amateur_result):
    res = design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, "fins", CATALOG, tier="amateur", k=5)
    assert res.enumerated > res.simulated >= len(res.candidates)
    assert res.passed <= res.simulated
    assert sum(res.rejected.values()) >= res.enumerated - res.passed
    assert all(isinstance(v, int) and v > 0 for v in res.rejected.values())


# --------------------------------------------------------------------------- ground truth


def test_ground_truth_kits_with_their_motor_fixed():
    """Each amateur kit's requirement (published apogee, its payload) with its motor fixed: the
    chain must pick an airframe that flies within the kit's tolerance (>= 15 %)."""
    kits = [e for e in load_references() if e.build is not None and e.design.tier == "amateur"]
    assert kits
    within_15 = 0
    for entry in kits:
        res = auto_design(
            entry.requirement,
            entry.env,
            CATALOG,
            tier="amateur",
            fixed={"motor": entry.build.motor_id},
        )
        assert res.build.motor_id == entry.build.motor_id
        published = entry.published["apogee_m"]
        err = abs(res.sim.metrics["apogee_m"] - published) / published
        within_15 += err <= 0.15
        assert err <= max(0.15, entry.tolerance_frac), (entry.id, res.sim.metrics["apogee_m"])
    assert within_15 >= len(kits) - 1
