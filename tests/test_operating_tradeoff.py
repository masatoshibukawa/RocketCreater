import copy

import pytest

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import sha, write_json
from rocketwright.analysis.record import compile_record
from rocketwright.analysis.tradeoff import (
    Study,
    boundary_choices,
    case_spec,
    check_geometry,
    reconcile_payload,
)
from rocketwright.physics.atmosphere import state_scalar
from rocketwright.physics.bottle_integrity import thermal
from rocketwright.physics.bottle_integrity.schema import AnalysisConfig
from tests.test_analysis_record import VOLUMES, spec


def test_legacy_payload_migration_is_explicit_and_does_not_change_loaded_mass():
    s = spec()
    original = s.model_dump()
    aligned, audit = reconcile_payload(s)
    assert aligned.requirement.payload_mass_kg == aligned.design.payload_mass_kg == 0.06
    assert audit["changed"] and audit["before"] == 0 and audit["after"] == 0.06
    assert s.model_dump() == original
    aligned.requirement = aligned.requirement.model_copy(update={"payload_mass_kg": 0.08})
    with pytest.raises(ValueError, match="conflicts"):
        reconcile_payload(aligned)


def test_factorial_conditions_recompute_density_mass_and_cg_without_goal_drift():
    base, _ = reconcile_payload(spec())
    original = copy.deepcopy(base.model_dump())
    cold = case_spec(base, 5, 30, 200)
    warm = case_spec(base, 35, 90, 400)
    for s, temperature, payload, pressure in ((cold, 5, 0.03, 200000), (warm, 35, 0.09, 400000)):
        assert s.requirement.payload_mass_kg == s.design.payload_mass_kg == payload
        assert s.design.initial_gauge_pressure_pa == pressure
        assert state_scalar(s.env.launch_altitude_m, s.env.temperature_offset_k)[
            0
        ] == pytest.approx(temperature + 273.15)
        assert s.requirement.target_altitude_m == base.requirement.target_altitude_m
        assert s.geometry == base.geometry and s.other_dry_mass_g == base.other_dry_mass_g
    a, b = (compile_record(s, VOLUMES) for s in (cold, warm))
    assert a["assembly"]["dry_mass_g"] == b["assembly"]["dry_mass_g"]
    assert b["assembly"]["wet_cg_mm"] < a["assembly"]["wet_cg_mm"]
    assert b["config"]["flight"]["air_density_kg_m3"] < a["config"]["flight"]["air_density_kg_m3"]
    assert base.model_dump() == original


def test_sealed_heating_pressure_is_absolute_kelvin_and_no_wait_is_identity():
    base, _ = reconcile_payload(spec())
    s = case_spec(base, 20, 60, 400)
    cfg = AnalysisConfig.model_validate(compile_record(s, VOLUMES)["config"])
    heated = thermal.wait(s.design, cfg, ambient_c=20, initial_c=20, sealed=True)
    initial_absolute = cfg.loads.ambient_pa + 400000
    expected = initial_absolute * (heated["final_c"]["gas"] + 273.15) / 293.15
    assert heated["trace"]["absolute_pressure_pa"][-1] == pytest.approx(expected)
    assert heated["peak_absolute_pressure_pa"] - cfg.loads.ambient_pa > 400000
    cfg.warm_wait_s = 0
    unchanged = thermal.wait(s.design, cfg, ambient_c=20, initial_c=20, sealed=True)
    assert unchanged["peak_absolute_pressure_pa"] == pytest.approx(initial_absolute)


def test_cad_cache_rejects_other_geometry_and_damaged_evidence(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"cad_metrics": VOLUMES})
    write_json(tmp_path / "manifest.json", {"data.json": sha(path)})
    geometry = spec().geometry.model_dump()
    e = dict(
        artifact=str(path),
        sha256=sha(path),
        manifest_sha256=sha(tmp_path / "manifest.json"),
        key=digest(dict(geometry=geometry, source="fixed")),
    )
    check_geometry(e, geometry, "fixed")
    with pytest.raises(ValueError, match="key mismatch"):
        check_geometry(e, dict(geometry, fin_span_mm=100), "fixed")
    write_json(path, {"cad_metrics": {}})
    with pytest.raises(ValueError, match="evidence changed"):
        check_geometry(e, geometry, "fixed")


def test_boundary_refinement_requires_measured_valid_crossing_and_retains_parents():
    def row(i, pressure, height):
        return dict(
            id=i,
            condition=dict(seed="a", temperature_c=20, payload_g=60, pressure_kpa=pressure),
            status="completed",
            metrics=dict(apogee_m=height),
            checks=dict(
                aero_domain=True, temporal=True, thermal_balance=True, propulsion_balance=True
            ),
        )

    rows = [row("a", 200, 12), row("b", 300, 25), row("c", 400, 33)]
    found = boundary_choices(rows, 30, 25)
    assert len(found) == 1 and found[0]["condition"]["pressure_kpa"] == 350
    assert found[0]["parents"] == ["b", "c"]
    rows.append(row("d", 350, 31))
    assert boundary_choices(rows, 30, 25)[0]["condition"]["pressure_kpa"] == 325
    rows.append(row("e", 325, 29))
    assert not boundary_choices(rows, 30, 25)
    rows = [row("b", 300, 25), row("c", 400, 33)]
    rows[1]["checks"]["aero_domain"] = False
    assert not boundary_choices(rows, 30, 25)


@pytest.mark.parametrize(
    "settings",
    [
        dict(temperatures_c=(5, 5)),
        dict(pressures_kpa=(500,)),
        dict(seeds=()),
        dict(payloads_g=(0,)),
    ],
)
def test_invalid_or_expanded_pressure_domain_is_rejected(settings):
    with pytest.raises(ValueError):
        Study(**settings)
