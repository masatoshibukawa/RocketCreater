"""Tool definitions (JSON Schema) handed to Claude and their implementations.

* `get_tool_definitions()` returns one strict schema per TOOL_NAMES entry (`additionalProperties:
  false`, every property required, no `$ref`). Input schemas are generated from the pydantic
  models in rocketwright.schema / rocketwright.build so the two never drift; numeric constraints
  are stripped from the exported schema because pydantic re-validates every input anyway.
* Bottle/amateur designs are made from parts: `list_parts` browses rocketwright.parts and
  `design_from_parts` resolves a build (rocketwright.build), checks buildability and simulates
  through the same `_simulate_dispatch` / `_finalize` path with the bill's cost.
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
from rocketwright.build import BuildAdapter, check_buildability, resolve
from rocketwright.classify import classify, load_tiers
from rocketwright.cost import COST_CONSTANTS, estimate_cost_jpy
from rocketwright.derive import derive
from rocketwright.design_chain import ALL_STAGES, auto_design, design_stage
from rocketwright.parts import KINDS, Part, PartsCatalog, load_parts
from rocketwright.physics import multistage, solid, water
from rocketwright.references import find_nearest, find_reference_designs, seed_design_with_build
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
    "find_reference_designs",
    "derive_requirements",
    "list_parts",
    "design_from_parts",
    "design_stage",
    "auto_design",
)

# list_parts row cap (the model browses by kind/query; the whole catalog is not a tool result).
LIST_PARTS_MAX_ROWS = 60

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

# tune_pitch_program budget: ~80 ascents at ~50-100 ms each, i.e. a few seconds per call.
_TUNE_MAX_EVALUATIONS = 80

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


def _build_schema() -> dict[str, Any]:
    raw = BuildAdapter.json_schema()
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
    # The Requirement / Env docstrings are shown once (classify_requirement /
    # simulate_design); the other tools reuse the bare schemas to keep the tool list
    # small (every tool definition is sent on every turn).
    req_full = _schema_of(Requirement)
    env_full = _schema_of(Env)
    req = {k: v for k, v in req_full.items() if k != "description"}
    env = {k: v for k, v in env_full.items() if k != "description"}
    design = _design_schema()
    tier_enum = {"type": "string", "enum": [t.value for t in Tier]}
    part_tier = {"type": "string", "enum": ["bottle", "amateur"]}
    stage_enum = {"type": "string", "enum": list(ALL_STAGES)}
    return [
        {
            "name": "classify_requirement",
            "description": (
                "Classify a normalised Requirement into a tier (bottle/amateur/commercial/heavy) "
                "using config/tiers.yaml. Returns tier, required_tier, an optional budget "
                "fallback requirement, warnings and reasons. Call this first."
            ),
            "strict": True,
            "input_schema": _obj({"requirement": req_full}),
        },
        {
            "name": "search_catalog",
            "description": (
                "List catalog items: engines and strap-on boosters (commercial/heavy, "
                "catalog/engines.yaml), parts (bottle/amateur) and solid motors (amateur, RASP "
                ".eng files). Filter by tier and/or free-text query. Use the returned `id` "
                "values verbatim as engine_id / booster_id / motor_id in designs."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "tier": _nullable(tier_enum),
                    "query": _nullable({"type": "string"}),
                    "kind": {"type": "string", "enum": ["engines", "parts", "motors", "all"]},
                }
            ),
        },
        {
            "name": "simulate_design",
            "description": (
                "Simulate one flight of a design in `env`. Pass the requirement so pass/fail is "
                "judged against it (apogee +-10 %, orbit perigee, payload, budget). Returns "
                "SimResult: success, failure_reasons, metrics (unit-suffixed keys), cost_jpy, "
                "trace, warnings, source_id. Commercial/heavy need engine ids from "
                "search_catalog. tune_pitch=true (orbit goals, a few seconds) searches "
                "pitch_start_s / initial_pitch_deg for the target orbit and returns "
                "`tuned_design` to adopt; the open-loop gravity turn is sensitive (0.1 deg can "
                "move the perigee by tens of km)."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "env": env_full,
                    "seed": _nullable({"type": "integer"}),
                    "requirement": _nullable(req),
                    "tune_pitch": {"type": "boolean"},
                }
            ),
        },
        {
            "name": "run_dispersion",
            "description": (
                "Monte-Carlo dispersion: n perturbed flights (bottle: pressure, wind; amateur: "
                "motor impulse, dry mass, wind, deploy delay; commercial/heavy: Isp, thrust, "
                "structural fraction; provisional sigmas), judged like simulate_design when the "
                "requirement is passed. Returns success_rate, quantiles (p05/p50/p95 of every "
                "metric), failure_counts, landing scatter with a 95 % ellipse (bottle/amateur) or "
                "orbit-insertion errors (commercial/heavy), warnings and `nominal`. "
                f"n: null = {DISPERSION_DEFAULT_N}, max {DISPERSION_MAX_N}. Run it on passing "
                "designs only and quote success_rate from it."
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
        {
            "name": "find_reference_designs",
            "description": (
                "Nearest real vehicles of the tier (log distance over target altitude and "
                "payload; k null = 3): id, name, sources, published performance, their "
                "requirement and site, provisional flag, notes and, for bottle/amateur kits, "
                "their parts `build` (ground truth for the design chain). With seed=true (null = "
                "true) the nearest one is scaled to the requirement by plain provisional rules: "
                "`seed` carries the design (build and bill for kits), notes explaining each step "
                "(quote them) and `sim`, its simulate_design result in `env` (null = the "
                "reference's site, trace dropped). Commercial/heavy scale propellant by the "
                "payload ratio and keep engine types; tune=true (orbit goals, a few seconds) "
                "re-tunes the seed's pitch program for the target perigee."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "requirement": req,
                    "tier": tier_enum,
                    "k": _nullable({"type": "integer"}),
                    "seed": _nullable({"type": "boolean"}),
                    "tune": _nullable({"type": "boolean"}),
                    "env": _nullable(env),
                }
            ),
        },
        {
            "name": "derive_requirements",
            "description": (
                "Closed-form quantitative targets (deterministic, no simulation); tier null = "
                "classify first. Orbit tiers: circular speed, rotation credit at "
                "launch_latitude_deg (null = provisional default), losses, Hohmann term, "
                "required delta-v, mass ratios, propellant and payload fractions, liftoff-mass "
                "scale. Amateur: burnout speed (vacuum and with drag), liftoff mass, total "
                "impulse, NAR motor class and the bundled motors in it or one above, parachute "
                "diameter. Bottle: gauge pressure for 1.5 L at 40 % fill (clipped at the safety "
                "cap), water mass, parachute need and size. Each quantity has its formula with "
                "numbers, inputs, assumptions and a provisional flag: quote the formulas, use "
                "the values as a scale, never as a result."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "requirement": req,
                    "tier": _nullable(tier_enum),
                    "launch_latitude_deg": _nullable({"type": "number"}),
                }
            ),
        },
        {
            "name": "list_parts",
            "description": (
                "Browse the parts catalog for the bottle and amateur tiers (catalog/parts.yaml): "
                "compact rows (id, name, kind, key dimensions, mass_kg, price_jpy, provisional) "
                "filtered by tier, kind (body_tube, nose_cone, motor_mount, fin_material, "
                "parachute, recovery_hardware, launch_lug, bottle, nozzle, bottle_fin_set, "
                f"launcher; null = all) and free-text query, at most {LIST_PARTS_MAX_ROWS} rows. "
                "Motors are listed by search_catalog (kind=motors). Use the ids verbatim in "
                "design_from_parts; nose cones and motor mounts say which tube they fit "
                "(fits_tube_id) and mounts which motor diameter they take."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "tier": {"type": "string", "enum": ["bottle", "amateur"]},
                    "kind": _nullable({"type": "string", "enum": list(KINDS)}),
                    "query": _nullable({"type": "string"}),
                }
            ),
        },
        {
            "name": "design_from_parts",
            "description": (
                "Design a bottle or amateur rocket by CHOOSING PARTS: mass, dimensions and cost "
                "come from the parts, never typed in. `build` is an AmateurBuild (tube id + cut "
                "length, nose, mount, motor, fin material + planform, parachute, optional "
                "recovery hardware / launch lug, payload, deploy delay) or a BottleBuild "
                "(bottle, fill, gauge pressure, nozzle, optional fin set / parachute / "
                "launcher, payload), by `tier`. Returns `design`, `bill` (rows, dry_mass_kg, "
                "cost_jpy), `issues` (buildability, severity error|warning: part fits, body "
                "length, fin sheet, chute packing, delay options, static margin, thrust-to-"
                "weight, descent; bottle: neck, pressure caps, fill, payload chute) and `sim` "
                "(judged, cost from the bill; null when any issue is an error). Fix errors "
                "first, then iterate on the warnings and the sim."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "build": _build_schema(),
                    "env": _nullable(env),
                    "requirement": _nullable(req),
                    "seed": _nullable({"type": "integer"}),
                }
            ),
        },
        {
            "name": "design_stage",
            "description": (
                "Staged bottle/amateur design: rank every catalog option of ONE stage, each "
                "completed into a full build by default rules, checked and simulated (all numbers "
                "from code). Order: amateur motor, mount, body_tube, nose_cone, body_length, "
                "fins, parachute, deploy_delay; bottle bottle, nozzle, water_fill, pressure, "
                "fins, parachute. `chosen`: upstream decisions as {stage, value = a candidate's "
                "`option`}; entries downstream of `stage` are dropped (listed in `invalidated`), "
                "missing upstream stages use the defaults. Returns the top k (null = "
                f"{DESIGN_STAGE_DEFAULT_K}) candidates (option, label, why, passed, metrics, "
                "cost_jpy, failure_reasons, issues, build), the funnel (enumerated, compatible, "
                "simulated, passed, rejected reason -> count), next_stage, derived_targets. "
                "Ranking: buildable > passes > derive's motor class +-1 > |apogee error| > cost "
                "> mass."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "tier": part_tier,
                    "requirement": req,
                    "env": _nullable(env),
                    "chosen": {
                        "type": "array",
                        "items": _obj(
                            {"stage": stage_enum, "value": {"type": "string"}},
                        ),
                    },
                    "stage": stage_enum,
                    "k": _nullable({"type": "integer"}),
                }
            ),
        },
        {
            "name": "auto_design",
            "description": (
                "Baseline bottle/amateur design: walk every design_stage in order adopting the "
                "best candidate (deterministic, 1-2 s). Returns build (confirm or edit with "
                "design_from_parts), design, bill, issues, sim (judged, trace omitted), trace "
                "per stage (chosen option, why, funnel, top-3 alternatives), derived_targets and "
                "derived_vs_chain (formula vs chosen part / simulation). Call it after "
                "derive_requirements, explain the trace, then revisit stages with design_stage."
            ),
            "strict": True,
            "input_schema": _obj({"tier": part_tier, "requirement": req, "env": _nullable(env)}),
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


def _finalize(
    result: SimResult,
    design: Design,
    req: Requirement | None,
    *,
    cost_jpy: float | None = None,
) -> SimResult:
    """Shared post-processing for every tier: `_judge` adds the requirement-level rules,
    cost.py owns the cost estimate (unless a parts bill gives `cost_jpy`) and the budget rule
    lives here once (CLAUDE.md section 6: "within budget")."""
    cost_jpy = round(estimate_cost_jpy(design) if cost_jpy is None else cost_jpy, 0)
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
    *,
    cost_jpy: float | None = None,
    **scales: float,
) -> SimResult:
    """Single dispatch point. Commercial/heavy -> physics.multistage, amateur -> physics.solid,
    bottle -> physics.water (all real models, judged against the requirement's target).
    `scales` are the model's perturbation keywords (multistage: isp_scale / thrust_scale,
    solid: thrust_scale) that rocketwright.dispersion passes per sample; empty for a nominal
    run. `cost_jpy` replaces the cost.py estimate when a parts bill is known. Module-level and
    picklable on purpose (dispersion workers)."""
    if isinstance(design, MultistageDesign):
        perigee_m, apogee_m = _orbit_targets(req)
        env, rotation_warnings = _orbit_env(env, req)
        # TODO: altitude goals for multistage (e.g. 100 km sounding flights) need a suborbital
        # judge in physics.multistage; today the model's minimum-perigee rule applies.
        result = multistage.simulate(
            design, env, seed, target_perigee_m=perigee_m, target_apogee_m=apogee_m, **scales
        )
        if rotation_warnings:
            result = result.model_copy(update={"warnings": result.warnings + rotation_warnings})
    elif isinstance(design, AmateurDesign):
        result = solid.simulate(design, env, seed, target_apogee_m=_altitude_target(req), **scales)
    elif isinstance(design, BottleDesign):
        result = water.simulate(design, env, seed, target_apogee_m=_altitude_target(req), **scales)
    else:  # pragma: no cover - the discriminated union has no other member
        raise TypeError(f"unsupported design type {type(design).__name__}")
    return _finalize(result, design, req, cost_jpy=cost_jpy)


ORBIT_ROTATION_WARNING = "earth rotation enabled for orbit goal (eastward launch assumed)"


def _orbit_env(env: Env, req: Requirement | None) -> tuple[Env, list[str]]:
    """Orbit goals are flown with Earth rotation on (the schema default stays off because Env is
    shared with the suborbital tiers): published LEO capabilities assume an eastward launch, and
    the open-loop gravity turn needs the pad speed to close an orbit at all for several
    reference vehicles. Returns the env to use and the warning to attach when it was changed."""
    if req is None or req.goal_kind is not GoalKind.ORBIT or env.earth_rotation:
        return env, []
    return env.model_copy(update={"earth_rotation": True}), [ORBIT_ROTATION_WARNING]


def _tune_pitch(design: Design, env: Env, req: Requirement | None) -> MultistageDesign:
    """Run physics.multistage.tune_pitch_program for the requirement's orbit (a few seconds)."""
    if not isinstance(design, MultistageDesign):
        raise ValueError("tune_pitch is only available for commercial/heavy designs")
    perigee_m, apogee_m = _orbit_targets(req)
    if perigee_m is None:
        raise ValueError("tune_pitch needs a requirement with goal_kind 'orbit'")
    env, _ = _orbit_env(env, req)
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


