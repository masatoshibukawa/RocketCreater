"""Import registered literature/new starting points into the saved-design contract."""

import copy

from rocketwright.adaptive import digest
from rocketwright.agent.design_projects import DesignSpec
from rocketwright.bottle_search import Search


def options():
    search = Search("mixed")
    return {
        key: dict(
            label=search.records[a.start]["title"],
            design=search.design(a).model_dump(mode="json"),
            source=search.records[a.start],
            original_results_carried=False,
        )
        for key, a in search.options().items()
    }


def import_seed(seed_id, template):
    """Keep explicit geometry/mass/mission/environment; discard old flight scores."""
    offered = options()
    if seed_id not in offered:
        raise ValueError("Select a registered initial-search candidate")
    row = offered[seed_id]
    data = copy.deepcopy(template.model_dump(mode="json"))
    data["design"] = row["design"]
    data["design"]["payload_mass_kg"] = template.design.payload_mass_kg
    data["measured_printed_mass_g"] = None
    data["assumptions"]["evidence"].update(
        initial_search_id=seed_id,
        initial_source_hash=digest(row["source"]),
        initial_source_scope="starting parameters only; new mass and all analyses required",
    )
    return DesignSpec.model_validate(data)
