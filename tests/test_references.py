"""Reference-vehicle catalog: validation, nearest-neighbour search, physics reproduction and
reference-seeded designs (seed_design + the find_reference_designs tool)."""

from pathlib import Path

import pytest
import yaml

from rocketwright.agent.tools import TOOL_NAMES, TOOL_REGISTRY, execute_tool, get_tool_definitions
from rocketwright.physics import multistage, solid, water
from rocketwright.references import (
    ReferenceEntry,
    find_nearest,
    find_reference_designs,
    get_reference,
    load_references,
    load_references_from,
    reproduce,
    requirement_distance,
    seed_design,
)
from rocketwright.schema import DesignAdapter, Env, GoalKind, Requirement, SimResult, Tier

_ENTRY = {
    "id": "toy_bottle",
    "tier": "bottle",
    "name": "Toy bottle",
    "sources": ["https://example.org/bottle"],
    "requirement": {"goal_kind": "altitude", "target_altitude_m": 40, "payload_mass_kg": 0.0},
    "design": {
        "tier": "bottle",
        "bottle_volume_m3": 0.0015,
        "water_fill_frac": 0.4,
        "initial_gauge_pressure_pa": 500_000,
        "nozzle_diameter_m": 0.022,
        "dry_mass_kg": 0.12,
    },
    "published": {"apogee_m": 40},
}


def _write(tmp_path: Path, *entries: dict) -> Path:
    (tmp_path / "x.yaml").write_text(yaml.safe_dump({"references": list(entries)}))
    return tmp_path


def test_loads_and_validates(tmp_path):
    entries = load_references_from(_write(tmp_path, _ENTRY))
    assert [e.id for e in entries] == ["toy_bottle"]
    assert entries[0].design.tier == "bottle"


@pytest.mark.parametrize(
    "patch, match",
    [
        ({"sources": ["wikipedia Electron"]}, "public URLs"),
        ({"sources": []}, "sources"),
        ({"published": {"apogee": 40}}, "unit suffix"),
        ({"published": {"max_speed_mps": 40}}, "missing"),
        ({"tier": "amateur"}, "design.tier"),
    ],
)
def test_rejects_bad_entries(tmp_path, patch, match):
    with pytest.raises((ValueError, Exception), match=match):
        load_references_from(_write(tmp_path, {**_ENTRY, **patch}))


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_references_from(_write(tmp_path, _ENTRY, _ENTRY))


def test_distance_and_nearest(tmp_path):
    far = {
        **_ENTRY,
        "id": "far",
        "requirement": {**_ENTRY["requirement"], "target_altitude_m": 4000},
    }
    orbit = {
        **_ENTRY,
        "id": "orbit",
        "requirement": {"goal_kind": "orbit", "target_altitude_m": 40, "payload_mass_kg": 0.0},
    }
    entries = tuple(load_references_from(_write(tmp_path, _ENTRY, far)))
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=50)
    ranked = find_nearest(req, Tier.BOTTLE, entries=entries)
    assert [e.id for _, e in ranked] == ["toy_bottle", "far"]
    assert ranked[0][0] < ranked[1][0]
    # orbit goals never match altitude goals, and vice versa
    orbit_entry = ReferenceEntry.model_validate(orbit)
    assert requirement_distance(req, orbit_entry) == float("inf")
    assert find_nearest(req, Tier.AMATEUR, entries=entries) == []


def test_bundled_catalog_is_valid():
    entries = load_references()
    for e in entries:
        assert e.sources, e.id


@pytest.mark.parametrize("entry", load_references(), ids=lambda e: e.id)
def test_reproduces_published_performance(entry):
    """Every bundled reference must fly through our physics within its tolerance. This is the
    precision claim of the project; loosen `tolerance_frac` on the entry only with a reason."""
    rep = reproduce(entry)
    assert rep.errors_frac, "nothing compared"
    assert rep.within_tolerance, (
        f"{entry.id}: errors {rep.errors_frac} exceed {rep.tolerance_frac:.0%}; "
        f"failure_reasons={rep.failure_reasons}"
    )