def _tool_derive_requirements(inp: dict[str, Any]) -> dict[str, Any]:
    """rocketwright.derive.derive: closed-form targets per tier (tier null -> classify first)."""
    req = Requirement.model_validate(inp["requirement"])
    tier_in = inp.get("tier")
    if tier_in is None:
        tier = classify(req).tier
        tier_from = "classify_requirement"
    else:
        tier = Tier(tier_in)
        tier_from = "input"
    lat = inp.get("launch_latitude_deg")
    out = derive(req, tier, launch_latitude_deg=None if lat is None else float(lat)).as_dict()
    out["tier_from"] = tier_from
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
    if kind not in ("engines", "parts", "motors", "all"):
        raise ValueError(f"kind must be engines|parts|motors|all, got {kind!r}")
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
    out["count"] = sum(len(v) for v in out.values() if isinstance(v, list))
    if out["count"] == 0:
        out["note"] = (
            "catalog is empty or nothing matched; propose representative values and say so"
        )
    else:
        out["note"] = (
            "use each item's `id` verbatim: engines -> Stage.engine_id, boosters -> "
            "Booster.booster_id, motors -> AmateurDesign.motor_id; unknown ids are rejected"
        )
    return out


def _tool_find_reference_designs(inp: dict[str, Any]) -> dict[str, Any]:
    """Nearest reference vehicles plus, by default, a seed design scaled from the nearest one
    and its judged simulate result (trace dropped) so the model sees the seed's performance."""
    req = Requirement.model_validate(inp["requirement"])
    tier = Tier(inp["tier"])
    k = 3 if inp.get("k") is None else int(inp["k"])
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    want_seed = True if inp.get("seed") is None else bool(inp["seed"])
    tune = bool(inp.get("tune") or False)
    out: dict[str, Any] = {
        "references": find_reference_designs(req, tier, k=k),
        "seed": None,
    }
    nearest = find_nearest(req, tier, k=1)
    if not want_seed or not nearest:
        if not nearest:
            out["note"] = f"no {tier.value} reference matches a {req.goal_kind.value} goal"
        return out
    entry = nearest[0][1]
    env = entry.env if inp.get("env") is None else Env.model_validate(inp["env"])
    # Orbit goals fly with Earth rotation on, exactly as simulate_design does, so the pitch
    # tuning and the seed's sim agree.
    env, rotation_warnings = _orbit_env(env, req)
    seed = seed_design_with_build(entry, req, env=env, tune=tune, catalog=_parts_catalog())
    design = seed.design
    cost = None if seed.bill is None else seed.bill.cost_jpy
    sim = _simulate_dispatch(design, env, None, req, cost_jpy=cost).model_dump(mode="json")
    sim["trace_point_count"] = len(sim.pop("trace"))
    if rotation_warnings and ORBIT_ROTATION_WARNING not in sim["warnings"]:
        sim["warnings"] = list(sim["warnings"]) + rotation_warnings
    out["seed"] = {
        "reference_id": entry.id,
        "design": design.model_dump(mode="json"),
        # Bottle/amateur references that carry a parts build are seeded in part space: adopt
        # `build` with design_from_parts (null for geometric seeds and the orbital tiers).
        "build": None if seed.build is None else seed.build.model_dump(mode="json"),
        "bill": None if seed.bill is None else seed.bill.model_dump(mode="json"),
        "notes": seed.notes,
        "env": env.model_dump(mode="json"),
        "sim": sim,
    }
    return out


