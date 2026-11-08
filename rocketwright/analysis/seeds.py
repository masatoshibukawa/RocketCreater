"""Import registered literature/new starting points into the saved-design contract."""

import copy
import json
from pathlib import Path

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec
from rocketwright.bottle_search import Search


def catalog():
    return json.loads(
        (Path(__file__).resolve().parents[1] / "catalog/initial_models.json").read_text(
            encoding="utf-8"
        )
    )


def options():
    search = Search("mixed")
    result = {
        key: dict(
            label=search.records[a.start]["title"],
            design=search.design(a).model_dump(mode="json"),
            source=search.records[a.start],
            original_results_carried=False,
        )
        for key, a in search.options().items()
    }
    registered = catalog()
    for row in registered["models"]:
        result[row["id"]] = dict(
            row,
            source=registered["sources"][row["family"]],
            original_results_carried=False,
        )
    return result


def import_seed(seed_id, template):
    """Import documented parameters/adaptations; preserve the mission and environment."""
    offered = options()
    if seed_id not in offered:
        raise ValueError("Select a registered initial-search candidate")
    row = offered[seed_id]
    data = copy.deepcopy(template.model_dump(mode="json"))
    if "geometry" in row:
        data["design"].update(row["design"])
        data["geometry"] = row["geometry"]
    else:
        data["design"] = row["design"]
    data["design"]["geometry"] = data["geometry"]
    data["design"]["payload_mass_kg"] = template.design.payload_mass_kg
    data["measured_printed_mass_g"] = None
    data["assumptions"]["evidence"].update(
        initial_search_id=seed_id,
        initial_source_hash=digest(row["source"]),
        initial_adapter_hash=digest(row),
        initial_source_scope="starting parameters only; new mass and all analyses required",
    )
    return DesignSpec.model_validate(data)