# --------------------------------------------------------------------------- design seeds

G0 = 9.80665
# The three demo scenarios (scenarios/*.yaml, fake_client.DEMO_REQUIREMENTS).
DEMO_COMMERCIAL = Requirement(
    goal_kind=GoalKind.ORBIT, target_altitude_m=400_000, payload_mass_kg=150, budget_jpy=2.0e9
)
DEMO_AMATEUR = Requirement(
    goal_kind=GoalKind.ALTITUDE,
    target_altitude_m=2000,
    payload_mass_kg=1.0,
    budget_jpy=50_000,
    recovery_required=True,
)
DEMO_BOTTLE = Requirement(
    goal_kind=GoalKind.ALTITUDE,
    target_altitude_m=30,
    payload_mass_kg=0.06,
    budget_jpy=3000,
    recovery_required=True,
)
ENV_COMMERCIAL = {"launch_latitude_deg": 31.25, "launch_altitude_m": 20, "wind_speed_mps": 5.0}
ENV_AMATEUR = {"launch_latitude_deg": 36.0, "launch_altitude_m": 300, "wind_speed_mps": 3.0}
ENV_BOTTLE = {"launch_latitude_deg": 35.0, "launch_altitude_m": 20, "wind_speed_mps": 2.0}


def _liftoff_twr(design) -> float:
    wet = sum(
        s.propellant_mass_kg
        + multistage.structural_mass_kg(s.propellant_mass_kg, s.structural_fraction)
        for s in design.stages
    )
    thrust = (
        multistage.get_engine(design.stages[0].engine_id).thrust_sl_n
        * design.stages[0].engine_count
    )
    for b in design.boosters:
        spec = multistage.get_engine(b.booster_id)
        wet += (spec.mass_kg + spec.propellant_mass_kg) * b.count
        thrust += spec.thrust_sl_n * b.count
    return thrust / ((wet + design.fairing_mass_kg + design.payload_mass_kg) * G0)


def _valid(design) -> None:
    DesignAdapter.validate_python(design.model_dump())


def test_seed_multistage_scales_payload_and_keeps_twr():
    entry = get_reference("electron")
    design, notes = seed_design(entry, DEMO_COMMERCIAL)
    _valid(design)
    assert design.tier == "commercial"
    assert design.payload_mass_kg == 150
    assert notes and all(isinstance(n, str) and n for n in notes)
    # propellant scaled by the payload ratio (linear SIMPLIFICATION), stage mass ratios kept
    ref = entry.design
    assert design.stages[0].propellant_mass_kg == pytest.approx(
        ref.stages[0].propellant_mass_kg * 0.5
    )
    assert design.stages[1].propellant_mass_kg == pytest.approx(
        ref.stages[1].propellant_mass_kg * 0.5
    )
    assert [s.engine_id for s in design.stages] == [s.engine_id for s in ref.stages]
    assert _liftoff_twr(design) >= 1.2
    # the pitch program is the reference's until the caller asks for tuning
    assert design.pitch_start_s == ref.pitch_start_s
    assert design.initial_pitch_deg == ref.initial_pitch_deg


def test_seed_multistage_keeps_boosters_and_twr_when_payload_grows():
    entry = get_reference("atlas_v_551")
    req = Requirement(goal_kind=GoalKind.ORBIT, target_altitude_m=200_000, payload_mass_kg=30_000)
    design, notes = seed_design(entry, req)
    _valid(design)
    assert design.boosters == entry.design.boosters
    assert design.stages[0].engine_count >= entry.design.stages[0].engine_count
    assert _liftoff_twr(design) >= 1.2
    assert any("booster" in n for n in notes)


def test_seed_amateur_picks_bigger_motor_when_payload_doubles():
    entry = get_reference("estes_alpha_iii_c6")
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=351, payload_mass_kg=0.068)
    design, notes = seed_design(entry, req)
    _valid(design)
    assert design.payload_mass_kg == 0.068
    ref_motor = solid.load_motor(entry.design.motor_id)
    new_motor = solid.load_motor(design.motor_id)
    assert new_motor.total_impulse_ns >= ref_motor.total_impulse_ns
    # the airframe must hold the motor
    assert design.body_diameter_m >= new_motor.diameter_m
    assert design.body_length_m >= new_motor.length_m
    # parachute grows with the square root of the landing mass
    assert design.parachute_diameter_m > entry.design.parachute_diameter_m
    assert design.fins.count == entry.design.fins.count
    assert any("motor" in n for n in notes)


