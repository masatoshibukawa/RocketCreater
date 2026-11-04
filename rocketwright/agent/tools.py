"""Tool definitions (JSON Schema) handed to Claude and their implementations.

* `get_tool_definitions()` returns the 7 tool schemas (strict mode: `additionalProperties:
  false`, every property required, no `$ref`). Input schemas are generated from the pydantic
  models in rocketwright.schema so the two never drift; numeric constraints are stripped from
  the exported schema because pydantic re-validates every input anyway.
* `TOOL_REGISTRY` maps tool name -> implementation (parsed input dict -> JSON-serialisable dict).
* `execute_tool(name, input, tool_use_id)` validates, runs, and stamps `source_id`.

Physics dispatch lives in `_simulate_dispatch` / `_dispersion_dispatch` ONLY. Commercial/heavy
designs go to rocketwright.physics.multistage, amateur to physics.solid and bottle to
physics.water (all real models). Monte-Carlo dispersion runs rocketwright.dispersion with the
tier's perturbation spec over the same judged `_simulate_dispatch`, so every sample is passed or
failed by the same rules (requirement target, payload, recovery, budget) as simulate_design.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from rocketwright import dispersion as mc
from rocketwright.agent.store import store_drawing, store_report
from rocketwright.classify import classify, load_tiers
from rocketwright.cost import COST_CONSTANTS, estimate_cost_jpy
from rocketwright.physics import multistage, solid, water
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    DesignAdapter,
    DispersionResult,
    Env,
    GoalKind,
    MultistageDesign,
    Requirement,
    SimResult,
    Tier,
)

__all__ = [
    "TOOL_NAMES",
    "TOOL_REGISTRY",
    "DISPERSION_DEFAULT_N",
    "DISPERSION_MAX_N",
    "PASS_CRITERIA",
    "execute_tool",
    "get_tool_definitions",
]

TOOL_NAMES: tuple[str, ...] = (
    "classify_requirement",
    "search_catalog",
    "simulate_design",
    "run_dispersion",
    "estimate_cost",
    "render_drawing",
    "export_report",
)

# run_dispersion sample count: default when the model passes null, and the hard cap (the
# schema caps the scatter at 5000 points; 500 keeps a commercial run at a few seconds).
DISPERSION_DEFAULT_N = 100
DISPERSION_MAX_N = 500

# Requirement-vs-design rules judged here (`_judge`, CLAUDE.md section 6). Flight rules live
# ONLY in the physics modules' PASS_THRESHOLDS (multistage: perigee/apogee tolerance, liftoff
# TWR, max-Q; solid: rail exit speed, stability margin, descent speed, apogee tolerance; water:
# apogee tolerance, descent speed, bottle pressure cap). The budget rule lives in `_finalize`.
PASS_CRITERIA: dict[str, float] = {
    "payload_shortfall_tolerance_kg": 0.0,  # design must carry at least the required payload
}

# tune_pitch_program budget: ~60 ascents at ~35 ms each, i.e. a few seconds per call.
_TUNE_MAX_EVALUATIONS = 60

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"
_MAX_ERROR_CHARS = 2000

# --------------------------------------------------------------------------- schema export

_DROP_KEYS = frozenset(
    {
        "title",
        "default",
        "discriminator",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
    }
)


def _strictify(node: Any, defs: dict[str, Any]) -> Any:
    """Inline $ref, drop keys unsupported by strict tool schemas, require every property."""
    if isinstance(node, list):
        return [_strictify(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
        return _strictify(merged, defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP_KEYS or key == "$defs":
            continue
        if key in ("properties",):
            out[key] = {k: _strictify(v, defs) for k, v in value.items()}
        elif key == "oneOf":
            # The strict subset documents anyOf/allOf only (the SDK's own structured-output
            # transform rewrites oneOf the same way); with const discriminators it is equivalent.
            out["anyOf"] = _strictify(value, defs)
        elif key in ("items", "anyOf", "allOf"):
            out[key] = _strictify(value, defs)
        else:
            out[key] = value
    if "properties" in out:
        out["type"] = "object"
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
    return out


def _schema_of(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    return _strictify(raw, raw.get("$defs", {}))


def _design_schema() -> dict[str, Any]:
    raw = DesignAdapter.json_schema()
    return _strictify(raw, raw.get("$defs", {}))


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def get_tool_definitions() -> list[dict[str, Any]]:
    req = _schema_of(Requirement)
    env = _schema_of(Env)
    design = _design_schema()
    tier_enum = {"type": "string", "enum": [t.value for t in Tier]}
    return [
        {
            "name": "classify_requirement",
            "description": (
                "Classify a normalised Requirement into a tier (bottle/amateur/commercial/heavy) "
                "using config/tiers.yaml. Returns tier, required_tier, an optional budget "
                "fallback requirement, warnings and reasons. Call this first."
            ),
            "strict": True,
            "input_schema": _obj({"requirement": req}),
        },
        {
            "name": "search_catalog",
            "description": (
                "List catalog items: engines and strap-on boosters (commercial/heavy, "
                "catalog/engines.yaml), parts (bottle/amateur) and solid motors (amateur, RASP "
                ".eng files). Filter by tier and/or free-text query. Use the returned `id` "
                "values verbatim as engine_id / booster_id / motor_id in designs. For water "
                "rockets use kind=resources to find candidate materials, components and "
                "equipment by model, shelf or role (e.g. fins, vibration, mass_measurement). "
                "Resource ids identify planning candidates, not simulator inputs or inventory."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "tier": _nullable(tier_enum),
                    "query": _nullable({"type": "string"}),
                    "kind": {
                        "type": "string",
                        "enum": ["engines", "parts", "motors", "resources", "all"],
                    },
                }
            ),
        },
        {
            "name": "simulate_design",
            "description": (
                "Simulate one flight of a design in the given environment. Pass the requirement "
                "so pass/fail is judged against it (orbit goals: perigee >= target - 10 %, "
                "budget). Returns SimResult: success, failure_reasons, metrics (unit-suffixed "
                "keys), cost_jpy, trace, warnings, source_id. Commercial/heavy designs use the "
                "real multistage model and need engine ids from search_catalog "
                "(catalog/engines.yaml, e.g. merlin_1d). Set tune_pitch=true (orbit goals "
                "only) to let scipy search pitch_start_s / initial_pitch_deg for the target "
                "orbit before simulating: it costs a few seconds and the result then includes "
                "`tuned_design`, which you should adopt as your design. The open-loop gravity "
                "turn is sensitive: a tenth of a degree can change the perigee by tens of km."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "env": env,
                    "seed": _nullable({"type": "integer"}),
                    "requirement": _nullable(req),
                    "tune_pitch": {"type": "boolean"},
                }
            ),
        },
        {
            "name": "run_dispersion",
            "description": (
                "Monte-Carlo dispersion: n perturbed flights of a design (bottle: pressure and "
                "wind; amateur: motor impulse, dry mass, wind, deploy delay; commercial/heavy: "
                "Isp, thrust, structural fraction; sigmas are provisional) judged by the same "
                "rules as simulate_design when the requirement is passed. Returns success_rate "
                "(fraction of samples that pass), quantiles (p05/p50/p95 of every metric), "
                "failure_counts (reason -> samples), landing scatter with a 95 % ellipse "
                "(bottle/amateur) or orbit-insertion error statistics about the nominal run "
                "(commercial/heavy), warnings, and `nominal` (the unperturbed result). "
                f"n: null = {DISPERSION_DEFAULT_N}, max {DISPERSION_MAX_N}. Run it on passing "
                "designs only (a few seconds each) and quote success_rate from it."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "env": env,
                    "n": _nullable({"type": "integer"}),
                    "seed": {"type": "integer"},
                    "requirement": _nullable(req),
                }
            ),
        },
        {
            "name": "estimate_cost",
            "description": "Estimate the cost of a design in JPY (provisional constants).",
            "strict": True,
            "input_schema": _obj({"design": design}),
        },
        {
            "name": "render_drawing",
            "description": (
                "Render a dimensioned SVG side view of a design (deterministic; commercial/heavy "
                "are concept sketches). The SVG itself is not returned: the result carries an "
                "artifact `id`, `svg_chars` and `download.svg` (a path served by the API) that "
                "you quote in the final answer."
            ),
            "strict": True,
            "input_schema": _obj({"design": design}),
        },
        {
            "name": "export_report",
            "description": (
                "Export the design report (Markdown + JSON) and the bill of materials (CSV) for "
                "ONE design. `result_json` is the simulate_design result for that design as JSON "
                "text (copy the tool result verbatim; its source_id is used as the provenance of "
                "every metric). `dispersion_json` is the matching run_dispersion result as JSON "
                "text, or null. `requirement` is the normalised requirement, or null. The report "
                "text is not returned: the result carries `id`, `markdown_chars`, `bom_rows` and "
                "a `download` map (report .md, json, bom .csv paths) to quote in the final answer."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "result_json": {"type": "string"},
                    "requirement": _nullable(req),
                    "dispersion_json": _nullable({"type": "string"}),
                }
            ),
        },
    ]


# --------------------------------------------------------------------------- helpers


def _parse_design(data: Any) -> Design:
    return DesignAdapter.validate_python(data)


def _parse_optional_requirement(data: Any) -> Requirement | None:
    return None if data is None else Requirement.model_validate(data)


def _judge(design: Design, req: Requirement | None) -> list[str]:
    """Requirement-vs-design rules that no physics module owns (payload carried, recovery
    requested). Flight rules are judged inside physics.multistage / solid / water; the budget
    rule is applied by `_finalize`."""
    reasons: list[str] = []
    if req is None:
        return reasons
    shortfall = req.payload_mass_kg - design.payload_mass_kg
    if shortfall > PASS_CRITERIA["payload_shortfall_tolerance_kg"]:
        reasons.append(
            f"design carries {design.payload_mass_kg:g} kg but the requirement needs "
            f"{req.payload_mass_kg:g} kg of payload"
        )
    if req.recovery_required and isinstance(design, BottleDesign) and not design.has_parachute:
        reasons.append("recovery is required but the design has no parachute")
    return reasons


def _finalize(result: SimResult, design: Design, req: Requirement | None) -> SimResult:
    """Shared post-processing for every tier: `_judge` adds the requirement-level rules,
    cost.py owns the cost estimate and the budget rule lives here once (CLAUDE.md section 6:
    "within budget")."""
    cost_jpy = round(estimate_cost_jpy(design), 0)
    reasons = list(result.failure_reasons) + _judge(design, req)
    if req is not None and req.budget_jpy is not None and cost_jpy > req.budget_jpy:
        reasons.append(f"cost {cost_jpy:,.0f} JPY exceeds budget {req.budget_jpy:,.0f} JPY")
    return result.model_copy(
        update={"cost_jpy": cost_jpy, "failure_reasons": reasons, "success": not reasons}
    )


def _altitude_target(req: Requirement | None) -> float | None:
    """target_apogee_m for physics.solid / physics.water when the requirement is an altitude
    goal (the models then apply their +-10 % apogee rule), else None."""
    if req is None or req.goal_kind is not GoalKind.ALTITUDE:
        return None
    return req.target_altitude_m


def _orbit_targets(req: Requirement | None) -> tuple[float | None, float | None]:
    """(target_perigee_m, target_apogee_m) for physics.multistage, or (None, None) when the
    requirement is not an orbit goal (the model then applies its default minimum perigee)."""
    if req is None or req.goal_kind is not GoalKind.ORBIT:
        return None, None
    return req.target_altitude_m, req.target_apogee_m


def _simulate_dispatch(
    design: Design,
    env: Env,
    seed: int | None,
    req: Requirement | None = None,
    **scales: float,
) -> SimResult:
    """Single dispatch point. Commercial/heavy -> physics.multistage, amateur -> physics.solid,
    bottle -> physics.water (all real models, judged against the requirement's target).
    `scales` are the model's perturbation keywords (multistage: isp_scale / thrust_scale,
    solid: thrust_scale) that rocketwright.dispersion passes per sample; empty for a nominal
    run. Module-level and picklable on purpose (dispersion workers)."""
    if isinstance(design, MultistageDesign):
        perigee_m, apogee_m = _orbit_targets(req)
        # TODO: altitude goals for multistage (e.g. 100 km sounding flights) need a suborbital
        # judge in physics.multistage; today the model's minimum-perigee rule applies.
        result = multistage.simulate(
            design, env, seed, target_perigee_m=perigee_m, target_apogee_m=apogee_m, **scales
        )
    elif isinstance(design, AmateurDesign):
        result = solid.simulate(design, env, seed, target_apogee_m=_altitude_target(req), **scales)
    elif isinstance(design, BottleDesign):
        result = water.simulate(design, env, seed, target_apogee_m=_altitude_target(req), **scales)
    else:  # pragma: no cover - the discriminated union has no other member
        raise TypeError(f"unsupported design type {type(design).__name__}")
    return _finalize(result, design, req)


def _tune_pitch(design: Design, env: Env, req: Requirement | None) -> MultistageDesign:
    """Run physics.multistage.tune_pitch_program for the requirement's orbit (a few seconds)."""
    if not isinstance(design, MultistageDesign):
        raise ValueError("tune_pitch is only available for commercial/heavy designs")
    perigee_m, apogee_m = _orbit_targets(req)
    if perigee_m is None:
        raise ValueError("tune_pitch needs a requirement with goal_kind 'orbit'")
    return multistage.tune_pitch_program(
        design,
        env,
        target_perigee_m=perigee_m,
        target_apogee_m=apogee_m,
        max_evaluations=_TUNE_MAX_EVALUATIONS,
    )