# --------------------------------------------------------------------------- parts tools


def _parts_catalog() -> PartsCatalog:
    """The parts catalog the tools use (cached by rocketwright.parts; tests repoint
    rocketwright.parts.DEFAULT_PARTS_PATH at a fixture)."""
    return load_parts()


_PART_BASE_FIELDS = frozenset(Part.model_fields)


def _part_row(part: Part) -> dict[str, Any]:
    dims = {k: v for k, v in part.model_dump(mode="json").items() if k not in _PART_BASE_FIELDS}
    return {
        "id": part.id,
        "name": part.name,
        "kind": part.kind,
        "tier": part.tier,
        "mass_kg": part.mass_kg,
        "price_jpy": part.price_jpy,
        "provisional": part.provisional,
        **dims,
    }


def _tool_list_parts(inp: dict[str, Any]) -> dict[str, Any]:
    tier = Tier(inp["tier"]).value
    if tier not in ("bottle", "amateur"):
        raise ValueError("list_parts covers the bottle and amateur tiers only")
    kind = inp.get("kind")
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS} or null, got {kind!r}")
    query = (inp.get("query") or "").strip().lower() or None
    catalog = _parts_catalog()
    rows: list[dict[str, Any]] = []
    for part in catalog.parts:
        if part.tier != tier or (kind is not None and part.kind != kind):
            continue
        if query and query not in f"{part.id} {part.name} {part.kind} {part.notes}".lower():
            continue
        rows.append(_part_row(part))
    total = len(rows)
    rows = rows[:LIST_PARTS_MAX_ROWS]
    out: dict[str, Any] = {"parts": rows, "count": len(rows), "total": total}
    if total == 0:
        out["note"] = (
            "no parts matched"
            + (" (the parts catalog is empty)" if len(catalog) == 0 else "")
            + "; widen the kind/query"
        )
    elif total > len(rows):
        out["note"] = f"{total} parts matched; showing {len(rows)}: narrow by kind or query"
    else:
        out["note"] = "use `id` verbatim in design_from_parts; motors come from search_catalog"
    return out