def test_seed_amateur_falls_back_to_largest_motor_with_a_note():
    entry = get_reference("estes_alpha_iii_c6")
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=20_000, payload_mass_kg=50.0)
    design, notes = seed_design(entry, req)
    _valid(design)
    biggest = max(solid.list_motor_ids(), key=lambda m: solid.load_motor(m).total_impulse_ns)
    assert design.motor_id == biggest
    assert any("largest" in n for n in notes)


def test_seed_bottle_clips_pressure_and_adds_parachute_for_an_egg():
    entry = get_reference("apte_2l_800ml_40psi")
    assert not entry.design.has_parachute
    # a 200 m target would need 2.5 MPa: clipped at the safety cap, with a note
    far = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=200, payload_mass_kg=0.06)
    design, notes = seed_design(entry, far)
    _valid(design)
    assert design.initial_gauge_pressure_pa == water.PASS_THRESHOLDS["max_gauge_pressure_pa"]
    assert any("cap" in n for n in notes)
    assert design.has_parachute and design.parachute_diameter_m is not None
    assert design.payload_mass_kg == 0.06
    # the bottle itself is kept
    assert design.bottle_volume_m3 == entry.design.bottle_volume_m3
    assert design.nozzle_diameter_m == entry.design.nozzle_diameter_m
    # pressure scales linearly with the apogee ratio below the cap
    design2, _ = seed_design(entry, DEMO_BOTTLE)
    assert design2.initial_gauge_pressure_pa == pytest.approx(
        entry.design.initial_gauge_pressure_pa * 30 / entry.requirement.target_altitude_m
    )
    # no payload and no recovery: no parachute added
    design3, _ = seed_design(
        entry, Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=25, payload_mass_kg=0.0)
    )
    assert not design3.has_parachute


def test_find_reference_designs_is_light_and_sorted():
    rows = find_reference_designs(DEMO_COMMERCIAL, Tier.COMMERCIAL, k=2)
    assert len(rows) == 2
    assert rows[0]["id"] == "electron"
    assert [r["distance"] for r in rows] == sorted(r["distance"] for r in rows)
    for r in rows:
        assert set(r) >= {
            "id",
            "name",
            "sources",
            "distance",
            "published",
            "requirement",
            "provisional",
            "notes",
        }
        assert "design" not in r and "trace" not in r
        assert len(r["notes"]) <= 300
    assert find_reference_designs(DEMO_COMMERCIAL, Tier.AMATEUR) == []


def test_find_reference_designs_tool_schema_and_registry():
    assert "find_reference_designs" in TOOL_NAMES
    assert "find_reference_designs" in TOOL_REGISTRY
    defs = {d["name"]: d for d in get_tool_definitions()}
    schema = defs["find_reference_designs"]["input_schema"]
    assert defs["find_reference_designs"]["strict"] is True
    assert set(schema["properties"]) == {"requirement", "tier", "k", "seed", "tune", "env"}
    assert sorted(schema["required"]) == sorted(schema["properties"])
    assert schema["additionalProperties"] is False