def _dispersion_dispatch(
    design: Design, env: Env, n: int, seed: int, req: Requirement | None = None
) -> mc.DispersionRun:
    """Single dispatch point for Monte-Carlo runs: rocketwright.dispersion with the tier's
    perturbation spec, every sample simulated and judged by `_simulate_dispatch` (so the
    requirement's target / payload / recovery / budget rules apply to each sample)."""
    perturb, summarize = mc.components_for(design.tier)
    return mc.run_dispersion_detailed(
        design,
        env,
        n,
        seed,
        perturb=perturb,
        simulate=functools.partial(_simulate_dispatch, req=req),
        tier=Tier(design.tier),
        summarize=summarize,
    )


# --------------------------------------------------------------------------- implementations


def _tool_classify(inp: dict[str, Any]) -> dict[str, Any]:
    req = Requirement.model_validate(inp["requirement"])
    res = classify(req)
    tiers = load_tiers()["tiers"]
    out = res.model_dump(mode="json")
    out["budget_min_jpy"] = {
        "required_tier": tiers[res.required_tier.value]["budget_min"]["value"],
        "tier": tiers[res.tier.value]["budget_min"]["value"],
        "provisional": True,
    }
    return out


def _load_yaml_list(name: str, key: str) -> list[dict[str, Any]]:
    path = _CATALOG_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get(key) or [])


