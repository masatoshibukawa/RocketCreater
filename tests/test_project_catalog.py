from rocketwright.agent.design_projects import DesignSpec
from rocketwright.agent.project_catalog import reconciled_catalog
from rocketwright.manufacturing import PrintGeometry
from rocketwright.schema import BottleDesign


def test_research_is_discoverable_without_becoming_an_executable_method():
    data = reconciled_catalog()
    proposals = [m for m in data["research_methods"] if m["origin"] == "literature_proposal"]
    assert len(proposals) == 6
    assert all(m["status"] == "planned" for m in proposals)
    assert not set(m["id"] for m in proposals) & data["executable_pool"]["methods"].keys()
    assert data["sha256"] == reconciled_catalog()["sha256"]


def test_adopted_variables_resolve_to_current_schema_without_capacity_inference():
    design = BottleDesign(
        bottle_volume_m3=0.002,
        water_fill_frac=0.3,
        initial_gauge_pressure_pa=300000,
        nozzle_diameter_m=0.009,
        dry_mass_kg=0.1,
        payload_mass_kg=0.06,
    )
    spec = DesignSpec(
        design=design, geometry=PrintGeometry.from_design(design), other_dry_mass_g=80
    )
    for row in reconciled_catalog()["variables"]:
        if row["status"] != "adopted":
            continue
        value = spec
        for field in row["destination"].split("."):
            value = getattr(value, field)
    rows = {v["id"]: v for v in reconciled_catalog()["variables"]}
    assert rows["measured_body_diameter_m"]["multiplier"] == 1000
    assert rows["dry_mass_kg"]["status"] == "derived_by_host"
    assert rows["nozzle_length_m"]["status"] == "reserved"