def test_find_reference_designs_tool_returns_references_and_seed_sim():
    inp = {
        "requirement": DEMO_BOTTLE.model_dump(mode="json"),
        "tier": "bottle",
        "k": 2,
        "seed": True,
        "tune": None,
        "env": ENV_BOTTLE,
    }
    out = execute_tool("find_reference_designs", inp, "toolu_ref")
    assert "error" not in out, out
    assert out["source_id"] == "toolu_ref"
    assert len(out["references"]) <= 2
    assert out["references"][0]["id"] == out["seed"]["reference_id"]
    seed = out["seed"]
    DesignAdapter.validate_python(seed["design"])
    assert seed["notes"]
    sim = seed["sim"]
    assert "trace" not in sim and sim["trace_point_count"] > 0
    assert set(sim) >= {"success", "failure_reasons", "metrics", "cost_jpy", "warnings"}
    assert sim["metrics"]["apogee_m"] > 0
    # seed=false skips the seed
    out2 = execute_tool("find_reference_designs", {**inp, "seed": False}, "toolu_ref2")
    assert out2["seed"] is None and len(out2["references"]) <= 2
    # no reference for this tier: empty list, seed None, not an error
    out3 = execute_tool("find_reference_designs", {**inp, "tier": "heavy"}, "toolu_ref3")
    assert out3["references"] == [] and out3["seed"] is None


def _seed_via_tool(req: Requirement, tier: str, env: dict, tune: bool) -> dict:
    out = execute_tool(
        "find_reference_designs",
        {
            "requirement": req.model_dump(mode="json"),
            "tier": tier,
            "k": None,
            "seed": True,
            "tune": tune,
            "env": env,
        },
        "toolu_e2e",
    )
    assert "error" not in out, out
    return out["seed"]


def test_demo_commercial_seed_passes_simulate_after_tuning():
    """The point of the catalog: a reference-seeded 150 kg -> 400 km design passes on the
    first try (perigee >= 360 km) once the pitch program is re-tuned for the new orbit."""
    seed = _seed_via_tool(DEMO_COMMERCIAL, "commercial", ENV_COMMERCIAL, tune=True)
    assert seed["reference_id"] == "electron"
    sim = SimResult.model_validate(
        {k: v for k, v in seed["sim"].items() if k in SimResult.model_fields}
    )
    assert sim.metrics["perigee_m"] >= 360_000, (sim.metrics, sim.failure_reasons)
    assert sim.success, sim.failure_reasons
    assert any("tuned" in n for n in seed["notes"])


def test_demo_amateur_seed_apogee_within_50_percent():
    """The seed is the drag-free scaling of a C6 kit (references._seed_amateur_build). With
    certified motors only (the synthetic dummy_J420 that used to land it within 25 % is no
    longer offered) the rule asks for ~1,250 Ns and the only certified motor at or above it,
    the J415W (1,232 Ns), overshoots in the 54 mm airframe (~+40 %). The seed is a starting
    point; design_chain.auto_design is the designer (test_design_chain). It must still be a
    certified motor in an airframe and fin stock rated for it."""
    seed = _seed_via_tool(DEMO_AMATEUR, "amateur", ENV_AMATEUR, tune=False)
    apogee = seed["sim"]["metrics"]["apogee_m"]
    assert abs(apogee - 2000) <= 0.50 * 2000, (seed["reference_id"], apogee, seed["notes"])
    from rocketwright.build import AmateurBuild, check_buildability
    from rocketwright.parts import load_parts

    build = AmateurBuild.model_validate(seed["build"])
    assert not build.motor_id.startswith("dummy_")
    codes = {i.code for i in check_buildability(build, load_parts()) if i.severity == "error"}
    assert not codes & {"tube_power_rating", "fin_power_rating", "body_length_min"}, codes


def test_demo_bottle_seed_apogee_within_25_percent():
    seed = _seed_via_tool(DEMO_BOTTLE, "bottle", ENV_BOTTLE, tune=False)
    apogee = seed["sim"]["metrics"]["apogee_m"]
    assert abs(apogee - 30) <= 0.25 * 30, (seed["reference_id"], apogee, seed["notes"])
    assert seed["design"]["has_parachute"]


# --------------------------------------------------------------------------- build-space seeds


def _fixture_catalog():
    from pathlib import Path

    from rocketwright.parts import load_parts

    return load_parts(Path(__file__).resolve().parent / "fixtures" / "parts_v2.yaml")


