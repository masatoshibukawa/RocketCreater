"""Design report (Markdown / JSON) and bill-of-materials CSV (CLAUDE.md section 5).

Every number in a report comes from a tool result (SimResult / DispersionResult) or from the
design itself; the report only converts units for display (`display_quantity`). Each metric row
carries the `source_id` of the tool call it came from (CLAUDE.md section 2).

Commercial/heavy reports are concept-level (CLAUDE.md section 4). Regulations are listed as a
checklist of items to confirm, never as a judgement.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

from rocketwright.schema import (
    AmateurDesign,
    BottleDesign,
    Design,
    DispersionResult,
    MultistageDesign,
    Requirement,
    SimResult,
)

__all__ = [
    "BOM_COLUMNS",
    "CHECKLIST",
    "CONCEPT_NOTE",
    "TIER_LABEL_JA",
    "display_quantity",
    "export_bom_csv",
    "export_report_json",
    "export_report_markdown",
]

CATALOG_PARTS_PATH = Path(__file__).resolve().parent / "catalog" / "parts.yaml"

TIER_LABEL_JA: dict[str, str] = {
    "bottle": "ペットボトル",
    "amateur": "アマチュア",
    "commercial": "企業級",
    "heavy": "重工級",
}

CONCEPT_NOTE = (
    "Concept-level design only (CLAUDE.md section 4): mass budget, delta-v split, approximate "
    "ascent and order-of-magnitude cost; not for manufacturing."
)

SIMPLIFICATION_NOTE = (
    "Physics and cost models are deliberately simplified; every `SIMPLIFICATION` is listed in the "
    "repository README together with the provisional values awaiting human confirmation."
)

# Checklist of items to confirm (CLAUDE.md section 4: regulations are a checklist, not a
# judgement). Generic wording on purpose; the human owner should review it.
_CHECKLIST_COMMON: tuple[str, ...] = (
    "Launch site: permission of the land owner / site operator and a safety area sized from the "
    "landing dispersion in this report",
    "Weather limits (wind, visibility) and a go/no-go rule agreed before launch day",
    "Range safety: spectator distance, recovery crew, first-aid, fire precautions",
    "Insurance or club coverage applicable to the activity",
)
CHECKLIST: dict[str, tuple[str, ...]] = {
    "bottle": _CHECKLIST_COMMON
    + (
        "Pressure limit of the bottle and the launcher release mechanism (never exceed the "
        "rated pressure; use water only, no gas other than air)",
        "Eye protection for the launch crew; nobody downrange during pressurisation",
    ),
    "amateur": _CHECKLIST_COMMON
    + (
        "Motor certification and purchase/handling rules that apply in the launch country "
        "(e.g. NAR/TRA certification in the US; the Japanese model-rocket association rules "
        "and explosives regulations in Japan)",
        "Airspace: notification to the aviation authority / NOTAM where the expected apogee "
        "requires it; confirm the altitude ceiling for the site",
        "Recovery system test (ejection charge, parachute packing) before flight",
    ),
    "commercial": _CHECKLIST_COMMON
    + (
        "National launch licence / authorisation (e.g. Japan Space Activities Act, US FAA Part "
        "450) and the applicable liability regime",
        "Range agreement, flight termination requirements and downrange hazard areas",
        "Spectrum licence for telemetry, orbital debris mitigation plan, payload registration",
        "Export control / technology transfer review for engines and avionics",
    ),
    "heavy": _CHECKLIST_COMMON
    + (
        "National launch licence / authorisation (e.g. Japan Space Activities Act, US FAA Part "
        "450) and the applicable liability regime and insurance thresholds",
        "Range agreement, flight termination requirements, booster impact zones and NOTAM / "
        "maritime notices for drop zones",
        "Spectrum licence for telemetry, orbital debris mitigation plan, payload registration",
        "Export control / technology transfer review for engines and avionics",
    ),
}

BOM_COLUMNS: tuple[str, ...] = (
    "item_id",
    "name",
    "qty",
    "mass_kg",
    "price_jpy",
    "source_or_provisional",
)

# SIMPLIFICATION: how the dry mass of a bottle/amateur airframe is split across BOM rows when the
# catalog does not carry the part (fractions of dry_mass_kg; provisional).
_BOTTLE_MASS_SPLIT: dict[str, float] = {
    "bottle": 0.45,
    "nozzle": 0.10,
    "fins": 0.25,
    "parachute": 0.20,
}
_AMATEUR_MASS_SPLIT: dict[str, float] = {
    "nose_cone": 0.15,
    "body_tube": 0.45,
    "fins": 0.25,
    "parachute": 0.10,
    "recovery_hardware": 0.05,
}

# Simple keyword match between a BOM row and catalog items (id / name substring).
_CATALOG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bottle": ("bottle",),
    "nozzle": ("nozzle",),
    "fins": ("fin",),
    "parachute": ("parachute", "chute"),
    "nose_cone": ("nose",),
    "body_tube": ("tube", "body"),
    "recovery_hardware": ("shock", "recovery"),
}


# --------------------------------------------------------------------------- display units


def _num(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"


def display_quantity(key: str, value: float | int | bool | str | None) -> str:
    """Convert an SI value to a display string using the unit suffix of its key.

    km / m / mm / kg / g / kPa / 万円 are chosen by magnitude; keys without a unit suffix are
    returned as plain text.
    """
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    v = float(value)
    a = abs(v)
    if key.endswith("_m"):
        if a >= 1000.0:
            return f"{_num(v / 1000.0, 2)} km"
        if a < 1.0 and key != "apogee_m":
            return f"{_num(v * 1000.0, 0)} mm"
        return f"{_num(v, 2)} m"
    if key.endswith("_mm"):
        return f"{_num(v, 0)} mm"
    if key.endswith("_kg"):
        if a < 1.0:
            return f"{_num(v * 1000.0, 0)} g"
        return f"{_num(v, 1)} kg"
    if key.endswith("_g"):
        return f"{_num(v, 0)} g"
    if key.endswith("_pa"):
        return f"{_num(v / 1000.0, 0)} kPa"
    if key.endswith("_jpy"):
        if a >= 1e8:
            return f"{_num(v / 1e8, 2)} 億円"
        if a >= 1e4:
            return f"{_num(v / 1e4, 1)} 万円"
        return f"{_num(v, 0)} 円"
    if key.endswith("_frac") or key.endswith("_fraction"):
        return f"{_num(v * 100.0, 0)} %"
    if key.endswith("_mps"):
        return f"{_num(v, 1)} m/s"
    if key.endswith("_mps2"):
        return f"{_num(v, 2)} m/s2"
    if key.endswith("_s"):
        return f"{_num(v, 1)} s"
    if key.endswith("_cal"):
        return f"{_num(v, 2)} cal"
    if key.endswith("_m3"):
        return f"{_num(v * 1000.0, 2)} L" if a < 1.0 else f"{_num(v, 2)} m3"
    if key.endswith("_m2"):
        return f"{_num(v, 3)} m2"
    if key.endswith("_deg"):
        return f"{_num(v, 1)} deg"
    if key.endswith("_rad"):
        return f"{_num(v, 3)} rad"
    if key.endswith("_n"):
        return f"{_num(v, 0)} N"
    if key.endswith("_ns"):
        return f"{_num(v, 0)} N·s"
    if key.endswith("_k"):
        return f"{_num(v, 1)} K"
    if key.endswith("_ratio"):
        return f"{_num(v, 2)}"
    if key.endswith("_count") or isinstance(value, int):
        return f"{int(round(v))}"
    return f"{_num(v, 3)}"


# --------------------------------------------------------------------------- helpers


def _tier_title(design: Design) -> str:
    return f"{TIER_LABEL_JA.get(design.tier, design.tier)} ({design.tier})"


def _is_concept(design: Design) -> bool:
    return design.tier in ("commercial", "heavy")


def _flatten_design(design: Design) -> list[tuple[str, Any]]:
    """Design variables as (dotted key, value) rows in schema order."""
    rows: list[tuple[str, Any]] = []

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{prefix}{k}" if not prefix else f"{prefix}.{k}", v)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(f"{prefix}[{i + 1}]", v)
        else:
            rows.append((prefix, node))

    walk("", design.model_dump(mode="json"))
    return [(k, v) for k, v in rows if k != "tier"]


def _leaf_key(dotted: str) -> str:
    return dotted.rsplit(".", 1)[-1].split("[")[0]


def _requirement_rows(req: Requirement) -> list[tuple[str, str]]:
    rows = [
        ("Goal", req.goal_kind.value),
        ("Target altitude / perigee", display_quantity("target_altitude_m", req.target_altitude_m)),
    ]
    if req.target_apogee_m is not None:
        rows.append(("Target apogee", display_quantity("target_apogee_m", req.target_apogee_m)))
    if req.bottle_volume_m3 is not None:
        rows.append(
            ("Required bottle volume", display_quantity("bottle_volume_m3", req.bottle_volume_m3))
        )
    rows.append(("Payload mass", display_quantity("payload_mass_kg", req.payload_mass_kg)))
    rows.append(
        ("Budget", display_quantity("budget_jpy", req.budget_jpy) if req.budget_jpy else "-")
    )
    rows.append(("Recovery required", "yes" if req.recovery_required else "no"))
    if req.tier_override is not None:
        rows.append(("Tier override", req.tier_override.value))
    if req.text:
        rows.append(("Request", req.text))
    return rows


def _metric_rows(result: SimResult, sources: dict[str, str] | None) -> list[dict[str, Any]]:
    src = sources or {}
    rows = [
        {
            "key": key,
            "value": value,
            "display": display_quantity(key, value),
            "source_id": src.get(key, result.source_id),
        }
        for key, value in result.metrics.items()
    ]
    rows.append(
        {
            "key": "cost_jpy",
            "value": result.cost_jpy,
            "display": display_quantity("cost_jpy", result.cost_jpy),
            "source_id": src.get("cost_jpy", result.source_id),
        }
    )
    return rows


def _dispersion_summary(disp: DispersionResult) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source_id": disp.source_id,
        "n": disp.n,
        "seed": disp.seed,
        "success_rate": disp.success_rate,
        "success_rate_display": f"{disp.success_rate * 100:.1f} %",
        "quantiles": {
            k: {
                "p05": q.p05,
                "p50": q.p50,
                "p95": q.p95,
                "display": (
                    f"{display_quantity(k, q.p05)} / {display_quantity(k, q.p50)} / "
                    f"{display_quantity(k, q.p95)}"
                ),
            }
            for k, q in disp.quantiles.items()
        },
        "failure_counts": dict(disp.failure_counts),
        "warnings": list(disp.warnings),
    }
    if disp.landing is not None:
        e = disp.landing.ellipse_95
        out["landing_ellipse_95"] = {
            "center_east_m": e.center_east_m,
            "center_north_m": e.center_north_m,
            "semi_major_m": e.semi_major_m,
            "semi_minor_m": e.semi_minor_m,
            "angle_deg": e.angle_deg,
            "point_count": len(disp.landing.points),
        }
    if disp.orbit_insertion is not None:
        oi = disp.orbit_insertion
        out["orbit_insertion"] = {
            name: {"p05": q.p05, "p50": q.p50, "p95": q.p95}
            for name, q in (
                ("perigee_error_m", oi.perigee_error_m),
                ("apogee_error_m", oi.apogee_error_m),
                ("payload_margin_kg", oi.payload_margin_kg),
            )
        }
    return out


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- json / markdown


def export_report_json(
    design: Design,
    result: SimResult,
    *,
    requirement: Requirement | None = None,
    dispersion: DispersionResult | None = None,
    sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    """JSON-serialisable report (round-trips through json.dumps/loads)."""
    return {
        "tier": design.tier,
        "tier_label_ja": TIER_LABEL_JA.get(design.tier, design.tier),
        "concept_level": _is_concept(design),
        "requirement": None if requirement is None else requirement.model_dump(mode="json"),
        "design": design.model_dump(mode="json"),
        "design_display": [
            {"key": k, "value": v, "display": display_quantity(_leaf_key(k), v)}
            for k, v in _flatten_design(design)
        ],
        "metrics": _metric_rows(result, sources),
        "passed": result.success,
        "failure_reasons": list(result.failure_reasons),
        "warnings": list(result.warnings),
        "sim_source_id": result.source_id,
        "dispersion": None if dispersion is None else _dispersion_summary(dispersion),
        "checklist": list(CHECKLIST.get(design.tier, _CHECKLIST_COMMON)),
        "notes": [SIMPLIFICATION_NOTE] + ([CONCEPT_NOTE] if _is_concept(design) else []),
    }


def export_report_markdown(
    design: Design,
    result: SimResult,
    *,
    requirement: Requirement | None = None,
    dispersion: DispersionResult | None = None,
    sources: dict[str, str] | None = None,
) -> str:
    data = export_report_json(
        design, result, requirement=requirement, dispersion=dispersion, sources=sources
    )
    out: list[str] = [f"# RocketWright design report — {_tier_title(design)}", ""]
    if _is_concept(design):
        out += [f"> **{CONCEPT_NOTE}**", ""]

    out += ["## Requirement", ""]
    if requirement is None:
        out += ["(no requirement given)", ""]
    else:
        out += [
            _md_table(["Item", "Value"], [[k, v] for k, v in _requirement_rows(requirement)]),
            "",
        ]

    out += ["## Design variables", ""]
    out += [
        _md_table(
            ["Variable", "Value"],
            [[row["key"], row["display"]] for row in data["design_display"]],
        ),
        "",
    ]

    out += ["## Key metrics", ""]
    out += [
        _md_table(
            ["Metric", "Value", "SI value", "Source (tool call id)"],
            [
                [m["key"], m["display"], repr(m["value"]), m["source_id"] or "-"]
                for m in data["metrics"]
            ],
        ),
        "",
    ]

    verdict = "PASS" if result.success else "FAIL"
    out += ["## Verdict", "", f"**{verdict}** (simulate_design `{result.source_id or '-'}`)", ""]
    if result.failure_reasons:
        out += ["Failure reasons:", ""] + [f"- {r}" for r in result.failure_reasons] + [""]
    if result.warnings:
        out += ["Warnings:", ""] + [f"- {w}" for w in result.warnings] + [""]

    if dispersion is not None:
        d = data["dispersion"]
        out += ["## Dispersion (Monte Carlo)", ""]
        out += [
            f"- n = {d['n']}, seed = {d['seed']}, success rate **{d['success_rate_display']}** "
            f"(run_dispersion `{d['source_id'] or '-'}`)",
        ]
        if d["failure_counts"]:
            out += [
                "- Failure counts: "
                + ", ".join(f"{k}: {v}" for k, v in d["failure_counts"].items())
            ]
        out += [""]
        if d["quantiles"]:
            out += [
                _md_table(
                    ["Metric", "p05", "p50", "p95"],
                    [
                        [
                            k,
                            display_quantity(k, q["p05"]),
                            display_quantity(k, q["p50"]),
                            display_quantity(k, q["p95"]),
                        ]
                        for k, q in d["quantiles"].items()
                    ],
                ),
                "",
            ]
        if "landing_ellipse_95" in d:
            e = d["landing_ellipse_95"]
            out += [
                "- 95 % landing ellipse: centre "
                f"({display_quantity('east_m', e['center_east_m'])} E, "
                f"{display_quantity('north_m', e['center_north_m'])} N), semi-axes "
                f"{display_quantity('semi_major_m', e['semi_major_m'])} x "
                f"{display_quantity('semi_minor_m', e['semi_minor_m'])}, "
                f"{e['point_count']} points",
                "",
            ]
        if "orbit_insertion" in d:
            out += [
                _md_table(
                    ["Orbit insertion", "p05", "p50", "p95"],
                    [
                        [
                            k,
                            display_quantity(k, q["p05"]),
                            display_quantity(k, q["p50"]),
                            display_quantity(k, q["p95"]),
                        ]
                        for k, q in d["orbit_insertion"].items()
                    ],
                ),
                "",
            ]
        for w in d["warnings"]:
            out += [f"- Warning: {w}"]
        if d["warnings"]:
            out += [""]

    out += ["## Checklist of items to confirm (not legal advice)", ""]
    out += [
        "This is a checklist of topics to confirm with the responsible authority or club; "
        "RocketWright does not decide on permits or legality.",
        "",
    ]
    out += [f"- [ ] {item}" for item in data["checklist"]] + [""]

    out += ["## Notes", ""] + [f"- {n}" for n in data["notes"]] + [""]
    return "\n".join(out)


# --------------------------------------------------------------------------- bom


def _load_catalog_parts() -> list[dict[str, Any]]:
    """parts.yaml items at call time (the physics agent fills the file; may be empty)."""
    try:
        with CATALOG_PARTS_PATH.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return [i for i in (items or []) if isinstance(i, dict)]


def _find_part(items: list[dict[str, Any]], tier: str, row_id: str) -> dict[str, Any] | None:
    keywords = _CATALOG_KEYWORDS.get(row_id, (row_id,))
    for item in items:
        tiers = item.get("tiers") or ([item["tier"]] if "tier" in item else [])
        if tiers and tier not in tiers:
            continue
        hay = f"{item.get('id', '')} {item.get('name', '')}".lower()
        if any(k in hay for k in keywords):
            return item
    return None


def _source_text(item: dict[str, Any] | None) -> str:
    if item is None:
        return "provisional"
    if item.get("source"):
        return str(item["source"])
    return "provisional" if item.get("provisional", True) else "catalog"


def _fmt_mass(mass: float | None) -> str:
    return "" if mass is None else f"{mass:.4f}"


def _fmt_price(price: float | None) -> str:
    return "" if price is None else f"{price:.0f}"


def _row(
    item_id: str,
    name: str,
    qty: int,
    mass_kg: float | None,
    price_jpy: float | None,
    source: str,
) -> list[str]:
    return [item_id, name, str(qty), _fmt_mass(mass_kg), _fmt_price(price_jpy), source]


def _catalog_row(
    items: list[dict[str, Any]], tier: str, row_id: str, name: str, qty: int, est_mass: float
) -> list[str]:
    """A BOM row from the catalog when a matching part exists, else a provisional row."""
    item = _find_part(items, tier, row_id)
    if item is None:
        return _row(row_id, name, qty, est_mass, None, "provisional")
    mass = item.get("mass_kg")
    price = item.get("price_jpy")
    return _row(
        str(item.get("id", row_id)),
        str(item.get("name", name)),
        qty,
        float(mass) if isinstance(mass, (int, float)) else est_mass,
        float(price) if isinstance(price, (int, float)) else None,
        _source_text(item),
    )


def _motor_row(design: AmateurDesign) -> list[str]:
    """Motor mass from physics.solid.load_motor when available (lazy, optional)."""
    mass: float | None = None
    source = "provisional"
    try:
        from rocketwright.physics import solid

        loader = getattr(solid, "load_motor", None)
        if loader is not None:
            motor: Any = loader(design.motor_id)
            for attr in ("total_mass_kg", "mass_kg"):
                v = getattr(motor, attr, None) if not isinstance(motor, dict) else motor.get(attr)
                if isinstance(v, (int, float)) and v > 0:
                    mass = float(v)
                    break
            src = (
                getattr(motor, "source", None)
                if not isinstance(motor, dict)
                else motor.get("source")
            )
            if src:
                source = str(src)
            elif mass is not None:
                source = "catalog/motors"
    except Exception:
        mass = None
    return _row("motor", f"Solid motor {design.motor_id}", 1, mass, None, source)


def _bom_bottle(design: BottleDesign) -> list[list[str]]:
    items = _load_catalog_parts()
    split = dict(_BOTTLE_MASS_SPLIT)
    if not design.has_fins:
        split.pop("fins")
    if not design.has_parachute:
        split.pop("parachute")
    total = sum(split.values())
    masses = {k: design.dry_mass_kg * v / total for k, v in split.items()}
    litres = design.bottle_volume_m3 * 1000.0
    rows = [
        _catalog_row(items, "bottle", "bottle", f"PET bottle {litres:.2f} L", 1, masses["bottle"]),
        _catalog_row(
            items,
            "bottle",
            "nozzle",
            f"Nozzle {design.nozzle_diameter_m * 1000:.1f} mm",
            1,
            masses["nozzle"],
        ),
    ]
    if design.has_fins:
        rows.append(_catalog_row(items, "bottle", "fins", "Fin set", 1, masses["fins"]))
    if design.has_parachute:
        rows.append(
            _catalog_row(
                items,
                "bottle",
                "parachute",
                f"Parachute {design.parachute_diameter_m or 0:.2f} m",
                1,
                masses["parachute"],
            )
        )
    rows.append(_row("payload", "Payload (placeholder)", 1, design.payload_mass_kg, None, "design"))
    return rows


def _bom_amateur(design: AmateurDesign) -> list[list[str]]:
    items = _load_catalog_parts()
    masses = {k: design.dry_mass_kg * v for k, v in _AMATEUR_MASS_SPLIT.items()}
    d_mm = design.body_diameter_m * 1000.0
    rows = [
        _catalog_row(
            items,
            "amateur",
            "nose_cone",
            f"Nose cone {design.nose_shape} {design.nose_length_m * 1000:.0f} mm",
            1,
            masses["nose_cone"],
        ),
        _catalog_row(
            items,
            "amateur",
            "body_tube",
            f"Body tube {d_mm:.0f} mm x {design.body_length_m * 1000:.0f} mm",
            1,
            masses["body_tube"],
        ),
    ]
    fins = _catalog_row(
        items,
        "amateur",
        "fins",
        f"Fin {design.fins.root_chord_m * 1000:.0f}/{design.fins.tip_chord_m * 1000:.0f}/"
        f"{design.fins.span_m * 1000:.0f} mm",
        design.fins.count,
        masses["fins"] / design.fins.count,
    )
    rows.append(fins)
    rows.append(_motor_row(design))
    rows.append(
        _catalog_row(
            items,
            "amateur",
            "parachute",
            f"Parachute {design.parachute_diameter_m:.2f} m",
            1,
            masses["parachute"],
        )
    )
    rows.append(
        _catalog_row(
            items,
            "amateur",
            "recovery_hardware",
            "Recovery hardware (shock cord, swivel)",
            1,
            masses["recovery_hardware"],
        )
    )
    rows.append(_row("payload", "Payload (placeholder)", 1, design.payload_mass_kg, None, "design"))
    return rows


def _engine_mass_kg(engine_id: str, kind: str) -> float | None:
    try:
        from rocketwright.physics import multistage

        spec = multistage.get_engine(engine_id, kind=kind)
        v = getattr(spec, "mass_kg", None)
        return float(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None


def _cost_estimate_jpy(design: Design) -> float | None:
    try:
        from rocketwright.cost import estimate_cost_jpy

        return float(estimate_cost_jpy(design))
    except Exception:
        return None


def _bom_multistage(design: MultistageDesign) -> list[list[str]]:
    note = "concept-level estimate"
    rows: list[list[str]] = []
    for i, stage in enumerate(design.stages, start=1):
        structure = (
            stage.propellant_mass_kg * stage.structural_fraction / (1.0 - stage.structural_fraction)
        )
        rows.append(
            _row(
                f"stage{i}_structure",
                f"Stage {i} structure (tanks, interstage)",
                1,
                structure,
                None,
                note,
            )
        )
        rows.append(
            _row(
                f"stage{i}_propellant",
                f"Stage {i} propellant",
                1,
                stage.propellant_mass_kg,
                None,
                note,
            )
        )
        rows.append(
            _row(
                f"stage{i}_engines",
                f"Stage {i} engine {stage.engine_id}",
                stage.engine_count,
                _engine_mass_kg(stage.engine_id, "engine"),
                None,
                f"{note}; catalog/engines.yaml",
            )
        )
    for b in design.boosters:
        rows.append(
            _row(
                "boosters",
                f"Strap-on booster {b.booster_id}",
                b.count,
                _engine_mass_kg(b.booster_id, "booster"),
                None,
                f"{note}; catalog/engines.yaml",
            )
        )
    rows.append(_row("fairing", "Payload fairing", 1, design.fairing_mass_kg, None, note))
    rows.append(_row("payload", "Payload", 1, design.payload_mass_kg, None, "design"))
    cost = _cost_estimate_jpy(design)
    if cost is not None:
        rows.append(
            _row(
                "cost_estimate",
                "Order-of-magnitude vehicle cost (mass-based, cost.py)",
                1,
                None,
                cost,
                "provisional; concept-level",
            )
        )
    return rows


def export_bom_csv(design: Design) -> str:
    """Bill of materials as CSV text with the BOM_COLUMNS header."""
    if isinstance(design, BottleDesign):
        rows = _bom_bottle(design)
    elif isinstance(design, AmateurDesign):
        rows = _bom_amateur(design)
    elif isinstance(design, MultistageDesign):
        rows = _bom_multistage(design)
    else:
        raise TypeError(f"unsupported design type {type(design).__name__}")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(BOM_COLUMNS)
    writer.writerows(rows)
    return buf.getvalue()