def _load_motors() -> list[dict[str, Any]]:
    """RASP .eng headers: `name diameter_mm length_mm delays prop_mass_kg total_mass_kg maker`."""
    out: list[dict[str, Any]] = []
    motors_dir = _CATALOG_DIR / "motors"
    if not motors_dir.is_dir():
        return out
    for path in sorted(motors_dir.glob("*.eng")):
        item: dict[str, Any] = {"id": path.stem, "tier": "amateur", "file": path.name}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(";") or not line.strip():
                continue
            fields = line.split()
            if len(fields) >= 7:
                item.update(
                    name=fields[0],
                    diameter_mm=float(fields[1]),
                    length_mm=float(fields[2]),
                    delays=fields[3],
                    propellant_mass_kg=float(fields[4]),
                    total_mass_kg=float(fields[5]),
                    manufacturer=fields[6],
                )
            break
        out.append(item)
    return out


def _item_matches(
    item: dict[str, Any], tier: str | None, query: str | None, default_tiers: set[str]
) -> bool:
    if tier is not None:
        item_tiers = item.get("tiers") or ([item["tier"]] if "tier" in item else default_tiers)
        if tier not in item_tiers:
            return False
    if query:
        return query.lower() in json.dumps(item, ensure_ascii=False).lower()
    return True