def _alpha_build_entry() -> ReferenceEntry:
    from rocketwright.build import AmateurBuild, FinGeometry, resolve_amateur

    build = AmateurBuild(
        body_tube_id="estes_bt50",
        body_length_m=0.24,
        nose_cone_id="estes_pnc50",
        motor_mount_id="mount_18mm_bt50",
        motor_id="estes_C6",
        fin_material_id="balsa_3_32in",
        fins=FinGeometry(
            count=3, root_chord_m=0.064, tip_chord_m=0.025, span_m=0.044, sweep_m=0.038
        ),
        parachute_id="chute_12in",
        recovery_hardware_id="recovery_kit_small",
        launch_lug_id="launch_lug_1_8in",
        deploy_delay_s=0.0,
    )
    design, _ = resolve_amateur(build, _fixture_catalog())
    return ReferenceEntry(
        id="alpha_build",
        tier=Tier.AMATEUR,
        name="Alpha-like kit (parts build)",
        sources=["https://estesrockets.com/products/alpha"],
        requirement=Requirement(
            goal_kind=GoalKind.ALTITUDE, target_altitude_m=300, recovery_required=True
        ),
        design=design,
        build=build,
        published={"apogee_m": 300.0},
        env=Env(rail_length_m=1.0),
    )


def _bottle_build_entry() -> ReferenceEntry:
    from rocketwright.build import BottleBuild, resolve_bottle

    build = BottleBuild(
        bottle_id="pet_bottle_1p5l",
        water_fill_frac=0.4,
        initial_gauge_pressure_pa=300000,
        nozzle_id="nozzle_21p7mm",
        fin_set_id="bottle_fins_cardboard",
        launcher_id="launcher_bike_pump",
    )
    design, _ = resolve_bottle(build, _fixture_catalog())
    return ReferenceEntry(
        id="bottle_build",
        tier=Tier.BOTTLE,
        name="1.5 L bottle rocket (parts build)",
        sources=["https://example.org/bottle"],
        requirement=Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=30),
        design=design,
        build=build,
        published={"apogee_m": 30.0},
    )


def test_reference_entry_build_tier_must_match():
    from rocketwright.references import _check_consistency

    entry = _alpha_build_entry()
    _check_consistency(entry)
    bad = entry.model_copy(update={"build": _bottle_build_entry().build})
    with pytest.raises(ValueError, match="build.tier"):
        _check_consistency(bad)


def test_seed_amateur_in_build_space_keeps_parts_for_a_near_requirement():
    from rocketwright.build import check_buildability, resolve_amateur
    from rocketwright.references import seed_design_with_build

    cat = _fixture_catalog()
    entry = _alpha_build_entry()
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=280, payload_mass_kg=0.0)
    seed = seed_design_with_build(entry, req, catalog=cat)
    assert seed.build is not None and seed.bill is not None
    assert seed.build.motor_id == "estes_C6" and seed.build.body_tube_id == "estes_bt50"
    design, bill = resolve_amateur(seed.build, cat)
    assert seed.design == design
    assert seed.bill.dry_mass_kg == pytest.approx(bill.dry_mass_kg)
    assert not [i for i in check_buildability(seed.build, cat) if i.severity == "error"]
    assert seed.notes[0].startswith("seeded from") and "part space" in seed.notes[0]
    assert any("bill" in n for n in seed.notes)


def test_seed_amateur_in_build_space_swaps_motor_mount_and_tube():
    from rocketwright.build import check_buildability
    from rocketwright.references import seed_design_with_build

    cat = _fixture_catalog()
    entry = _alpha_build_entry()
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=1500, payload_mass_kg=0.1)
    seed = seed_design_with_build(entry, req, catalog=cat)
    b = seed.build
    assert b is not None
    assert b.motor_id != "estes_C6"
    motor = solid.load_motor(b.motor_id)
    mount = cat.get(b.motor_mount_id)
    assert abs(mount.motor_diameter_m - motor.diameter_m) < 1e-3
    assert mount.fits_tube_id == b.body_tube_id
    assert cat.get(b.nose_cone_id).fits_tube_id == b.body_tube_id
    assert b.payload_mass_kg == 0.1
    # the catalog has no mount for 38/54 mm motors: they are never picked
    assert motor.diameter_m <= 0.029
    issues = check_buildability(b, cat)
    assert not [
        i
        for i in issues
        if i.code
        in (
            "motor_mount_diameter",
            "mount_fits_tube",
            "nose_fits_tube",
            "body_length_min",
            "body_length_stock",
            "deploy_delay",
            "parachute_packed",
        )
    ], issues
    assert any("-> " + b.motor_id in n for n in seed.notes)


