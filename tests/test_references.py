"""Reference-vehicle catalog: validation, nearest-neighbour search and physics reproduction."""

from pathlib import Path

import pytest
import yaml

from rocketwright.references import (
    ReferenceEntry,
    find_nearest,
    load_references,
    load_references_from,
    reproduce,
    requirement_distance,
)
from rocketwright.schema import GoalKind, Requirement, Tier

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
