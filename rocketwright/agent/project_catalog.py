"""Reconcile archived research contracts with the executable, host-owned pool.

Literature proposals are discoverable metadata; listing them never registers a
runner or promotes a bibliography entry into numerical/physical evidence.
"""

from pathlib import Path

import yaml

from rocketwright.adaptive import Pool, digest

CATALOG = Path(__file__).resolve().parents[1] / "catalog"

# Explicit unit conversions into the current saved-design schema. Unmapped research
# variables stay reserved. No value is inferred from bottle capacity here.
BINDINGS = {
    "measured_body_diameter_m": ("geometry.body_diameter_mm", 1000),
    "fins.count": ("geometry.fin_count", 1),
    "fins.root_chord_m": ("geometry.fin_root_mm", 1000),
    "fins.tip_chord_m": ("geometry.fin_tip_mm", 1000),
    "fins.span_m": ("geometry.fin_span_mm", 1000),
    "fins.sweep_m": ("geometry.fin_sweep_mm", 1000),
    "fins.thickness_m": ("geometry.fin_thickness_mm", 1000),
    "fins.mount_type": ("assumptions.mount", 1),
    "env.rail_length_m": ("env.rail_length_m", 1),
}


def reconciled_catalog():
    from rocketwright.agent.tools import TOOL_REGISTRY

    legacy = yaml.safe_load((CATALOG / "bottle_variables.yaml").read_text(encoding="utf-8"))
    literature = yaml.safe_load((CATALOG / "bottle_literature.yaml").read_text(encoding="utf-8"))
    pool = Pool.load()
    references = literature["references"]
    variables, methods, evaluations = [], [], []
    for component in legacy["components"]:
        for role in ("design_inputs", "environment_inputs", "reserved", "derived"):
            for key, row in component.get(role, {}).items():
                target = BINDINGS.get(key)
                if key in ("dry_mass_kg",):
                    status, destination = "derived_by_host", "analysis.design.dry_mass_kg"
                elif role == "design_inputs":
                    status, destination = "adopted", "design." + key
                elif target:
                    status, destination = "adopted", target[0]
                else:
                    status, destination = "reserved", None
                variables.append(
                    dict(
                        id=key,
                        component=component["kind"],
                        role=role,
                        status=status,
                        destination=destination,
                        multiplier=target[1] if target else 1,
                        definition=row,
                        references=component.get("references", []),
                    )
                )
    for key, row in legacy["analysis_methods"].items():
        methods.append(
            dict(
                id=key,
                origin="legacy_tool",
                status="available" if key in TOOL_REGISTRY else "reserved",
                definition=row,
            )
        )
    for key, row in literature["analysis_methods"].items():
        methods.append(dict(id=key, origin="literature_proposal", status="planned", definition=row))
    for origin, document in (("legacy_tool", legacy), ("literature_proposal", literature)):
        for key, row in document["evaluation_functions"].items():
            evaluations.append(
                dict(id=key, origin=origin, status="reference_contract", definition=row)
            )
    for row in variables + methods:
        refs = row.get("references", row["definition"].get("references", []))
        if set(refs) - references.keys():
            raise ValueError(f"Unknown research reference in {row['id']}")
    for key, row in literature["evaluation_functions"].items():
        method = literature["analysis_methods"][row["method"]]
        if set(row["uses"]) - method["outputs"].keys():
            raise ValueError(f"Unknown observable in {key}")
    result = dict(
        schema_version=1,
        variables=variables,
        research_methods=methods,
        research_evaluations=evaluations,
        references=references,
        executable_pool=pool.model_dump(mode="json"),
        policy=(
            "Only host-registered actions execute. "
            "References and planned contracts do not establish validation."
        ),
    )
    return {**result, "sha256": digest(result)}