def test_seed_bottle_in_build_space_adds_catalog_parachute_and_clips_pressure():
    from rocketwright.build import check_buildability
    from rocketwright.references import seed_design_with_build

    cat = _fixture_catalog()
    entry = _bottle_build_entry()
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=120, payload_mass_kg=0.06)
    seed = seed_design_with_build(entry, req, catalog=cat)
    b = seed.build
    assert b is not None and b.parachute_id == "chute_0p5m_plastic"
    # 300 kPa x 4 = 1.2 MPa wanted; clipped at the launcher's 600 kPa (the smallest cap)
    assert b.initial_gauge_pressure_pa == pytest.approx(600000)
    assert any("launcher_bike_pump" in n for n in seed.notes)
    assert seed.design.has_parachute and seed.design.payload_mass_kg == 0.06
    assert not [i for i in check_buildability(b, cat) if i.severity == "error"]


def test_seed_without_build_falls_back_to_geometry():
    from rocketwright.references import seed_design, seed_design_with_build

    entry = get_reference("estes_alpha_iii_c6").model_copy(update={"build": None})
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=400)
    seed = seed_design_with_build(entry, req, catalog=_fixture_catalog())
    design, notes = seed_design(entry, req)
    assert seed.build is None and seed.bill is None
    assert seed.design == design and seed.notes == notes


def test_seed_with_build_falls_back_when_catalog_lacks_the_parts(tmp_path):
    from rocketwright.parts import load_parts
    from rocketwright.references import seed_design_with_build

    empty = tmp_path / "parts.yaml"
    empty.write_text("version: 2\nparts: []\n", encoding="utf-8")
    entry = _alpha_build_entry()
    req = Requirement(goal_kind=GoalKind.ALTITUDE, target_altitude_m=400)
    seed = seed_design_with_build(entry, req, catalog=load_parts(empty))
    assert seed.build is None
    assert any("could not be seeded" in n for n in seed.notes)


def test_find_reference_designs_tool_reports_seed_build(monkeypatch):
    from rocketwright import references

    entry = _alpha_build_entry()
    monkeypatch.setattr(references, "load_references", lambda: (entry,))
    monkeypatch.setattr("rocketwright.agent.tools._parts_catalog", lambda: _fixture_catalog())
    inp = {
        "requirement": {"goal_kind": "altitude", "target_altitude_m": 280, "payload_mass_kg": 0.0},
        "tier": "amateur",
        "k": None,
        "seed": None,
        "tune": None,
        "env": None,
    }
    out = execute_tool("find_reference_designs", inp, "toolu_sb")
    assert "error" not in out, out
    seed = out["seed"]
    assert seed["build"]["tier"] == "amateur" and seed["build"]["motor_id"] == "estes_C6"
    assert seed["bill"]["cost_jpy"] == pytest.approx(seed["sim"]["cost_jpy"], abs=0.5)
    assert seed["design"]["dry_mass_kg"] == pytest.approx(seed["bill"]["dry_mass_kg"])


# --------------------------------------------------------------------------- kit-level ground truth


def _kit_entries() -> list[ReferenceEntry]:
    return [e for e in load_references() if e.tier in (Tier.BOTTLE, Tier.AMATEUR)]


def test_every_bottle_and_amateur_reference_is_a_kit():
    """Bottle/amateur ground truth is kit-level: every entry carries a parts build whose ids
    resolve against the bundled catalog, and its `design` IS that build resolved (hand-written
    designs only remain as documented fallbacks)."""
    from rocketwright.build import resolve
    from rocketwright.parts import load_parts

    cat = load_parts()
    kits = _kit_entries()
    assert len(kits) >= 9 + 6 + 2
    for e in kits:
        assert e.build is not None, e.id
        design, bill = resolve(e.build, cat)
        assert design.tier == e.tier.value
        assert bill.dry_mass_kg > 0