def _tool_search_catalog(inp: dict[str, Any]) -> dict[str, Any]:
    tier = inp.get("tier")
    if tier is not None:
        tier = Tier(tier).value
    query = inp.get("query") or None
    kind = inp.get("kind") or "all"
    if kind not in ("engines", "parts", "motors", "resources", "all"):
        raise ValueError(f"kind must be engines|parts|motors|resources|all, got {kind!r}")
    out: dict[str, Any] = {"engines": [], "parts": [], "motors": []}
    if kind in ("engines", "all"):
        out["engines"] = [
            e
            for e in _load_yaml_list("engines.yaml", "engines")
            if _item_matches(e, tier, query, {"commercial", "heavy"})
        ]
    if kind in ("parts", "all"):
        out["parts"] = [
            p
            for p in _load_yaml_list("parts.yaml", "items")
            if _item_matches(p, tier, query, {"bottle", "amateur"})
        ]
    if kind in ("motors", "all"):
        out["motors"] = [m for m in _load_motors() if _item_matches(m, tier, query, {"amateur"})]
    if kind == "resources" or (kind == "all" and tier in (None, "bottle")):
        out["resources"] = [
            row
            for row in _load_yaml_list("bottle_resources.yaml", "items")
            if _item_matches(row, tier, query, {"bottle"})
        ]
        out["resource_scope"] = (
            "Planning candidates only. Source facts apply to the named object. 'needs' lists "
            "evidence to collect for the intended use. Stock, compatibility, pressure rating "
            "and measured properties are not implied. Resource ids do not go into BottleDesign."
        )
    out["count"] = sum(len(v) for v in out.values() if isinstance(v, list))
    if kind == "resources":
        out["note"] = (
            "Select a resource id and plan its checks." if out["resources"]
            else "No registered resource matched. Broaden the query or request a sourced entry."
        )
    elif out["count"] == 0:
        out["note"] = (
            "catalog is empty or nothing matched; propose representative values and say so"
        )
    else:
        out["note"] = (
            "use each item's `id` verbatim: engines -> Stage.engine_id, boosters -> "
            "Booster.booster_id, motors -> AmateurDesign.motor_id; unknown ids are rejected"
        )
    return out


