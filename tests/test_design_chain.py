"""Tests for rocketwright.design_chain: the staged, code-enumerated design chain of the bottle and
amateur tiers (stage order and invalidation, candidate compatibility, the default rules, the
greedy auto design on the demo requirements, ground truth against the reference kits,
determinism and speed)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from rocketwright.build import (
    AmateurBuild,
    check_buildability,
    min_body_length_m,
    payload_bay_length_m,
    resolve,
)
from rocketwright.design_chain import (
    AMATEUR_STAGES,
    BOTTLE_STAGES,
    CHAIN_RULES,
    SYNTHETIC_MOTOR_WARNING,
    auto_design,
    candidates_for,
    complete_build,
    design_stage,
    invalidated_stages,
    is_synthetic_motor,
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


@pytest.mark.parametrize(
    "motor_id", ["estes_C6", "estes_E12", "aerotech_G80T", "aerotech_J350W", "dummy_J420"]
)
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
    chute = CATALOG.get(build.parachute_id)
    # the airframe is the best of the beam: a tube the mount fits, rated for the C6
    assert tube.id in mount.fits_tubes
    assert tube.max_motor_impulse_ns >= motor.total_impulse_ns
    # body = buildability minimum (motor bay + packed chute + shock cord + payload) + 1 caliber,
    # clipped to one stock tube when the minimum fits in one
    min_len, _ = min_body_length_m(motor, mount, tube, chute)
    expected = min(min_len + tube.outer_diameter_m, tube.length_m)
    assert build.body_length_m == pytest.approx(expected, abs=1.5e-3)
    margin = stability.static_margin_cal(design, motor.total_mass_kg, motor_length_m=motor.length_m)
    assert margin >= CHAIN_RULES["default_static_margin_cal"]
    landing = bill.dry_mass_kg + motor.total_mass_kg - motor.propellant_mass_kg
    v = recovery.descend(landing, design.parachute_diameter_m, env, 100.0).descent_speed_mps
    assert v <= CHAIN_RULES["default_descent_speed_mps"] + 0.2
    assert build.deploy_delay_s == 0.0


def test_default_body_holds_the_payload():
    """The payload bay (mass at the packing density over the bore) is part of the default body
    and of the body_length grid's minimum; the product owner's 1 kg in a short BT-80 is gone."""
    req = Requirement(goal_kind="altitude", target_altitude_m=1000, payload_mass_kg=1.0)
    chosen = {"motor": "aerotech_I284W"}
    build = complete_build(req, Env(), chosen, CATALOG, tier="amateur")
    motor = solid.load_motor(build.motor_id)
    tube, mount = CATALOG.get(build.body_tube_id), CATALOG.get(build.motor_mount_id)
    chute = CATALOG.get(build.parachute_id)
    min_len, bays = min_body_length_m(motor, mount, tube, chute, 1.0)
    assert bays["payload_bay_m"] == pytest.approx(payload_bay_length_m(1.0, None, tube), rel=1e-9)
    assert bays["payload_bay_m"] > 0.1
    assert build.body_length_m >= min_len - 1e-9
    assert "body_length_min" not in {i.code for i in check_buildability(build, CATALOG)}
    grid = candidates_for("body_length", req, Env(), dict(chosen), CATALOG, tier="amateur")
    assert min(c.value for c in grid) >= min_len - 1.5e-3


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
    # the motor stage runs the airframe beam of every motor (up to beam_max_sims flights each
    # inside derive's class window): 2 s; every other stage 1 s
    for stage in AMATEUR_STAGES:
        t0 = time.perf_counter()
        design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, stage, CATALOG, tier="amateur")
        limit = 2.0 if stage == "motor" else 1.0
        assert time.perf_counter() - t0 < limit, stage


def test_motor_stage_ranks_the_derived_class_first():
    res = design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, "motor", CATALOG, tier="amateur", k=None)
    assert res.enumerated == len(solid.list_motor_ids())
    assert res.simulated == sum(
        1 for c in res.candidates if not any(i.severity == "error" for i in c.issues)
    )  # the motor stage is never pruned
    # derive: 2 km with 1 kg is class J; the window is I..K (certified motors only: a real
    # motor passes, so the synthetic placeholders are not offered)
    assert res.derived_targets["motor_class_letter"] == "J"
    window = {c.value for c in res.candidates if c.in_class_window}
    letters = {solid.load_motor(m).name[0] for m in window}
    assert letters <= {"I", "J", "K"} and {"I", "J"} <= letters
    assert not any(is_synthetic_motor(c.value) for c in res.candidates)
    # within the same pass status and tube count, every in-window motor ranks before the others
    buildable = [c for c in res.candidates if not any(i.severity == "error" for i in c.issues)]
    for status in (True, False):
        for joints in (0, 1):
            flags = [
                c.in_class_window
                for c in buildable
                if (c.passed, min(1, _couplers(c.build))) == (status, joints)
            ]
            assert flags == sorted(flags, reverse=True)
    assert res.candidates[0].in_class_window
    assert "derive: class J" in res.candidates[0].why
    # a passing motor outside the window still beats a failing one inside it
    small = Requirement(goal_kind="altitude", target_altitude_m=300)
    low = design_stage(small, Env(), {}, "motor", CATALOG, tier="amateur", k=None)
    first = low.candidates[0]
    assert first.passed or not any(c.passed for c in low.candidates)


def _couplers(build) -> int:
    from rocketwright.build import tube_count

    tube = CATALOG.get(build.body_tube_id)
    return tube_count(build.body_length_m, tube.length_m) - 1


def test_synthetic_motors_only_when_no_real_motor_passes():
    # 1 kg to 2 km: a certified J passes, the dummy_* placeholders are held back
    res = design_stage(AMATEUR_REQ, AMATEUR_ENV, {}, "motor", CATALOG, tier="amateur", k=None)
    assert any(c.passed for c in res.candidates)
    n_dummy = sum(is_synthetic_motor(m) for m in solid.list_motor_ids())
    assert res.rejected[f"{SYNTHETIC_MOTOR_WARNING} (a certified motor passes)"] == n_dummy
    # 5 kg to 3 km: nothing certified passes -> the placeholders are evaluated, labelled
    hard = Requirement(goal_kind="altitude", target_altitude_m=3000, payload_mass_kg=5.0)
    res = design_stage(hard, AMATEUR_ENV, {}, "motor", CATALOG, tier="amateur", k=None)
    real = [c for c in res.candidates if not is_synthetic_motor(c.value)]
    dummies = [c for c in res.candidates if is_synthetic_motor(c.value)]
    assert not any(c.passed for c in real)
    assert len(dummies) == n_dummy
    assert all(SYNTHETIC_MOTOR_WARNING in c.label for c in dummies)


def test_motor_scored_on_its_best_airframe_not_the_narrowest():
    """Beam: a motor that passes in a wider tube ranks as passing. 1 kg to 1 km on the J435WS
    overshoots in the narrowest (54 mm) LOC tube that takes it and passes in the 98 mm one."""
    req = Requirement(goal_kind="altitude", target_altitude_m=1000, payload_mass_kg=1.0)
    cands = candidates_for("motor", req, AMATEUR_ENV, {}, CATALOG, tier="amateur")
    by_id = {c.value: c for c in cands}
    motor = solid.load_motor("aerotech_J435WS")
    best = by_id[motor.id]
    assert best.passed
    narrow = complete_build(
        req,
        AMATEUR_ENV,
        {"motor": motor.id, "mount": "motor_mount_38mm", "body_tube": "loc_tube_54mm"},
        CATALOG,
        tier="amateur",
    )
    assert best.build.body_tube_id != narrow.body_tube_id
    sim = solid.simulate(resolve(narrow, CATALOG)[0], AMATEUR_ENV, target_apogee_m=1000)
    assert not sim.success


def test_couplers_rank_below_single_tube_bodies():
    """Same pass state: a body that needs a coupler scores below one that fits one stock tube
    (the coupler is also on the bill: mass and price)."""
    from rocketwright.design_chain import _Chain

    req = Requirement(goal_kind="altitude", target_altitude_m=400, payload_mass_kg=0.1)
    chain = _Chain(req, AMATEUR_ENV, CATALOG, "amateur")
    base = {"motor": "aerotech_F32T", "mount": "motor_mount_24mm", "body_tube": "estes_bt60_tube"}
    tube = CATALOG.get("estes_bt60_tube")
    single = chain.evaluate(chain.complete({**base, "body_length": 0.45}))
    double = chain.evaluate(chain.complete({**base, "body_length": 0.47}))
    assert single.build.body_length_m <= tube.length_m < double.build.body_length_m
    assert (single.has_error, single.passed) == (double.has_error, double.passed)
    assert chain.couplers(single.build) == 0 and chain.couplers(double.build) == 1
    assert chain.score(single, None, "x") < chain.score(double, None, "x")
    row = next(r for r in double.bill.parts if r.part_id == "estes_jt60c_coupler")
    assert row.qty == 1 and row.mass_kg > 0 and row.price_jpy > 0
    assert not any(r.part_id == "estes_jt60c_coupler" for r in single.bill.parts)


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


# --------------------------------------------------------------------------- feasibility


def test_auto_design_says_when_the_budget_cannot_be_met():
    """1 kg to 2 km for 30,000 JPY: the cheapest passing design costs more; auto_design must
    say so, name that design and its cost, and the best design within the budget with the
    reasons it fails (the constants are not bent to make it fit)."""
    req = AMATEUR_REQ.model_copy(update={"budget_jpy": 30000})
    t0 = time.perf_counter()
    res = auto_design(req, AMATEUR_ENV, CATALOG, tier="amateur")
    assert time.perf_counter() - t0 < 3.0
    assert not res.sim.success
    f = res.feasibility
    assert f is not None and f["passing_design_exists"]
    cheapest = f["cheapest_passing"]
    assert cheapest["cost_jpy"] > 30000 and not cheapest["failure_reasons"]
    assert "no passing design within the 30,000 JPY budget" in f["verdict"]
    assert f"{cheapest['cost_jpy']:,.0f} JPY" in f["verdict"]
    within = f["best_within_budget"]
    assert within is not None and within["cost_jpy"] <= 30000 and within["failure_reasons"]
    assert f["verdict"] in res.warnings
    # every number in the report is a bill / sim number of a real chain design
    b = AmateurBuild.model_validate(cheapest["build"])
    _, bill = resolve(b, CATALOG)
    assert round(bill.cost_jpy) == cheapest["cost_jpy"]


def test_auto_design_without_a_feasibility_question(amateur_result):
    # a passing design needs no feasibility report
    assert amateur_result.sim.success and amateur_result.feasibility is None
    assert not any(SYNTHETIC_MOTOR_WARNING in w for w in amateur_result.warnings)
    assert not is_synthetic_motor(amateur_result.build.motor_id)


@pytest.mark.parametrize(
    ("target_m", "payload_kg", "budget_jpy"),
    [(2000, 1.0, 50000), (1000, 1.0, 50000), (500, 0.2, 20000)],
)
def test_amateur_requirements_get_real_buildable_designs(target_m, payload_kg, budget_jpy):
    """The product owner's requirements: certified motors, rated airframe and fins, the payload
    inside the body, and a pass within the budget (2026-11-03 catalog)."""
    req = Requirement(
        goal_kind="altitude",
        target_altitude_m=target_m,
        payload_mass_kg=payload_kg,
        budget_jpy=budget_jpy,
        recovery_required=True,
    )
    res = auto_design(req, AMATEUR_ENV, CATALOG, tier="amateur")
    _assert_passing(res, req)
    assert not is_synthetic_motor(res.build.motor_id)
    codes = {i.code for i in res.issues}
    assert not codes & {"tube_power_rating", "fin_power_rating", "body_length_min"}
    motor = solid.load_motor(res.build.motor_id)
    tube = CATALOG.get(res.build.body_tube_id)
    assert motor.total_impulse_ns <= tube.max_motor_impulse_ns