def test_reference_builds_have_no_buildability_error():
    """A real kit must be buildable by our rules; a kit that is not is evidence against the
    rule (build.BUILD_THRESHOLDS carries the kits that changed them)."""
    from rocketwright.build import check_buildability
    from rocketwright.parts import load_parts

    cat = load_parts()
    bad = {
        e.id: [i.message for i in check_buildability(e.build, cat) if i.severity == "error"]
        for e in _kit_entries()
    }
    assert not {k: v for k, v in bad.items() if v}


def test_entries_without_design_get_it_from_the_build(tmp_path):
    raw = {
        "id": "kit_only",
        "tier": "amateur",
        "name": "Kit stated once",
        "sources": ["https://example.org/kit"],
        "requirement": {"goal_kind": "altitude", "target_altitude_m": 300},
        "build": _alpha_build_entry().build.model_dump(mode="json"),
        "published": {"apogee_m": 300, "dry_mass_kg": 0.03},
    }
    [entry] = load_references_from(_write(tmp_path, raw), catalog=_fixture_catalog())
    assert entry.design.tier == "amateur"
    assert entry.design.dry_mass_kg == pytest.approx(_alpha_build_entry().design.dry_mass_kg)
    assert entry.design.motor_id == "estes_C6"
    # a build naming parts the catalog lacks is a loading error, not a silent fallback
    from rocketwright.parts import load_parts

    empty = tmp_path / "empty.yaml"
    empty.write_text("version: 2\nparts: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="catalog lacks"):
        load_references_from(_write(tmp_path, raw), catalog=load_parts(empty))


def test_reproduce_flies_the_resolved_build_and_compares_mass():
    from rocketwright.build import resolve_amateur

    cat = _fixture_catalog()
    entry = _alpha_build_entry()
    design, bill = resolve_amateur(entry.build, cat)
    heavy = entry.model_copy(
        update={
            # a hand-written design twice as heavy: it must NOT be the one flown
            "design": design.model_copy(update={"dry_mass_kg": 2 * design.dry_mass_kg}),
            "published": {"apogee_m": 300.0, "dry_mass_kg": bill.dry_mass_kg * 1.1},
            "mass_tolerance_frac": 0.15,
            "tolerance_frac": 0.60,
        }
    )
    rep = reproduce(heavy, catalog=cat)
    assert rep.from_build
    assert rep.simulated["dry_mass_kg"] == pytest.approx(bill.dry_mass_kg)
    assert rep.errors_frac["dry_mass_kg"] == pytest.approx(1 / 1.1 - 1)
    assert rep.tolerance_for("dry_mass_kg") == 0.15 and rep.tolerance_for("apogee_m") == 0.60
    assert rep.within_tolerance
    flown_light = solid.simulate(design, heavy.env, None).metrics["apogee_m"]
    assert rep.simulated["apogee_m"] == pytest.approx(flown_light)
    # the mass tolerance is its own: 30 % off the published weight fails at 0.15
    off = heavy.model_copy(
        update={"published": {"apogee_m": 300.0, "dry_mass_kg": bill.dry_mass_kg * 1.3}}
    )
    assert not reproduce(off, catalog=cat).within_tolerance
    # no build: the hand-written design is flown and no mass is compared
    geometric = heavy.model_copy(update={"build": None})
    rep2 = reproduce(geometric, catalog=cat)
    assert not rep2.from_build and "dry_mass_kg" not in rep2.simulated
    assert rep2.simulated["apogee_m"] < flown_light


def test_find_reference_designs_rows_carry_the_build():
    rows = find_reference_designs(DEMO_AMATEUR, Tier.AMATEUR, k=2)
    assert rows and all(r["build"] is not None and r["build"]["tier"] == "amateur" for r in rows)
    assert all("design" not in r for r in rows)
    assert find_reference_designs(DEMO_COMMERCIAL, Tier.COMMERCIAL, k=1)[0]["build"] is None