def _tool_simulate(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    env = Env.model_validate(inp.get("env") or {})
    seed = inp.get("seed")
    req = _parse_optional_requirement(inp.get("requirement"))
    tuned: MultistageDesign | None = None
    if inp.get("tune_pitch"):
        tuned = _tune_pitch(design, env, req)
        design = tuned
    out = _simulate_dispatch(design, env, seed, req).model_dump(mode="json")
    if tuned is not None:
        out["tuned_design"] = tuned.model_dump(mode="json")
    return out


def _tool_dispersion(inp: dict[str, Any]) -> dict[str, Any]:
    """DispersionResult fields plus `nominal` (the unperturbed run's success / failure_reasons /
    metrics, not one of the n samples) so the model can relate the spread to simulate_design."""
    design = _parse_design(inp["design"])
    env = Env.model_validate(inp.get("env") or {})
    n = DISPERSION_DEFAULT_N if inp.get("n") is None else int(inp["n"])
    seed = int(inp["seed"])
    if not 1 <= n <= DISPERSION_MAX_N:
        raise ValueError(f"n must be between 1 and {DISPERSION_MAX_N}, got {n}")
    req = _parse_optional_requirement(inp.get("requirement"))
    run = _dispersion_dispatch(design, env, n, seed, req)
    out = run.result.model_dump(mode="json")
    out["nominal"] = {
        "success": run.nominal.success,
        "failure_reasons": list(run.nominal.failure_reasons),
        "metrics": dict(run.nominal.metrics),
    }
    return out


def _tool_estimate_cost(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    return {
        "tier": design.tier,
        "cost_jpy": round(estimate_cost_jpy(design), 0),
        "provisional": True,
        "constants": {k: v["value"] for k, v in COST_CONSTANTS.items()},
    }


def _tool_render_drawing(inp: dict[str, Any]) -> dict[str, Any]:
    """SVG side view -> artifact store; the model gets the id and download path only."""
    design = _parse_design(inp["design"])
    return store_drawing(design)


def _parse_json_model(text: Any, model: type[BaseModel], label: str) -> Any:
    """Parse JSON text into `model`, keeping only the model's own fields (tool results carry
    extras such as `source_id`-less `tuned_design` or `trace_point_count`)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label} must be JSON text of the corresponding tool result")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    kept = {k: v for k, v in data.items() if k in model.model_fields}
    return model.model_validate(kept)


def _tool_export_report(inp: dict[str, Any]) -> dict[str, Any]:
    """Markdown/JSON report + BOM CSV -> artifact store (ids and download paths returned)."""
    design = _parse_design(inp["design"])
    result: SimResult = _parse_json_model(inp.get("result_json"), SimResult, "result_json")
    if result.tier.value != design.tier:
        raise ValueError(f"result tier {result.tier.value!r} does not match design {design.tier!r}")
    req = _parse_optional_requirement(inp.get("requirement"))
    disp_text = inp.get("dispersion_json")
    dispersion: DispersionResult | None = (
        None
        if disp_text is None
        else _parse_json_model(disp_text, DispersionResult, "dispersion_json")
    )
    return store_report(design, result, requirement=req, dispersion=dispersion)


TOOL_REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "classify_requirement": _tool_classify,
    "search_catalog": _tool_search_catalog,
    "simulate_design": _tool_simulate,
    "run_dispersion": _tool_dispersion,
    "estimate_cost": _tool_estimate_cost,
    "render_drawing": _tool_render_drawing,
    "export_report": _tool_export_report,
}


def execute_tool(name: str, tool_input: Any, tool_use_id: str) -> dict[str, Any]:
    """Run a tool by name. Never raises on bad input: returns {"error": ...} instead, which the
    loop forwards with is_error=True. Every result carries `source_id` = the tool_use id."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}", "source_id": tool_use_id}
    if not isinstance(tool_input, dict):
        return {
            "error": f"tool input must be an object, got {type(tool_input).__name__}",
            "source_id": tool_use_id,
        }
    try:
        result = fn(tool_input)
    except ValidationError as exc:
        return {
            "error": f"validation error: {str(exc)[:_MAX_ERROR_CHARS]}",
            "source_id": tool_use_id,
        }
    except (KeyError, ValueError, TypeError, RuntimeError) as exc:
        # KeyError: unknown catalog id (physics.multistage.get_engine lists the valid ones);
        # RuntimeError: the ODE integration failed. Both go back to the model as is_error.
        return {
            "error": f"{type(exc).__name__}: {str(exc)[:_MAX_ERROR_CHARS]}",
            "source_id": tool_use_id,
        }
    result["source_id"] = tool_use_id
    return result