def _tool_design_from_parts(inp: dict[str, Any]) -> dict[str, Any]:
    """resolve -> check_buildability -> (no errors) simulate. The bill's cost is the design's
    cost; the buildability warnings are appended to the sim's warnings."""
    build = BuildAdapter.validate_python(inp["build"])
    env = Env.model_validate(inp.get("env") or {})
    seed = inp.get("seed")
    req = _parse_optional_requirement(inp.get("requirement"))
    catalog = _parts_catalog()
    issues = check_buildability(build, catalog)
    out: dict[str, Any] = {
        "tier": build.tier,
        "build": build.model_dump(mode="json"),
        "design": None,
        "bill": None,
        "issues": [i.model_dump() for i in issues],
        "sim": None,
    }
    errors = [i for i in issues if i.severity == "error"]
    if any(i.code == "unknown_part" for i in errors):
        out["note"] = "unknown or wrong-kind part id: pick ids from list_parts / search_catalog"
        return out
    design, bill = resolve(build, catalog)
    out["design"] = design.model_dump(mode="json")
    out["bill"] = bill.model_dump(mode="json")
    if errors:
        out["note"] = (
            f"{len(errors)} buildability error(s): the rocket cannot be built as chosen, so it "
            "was not simulated; fix the `issues` with severity error first"
        )
        return out
    sim = _simulate_dispatch(design, env, seed, req, cost_jpy=bill.cost_jpy)
    build_warnings = [f"build: {i.message}" for i in issues]
    out["sim"] = sim.model_copy(
        update={"warnings": list(sim.warnings) + build_warnings}
    ).model_dump(mode="json")
    out["note"] = (
        "sim.cost_jpy is the bill total; iterate with design_from_parts (never simulate_design "
        "with hand-typed masses for this tier)"
        if not issues
        else "buildability warnings were appended to sim.warnings; judge them with the sim"
    )
    return out


