"""Tests for rocketwright.parts: the v2 parts catalog models and loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rocketwright import parts as parts_mod
from rocketwright.parts import (
    KINDS,
    BodyTube,
    Bottle,
    FinMaterial,
    MotorMount,
    NoseCone,
    Parachute,
    PartsCatalog,
    load_parts,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parts_v2.yaml"


@pytest.fixture(scope="module")
def catalog() -> PartsCatalog:
    return load_parts(FIXTURE)


def test_fixture_loads_typed_parts(catalog):
    assert len(catalog) >= 12
    assert isinstance(catalog.get("estes_bt50"), BodyTube)
    assert isinstance(catalog.get("estes_pnc50"), NoseCone)
    assert isinstance(catalog.get("mount_18mm_bt50"), MotorMount)
    assert isinstance(catalog.get("balsa_3_32in"), FinMaterial)
    assert isinstance(catalog.get("chute_12in"), Parachute)
    assert isinstance(catalog.get("pet_bottle_1p5l"), Bottle)
    assert catalog.get("estes_bt50").outer_diameter_m == pytest.approx(0.0246)
    assert catalog.get("estes_bt50").provisional is True
    assert "legacy_v1_item" not in catalog.ids()  # the v1 `items:` block is ignored


def test_by_kind_filters_kind_and_tier(catalog):
    tubes = catalog.by_kind("body_tube")
    assert {p.id for p in tubes} == {"estes_bt50", "estes_bt60"}
    chutes_amateur = catalog.by_kind("parachute", "amateur")
    chutes_bottle = catalog.by_kind("parachute", "bottle")
    assert {p.id for p in chutes_amateur} == {"chute_12in", "chute_18in"}
    assert {p.id for p in chutes_bottle} == {"chute_0p5m_plastic"}
    assert catalog.by_kind("body_tube", "bottle") == []
    assert set(KINDS) >= {"body_tube", "nose_cone", "motor_mount", "bottle", "launcher"}


def test_get_unknown_id_lists_available(catalog):
    with pytest.raises(KeyError, match="estes_bt50"):
        catalog.get("no_such_part")


def test_get_with_expected_kind(catalog):
    assert catalog.get("estes_bt50", kind="body_tube").id == "estes_bt50"
    with pytest.raises(ValueError, match="nose_cone"):
        catalog.get("estes_bt50", kind="nose_cone")


def test_load_is_cached_per_path(catalog):
    assert load_parts(FIXTURE) is catalog


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "parts.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _tube(**over):
    base = {
        "id": "t1",
        "kind": "body_tube",
        "tier": "amateur",
        "name": "tube",
        "mass_kg": 0.01,
        "price_jpy": 100,
        "provisional": True,
        "outer_diameter_m": 0.025,
        "inner_diameter_m": 0.024,
        "length_m": 0.45,
    }
    base.update(over)
    return base


def test_duplicate_ids_rejected(tmp_path):
    path = _write(tmp_path, {"version": 2, "parts": [_tube(), _tube()]})
    with pytest.raises(ValueError, match="duplicate"):
        load_parts(path)


def test_dangling_fits_tube_id_rejected(tmp_path):
    nose = {
        "id": "n1",
        "kind": "nose_cone",
        "tier": "amateur",
        "name": "nose",
        "mass_kg": 0.01,
        "price_jpy": 100,
        "provisional": True,
        "fits_tube_id": "missing_tube",
        "shape": "ogive",
        "length_m": 0.07,
        "shoulder_length_m": 0.02,
    }
    path = _write(tmp_path, {"version": 2, "parts": [_tube(), nose]})
    with pytest.raises(ValueError, match="missing_tube"):
        load_parts(path)


def test_source_or_provisional_rule(tmp_path):
    path = _write(tmp_path, {"version": 2, "parts": [_tube(provisional=False)]})
    with pytest.raises(ValueError, match="source"):
        load_parts(path)
    ok = _write(tmp_path, {"version": 2, "parts": [_tube(provisional=False, source="https://x")]})
    assert load_parts(ok).get("t1").provisional is False


def test_unknown_kind_rejected(tmp_path):
    path = _write(tmp_path, {"version": 2, "parts": [_tube(kind="wing")]})
    with pytest.raises(ValueError):
        load_parts(path)


def test_old_file_without_parts_key_gives_empty_catalog_with_warning(tmp_path):
    path = _write(tmp_path, {"version": 2, "items": [_tube()]})
    with pytest.warns(UserWarning, match="parts"):
        cat = load_parts(path)
    assert len(cat) == 0
    assert cat.by_kind("body_tube") == []


def test_missing_file_gives_empty_catalog_with_warning(tmp_path):
    with pytest.warns(UserWarning):
        cat = load_parts(tmp_path / "nope.yaml")
    assert len(cat) == 0


def test_real_catalog_loads_or_is_empty():
    """The bundled parts.yaml is maintained separately: a v1 file gives an empty catalog, a v2
    file must validate. Either way loading never raises."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cat = load_parts(parts_mod.DEFAULT_PARTS_PATH)
    assert isinstance(cat, PartsCatalog)
    for p in cat.parts:
        assert p.provisional or p.source


def test_motor_mount_accepts_extra_fitting_tubes(tmp_path):
    bt50 = _tube(id="bt50")
    bt55 = _tube(id="bt55", outer_diameter_m=0.0338, inner_diameter_m=0.0325)
    mount = {
        "id": "m18",
        "kind": "motor_mount",
        "tier": "amateur",
        "name": "18 mm mount",
        "mass_kg": 0.006,
        "price_jpy": 500,
        "provisional": True,
        "motor_diameter_m": 0.018,
        "fits_tube_id": "bt50",
        "fits_tube_ids": ["bt55"],
        "length_m": 0.07,
    }
    cat = load_parts(_write(tmp_path, {"version": 2, "parts": [bt50, bt55, mount]}))
    assert cat.get("m18").fits_tubes == {"bt50", "bt55"}
    bad = dict(mount, fits_tube_ids=["bt99"])
    with pytest.raises(ValueError, match="bt99"):
        (tmp_path / "b").mkdir()
        load_parts(_write(tmp_path / "b", {"version": 2, "parts": [bt50, bad]}))


def test_couplers_and_power_ratings_parse(catalog):
    coupler = catalog.coupler_for("estes_bt50")
    assert coupler is not None and coupler.kind == "coupler" and coupler.length_m > 0
    assert catalog.coupler_for("estes_bt60") is None
    tube = catalog.get("estes_bt50", kind="body_tube")
    assert tube.max_motor_impulse_ns == pytest.approx(10.0)
    assert catalog.get("balsa_3_32in").max_motor_impulse_ns == pytest.approx(40.0)
    assert catalog.get("recovery_kit_small").max_rocket_mass_kg == pytest.approx(0.68)


def test_coupler_must_reference_a_tube(tmp_path):
    data = {
        "version": 2,
        "parts": [
            {
                "id": "c1",
                "kind": "coupler",
                "tier": "amateur",
                "name": "orphan coupler",
                "mass_kg": 0.001,
                "price_jpy": 100,
                "provisional": True,
                "fits_tube_id": "no_such_tube",
                "length_m": 0.03,
            }
        ],
    }
    path = tmp_path / "orphan.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="no_such_tube"):
        load_parts(path)


def test_project_catalog_has_a_coupler_for_every_tube():
    cat = load_parts()
    for tube in cat.by_kind("body_tube", "amateur"):
        if tube.id == "estes_bt5_tube":  # no mount puts a motor in it; no coupler listed
            continue
        assert cat.coupler_for(tube.id) is not None, tube.id
