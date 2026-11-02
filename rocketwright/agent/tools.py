"""Tool definitions (JSON Schema) handed to Claude and their implementations.

* `get_tool_definitions()` returns the 7 tool schemas (strict mode: `additionalProperties:
  false`, every property required, no `$ref`). Input schemas are generated from the pydantic
  models in rocketwright.schema so the two never drift; numeric constraints are stripped from
  the exported schema because pydantic re-validates every input anyway.
* `TOOL_REGISTRY` maps tool name -> implementation (parsed input dict -> JSON-serialisable dict).
* `execute_tool(name, input, tool_use_id)` validates, runs, and stamps `source_id`.

Physics dispatch lives in `_simulate_dispatch` / `_dispersion_dispatch` ONLY, so phase 2 can swap
the dummy for rocketwright.physics.{multistage,solid,water} in one place.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from rocketwright.classify import classify, load_tiers
from rocketwright.cost import COST_CONSTANTS, estimate_cost_jpy, liftoff_mass_kg
from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    DesignAdapter,
    DispersionResult,
    Ellipse95,
    Env,
    GoalKind,
    LandingPoint,
    LandingScatter,
    MultistageDesign,
    OrbitInsertionStats,
    OrbitSample,
    Quantiles,
    Requirement,
    SimResult,
    Tier,
    TracePoint,
)

__all__ = [
    "TOOL_NAMES",
    "TOOL_REGISTRY",
    "DUMMY_WARNING",
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

DUMMY_WARNING = "DUMMY PHYSICS: values are placeholders"

# Pass/fail thresholds used by the dummy judge (CLAUDE.md section 6). The real physics modules
# own their own criteria; these are kept here only until phase 2 swaps the dummy out.
PASS_CRITERIA: dict[str, float] = {
    "altitude_tolerance_frac": 0.10,  # apogee within +-10 % of target
    "min_stability_margin_cal": 1.5,
    "max_descent_speed_mps": 6.0,
}

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
        elif key in ("items", "anyOf", "oneOf", "allOf"):
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
                "List catalog items: engines (commercial/heavy), parts (bottle/amateur) and "
                "solid motors (amateur, RASP .eng files). Filter by tier and/or free-text query."
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
                "Simulate one flight of a design in the given environment. Pass the requirement "
                "so pass/fail is judged against it. Returns SimResult: success, failure_reasons, "
                "metrics (unit-suffixed keys), cost_jpy, trace, warnings, source_id."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "env": env,
                    "seed": _nullable({"type": "integer"}),
                    "requirement": _nullable(req),
                }
            ),
        },
        {
            "name": "run_dispersion",
            "description": (
                "Monte-Carlo dispersion of n flights with a seed. Returns success_rate, "
                "quantiles (p05/p50/p95), failure_counts and landing scatter (bottle/amateur) "
                "or orbit-insertion statistics (commercial/heavy)."
            ),
            "strict": True,
            "input_schema": _obj(
                {
                    "design": design,
                    "env": env,
                    "n": {"type": "integer"},
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
            "description": "Render a dimensioned SVG side view of a design (phase 3; stub).",
            "strict": True,
            "input_schema": _obj({"design": design}),
        },
        {
            "name": "export_report",
            "description": "Export a design report and bill of materials (phase 3; stub).",
            "strict": True,
            "input_schema": _obj(
                {
                    "designs": {"type": "array", "items": design},
                    "format": {"type": "string", "enum": ["markdown", "json", "csv"]},
                }
            ),
        },
    ]


# --------------------------------------------------------------------------- helpers


def _parse_design(data: Any) -> Design:
    return DesignAdapter.validate_python(data)


def _parse_optional_requirement(data: Any) -> Requirement | None:
    return None if data is None else Requirement.model_validate(data)


def _rng_for(design: Design, env: Env, seed: int | None, salt: str) -> random.Random:
    """Deterministic RNG from a hash of (design, env, seed, salt)."""
    payload = json.dumps(
        {
            "design": design.model_dump(mode="json"),
            "env": env.model_dump(mode="json"),
            "seed": seed,
            "salt": salt,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _parabola_trace(apogee_m: float, flight_time_s: float, n: int = 60) -> list[TracePoint]:
    pts: list[TracePoint] = []
    for i in range(n):
        t = flight_time_s * i / (n - 1)
        frac = t / flight_time_s
        alt = max(0.0, 4.0 * apogee_m * frac * (1.0 - frac))
        speed = abs(4.0 * apogee_m * (1.0 - 2.0 * frac) / flight_time_s)
        pts.append(TracePoint(t_s=t, altitude_m=alt, downrange_m=0.0, speed_mps=speed))
    return pts


# --------------------------------------------------------------------------- dummy physics
#
# SIMPLIFICATION: crude closed-form placeholders so that the dummy responds monotonically to the
# design (bigger motor -> higher, bigger chute -> slower) while phase 2 physics is not wired in.
# Every number produced here is marked with DUMMY_WARNING. Constants are provisional.

_G0 = 9.80665
_RHO_SL = 1.225
_CHUTE_CD = 1.5
_DUMMY_ISP_S = 300.0  # provisional, all engines alike
_DUMMY_DRAG_FACTOR = 0.5  # fraction of the drag-free apogee actually reached
_DUMMY_WATER_EFFICIENCY = 0.6  # fraction of p*V turned into height
_MU_EARTH = 3.986004418e14
_R_EARTH = 6_371_000.0


def _jitter(rng: random.Random, frac: float = 0.03) -> float:
    return 1.0 + frac * (2.0 * rng.random() - 1.0)


def _motor_class_impulse_ns(motor_id: str) -> float:
    """Mid-point total impulse of the NAR letter class found in the id (e.g. 'dummy-J700' -> J)."""
    m = re.search(r"(?:^|[-_ ])([A-Oa-o])\d", motor_id) or re.search(r"([A-Oa-o])", motor_id)
    letter = (m.group(1) if m else "G").upper()
    k = ord(letter) - ord("A") + 1
    return 0.9375 * 2.0**k  # A: 1.875 Ns, G: 120 Ns, J: 960 Ns


def _motor_avg_thrust_n(motor_id: str, impulse_ns: float) -> float:
    m = re.search(r"[A-Oa-o](\d+)", motor_id)
    return float(m.group(1)) if m else 8.0 * impulse_ns**0.5


def _descent_speed_mps(mass_kg: float, chute_diameter_m: float | None) -> float:
    if not chute_diameter_m:
        return math.sqrt(2.0 * mass_kg * _G0 / (_RHO_SL * 0.5 * 0.01))  # tumbling body, ~8 cm^2
    area = math.pi * (chute_diameter_m / 2.0) ** 2
    return math.sqrt(2.0 * mass_kg * _G0 / (_RHO_SL * _CHUTE_CD * area))


def _dummy_suborbital(
    design: BottleDesign | AmateurDesign, env: Env, seed: int | None, req: Requirement | None
) -> SimResult:
    tier = Tier(design.tier)
    rng = _rng_for(design, env, seed, "sim")
    metrics: dict[str, float] = {}
    if isinstance(design, AmateurDesign):
        impulse = _motor_class_impulse_ns(design.motor_id)
        motor_mass = impulse / 1000.0  # ~1 kg per 1000 Ns, provisional
        liftoff_mass = design.dry_mass_kg + design.payload_mass_kg + motor_mass
        v_burnout = impulse / liftoff_mass  # impulsive burn, no drag
        apogee = _DUMMY_DRAG_FACTOR * v_burnout**2 / (2.0 * _G0) * _jitter(rng)
        thrust = _motor_avg_thrust_n(design.motor_id, impulse)
        accel = max(thrust / liftoff_mass - _G0, 0.1)
        descent_mass = design.dry_mass_kg + design.payload_mass_kg + 0.5 * motor_mass
        descent = _descent_speed_mps(descent_mass, design.parachute_diameter_m)
        span_ratio = design.fins.span_m / design.body_diameter_m
        metrics["rail_exit_speed_mps"] = round(math.sqrt(2.0 * accel * env.rail_length_m), 1)
        metrics["stability_margin_cal"] = round(
            (0.4 + 1.0 * span_ratio + 0.3 * (design.fins.count - 3)) * _jitter(rng), 2
        )
        metrics["liftoff_mass_kg"] = round(liftoff_mass, 3)
    else:
        water_mass = design.bottle_volume_m3 * design.water_fill_frac * 1000.0
        air_volume = design.bottle_volume_m3 * (1.0 - design.water_fill_frac)
        energy = design.initial_gauge_pressure_pa * air_volume * 0.3
        mass = design.dry_mass_kg + design.payload_mass_kg + 0.5 * water_mass
        apogee = _DUMMY_WATER_EFFICIENCY * energy / (mass * _G0) * _jitter(rng)
        descent_mass = design.dry_mass_kg + design.payload_mass_kg
        chute = design.parachute_diameter_m if design.has_parachute else None
        descent = _descent_speed_mps(descent_mass, chute)
        metrics["liftoff_mass_kg"] = round(
            design.dry_mass_kg + design.payload_mass_kg + water_mass, 3
        )
    max_speed = math.sqrt(2.0 * _G0 * apogee / _DUMMY_DRAG_FACTOR)
    flight_time = math.sqrt(2.0 * apogee / _G0) * 2.0 + apogee / descent
    drift = env.wind_speed_mps * (apogee / descent) * (0.7 + 0.3 * rng.random())
    theta = math.radians(env.wind_direction_deg + 180.0)
    metrics.update(
        {
            "apogee_m": round(apogee, 1),
            "max_speed_mps": round(max_speed, 1),
            "descent_speed_mps": round(descent, 2),
            "flight_time_s": round(flight_time, 1),
            "landing_east_m": round(drift * math.sin(theta), 1),
            "landing_north_m": round(drift * math.cos(theta), 1),
        }
    )
    cost = round(estimate_cost_jpy(design), 0)
    reasons = _judge(metrics, cost, req)
    return SimResult(
        tier=tier,
        success=not reasons,
        failure_reasons=reasons,
        metrics=metrics,
        cost_jpy=cost,
        trace=_parabola_trace(apogee, flight_time),
        warnings=[DUMMY_WARNING],
    )


def _dummy_multistage(
    design: MultistageDesign, env: Env, seed: int | None, req: Requirement | None
) -> SimResult:
    tier = Tier(design.tier)
    rng = _rng_for(design, env, seed, "sim")
    target = req.target_altitude_m if req is not None else 400_000.0
    orbit_goal = req is None or req.goal_kind is GoalKind.ORBIT

    # Serial-staging Tsiolkowsky with one provisional Isp for every engine (boosters ignored).
    masses = [
        (
            s.propellant_mass_kg,
            s.propellant_mass_kg * s.structural_fraction / (1.0 - s.structural_fraction),
        )
        for s in design.stages
    ]
    remaining = design.fairing_mass_kg + design.payload_mass_kg + sum(p + st for p, st in masses)
    dv_ideal = 0.0
    for prop, struct in masses:
        dv_ideal += _G0 * _DUMMY_ISP_S * math.log(remaining / (remaining - prop))
        remaining -= prop + struct
    gravity_loss = (1_100.0 + 300.0 * rng.random()) * (1.0 + 0.01 * design.pitch_start_s)
    drag_loss = 80.0 + 120.0 * rng.random()
    v_net = dv_ideal - gravity_loss - drag_loss
    liftoff = liftoff_mass_kg(design)
    if orbit_goal:
        v_orbit = math.sqrt(_MU_EARTH / (_R_EARTH + target))
        surplus = v_net - v_orbit
        perigee = target + surplus * 150.0  # m of perigee per m/s of surplus, provisional
        apogee = perigee + max(surplus, 0.0) * 50.0 * _jitter(rng)
        payload_margin = surplus / 10.0  # kg per m/s, provisional
    else:
        perigee = -_R_EARTH
        apogee = v_net**2 / (2.0 * _G0) * _jitter(rng) if v_net > 0 else 0.0
        payload_margin = 0.1 * design.payload_mass_kg
    metrics: dict[str, float] = {
        "perigee_m": round(perigee, 0),
        "apogee_m": round(apogee, 0),
        "max_q_pa": round(
            (25_000.0 + 20_000.0 * rng.random()) * (1.0 + 2.0 / max(design.pitch_start_s, 1.0)), 0
        ),
        "payload_margin_kg": round(payload_margin, 1),
        "delta_v_ideal_mps": round(dv_ideal, 0),
        "gravity_loss_mps": round(gravity_loss, 0),
        "drag_loss_mps": round(drag_loss, 0),
        "burnout_speed_mps": round(v_net, 0),
        "liftoff_mass_kg": round(liftoff, 0),
        "stage_count_count": float(len(design.stages)),
    }
    cost = round(estimate_cost_jpy(design), 0)
    reasons = _judge(metrics, cost, req)
    flight_time = 500.0 + 100.0 * rng.random()
    return SimResult(
        tier=tier,
        success=not reasons,
        failure_reasons=reasons,
        metrics=metrics,
        cost_jpy=cost,
        trace=_parabola_trace(max(apogee, 1.0), flight_time),
        warnings=[DUMMY_WARNING],
    )


def _judge(metrics: dict[str, float], cost_jpy: float, req: Requirement | None) -> list[str]:
    """Pass/fail against the requirement; thresholds in PASS_CRITERIA."""
    reasons: list[str] = []
    tol = PASS_CRITERIA["altitude_tolerance_frac"]
    if req is not None:
        if req.goal_kind is GoalKind.ORBIT:
            if metrics.get("perigee_m", -1.0) < req.target_altitude_m:
                reasons.append(
                    f"perigee {metrics.get('perigee_m'):.0f} m below target "
                    f"{req.target_altitude_m:.0f} m"
                )
        else:
            apogee = metrics.get("apogee_m", 0.0)
            if abs(apogee - req.target_altitude_m) > tol * req.target_altitude_m:
                reasons.append(
                    f"apogee {apogee:.1f} m outside +-{tol:.0%} of target "
                    f"{req.target_altitude_m:.1f} m"
                )
        if req.budget_jpy is not None and cost_jpy > req.budget_jpy:
            reasons.append(f"cost {cost_jpy:,.0f} JPY exceeds budget {req.budget_jpy:,.0f} JPY")
    margin = metrics.get("stability_margin_cal")
    if margin is not None and margin < PASS_CRITERIA["min_stability_margin_cal"]:
        reasons.append(
            f"static margin {margin:.2f} cal below {PASS_CRITERIA['min_stability_margin_cal']} cal"
        )
    descent = metrics.get("descent_speed_mps")
    if descent is not None and descent > PASS_CRITERIA["max_descent_speed_mps"]:
        reasons.append(
            f"descent speed {descent:.2f} m/s above {PASS_CRITERIA['max_descent_speed_mps']} m/s"
        )
    payload_margin = metrics.get("payload_margin_kg")
    if payload_margin is not None and payload_margin < 0:
        reasons.append(f"negative payload margin {payload_margin:.1f} kg")
    return reasons


def _simulate_dispatch(
    design: Design, env: Env, seed: int | None, req: Requirement | None = None
) -> SimResult:
    """Single dispatch point. Phase 2: route commercial/heavy to physics.multistage.simulate,
    amateur to physics.solid, bottle to physics.water."""
    if isinstance(design, MultistageDesign):
        return _dummy_multistage(design, env, seed, req)
    return _dummy_suborbital(design, env, seed, req)


def _quantiles_around(value: float, rng: random.Random) -> Quantiles:
    spread = abs(value) * (0.04 + 0.04 * rng.random()) + 1e-9
    return Quantiles(p05=value - spread, p50=value, p95=value + spread)


def _dispersion_dispatch(
    design: Design, env: Env, n: int, seed: int, req: Requirement | None = None
) -> DispersionResult:
    """Single dispatch point for Monte-Carlo runs (phase 3: rocketwright.dispersion)."""
    sim = _simulate_dispatch(design, env, seed, req)
    rng = _rng_for(design, env, seed, f"dispersion:{n}")
    success_rate = round(0.60 + 0.38 * rng.random(), 3)
    quantiles = {k: _quantiles_around(v, rng) for k, v in sim.metrics.items()}
    n_fail = int(round(n * (1.0 - success_rate)))
    failure_counts = {"apogee outside tolerance": n_fail} if n_fail else {}
    landing: LandingScatter | None = None
    orbit: OrbitInsertionStats | None = None
    if isinstance(design, MultistageDesign):
        samples = [
            OrbitSample(
                perigee_m=sim.metrics["perigee_m"] + rng.gauss(0, 5_000),
                apogee_m=sim.metrics["apogee_m"] + rng.gauss(0, 8_000),
                payload_margin_kg=sim.metrics["payload_margin_kg"] + rng.gauss(0, 5),
            )
            for _ in range(min(n, 200))
        ]
        orbit = OrbitInsertionStats(
            perigee_error_m=Quantiles(p05=-8_000.0, p50=0.0, p95=8_000.0),
            apogee_error_m=Quantiles(p05=-13_000.0, p50=0.0, p95=13_000.0),
            payload_margin_kg=_quantiles_around(sim.metrics["payload_margin_kg"], rng),
            samples=samples,
        )
    else:
        ce, cn = sim.metrics["landing_east_m"], sim.metrics["landing_north_m"]
        sigma = max(5.0, 0.15 * sim.metrics["apogee_m"])
        points = [
            LandingPoint(east_m=ce + rng.gauss(0, sigma), north_m=cn + rng.gauss(0, 0.6 * sigma))
            for _ in range(n)
        ]
        landing = LandingScatter(
            points=points,
            ellipse_95=Ellipse95(
                center_east_m=ce,
                center_north_m=cn,
                semi_major_m=2.45 * sigma,
                semi_minor_m=2.45 * 0.6 * sigma,
                angle_deg=0.0,
            ),
        )
    return DispersionResult(
        tier=sim.tier,
        n=n,
        seed=seed,
        success_rate=success_rate,
        quantiles=quantiles,
        failure_counts=failure_counts,
        landing=landing,
        orbit_insertion=orbit,
        warnings=[DUMMY_WARNING],
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
    return out


def _tool_simulate(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    env = Env.model_validate(inp.get("env") or {})
    seed = inp.get("seed")
    req = _parse_optional_requirement(inp.get("requirement"))
    return _simulate_dispatch(design, env, seed, req).model_dump(mode="json")


def _tool_dispersion(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    env = Env.model_validate(inp.get("env") or {})
    n = int(inp["n"])
    seed = int(inp["seed"])
    if n < 1:
        raise ValueError("n must be >= 1")
    req = _parse_optional_requirement(inp.get("requirement"))
    return _dispersion_dispatch(design, env, n, seed, req).model_dump(mode="json")


def _tool_estimate_cost(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    return {
        "tier": design.tier,
        "cost_jpy": round(estimate_cost_jpy(design), 0),
        "provisional": True,
        "constants": {k: v["value"] for k, v in COST_CONSTANTS.items()},
    }


def _tool_render_drawing(inp: dict[str, Any]) -> dict[str, Any]:
    design = _parse_design(inp["design"])
    return {"status": "not_implemented", "tier": design.tier, "svg": None}


def _tool_export_report(inp: dict[str, Any]) -> dict[str, Any]:
    designs = [_parse_design(d) for d in inp.get("designs", [])]
    return {
        "status": "not_implemented",
        "format": inp.get("format", "markdown"),
        "design_count": len(designs),
    }


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
    except (KeyError, ValueError, TypeError) as exc:
        return {
            "error": f"{type(exc).__name__}: {str(exc)[:_MAX_ERROR_CHARS]}",
            "source_id": tool_use_id,
        }
    result["source_id"] = tool_use_id
    return result