# --------------------------------------------------------------------------- design chain

# design_stage default top-k when the model passes null (rocketwright.design_chain.CHAIN_RULES).
DESIGN_STAGE_DEFAULT_K = 5
DESIGN_STAGE_MAX_K = 20


def _chain_inputs(inp: dict[str, Any]) -> tuple[str, Requirement, Env]:
    tier = Tier(inp["tier"]).value
    if tier not in ("bottle", "amateur"):
        raise ValueError("the design chain covers the bottle and amateur tiers only")
    req = Requirement.model_validate(inp["requirement"])
    env = Env.model_validate(inp.get("env") or {})
    return tier, req, env


def _tool_design_stage(inp: dict[str, Any]) -> dict[str, Any]:
    """rocketwright.design_chain.design_stage: one stage's ranked candidates and funnel."""
    tier, req, env = _chain_inputs(inp)
    chosen: dict[str, str] = {}
    for pair in inp.get("chosen") or []:
        stage = pair["stage"]
        if stage in chosen:
            raise ValueError(f"stage {stage!r} appears twice in chosen")
        chosen[stage] = pair["value"]
    k = DESIGN_STAGE_DEFAULT_K if inp.get("k") is None else int(inp["k"])
    if not 1 <= k <= DESIGN_STAGE_MAX_K:
        raise ValueError(f"k must be between 1 and {DESIGN_STAGE_MAX_K}, got {k}")
    res = design_stage(req, env, chosen, inp["stage"], _parts_catalog(), tier=tier, k=k)
    out = res.as_dict()
    out["note"] = (
        "pass a candidate's `option` back in `chosen` and continue with next_stage; every "
        "number is from the bill and the simulation of that candidate's full build"
        + (f"; dropped downstream choices: {res.invalidated}" if res.invalidated else "")
    )
    return out


def _tool_auto_design(inp: dict[str, Any]) -> dict[str, Any]:
    """rocketwright.design_chain.auto_design, with the final build judged through the same
    `_simulate_dispatch` as design_from_parts (trace dropped, buildability warnings appended)."""
    tier, req, env = _chain_inputs(inp)
    res = auto_design(req, env, _parts_catalog(), tier=tier)
    sim = _simulate_dispatch(res.design, env, None, req, cost_jpy=res.bill.cost_jpy)
    sim = sim.model_copy(
        update={"warnings": list(sim.warnings) + [f"build: {i.message}" for i in res.issues]}
    ).model_dump(mode="json")
    sim["trace_point_count"] = len(sim.pop("trace"))
    return {
        "tier": tier,
        "build": res.build.model_dump(mode="json"),
        "design": res.design.model_dump(mode="json"),
        "bill": res.bill.model_dump(mode="json"),
        "issues": [i.model_dump() for i in res.issues],
        "sim": sim,
        "trace": [t.as_dict() for t in res.trace],
        "derived_targets": res.derived_targets,
        "derived_vs_chain": res.derived_vs_chain,
        "note": (
            "baseline from the staged chain; confirm or edit it with design_from_parts and "
            "revisit a stage with design_stage (later stages are then redone)"
        ),
    }


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
    "find_reference_designs": _tool_find_reference_designs,
    "derive_requirements": _tool_derive_requirements,
    "list_parts": _tool_list_parts,
    "design_from_parts": _tool_design_from_parts,
    "design_stage": _tool_design_stage,
    "auto_design": _tool_auto_design,
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
